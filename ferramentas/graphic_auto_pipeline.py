#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Graphics Auto: escolhe, renderiza e injeta motion typography pela letra.

Sem input editorial manual: usa letra/transcricao alinhada + 808 + tema do projeto.
A timeline original e preservada em estado para permitir reexecucao idempotente.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import shutil
from pathlib import Path

from audio_reactive_fx import carregar_picos, relativos
from render_impact_scene import renderizar_cena_impacto
from semantic_vision import scene_semantics_cfg
from style_preset_engine import (
    candidatos_semanticos,
    carregar_presets,
    montar_spec_design,
    normalizar,
)
from timeline_clipe import validar as validar_timeline

RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"
FPS = 30
from _vx import cache as vx_cache, config as vx_config, projeto as vx_projeto  # noqa: E402

DEFAULT_CONFIG = {
    "enabled": True,
    "max_scenes": 6,
    "min_gap_seconds": 9.0,
    "max_per_minute": 2,
    "min_score": 0.56,
    "intro_guard_seconds": 8.0,
    "outro_guard_seconds": 4.0,
    "protect_existing_specials": True,
    # Motion sobre a cena REAL (motion_lab, aprovado em 2026-09-30, decisao 003):
    # o take mostra a propria cena do anime com a tipografia em movimento em vez do
    # fundo procedural. Sem footage real no intervalo -> volta ao take procedural.
    "motion_real": True,
    "motion_estilos": ["atras_personagem", "palavra_por_palavra", "glitch_slice",
                       "kanji_fundo", "maquina_escrever", "impacto_zoom", "eco_repeticao",
                       "fragmentos", "contorno_energia", "letterbox_cinema", "faiscas",
                       "card_cena_escura", "card_cenario", "card_manga", "card_letra", "card_retrato"],
    "motion_max_linha": 3.6,
    # ritmo com motion: ~1 take a cada N segundos (sem motion o padrao antigo e 35 s)
    "motion_segundos_por_take": 12.0,
    "motion_max_scenes": 12,
    "motion_min_gap": 6.0,          # entre centros de takes
    "motion_max_por_30s": 3,        # takes numa janela de +-30 s
    "motion_max_take_linha": 5.5,   # take de linha mais longo que isso -> estilo de palavra
    "motion_repetir_palavra": 3,    # mesma palavra (tema do refrao) ate N vezes no video
    "motion_distancia_mesma_palavra": 25.0,
}

NORMAL_TYPES = {"", "lyric", "narrativo", "respiro"}
PRESET_STRENGTH = {
    "blood_burn": 1.00,
    "fire_burst": 0.98,
    "manga_brutal_pro": 0.97,
    "thunder_strike": 0.94,
    "void_glitch": 0.91,
    "cinematic_gold": 0.84,
    "neon_royal": 0.82,
}
NAME_PRESETS = (
    "neon_write_on",
    "neon_letter_reveal",
    "neon_outline_fill",
    "neon_trace",
)


def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return default


def _atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    tmp.write_text(payload, encoding="utf-8")
    try:
        tmp.replace(path)
    except PermissionError:
        # Alguns editores/antivirus no Windows permitem escrita mas bloqueiam
        # ReplaceFile/os.replace. Mantemos backup antes do fallback in-place.
        backup = path.with_suffix(path.suffix + ".vxg.bak")
        if path.exists():
            shutil.copy2(path, backup)
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.unlink(missing_ok=True)


def _hash_obj(data) -> str:
    # Hash canonico do nucleo (vx/cache.hash_obj). Ver decisao 008.
    return vx_cache.hash_obj(data)


def _cfg(manifesto: dict) -> dict:
    # codigo < config/estudio.json[graphics_auto] < projeto.json[graphics_auto]
    return vx_config.secao("graphics_auto", DEFAULT_CONFIG, manifesto)


def _audio_path(projeto: Path, manifesto: dict) -> Path:
    return vx_projeto.audio(projeto, manifesto)


def _audio_duration(projeto: Path, timeline: dict, manifesto: dict) -> float:
    value = timeline.get("audio_duration")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    from timeline_clipe import duracao
    return duracao(_audio_path(projeto, manifesto))


def _aliases(manifesto: dict) -> set[str]:
    """Aliases de identidade; titulo da faixa nao conta como nome do personagem."""
    values = set()
    personagem = normalizar(manifesto.get("personagem", ""))
    if personagem:
        values.add(personagem)
        values.update(x for x in personagem.split() if len(x) >= 3)
    return values


def _canonical_lines(projeto: Path) -> list[dict]:
    canonical = _json(projeto / "transcricao_canonica.json", {})
    if isinstance(canonical, dict) and canonical.get("lines"):
        out = []
        for line in canonical["lines"]:
            try:
                start, end = float(line["start"]), float(line["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                continue
            out.append({
                "text": str(line.get("text", "")).strip(),
                "start": start,
                "end": end,
                "words": line.get("words") or [],
                "confidence": str(line.get("confidence", "medium")),
                "source": "canonical",
            })
        if out:
            return out

    sync = _json(projeto / "letra_sincronizada.json", [])
    if isinstance(sync, list) and sync:
        out = []
        for line in sync:
            text = line.get("text") or line.get("texto") or line.get("line") or ""
            start = line.get("start", line.get("inicio"))
            end = line.get("end", line.get("fim"))
            try:
                start, end = float(start), float(end)
            except (TypeError, ValueError):
                continue
            if end > start:
                words = []
                for w in line.get("words") or []:
                    words.append({"word": w.get("word", w.get("text", "")),
                                  "start": w.get("start"), "end": w.get("end")})
                out.append({
                    "text": str(text).strip(), "start": start, "end": end,
                    "words": words,
                    "confidence": "medium", "source": "sync",
                })
        if out:
            return out

    raw = _json(projeto / "entradas" / "transcricao.json", {})
    raw_words = raw.get("words", []) if isinstance(raw, dict) else raw
    manifesto = _json(projeto / "projeto.json", {}) or {}
    letra_cfg = manifesto.get("letra", {})
    linhas_rel = letra_cfg.get("linhas") if isinstance(letra_cfg, dict) else None
    letra_rel = (letra_cfg.get("arquivo") if isinstance(letra_cfg, dict) else letra_cfg)
    authored = projeto / linhas_rel if linhas_rel else None
    if not authored or not authored.is_file():
        authored = projeto / letra_rel if letra_rel else None
    if authored and authored.is_file() and isinstance(raw_words, list) and raw_words:
        import sincronizar_letra as sl
        rows = [x.strip() for x in authored.read_text(encoding="utf-8").splitlines() if x.strip()]
        if not linhas_rel:
            rows = [re.sub(r"^\s*\d+(?:[.,]\d+)?\s+", "", x).strip()
                    for x in rows if re.match(r"^\s*\d+(?:[.,]\d+)?\s+", x)]
        # marcadores de secao ([Intro], [Refrao]...) nao sao cantados
        rows = sl.extrair_linhas_suno("\n".join(rows))
        if rows:
            aligned = sl.corrigir_sobreposicao(sl.alinhar(rows, raw_words))
            out = []
            for line in aligned:
                words = [{"word": w.get("word", w.get("text", "")),
                          "start": w.get("start"), "end": w.get("end")}
                         for w in line.get("words") or []]
                out.append({"text": line["text"], "start": float(line["start"]),
                            "end": float(line["end"]), "words": words,
                            "confidence": "medium", "source": "author_lyrics_aligned"})
            if out:
                return out

    raw = raw
    words = raw.get("words", []) if isinstance(raw, dict) else raw
    if not isinstance(words, list):
        return []
    frases, current = [], []
    for w in words:
        if not isinstance(w, dict) or "start" not in w:
            continue
        if current:
            gap = float(w.get("start", 0)) - float(current[-1].get("end", 0))
            if gap > 0.45 or len(current) >= 8:
                frases.append(current)
                current = []
        current.append(w)
    if current:
        frases.append(current)
    out = []
    for group in frases:
        if not group:
            continue
        start = float(group[0].get("start", 0))
        end = float(group[-1].get("end", start + 0.5))
        out.append({
            "text": " ".join(str(x.get("word", "")).strip() for x in group).strip(),
            "start": start, "end": end, "words": group,
            "confidence": "medium", "source": "asr",
        })
    return out


def _word_events(line: dict) -> list[dict]:
    events = []
    for item in line.get("words") or []:
        token = str(item.get("word", "")).strip()
        if not token:
            continue
        try:
            start = float(item.get("start", line["start"]))
            end = float(item.get("end", start + 0.2))
        except (TypeError, ValueError):
            continue
        events.append({
            "word": token, "norm": normalizar(token),
            "start": start, "end": max(start + 0.03, end),
        })
    if events:
        return events
    text = str(line.get("text", ""))
    tokens = re.findall(r"[\wÀ-ÿ'-]+", text, flags=re.UNICODE)
    if not tokens:
        return []
    span = max(0.1, float(line["end"]) - float(line["start"]))
    step = span / len(tokens)
    return [{
        "word": token, "norm": normalizar(token),
        "start": float(line["start"]) + i * step,
        "end": float(line["start"]) + (i + 1) * step,
    } for i, token in enumerate(tokens)]


def _semantic_strength(token: str) -> tuple[float, str | None]:
    presets = candidatos_semanticos(token)
    if not presets:
        return 0.0, None
    first = presets[0]
    return PRESET_STRENGTH.get(first, 0.80), first


def vocabulario_motion(manifesto: dict) -> dict[str, float]:
    """Palavras que valem take de motion sobre cena real mesmo sem preset procedural:
    termos do manifesto (0.90) e conceitos com kanji em assets/design/motion_lab.json (0.74)."""
    import motion_lab as ml
    voc: dict[str, float] = {}
    for chave in (ml.carregar_cfg(manifesto=manifesto).get("kanji") or {}):
        for p in normalizar(chave).split():
            if len(p) >= 3:
                voc[p] = max(voc.get(p, 0.0), 0.74)
    termos = ((manifesto.get("vocabulario") or {}).get("termos") or []) \
        if isinstance(manifesto.get("vocabulario"), dict) else []
    for termo in termos:
        for p in normalizar(termo).split():
            if len(p) >= 3:
                voc[p] = 0.90
    return voc


def _forca_motion(n: str, voc: dict[str, float] | None) -> float:
    if voc is None:
        return 0.0
    if n in voc:
        return voc[n]
    import motion_lab as ml
    # palavra longa e forte (nao stopword) tambem pode virar take; o score ainda filtra
    return 0.62 if len(n) >= 6 and ml.normalizar(n) not in ml.STOP else 0.0


def _dominant(line: dict, aliases: set[str], voc_motion: dict[str, float] | None = None) -> dict | None:
    best = None
    for ev in _word_events(line):
        n = ev["norm"]
        if not n:
            continue
        name_hit = n in aliases
        strength, suggested = _semantic_strength(n)
        if strength <= 0 and not name_hit:
            strength = _forca_motion(n, voc_motion)
        if not name_hit and strength <= 0:
            continue
        value = 1.05 if name_hit else strength
        item = dict(ev, strength=value, name_hit=name_hit, suggested=suggested)
        if best is None or item["strength"] > best["strength"]:
            best = item
    return best


def _beat_score(events: list[dict], anchor: float, line: dict) -> float:
    best = 0.0
    a, b = float(line["start"]) - 0.18, float(line["end"]) + 0.22
    for ev in events:
        try:
            t = float(ev.get("tempo", -999))
            intensity = max(0.0, min(1.25, float(ev.get("intensidade", 0.0))))
        except (TypeError, ValueError):
            continue
        if not (a <= t <= b):
            continue
        distance = abs(t - anchor)
        proximity = max(0.28, 1.0 - distance / 1.0)
        best = max(best, min(1.0, intensity) * proximity)
    return best


def _confidence_score(label: str) -> float:
    return {
        "high": 1.0, "medium": 0.82, "low": 0.50, "gap": 0.20
    }.get(str(label).lower(), 0.72)


def _secondary(line: dict, primary_norm: str) -> str:
    """Linha autoral completa; o renderer pode destacar a palavra dominante nela."""
    text = str(line.get("text", "")).strip()
    if len(text) > 72:
        text = text[:69].rsplit(" ", 1)[0] + "..."
    return text.upper()


def _protected_ranges(timeline: dict) -> list[tuple[float, float, str]]:
    out = []
    for seg in timeline.get("segments", []):
        typ = str(seg.get("type", ""))
        if typ in NORMAL_TYPES:
            continue
        try:
            out.append((float(seg["start"]), float(seg["end"]), typ))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _overlaps(start: float, end: float, ranges) -> bool:
    return any(start < b - 0.02 and end > a + 0.02 for a, b, _ in ranges)


def _candidate(line: dict, dominant: dict, beats: list[dict],
               audio_duration: float, cfg: dict, manifesto: dict) -> dict | None:
    anchor = (dominant["start"] + dominant["end"]) / 2.0
    name_hit = bool(dominant["name_hit"])
    beat = _beat_score(beats, anchor, line)
    sem = min(1.0, float(dominant["strength"]))
    confidence = _confidence_score(line.get("confidence", "medium"))
    pos = anchor / max(1.0, audio_duration)
    position_score = 1.0 if 0.08 <= pos <= 0.92 else 0.60
    score = 0.62 * sem + 0.24 * beat + 0.08 * confidence + 0.06 * position_score
    if name_hit:
        score = max(score, 0.88)

    if score < float(cfg["min_score"]):
        return None
    intro_guard = float(cfg["intro_guard_seconds"])
    outro_guard = float(cfg["outro_guard_seconds"])
    if anchor < intro_guard and not name_hit:
        return None
    if anchor > audio_duration - outro_guard:
        return None

    target = 1.95 if name_hit else 1.15 + 0.45 * score
    target = max(0.9, min(2.2, target))
    start = max(float(line["start"]), anchor - target * (0.30 if name_hit else 0.38))
    end = start + target
    max_end = min(audio_duration - 0.03, float(line["end"]) + 0.38)
    if end > max_end:
        shift = end - max_end
        start = max(float(line["start"]), start - shift)
        end = start + target
    frames = max(27, round((end - start) * FPS))
    duration = frames / FPS
    start = round(start * FPS) / FPS
    end = start + duration
    if end > audio_duration:
        end = math.floor(audio_duration * FPS) / FPS
        start = end - duration

    return {
        "line_text": line["text"],
        "line_start": round(float(line["start"]), 3),
        "line_end": round(float(line["end"]), 3),
        "source": line.get("source"),
        "word": dominant["word"].strip(" ,.;:!?").upper(),
        "word_norm": dominant["norm"],
        "word_start": round(float(dominant["start"]), 3),
        "word_end": round(float(dominant["end"]), 3),
        "sub": _secondary(line, dominant["norm"]),
        "name_hit": name_hit,
        "semantic_strength": round(sem, 4),
        "beat_score": round(beat, 4),
        "score": round(score, 4),
        "start": round(start, 6),
        "end": round(end, 6),
        "duration": round(duration, 6),
        "suggested_preset": dominant.get("suggested"),
        "support": (
            manifesto.get("anime", "") if name_hit
            else manifesto.get("faixa", "") or manifesto.get("personagem", "")
        ).upper(),
    }


def _select(candidates: list[dict], timeline: dict, cfg: dict,
            audio_duration: float) -> list[dict]:
    protected = _protected_ranges(timeline) if cfg.get("protect_existing_specials") else []
    motion = bool(cfg.get("motion_real"))
    # com motion sobre cena real o video pode ter bem mais takes (edicao "cheia");
    # sem motion vale o ritmo antigo (take procedural cansa se repetir muito)
    max_cfg = max(1, int(cfg["motion_max_scenes"] if motion else cfg["max_scenes"]))
    por_take = float(cfg.get("motion_segundos_por_take", 12.0)) if motion else 35.0
    natural = max(2, int(round(audio_duration / max(6.0, por_take))))
    limit = min(max_cfg, natural)
    min_gap = float(cfg["motion_min_gap"] if motion else cfg["min_gap_seconds"])
    max_per_min = max(1, int(cfg["motion_max_por_30s"] if motion else cfg["max_per_minute"]))

    selected = []
    used_words = set()
    for c in sorted(candidates, key=lambda x: (-x["score"], x["start"])):
        if _overlaps(c["start"], c["end"], protected):
            continue
        if c["word_norm"] in used_words:
            # com motion o refrao pode repetir a palavra-tema (ex.: INFINITO a cada refrao),
            # longe da anterior; o estilo muda sozinho (anti-repeticao de estilo)
            mesmas = [x for x in selected if x["word_norm"] == c["word_norm"]]
            if not motion or len(mesmas) >= int(cfg.get("motion_repetir_palavra", 3)) or any(
                    abs(c["start"] - x["start"]) < float(cfg.get("motion_distancia_mesma_palavra", 25.0))
                    for x in mesmas):
                continue
        center = (c["start"] + c["end"]) / 2
        if any(abs(center - (x["start"] + x["end"]) / 2) < min_gap for x in selected):
            continue
        # sem motion: <= max_per_minute em +-30 s (60 s); com motion: <= motion_max_por_30s em +-15 s
        raio = 15.0 if motion else 30.0
        if sum(1 for x in selected if abs(center - (x["start"] + x["end"]) / 2) < raio) >= max_per_min:
            continue
        selected.append(c)
        used_words.add(c["word_norm"])
        if len(selected) >= limit:
            break
    return sorted(selected, key=lambda x: x["start"])


def _base_timeline(projeto: Path, current: dict) -> tuple[dict, dict]:
    qa_dir = projeto / "qa" / "vx_graphics_auto"
    state_path = qa_dir / "state.json"
    state = _json(state_path, {}) or {}
    current_hash = _hash_obj(current)
    has_auto = any(s.get("type") == "vx_graphics_auto" for s in current.get("segments", []))

    if state.get("applied_hash") == current_hash and isinstance(state.get("base_timeline"), dict):
        return copy.deepcopy(state["base_timeline"]), state
    if has_auto:
        raise RuntimeError(
            "timeline contem VX Graphics Auto alterado fora do pipeline; "
            "regenere a timeline ou restaure o estado antes de reaplicar"
        )
    return copy.deepcopy(current), state


def _replace_interval(segments: list[dict], start: float, end: float,
                      graphics_segment: dict) -> list[dict]:
    out, inserted = [], False
    for seg in segments:
        ss, se = float(seg["start"]), float(seg["end"])
        if se <= start + 1e-6 or ss >= end - 1e-6:
            out.append(copy.deepcopy(seg))
            continue
        if ss < start - 1e-6:
            left = copy.deepcopy(seg)
            left["end"] = round(start, 6)
            left["duration"] = round(start - ss, 6)
            out.append(left)
        if not inserted:
            out.append(copy.deepcopy(graphics_segment))
            inserted = True
        if se > end + 1e-6:
            right = copy.deepcopy(seg)
            delta = end - ss
            right["start"] = round(end, 6)
            right["duration"] = round(se - end, 6)
            right["src"] = round(float(seg["src"]) + delta, 6)
            out.append(right)
    if not inserted:
        raise ValueError(f"intervalo grafico fora da timeline: {start:.3f}-{end:.3f}")
    return out


def _inject(base: dict, planned: list[dict]) -> dict:
    timeline = copy.deepcopy(base)
    segments = timeline.get("segments", [])
    for item in planned:
        seg = {
            "start": item["start"],
            "end": item["end"],
            "duration": item["duration"],
            "clip": item["clip"],
            "src": 0.0,
            "categoria": "motion_design",
            "note": (
                f"VX Graphics Auto: {item['word']} | {item['preset']} | "
                f"score={item['score']:.3f}"
            ),
            "type": "vx_graphics_auto",
            "graphics_auto": {
                "word": item["word"],
                "line": item["line_text"],
                "preset": item["preset"],
                "layout": item["layout"],
                "score": item["score"],
                "beat_score": item["beat_score"],
                "oculta_legenda": bool(item.get("oculta_legenda")),
            },
        }
        segments = _replace_interval(segments, item["start"], item["end"], seg)
    timeline["segments"] = segments
    timeline["total_segmentos"] = len(segments)
    timeline["graphics_auto"] = {
        "enabled": True,
        "version": 1,
        "count": len(planned),
        "moments": [{
            "start": x["start"], "end": x["end"], "word": x["word"],
            "preset": x["preset"], "score": x["score"],
        } for x in planned],
    }
    return timeline


def _alinhar_quadro(start: float, end: float, audio_duration: float) -> tuple[float, float, float]:
    start = max(0.0, round(start * FPS) / FPS)
    frames = max(27, round((end - start) * FPS))
    end = start + frames / FPS
    if end > audio_duration:
        end = math.floor(audio_duration * FPS) / FPS
        start = end - frames / FPS
    return round(start, 6), round(end, 6), round(frames / FPS, 6)


def linha_sincronizada(sync: list[dict], inicio: float, fim: float) -> tuple[dict, float | None] | None:
    """Linha de letra_sincronizada.json que mais se sobrepoe a [inicio, fim] + inicio da proxima."""
    ordenadas = sorted(sync or [], key=lambda l: float(l["start"]))
    melhor, prox, sobre = None, None, 0.0
    for k, ln in enumerate(ordenadas):
        s = min(fim, float(ln["end"])) - max(inicio, float(ln["start"]))
        if s > sobre:
            melhor, sobre = ln, s
            prox = float(ordenadas[k + 1]["start"]) if k + 1 < len(ordenadas) else None
    return (melhor, prox) if melhor else None


def janela_de_linha(item: dict, sync: list[dict] | None, audio_duration: float,
                    max_take: float) -> tuple[float, float, float] | None:
    """Janela de um take de linha: do inicio da linha ate o FIM REAL (ultima palavra
    sustentada) + tempo do fade. None se passar de `max_take` (entao usa estilo de palavra).
    Regressao: 'tormento' sumia porque o take acabava antes da ultima palavra."""
    import motion_lab as ml
    ini, fim = float(item["line_start"]), float(item["line_end"])
    achada = linha_sincronizada(sync or [], ini, fim)
    if achada:
        ln, prox = achada
        ini = min(ini, float(ln["start"]))
        fim = max(fim, ml.fim_da_linha(ln, prox))
    s, e = ini - 0.12, min(audio_duration - 0.03, fim + ml.TAKE_LINHA_SOBRA)
    if e - s > max_take:
        return None
    return _alinhar_quadro(s, e, audio_duration)


def entidade_protagonista(manifesto: dict) -> str | None:
    """Id do rotulo 'entity' do personagem principal em projeto.json -> scene_semantics.
    Casa pelo nome (qualquer palavra do `personagem` no name/prompt do rotulo); senao o 1o entity."""
    rotulos = [r for r in (scene_semantics_cfg(manifesto).get("labels") or [])
               if isinstance(r, dict) and r.get("kind") == "entity" and r.get("id")]
    if not rotulos:
        return None
    nomes = {p for p in normalizar(manifesto.get("personagem", "")).split() if len(p) >= 3}
    for r in rotulos:
        alvo = normalizar(f"{r.get('name', '')} {r.get('prompt', '')}")
        if nomes and any(n in alvo.split() for n in nomes):
            return r["id"]
    return rotulos[0]["id"]


def protagonista_em_cena(base: dict, inicio: float, fim: float, entidade: str | None,
                         minimo: float = 0.40, precisa_ser_top: bool = True) -> bool:
    """True se o personagem principal esta nos planos reais que o take cobre.

    Usa `scene_match.scene_semantic_scores` gravado pelo cenas-auto (OpenCLIP por cena),
    ponderado pela sobreposicao. Sem dados -> False (regra conservadora do usuario:
    contorno_energia/card_retrato so com o protagonista comprovado)."""
    if not entidade:
        return False
    soma, peso, top_ok = 0.0, 0.0, True
    for s in base.get("segments") or []:
        sobre = min(fim, float(s["end"])) - max(inicio, float(s["start"]))
        scores = (s.get("scene_match") or {}).get("scene_semantic_scores") or {}
        if sobre <= 0 or entidade not in scores:
            continue
        ent = {k: float(v) for k, v in scores.items() if k.startswith("entity:")}
        soma += float(scores[entidade]) * sobre
        peso += sobre
        if precisa_ser_top and ent and max(ent, key=ent.get) != entidade:
            top_ok = False
    return peso > 0 and soma / peso >= minimo and top_ok


def aplicar_motion_real(planned: list[dict], base: dict, cfg: dict, audio_duration: float,
                        manifesto: dict, subtitle_aware: bool,
                        sync: list[dict] | None = None,
                        score_protagonista=None) -> list[dict]:
    """`score_protagonista(inicio, dur) -> float|None`: verificacao visual (DetectorProtagonista).
    None/ausente -> regra por scene_semantic_scores."""
    """Troca o take procedural por motion typography sobre a cena real que ele cobre.

    Estilos de linha (palavra_por_palavra, maquina_escrever) cobrem a linha inteira e
    ocultam a legenda ASS nesse trecho (senao a frase aparece duas vezes). Se a linha
    expandida colidir com outro take/especial, usa um estilo de palavra unica.
    """
    import motion_lab as ml
    protegidos = _protected_ranges(base) if cfg.get("protect_existing_specials") else []
    # biblioteca decide o status (ativo/em_teste/desativado); motion_estilos e a lista permitida
    estilos = [e for e in cfg.get("motion_estilos") or [] if e in ml.ESTILOS and ml.status_de(e) == "ativo"]
    cfg_motion_hash = _hash_obj(ml.carregar_cfg(manifesto=manifesto))
    rg = ml.regras()
    entidade = entidade_protagonista(manifesto)
    out, recentes = [], []
    for item in planned:
        visual = score_protagonista(float(item["start"]), float(item["duration"])) if score_protagonista else None
        if visual is not None:
            prot = visual >= float(rg.get("protagonista_visual_min", 0.5))
        else:
            prot = protagonista_em_cena(base, float(item["start"]), float(item["end"]), entidade,
                                        float(rg.get("protagonista_min", 0.40)),
                                        bool(rg.get("protagonista_precisa_ser_top", True)))
        item = {**item, "posicao": float(item["start"]) / max(1.0, audio_duration), "protagonista": prot,
                "protagonista_score": None if visual is None else round(visual, 3)}
        estilo = ml.escolher_estilo(item, recentes, estilos, float(cfg.get("motion_max_linha", 3.6)))
        if not estilo:
            out.append(item)
            continue
        start, end, dur = item["start"], item["end"], item["duration"]
        if estilo in ml.ESTILOS_DE_LINHA:
            jan = janela_de_linha(item, sync, audio_duration, float(cfg.get("motion_max_take_linha", 5.5)))
            outros = [(x["start"], x["end"], "gfx") for x in out] + \
                     [(x["start"], x["end"], "gfx") for x in planned[len(out) + 1:]]
            if jan is None or _overlaps(jan[0], jan[1], protegidos) or _overlaps(jan[0], jan[1], outros):
                estilo = ml.escolher_estilo(item, recentes, [e for e in estilos if e in ml.ESTILOS_DE_PALAVRA])
            else:
                start, end, dur = jan
        trechos = ml.trechos_fonte(base, start, dur)
        if not estilo or not trechos:
            out.append(item)     # sem cena real: mantem o take procedural
            continue
        recentes.append(estilo)
        oculta = bool(subtitle_aware and estilo in ml.ESTILOS_DE_LINHA)
        motion = {
            "engine": "vx_motion_real", "estilo": estilo, "start": start, "duration": dur,
            "word": item["word"], "word_start": item["word_start"], "oculta_legenda": oculta,
            "line_text": item.get("line_text", ""),
            "fonte": trechos, "cfg_hash": cfg_motion_hash,
        }
        out.append({**item, "start": start, "end": end, "duration": dur,
                     "preset": f"motion_{estilo}", "layout": "motion_real",
                     "background": "cena_real", "oculta_legenda": oculta, "spec": motion})
    return out


def planejar(slug: str) -> dict:
    projeto = PROJETOS / slug
    if not projeto.is_dir():
        raise FileNotFoundError(f"projeto nao encontrado: {projeto}")
    manifesto = _json(projeto / "projeto.json", {}) or {}
    current = _json(projeto / "timeline.json", {}) or {}
    if not current.get("segments"):
        raise ValueError("timeline ausente ou sem segments")
    base, state = _base_timeline(projeto, current)
    cfg = _cfg(manifesto)
    if not cfg.get("enabled", True):
        return {"slug": slug, "enabled": False, "selected": [], "config": cfg}

    lines = _canonical_lines(projeto)
    if not lines:
        raise RuntimeError("nenhuma letra/transcricao alinhada disponivel para VX Graphics Auto")
    beats = carregar_picos(projeto, manifesto)
    duration = _audio_duration(projeto, base, manifesto)
    aliases = _aliases(manifesto)

    voc_motion = vocabulario_motion(manifesto) if cfg.get("motion_real") else None
    candidates = []
    for line in lines:
        dom = _dominant(line, aliases, voc_motion)
        if dom is None:
            continue
        c = _candidate(line, dom, beats, duration, cfg, manifesto)
        if c is not None:
            candidates.append(c)
    selected = _select(candidates, base, cfg, duration)

    recent_presets, recent_layouts = [], []
    planned = []
    subtitle_aware = bool(manifesto.get("legenda_ass"))
    for i, c in enumerate(selected, 1):
        spec = montar_spec_design(
            palavra=c["word"], slug=slug, manifesto=manifesto,
            texto_secundario="" if subtitle_aware else c["sub"], duracao=c["duration"],
            energia=max(0.72, min(1.0, 0.72 + c["score"] * 0.26)),
            preset="auto", layout="auto",
            presets_recentes=tuple(recent_presets[-3:]),
            layouts_recentes=tuple(recent_layouts[-2:]),
        )
        spec["tempo_inicio"] = c["start"]
        spec["duracao"] = c["duration"]
        spec["suporte"] = c["support"]
        spec["subtitle_aware"] = subtitle_aware
        spec["beat_events"] = relativos(beats, c["start"], c["duration"])
        spec.setdefault("audio_reactive", {})["source"] = (
            "subgrave_808" if spec["beat_events"] else "curve_only"
        )
        spec["audio_reactive"]["beat_count"] = len(spec["beat_events"])
        recent_presets.append(spec["preset"])
        recent_layouts.append(spec["layout"])
        planned.append({
            **c,
            "id": f"auto_gfx_{i:02d}",
            "preset": spec["preset"],
            "layout": spec["layout"],
            "background": spec["background"],
            "spec": spec,
        })

    if cfg.get("motion_real"):
        import motion_lab as ml
        sync = _json(projeto / "letra_sincronizada.json", []) or []
        score_prot = None
        if any("protagonista" in ml.exige(e) for e in ml.ativos()):
            try:
                det = ml.DetectorProtagonista(manifesto)
                if det.ok:
                    auditoria = projeto / "qa" / "vx_graphics_auto" / "protagonista"
                    if auditoria.is_dir():
                        for velho in auditoria.glob("*.jpg"):
                            velho.unlink()
                    score_prot = lambda ini, dur: det.score_janela(projeto, base, ini, dur, salvar=auditoria)  # noqa: E731
            except Exception as exc:   # sem CLIP: cai na regra por scene_semantic_scores
                print(f"  [graficos-auto] detector de protagonista indisponivel: {exc}")
        planned = aplicar_motion_real(planned, base, cfg, duration, manifesto, subtitle_aware, sync, score_prot)

    return {
        "slug": slug,
        "enabled": True,
        "config": cfg,
        "source_lines": len(lines),
        "candidate_count": len(candidates),
        "audio_duration": duration,
        "protected_ranges": _protected_ranges(base),
        "selected": planned,
        "base_timeline": base,
        "previous_state": state,
    }


def executar(slug: str, somente_planejar: bool = False) -> dict:
    result = planejar(slug)
    projeto = PROJETOS / slug
    qa_dir = projeto / "qa" / "vx_graphics_auto"
    qa_dir.mkdir(parents=True, exist_ok=True)
    plan_public = {
        k: copy.deepcopy(v) for k, v in result.items()
        if k not in {"base_timeline", "previous_state"}
    }
    for item in plan_public.get("selected", []):
        item.pop("spec", None)
    _atomic_json(qa_dir / "plano.json", plan_public)

    if somente_planejar or not result.get("enabled"):
        return plan_public

    selected = result["selected"]
    manifesto = _json(projeto / "projeto.json", {}) or {}
    sync = None
    clips_dir = projeto / "clips_raw" / "vx_graphics_auto"
    clips_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for i, item in enumerate(selected, 1):
        safe = re.sub(r"[^a-z0-9]+", "_", normalizar(item["word"])).strip("_") or "impacto"
        out = clips_dir / f"{i:02d}_{safe}_{item['preset']}.mp4"
        design = out.with_suffix(".design.json")
        cached_spec = _json(design, None)
        spec = json.loads(json.dumps(item["spec"], default=str))
        if not (out.is_file() and out.stat().st_size and cached_spec == spec):
            if spec.get("engine") == "vx_motion_real":
                import motion_lab as ml
                if sync is None:
                    sync = _json(projeto / "letra_sincronizada.json", []) or []
                ml.renderizar_take(projeto, manifesto, result["base_timeline"], sync, spec, out)
                _atomic_json(design, spec)
            else:
                renderizar_cena_impacto(item["spec"], projeto, out)
        item["clip"] = str(out.relative_to(projeto)).replace("\\", "/")
        rendered.append(str(out))

    timeline = _inject(result["base_timeline"], selected)
    manifesto = _json(projeto / "projeto.json", {}) or {}
    errors = validar_timeline(
        projeto, timeline, _audio_path(projeto, manifesto), verificar_fontes=True
    )
    if errors:
        raise RuntimeError(
            "timeline VX Graphics Auto invalida:\n" + "\n".join(errors[:20])
        )

    timeline_path = projeto / "timeline.json"
    _atomic_json(timeline_path, timeline)
    state = {
        "version": 1,
        "slug": slug,
        "base_timeline": result["base_timeline"],
        "base_hash": _hash_obj(result["base_timeline"]),
        "applied_hash": _hash_obj(timeline),
        "generated_clips": rendered,
        "plan": plan_public,
    }
    _atomic_json(qa_dir / "state.json", state)
    return {
        **plan_public,
        "rendered": rendered,
        "timeline": str(timeline_path),
        "timeline_segments": len(timeline["segments"]),
        "applied": True,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--planejar", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        executar(args.slug, somente_planejar=args.planejar),
        ensure_ascii=False, indent=2,
    ))
