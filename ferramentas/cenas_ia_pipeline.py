#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Cenas IA — gera cenas novas (ComfyUI/SDXL) onde o material do anime nao responde a letra.

Ordem de producao:
    cenas-auto -> cenas-ia -> manga-auto -> graficos-auto -> planejar

Filosofia:
- a cena real do anime sempre vence; IA so entra onde o Scene Matcher ficou fraco
  (score baixo ou alvo semantico obrigatorio reprovado);
- prompt 100% automatico: letra -> conceitos (semantic_scene_matcher) + palavras
  concretas (assets/design/cenas_ia_map.json) + identidade (projeto.json -> imagem_ia);
- recurso raro: limite por faixa e espacamento minimo;
- cada imagem vira um take 1080p com movimento de camera (push/pull/pan) em NVENC;
- idempotente (state.json), cache de imagem e de render, falha fechada se a
  timeline aplicada for editada fora do pipeline;
- ComfyUI offline/indisponivel NAO derruba a esteira: o estagio e pulado com aviso.

Config por projeto (opcional) em projeto.json -> "cenas_ia": {...} (chaves de DEFAULTS).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from _vx import config as vx_config, projeto as vx_projeto
import gerador_imagem_local as gil
import render_dispatch as rd
import semantic_scene_matcher as sm
from manga_auto_pipeline import _replace_interval
from style_preset_engine import normalizar
from timeline_clipe import validar as validar_timeline

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projetos"
MAPA_PADRAO = ROOT / "assets" / "design" / "cenas_ia_map.json"
SCHEMA_VERSION = 1
RENDER_VERSION = 1
TIPO_SEGMENTO = "vx_cena_ia"
FPS = 30

DEFAULTS = {
    "enabled": True,
    "max_scenes": 4,
    "min_gap_seconds": 20.0,
    "max_match_score": 0.36,
    "duration_min": 1.2,
    "duration_max": 3.2,
    "intro_guard_seconds": 12.0,
    "outro_guard_seconds": 6.0,
    "auto_desligar_comfy": True,
    "strict": False,
    "variacoes": 3,
}
IGNORAR_CONCEITOS = {"generic_lyric", "breathing_space"}
NORMAL_TYPES = {"", "lyric", "narrativo"}
MOVIMENTOS = ("push_in", "pan_lr", "pull_out", "pan_rl", "rise")


# ---------------------------------------------------------------------------
# utilitarios
# ---------------------------------------------------------------------------

def _read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except PermissionError:
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".vxcia.bak"))
        path.write_text(payload, encoding="utf-8")
        tmp.unlink(missing_ok=True)


def _hash(data) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _config(manifest: dict) -> dict:
    # codigo < config/estudio.json[cenas_ia] < projeto.json[cenas_ia]
    return vx_config.secao("cenas_ia", DEFAULTS, manifest)


def _audio_path(project: Path, timeline: dict, manifest: dict) -> Path:
    rel = timeline.get("audio")
    if rel:
        p = Path(rel)
        return p if p.is_absolute() else project / p
    return vx_projeto.audio(project, manifest)


def _tem_tipo(timeline: dict, tipos: set) -> bool:
    return any(s.get("type") in tipos for s in timeline.get("segments", []))


# ---------------------------------------------------------------------------
# prompt automatico
# ---------------------------------------------------------------------------

def carregar_mapa(path: Path = MAPA_PADRAO) -> dict:
    return _read_json(path, {}) or {}


def _dedup_tags(*grupos: str) -> str:
    vistos, out = set(), []
    for g in grupos:
        for tag in str(g or "").split(","):
            t = tag.strip()
            if t and t.lower() not in vistos:
                vistos.add(t.lower())
                out.append(t)
    return ", ".join(out)


def prompt_para_letra(texto: str, concepts: list, targets: list, manifest: dict,
                      mapa: dict) -> dict:
    """Retorna {"tipo": "cena"|"fundo", "tags": str, "fontes": {...}} — sem nomes hardcodados."""
    conceitos_mapa = mapa.get("conceitos", {})
    palavras_mapa = {normalizar(k): v for k, v in (mapa.get("palavras") or {}).items()}
    bloco = manifest.get("imagem_ia") or {}
    alvos_tags = bloco.get("tags_alvos") or {}
    personagem = normalizar(manifest.get("personagem", ""))

    usados = [c for c in concepts if c not in IGNORAR_CONCEITOS]
    tags_conceito = [conceitos_mapa[c]["tags"] for c in usados if c in conceitos_mapa]
    tokens = normalizar(texto).split()
    tags_palavra = list(dict.fromkeys(palavras_mapa[t] for t in tokens if t in palavras_mapa))

    tags_alvo = []
    for t in targets or []:
        tid = str(t.get("id", ""))
        if tid in alvos_tags:
            tags_alvo.append(str(alvos_tags[tid]))
        elif tid.startswith("entity:"):
            # outro personagem: SDXL nao desenha dois canonicos com fidelidade -> nao arriscar
            continue
        elif t.get("name") and normalizar(t["name"]) not in personagem:
            tags_alvo.append(str(t["name"]).lower())

    so_cenario = bool(usados) and all(conceitos_mapa.get(c, {}).get("cenario") for c in usados)
    tags = _dedup_tags(*tags_alvo, *tags_conceito, *tags_palavra)
    return {"tipo": "fundo" if so_cenario else "cena", "tags": tags,
            "fontes": {"conceitos": usados, "palavras": tags_palavra, "alvos": tags_alvo}}


# ---------------------------------------------------------------------------
# planejamento
# ---------------------------------------------------------------------------

def _fraqueza(seg: dict, manifest: dict) -> tuple[float, list]:
    """(score_match, alvos obrigatorios reprovados que a IA consegue desenhar).

    Alvos ``entity:*`` (outro personagem) ficam fora: SDXL nao entrega esse
    personagem com fidelidade, entao a falha nao justifica trocar a cena real.
    """
    m = seg.get("scene_match") or {}
    score = float(m.get("score", 1.0))
    req = float((manifest.get("scene_semantics") or {}).get("required_score", 0.16))
    scores = m.get("semantic_target_scores") or {}
    falhas = [t for t in m.get("semantic_targets", []) or []
              if t.get("required") and not str(t.get("id", "")).startswith("entity:")
              and float(scores.get(t.get("id"), 0.0)) < req]
    return score, falhas


def _janela(seg: dict, cfg: dict) -> tuple[float, float]:
    a, b = float(seg["start"]), float(seg["end"])
    dur = min(b - a, float(cfg["duration_max"]))
    centro = (a + b) / 2.0
    ini = max(a, centro - dur / 2.0)
    ini = round(ini * FPS) / FPS
    fim = min(b, round((ini + dur) * FPS) / FPS)
    return round(ini, 6), round(fim, 6)


def planejar(slug: str, timeline_override: dict | None = None) -> dict:
    project = PROJECTS / slug
    manifest = _read_json(project / "projeto.json", {}) or {}
    timeline = copy.deepcopy(timeline_override) if timeline_override is not None \
        else (_read_json(project / "timeline.json", {}) or {})
    if not timeline.get("segments"):
        raise ValueError("timeline ausente ou vazia")
    cfg = _config(manifest)
    base = {"slug": slug, "config": cfg, "base_timeline": timeline, "selected": []}
    if not cfg.get("enabled", True):
        return {**base, "status": "disabled"}
    if not any("scene_match" in s for s in timeline["segments"]):
        return {**base, "status": "skipped_sem_scene_matcher"}

    mapa = carregar_mapa()
    try:
        audio_dur = float(timeline.get("audio_duration") or timeline["segments"][-1]["end"])
    except (TypeError, ValueError, KeyError):
        audio_dur = float(timeline["segments"][-1]["end"])

    candidatos = []
    for idx, seg in enumerate(timeline["segments"]):
        if str(seg.get("type", "")) not in NORMAL_TYPES or "scene_match" not in seg:
            continue
        a, b = float(seg["start"]), float(seg["end"])
        if b - a < float(cfg["duration_min"]):
            continue
        centro = (a + b) / 2.0
        if centro < float(cfg["intro_guard_seconds"]) or centro > audio_dur - float(cfg["outro_guard_seconds"]):
            continue
        m = seg["scene_match"]
        score, falhas = _fraqueza(seg, manifest)
        fraco = score < float(cfg["max_match_score"])
        if not fraco and not falhas:
            continue
        texto = str(m.get("lyric_text") or seg.get("note") or "").strip()
        concepts = [c for c in (m.get("concepts") or []) if c not in IGNORAR_CONCEITOS]
        if not texto or not concepts:
            continue
        prompt = prompt_para_letra(texto, concepts, falhas or m.get("semantic_targets", []),
                                   manifest, mapa)
        if not prompt["tags"]:
            continue
        lacuna = max(0.0, float(cfg["max_match_score"]) - score) / max(0.01, float(cfg["max_match_score"]))
        prioridade = round(0.55 * lacuna + 0.30 * min(1.0, len(falhas) / 2) + 0.15 * min(1.0, len(concepts) / 2), 5)
        ini, fim = _janela(seg, cfg)
        candidatos.append({
            "segment_index": idx, "text": texto, "start": ini, "end": fim,
            "duration": round(fim - ini, 6), "match_score": round(score, 5),
            "failed_targets": [t.get("id") for t in falhas], "concepts": concepts,
            "priority": prioridade, "tipo": prompt["tipo"], "tags": prompt["tags"],
            "prompt_sources": prompt["fontes"], "replaced_clip": seg.get("clip"),
        })

    selecionados, textos = [], set()
    for c in sorted(candidatos, key=lambda x: (-x["priority"], x["start"])):
        chave = normalizar(c["text"])
        if chave in textos:
            continue
        centro = (c["start"] + c["end"]) / 2.0
        if any(abs(centro - (x["start"] + x["end"]) / 2.0) < float(cfg["min_gap_seconds"]) for x in selecionados):
            continue
        selecionados.append(c)
        textos.add(chave)
        if len(selecionados) >= int(cfg["max_scenes"]):
            break
    selecionados.sort(key=lambda x: x["start"])
    for i, c in enumerate(selecionados):
        c["movement"] = MOVIMENTOS[i % len(MOVIMENTOS)]
    return {**base, "status": "planned", "candidate_count": len(candidatos),
            "selected": selecionados}


# ---------------------------------------------------------------------------
# render do take (still -> movimento de camera) em NVENC
# ---------------------------------------------------------------------------

def filtro_movimento(movimento: str, frames: int) -> str:
    n = max(1, frames - 1)
    p = f"(on/{n})"
    ease = f"({p}*{p}*(3-2*{p}))"
    z0, z1, px0, px1, py0, py1 = {
        "push_in": (1.00, 1.12, .5, .5, .45, .45),
        "pull_out": (1.14, 1.02, .5, .5, .45, .45),
        "pan_lr": (1.12, 1.12, .15, .85, .45, .45),
        "pan_rl": (1.12, 1.12, .85, .15, .45, .45),
        "rise": (1.10, 1.10, .5, .5, .80, .25),
    }.get(movimento, (1.00, 1.12, .5, .5, .45, .45))
    z = f"{z0}+({z1 - z0:.4f})*{ease}"
    x = f"(iw-iw/zoom)*({px0}+({px1 - px0:.4f})*{ease})"
    y = f"(ih-ih/zoom)*({py0}+({py1 - py0:.4f})*{ease})"
    return (
        "scale=3840:2160:force_original_aspect_ratio=increase:flags=lanczos,crop=3840:2160,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1920x1080:fps={FPS},"
        "eq=contrast=1.05:saturation=1.06,noise=alls=4:allf=t,vignette=PI/5,format=yuv420p"
    )


def renderizar_take(imagem: Path, saida: Path, duracao: float, movimento: str) -> Path:
    frames = max(2, int(round(duracao * FPS)))
    design = {"version": RENDER_VERSION, "image": imagem.name, "frames": frames, "movement": movimento}
    sidecar = saida.with_suffix(".design.json")
    if saida.is_file() and saida.stat().st_size and _read_json(sidecar) == design:
        return saida
    rd.encode(str(saida), ["-i", str(imagem)], filtro_v=filtro_movimento(movimento, frames),
              mapa=["-map", "0:v:0"], args_audio=["-an"],
              args_extra=["-frames:v", str(frames), "-r", str(FPS)], silencioso=True)
    _write_json(sidecar, design)
    return saida


# ---------------------------------------------------------------------------
# injecao
# ---------------------------------------------------------------------------

def _inject(base: dict, selected: list[dict]) -> dict:
    timeline = copy.deepcopy(base)
    segments = timeline.get("segments", [])
    for item in selected:
        seg = {
            "start": item["start"], "end": item["end"], "duration": item["duration"],
            "clip": item["clip"], "src": 0.0, "categoria": "cena_ia", "type": TIPO_SEGMENTO,
            "note": f"VX Cenas IA: {item['text']} | match={item['match_score']:.3f}",
            "cena_ia": {k: item[k] for k in ("text", "tags", "tipo", "match_score", "failed_targets",
                                              "concepts", "image", "seed", "movement", "replaced_clip")},
        }
        segments = _replace_interval(segments, item["start"], item["end"], seg)
    timeline["segments"] = segments
    timeline["total_segmentos"] = len(segments)
    timeline["cenas_ia"] = {"version": SCHEMA_VERSION, "count": len(selected),
                            "moments": [{"start": x["start"], "end": x["end"], "text": x["text"]}
                                        for x in selected]}
    return timeline


def executar(slug: str, somente_planejar: bool = False) -> dict:
    project = PROJECTS / slug
    qa = project / "qa" / "vx_cenas_ia"
    qa.mkdir(parents=True, exist_ok=True)
    state_path, plan_path = qa / "state.json", qa / "plano.json"
    state = _read_json(state_path, {}) or {}
    current = _read_json(project / "timeline.json", {}) or {}
    manifest = _read_json(project / "projeto.json", {}) or {}
    cfg = _config(manifest)

    if _tem_tipo(current, {"vx_title_card", "vx_end_card", "vx_manga_auto", "vx_graphics_auto"}):
        return {"slug": slug, "status": "preserved_after_downstream_visuals", "applied": False,
                "selected": state.get("plan", {}).get("selected", [])}
    if _tem_tipo(current, {TIPO_SEGMENTO}):
        if state.get("applied_hash") == _hash(current):
            return {"slug": slug, "status": "cached", "applied": False,
                    "selected": state.get("plan", {}).get("selected", [])}
        raise RuntimeError("timeline com VX Cenas IA foi alterada externamente; falha fechada")

    result = planejar(slug)
    public = {k: copy.deepcopy(v) for k, v in result.items() if k != "base_timeline"}
    _write_json(plan_path, public)
    if somente_planejar or result["status"] != "planned":
        return {**public, "applied": False}
    selected = result["selected"]
    if not selected:
        return {**public, "applied": False, "status": "skipped_material_suficiente"}

    out_dir = project / "clips_raw" / "vx_cenas_ia"
    out_dir.mkdir(parents=True, exist_ok=True)
    prontos, falhas = [], []
    # ComfyUI sob demanda: imagens ja escolhidas (artes_ia/escolhas.json) nao sobem o ComfyUI
    sessao = gil.sessao_comfy(desligar=cfg.get("auto_desligar_comfy", True))
    try:
        sessao.__enter__()
        for i, item in enumerate(selected, 1):
            try:
                png = gil.gerar_melhor(project, item["tipo"], cena=item["tags"],
                                       variacoes=max(1, int(cfg["variacoes"])))
            except gil.ComfyIndisponivel as exc:
                if cfg.get("strict"):
                    raise
                aviso = {**public, "applied": False, "status": "skipped_comfy_indisponivel",
                         "erro": str(exc)}
                _write_json(plan_path, aviso)
                print(f"[VX CENAS IA] aviso: {exc}")
                return aviso
            except (RuntimeError, TimeoutError) as exc:
                if cfg.get("strict"):
                    raise
                falhas.append({"text": item["text"], "erro": str(exc)[:300]})
                continue
            safe = re.sub(r"[^a-z0-9]+", "_", normalizar(item["text"])).strip("_")[:36] or "cena"
            take = renderizar_take(png, out_dir / f"{i:02d}_{safe}_cena_ia.mp4",
                                   item["duration"], item["movement"])
            item["image"] = str(png.relative_to(project)).replace("\\", "/")
            item["seed"] = int(png.stem.split("_")[1])
            item["clip"] = str(take.relative_to(project)).replace("\\", "/")
            prontos.append(item)
    finally:
        sessao.__exit__(None, None, None)
        try:
            import critico_imagem
            critico_imagem.liberar()
        except ImportError:
            pass

    public["failures"] = falhas
    if not prontos:
        return {**public, "applied": False, "status": "skipped_geracao_falhou"}

    timeline = _inject(result["base_timeline"], prontos)
    errors = validar_timeline(project, timeline, _audio_path(project, timeline, manifest),
                              verificar_fontes=True)
    if errors:
        raise RuntimeError("timeline VX Cenas IA invalida:\n" + "\n".join(errors[:20]))
    _write_json(project / "timeline.json", timeline)
    public.update(selected=copy.deepcopy(prontos), status="applied", applied=True,
                  timeline=str(project / "timeline.json"))
    _write_json(plan_path, public)
    _write_json(state_path, {
        "schema_version": SCHEMA_VERSION, "slug": slug,
        "base_timeline": result["base_timeline"], "base_hash": _hash(result["base_timeline"]),
        "applied_hash": _hash(timeline), "plan": public,
    })
    return public


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--planejar", action="store_true")
    a = ap.parse_args()
    print(json.dumps(executar(a.slug, a.planejar), ensure_ascii=False, indent=2))
