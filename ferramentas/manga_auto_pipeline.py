#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Manga Auto — insere raros takes de manga em clímax reais da letra.

Ordem de produção:
    cenas-auto -> manga-auto -> graficos-auto -> planejar

Filosofia:
- manga é recurso raro, não decoração recorrente;
- no máximo 1–2 takes por faixa;
- exige letra intensa + suporte visual + energia de áudio;
- protege qualquer segmento especial já existente;
- idempotente e cacheado;
- se não existir um candidato realmente forte, não insere nada.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
from pathlib import Path

from _vx import config as vx_config, projeto as vx_projeto
from audio_reactive_fx import carregar_picos
import graphic_auto_pipeline as gap
import manga_panel_director as manga
import semantic_scene_matcher as sm
from timeline_clipe import validar as validar_timeline

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projetos"
SCHEMA_VERSION = 1

DEFAULTS = {
    "enabled": True,
    "max_scenes": 2,
    "min_gap_seconds": 38.0,
    "min_score": 0.77,
    "intro_guard_seconds": 13.0,
    "outro_guard_seconds": 7.0,
    "duration_min": 1.30,
    "duration_max": 1.60,
}

HIGH_CONCEPTS = {
    "electric", "fire", "rage", "fight", "power", "blood", "speed",
}
MEDIUM_CONCEPTS = {"dark", "victory"}


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
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
        backup = path.with_suffix(path.suffix + ".vxmanga.bak")
        if path.exists():
            shutil.copy2(path, backup)
        path.write_text(payload, encoding="utf-8")
        tmp.unlink(missing_ok=True)


def _hash(data) -> str:
    raw = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _config(manifest: dict) -> dict:
    # codigo < config/estudio.json[manga_auto] < projeto.json[manga_auto]
    return vx_config.secao("manga_auto", DEFAULTS, manifest)


def _audio_path(project: Path, manifest: dict) -> Path:
    return vx_projeto.audio(project, manifest)


def _duration(timeline: dict, project: Path, manifest: dict) -> float:
    try:
        value = float(timeline.get("audio_duration"))
        if math.isfinite(value) and value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return float(gap._audio_duration(project, timeline, manifest))


def _beat_score(events: list[dict], start: float, end: float) -> float:
    best = 0.0
    for ev in events:
        try:
            t = float(ev.get("tempo", -999))
            intensity = float(ev.get("intensidade", 0.0))
        except (TypeError, ValueError):
            continue
        if start - 0.16 <= t <= end + 0.16:
            best = max(best, min(1.0, max(0.0, intensity)))
    return best


def _special_ranges(timeline: dict):
    normal = {"", "lyric", "narrativo", "respiro", "gap", "intro", "outro"}
    out = []
    for seg in timeline.get("segments", []):
        typ = str(seg.get("type", ""))
        if typ in normal:
            continue
        try:
            out.append((float(seg["start"]), float(seg["end"]), typ))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _overlap(a: float, b: float, ranges) -> bool:
    return any(a < y - 0.02 and b > x + 0.02 for x, y, _ in ranges)


def _take_window(line: dict, duration: float, audio_duration: float) -> tuple[float, float]:
    a, b = float(line["start"]), float(line["end"])
    center = (a + b) / 2.0
    start = center - duration / 2.0
    if start < a:
        start = a
    if start + duration > b + 0.35:
        start = max(a, b + 0.35 - duration)
    start = max(0.0, min(start, audio_duration - duration - 0.02))
    start = round(start * 30.0) / 30.0
    end = start + duration
    return round(start, 6), round(end, 6)


def _candidate(
    project: Path,
    line: dict,
    manifest: dict,
    beats: list[dict],
    audio_duration: float,
    cfg: dict,
) -> dict | None:
    text = str(line.get("text", "")).strip()
    if not text:
        return None
    intent = sm.interpretar_texto(text, manifest, tipo="lyric")
    concepts = set(intent.get("concepts") or [])
    strong = bool(concepts & HIGH_CONCEPTS)
    medium = bool(concepts & MEDIUM_CONCEPTS)
    if not strong and not medium:
        return None

    line_start, line_end = float(line["start"]), float(line["end"])
    center = (line_start + line_end) / 2.0
    if center < float(cfg["intro_guard_seconds"]):
        return None
    if center > audio_duration - float(cfg["outro_guard_seconds"]):
        return None

    target = float(intent.get("target_intensity", 0.5))
    concept_bonus = 1.0 if strong else 0.66
    beat = _beat_score(beats, line_start, line_end)

    try:
        _, picks = manga._rank_scenes(project, text, 1.5, count=3)
    except Exception:
        return None
    visual_scores = [float(x.get("score", 0.0)) for x in picks]
    visual = sum(visual_scores) / max(1, len(visual_scores))
    visual_min = min(visual_scores) if visual_scores else 0.0

    score = (
        0.34 * target
        + 0.31 * visual
        + 0.19 * beat
        + 0.16 * concept_bonus
    )
    # Sem três fontes visualmente fortes, não vale gastar o efeito.
    if visual_min < 0.66:
        score -= 0.09

    if score < float(cfg["min_score"]):
        return None

    # Clímax mais forte pode ganhar alguns frames extras; sempre curto.
    dmin = float(cfg["duration_min"])
    dmax = float(cfg["duration_max"])
    duration = dmin + (dmax - dmin) * max(0.0, min(1.0, (score - 0.72) / 0.24))
    duration = round(max(39, min(48, round(duration * 30))) / 30.0, 6)
    start, end = _take_window(line, duration, audio_duration)
    return {
        "text": text,
        "source": line.get("source", "lyrics"),
        "line_start": round(line_start, 4),
        "line_end": round(line_end, 4),
        "start": start,
        "end": end,
        "duration": duration,
        "score": round(score, 5),
        "lyric_intensity": round(target, 5),
        "beat_score": round(beat, 5),
        "visual_score": round(visual, 5),
        "visual_min": round(visual_min, 5),
        "concepts": sorted(concepts),
        "sources_preview": [
            {
                "clip": x["scene"]["clip"],
                "scene_id": x["scene"]["id"],
                "scene_start": x["scene"]["start"],
                "score": round(float(x["score"]), 5),
                "tags": x["scene"].get("tags", []),
            }
            for x in picks
        ],
    }


def _spec_render(item: dict) -> dict:
    """O que define o take renderizado: mudou qualquer coisa aqui -> renderiza de novo."""
    return {
        "render_version": 2,
        "text": item.get("text"),
        "duration": item.get("duration"),
        # listas (nao tuplas): o spec volta do JSON e precisa comparar igual
        "sources": [[s.get("clip"), s.get("scene_id"), s.get("scene_start")]
                    for s in item.get("sources_preview") or []],
    }


def _select(candidates: list[dict], timeline: dict, cfg: dict) -> list[dict]:
    protected = _special_ranges(timeline)
    selected = []
    used_concepts = set()
    for c in sorted(candidates, key=lambda x: (-x["score"], x["start"])):
        if _overlap(c["start"], c["end"], protected):
            continue
        concepts = set(c.get("concepts") or [])
        # Manga é raro: não repetir a mesma linguagem semântica na faixa.
        if concepts & used_concepts:
            continue
        center = (c["start"] + c["end"]) / 2.0
        if any(
            abs(center - (x["start"] + x["end"]) / 2.0)
            < float(cfg["min_gap_seconds"])
            for x in selected
        ):
            continue
        selected.append(c)
        used_concepts.update(concepts)
        if len(selected) >= int(cfg["max_scenes"]):
            break
    return sorted(selected, key=lambda x: x["start"])


def _replace_interval(segments: list[dict], start: float, end: float, special: dict):
    out = []
    inserted = False
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
            out.append(copy.deepcopy(special))
            inserted = True
        if se > end + 1e-6:
            right = copy.deepcopy(seg)
            right["start"] = round(end, 6)
            right["duration"] = round(se - end, 6)
            right["src"] = round(float(seg["src"]) + (end - ss), 6)
            out.append(right)
    if not inserted:
        raise ValueError(f"intervalo manga fora da timeline {start:.3f}-{end:.3f}")
    return out


def _inject(base: dict, selected: list[dict]) -> dict:
    timeline = copy.deepcopy(base)
    segments = timeline.get("segments", [])
    for item in selected:
        seg = {
            "start": item["start"],
            "end": item["end"],
            "duration": item["duration"],
            "clip": item["clip"],
            "src": 0.0,
            "categoria": "manga_climax",
            "type": "vx_manga_auto",
            "note": f"VX Manga Auto: {item['text']} | score={item['score']:.3f}",
            "manga_auto": {
                "text": item["text"],
                "score": item["score"],
                "concepts": item["concepts"],
                "beat_score": item["beat_score"],
                "visual_score": item["visual_score"],
            },
        }
        segments = _replace_interval(
            segments, item["start"], item["end"], seg
        )
    timeline["segments"] = segments
    timeline["total_segmentos"] = len(segments)
    timeline["manga_auto"] = {
        "version": SCHEMA_VERSION,
        "count": len(selected),
        "moments": [
            {
                "start": x["start"], "end": x["end"],
                "text": x["text"], "score": x["score"],
            }
            for x in selected
        ],
    }
    return timeline


def planejar(slug: str, timeline_override: dict | None = None) -> dict:
    project = PROJECTS / slug
    manifest = _read_json(project / "projeto.json", {}) or {}
    timeline = (copy.deepcopy(timeline_override) if timeline_override is not None
                else (_read_json(project / "timeline.json", {}) or {}))
    if not timeline.get("segments"):
        raise ValueError("timeline ausente ou vazia")
    cfg = _config(manifest)
    if not cfg.get("enabled", True):
        return {
            "slug": slug, "enabled": False, "selected": [],
            "config": cfg, "base_timeline": timeline,
        }

    # Ordem obrigatória: manga antes do Graphics Auto.
    if any(
        s.get("type") == "vx_graphics_auto"
        for s in timeline.get("segments", [])
    ):
        return {
            "slug": slug,
            "enabled": True,
            "status": "preserved_after_graphics_auto",
            "selected": [],
            "config": cfg,
            "base_timeline": timeline,
        }

    lines = gap._canonical_lines(project)
    beats = carregar_picos(project, manifest)
    audio_duration = _duration(timeline, project, manifest)
    candidates = []
    for line in lines:
        c = _candidate(
            project, line, manifest, beats, audio_duration, cfg
        )
        if c:
            candidates.append(c)
    selected = _select(candidates, timeline, cfg)
    return {
        "slug": slug,
        "enabled": True,
        "status": "planned",
        "config": cfg,
        "audio_duration": audio_duration,
        "candidate_count": len(candidates),
        "selected": selected,
        "base_timeline": timeline,
    }


def executar(slug: str, somente_planejar: bool = False) -> dict:
    project = PROJECTS / slug
    qa = project / "qa" / "vx_manga_auto"
    qa.mkdir(parents=True, exist_ok=True)
    state_path = qa / "state.json"
    plan_path = qa / "plano.json"
    state = _read_json(state_path, {}) or {}
    current = _read_json(project / "timeline.json", {}) or {}
    current_hash = _hash(current)

    # Graphics Auto vem depois do Manga Auto e altera legitimamente a timeline.
    # Em uma retomada da esteira, preservar em vez de confundir com edição externa.
    if any(s.get("type") == "vx_graphics_auto" for s in current.get("segments", [])):
        return {
            "slug": slug,
            "status": "preserved_after_graphics_auto",
            "applied": False,
            "selected": state.get("plan", {}).get("selected", []),
            "timeline": str(project / "timeline.json"),
        }

    # Idempotência após aplicação.
    if (
        any(s.get("type") == "vx_manga_auto" for s in current.get("segments", []))
        and state.get("applied_hash") == current_hash
    ):
        return {
            "slug": slug, "status": "cached", "applied": False,
            "selected": state.get("plan", {}).get("selected", []),
            "timeline": str(project / "timeline.json"),
        }
    if (
        any(s.get("type") == "vx_manga_auto" for s in current.get("segments", []))
        and state.get("applied_hash") != current_hash
    ):
        raise RuntimeError(
            "timeline com VX Manga Auto foi alterada externamente; falha fechada"
        )

    result = planejar(slug)
    public = {
        k: copy.deepcopy(v)
        for k, v in result.items()
        if k != "base_timeline"
    }
    _write_json(plan_path, public)

    if somente_planejar or result.get("status") == "preserved_after_graphics_auto":
        return {**public, "applied": False}

    selected = result["selected"]
    if not selected:
        return {**public, "applied": False, "status": "skipped_no_strong_candidate"}

    out_dir = project / "clips_raw" / "vx_manga_auto"
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(selected, 1):
        safe = re.sub(r"[^a-z0-9]+", "_", gap.normalizar(item["text"])).strip("_")[:36]
        out = out_dir / f"{i:02d}_{safe or 'climax'}_manga.mp4"
        design = out.with_suffix(".design.json")
        # cache pelo CONTEUDO (texto, duracao e cenas-fonte), nao so pelo nome do arquivo.
        # Regressao Douma (01/10/2026): o take antigo, com a cartela "Watch on Crunchyroll",
        # ficou no video depois que a cena passou a ser poluida, porque o nome nao mudou.
        spec = _spec_render(item)
        should_render = (not out.is_file() or out.stat().st_size <= 0
                         or (_read_json(design, {}) or {}).get("spec") != spec)
        if should_render:
            manga.render_take(
                project, item["text"], out,
                duration=item["duration"], layout="3_shonen",
            )
            _write_json(design, {"spec": spec})
        item["clip"] = str(out.relative_to(project)).replace("\\", "/")

    timeline = _inject(result["base_timeline"], selected)
    manifest = _read_json(project / "projeto.json", {}) or {}
    errors = validar_timeline(
        project, timeline, _audio_path(project, manifest),
        verificar_fontes=True,
    )
    if errors:
        raise RuntimeError(
            "timeline VX Manga Auto invalida:\n" + "\n".join(errors[:20])
        )

    _write_json(project / "timeline.json", timeline)
    public["selected"] = copy.deepcopy(selected)
    public["status"] = "applied"
    public["applied"] = True
    public["timeline"] = str(project / "timeline.json")
    _write_json(plan_path, public)
    _write_json(state_path, {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "base_timeline": result["base_timeline"],
        "base_hash": _hash(result["base_timeline"]),
        "applied_hash": _hash(timeline),
        "plan": public,
    })
    return public
