#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Semantic Scene Matcher — casa letra/narrativa com cenas visuais.

Consome scene_intelligence.json e uma timeline-base. Para cada segmento comum,
escolhe uma cena real do material bruto usando semântica, intensidade,
qualidade e memória anti-repetição. Não depende do nome do arquivo nem de um
anime específico.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from difflib import SequenceMatcher
from pathlib import Path

from scene_intelligence import catalogar_projeto
from semantic_vision import profile_from_manifest, semantic_targets
from style_preset_engine import normalizar
from timeline_clipe import validar as validar_timeline

SCHEMA_VERSION = 2
NORMAL_TYPES = {"", "lyric", "narrativo", "respiro", "gap", "intro", "outro"}

CONCEPTS = [
    {
        "name": "fire",
        "keywords": ["fogo", "chama", "chamas", "queimar", "queima", "incendio", "amaterasu"],
        "tags": {"fire": 1.0, "destruction": 0.72, "impact": 0.48},
        "intensity": 0.82,
    },
    {
        "name": "electric",
        "keywords": ["raio", "trovao", "relampago", "eletrico", "eletricidade", "chidori", "kirin"],
        "tags": {"electric": 1.0, "energy": 0.82, "action": 0.48},
        "intensity": 0.88,
    },
    {
        "name": "blood",
        "keywords": ["sangue", "sangrar", "ferida", "corte", "cortar"],
        "tags": {"blood": 1.0, "impact": 0.62, "fight": 0.58},
        "intensity": 0.76,
    },
    {
        "name": "rage",
        "keywords": ["odio", "raiva", "furia", "vinganca", "vingador", "matar", "destruir", "destruicao"],
        "tags": {"fight": 0.90, "impact": 0.82, "dark": 0.46, "destruction": 0.72},
        "intensity": 0.90,
    },
    {
        "name": "fight",
        "keywords": ["luta", "batalha", "golpe", "soco", "espada", "lamina", "ataque", "combate", "duelo"],
        "tags": {"fight": 1.0, "action": 0.88, "impact": 0.66},
        "intensity": 0.82,
    },
    {
        "name": "power",
        "keywords": ["poder", "energia", "aura", "despertar", "desperta", "deus", "rei", "monarca", "dominio", "susanoo"],
        "tags": {"power": 1.0, "energy": 0.86, "high_contrast": 0.35},
        "intensity": 0.78,
    },
    {
        "name": "dark",
        "keywords": ["escuridao", "sombra", "sombras", "noite", "maldicao", "maldito", "abismo"],
        "tags": {"dark": 1.0, "purple_energy": 0.42, "emotional": 0.30},
        "intensity": 0.48,
    },
    {
        "name": "pain",
        "keywords": ["dor", "perder", "perdi", "perda", "sozinho", "solidao", "chorar", "lagrima", "passado", "memoria", "lembranca"],
        "tags": {"emotional": 1.0, "portrait": 0.76, "closeup": 0.58, "calm": 0.46},
        "intensity": 0.34,
    },
    {
        "name": "identity",
        "keywords": ["cla", "familia", "irmao", "pai", "mae", "nome", "legado", "olho", "olhos", "olhar"],
        "tags": {"portrait": 0.86, "closeup": 0.74, "emotional": 0.55, "center_subject": 0.42},
        "intensity": 0.42,
    },
    {
        "name": "speed",
        "keywords": ["rapido", "velocidade", "voar", "voando", "correndo", "correr", "flash"],
        "tags": {"speed": 1.0, "action": 0.80, "fight": 0.42},
        "intensity": 0.84,
    },
    {
        "name": "victory",
        "keywords": ["vitoria", "liberdade", "vencer", "fim", "destino", "renascer"],
        "tags": {"power": 0.76, "bright": 0.52, "center_subject": 0.46},
        "intensity": 0.62,
    },
]


def _hash_obj(data) -> str:
    raw = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _character_aliases(manifesto: dict) -> set[str]:
    out = set()
    p = normalizar(manifesto.get("personagem", ""))
    if p:
        out.add(p)
        out.update(x for x in p.split() if len(x) >= 3)
    return out


def interpretar_texto(texto: str, manifesto: dict | None = None, tipo="lyric", section="verse") -> dict:
    manifesto = manifesto or {}
    n = normalizar(texto)
    tokens = set(n.split())
    tag_weights = {}
    concepts = []
    intensities = []

    for concept in CONCEPTS:
        hits = [k for k in concept["keywords"] if normalizar(k) in tokens]
        if not hits:
            continue
        concepts.append(concept["name"])
        intensities.append(float(concept["intensity"]))
        for tag, weight in concept["tags"].items():
            tag_weights[tag] = max(tag_weights.get(tag, 0.0), float(weight))

    aliases = _character_aliases(manifesto)
    if aliases and any(alias in n or alias in tokens for alias in aliases):
        concepts.append("character")
        tag_weights["portrait"] = max(tag_weights.get("portrait", 0.0), 1.0)
        tag_weights["closeup"] = max(tag_weights.get("closeup", 0.0), 0.74)
        tag_weights["center_subject"] = max(
            tag_weights.get("center_subject", 0.0), 0.62
        )
        intensities.append(0.52)

    if not tag_weights:
        if tipo in {"intro", "outro", "gap", "respiro"}:
            tag_weights = {"calm": 0.80, "portrait": 0.35, "dark": 0.20}
            intensities = [0.28]
            concepts = ["breathing_space"]
        else:
            tag_weights = {"action": 0.54, "center_subject": 0.34}
            intensities = [0.58]
            concepts = ["generic_lyric"]

    target = float(np_mean(intensities)) if intensities else 0.55
    if section == "refrain":
        target = min(1.0, target + 0.06)
    semantic_profile = profile_from_manifest(manifesto)
    vision_targets = semantic_targets(texto, semantic_profile)
    return {
        "text": texto,
        "normalized": n,
        "concepts": concepts,
        "tag_weights": tag_weights,
        "target_intensity": round(max(0.0, min(1.0, target)), 4),
        "section": section,
        "semantic_targets": vision_targets,
        "required_semantic_score": float(semantic_profile.get("required_score", 0.16)),
    }


def np_mean(values):
    return sum(values) / max(1, len(values))


def _infer_song_sections(lines: list[dict]) -> list[dict]:
    if not lines:
        return lines
    out = [dict(row, section=str(row.get("section") or "verse")) for row in lines]
    normalized = [normalizar(row.get("text", "")) for row in out]
    best = (0, -1, -1)
    n = len(out)
    for i in range(n):
        for j in range(i + 2, n):
            k = 0
            while i+k < n and j+k < n:
                ratio = SequenceMatcher(None, normalized[i+k], normalized[j+k]).ratio()
                if ratio < 0.64:
                    break
                k += 1
            if k >= 2 and k > best[0]:
                best = (k, i, j)
    if best[0] >= 2:
        length, a, b = best
        for idx in list(range(a, a+length)) + list(range(b, b+length)):
            out[idx]["section"] = "refrain"
    for i in range(n):
        for j in range(i+1, n):
            if SequenceMatcher(None, normalized[i], normalized[j]).ratio() >= 0.86:
                out[i]["section"] = out[j]["section"] = "refrain"
    return out


def _lyric_lines(projeto_dir: Path) -> list[dict]:
    canonical = _read_json(projeto_dir / "transcricao_canonica.json", {}) or {}
    if isinstance(canonical, dict) and canonical.get("lines"):
        out = []
        for row in canonical["lines"]:
            try:
                a, b = float(row["start"]), float(row["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if b > a:
                out.append({"start": a, "end": b, "text": str(row.get("text", "")).strip()})
        if out:
            return _infer_song_sections(out)
    sync = _read_json(projeto_dir / "letra_sincronizada.json", []) or []
    out = []
    if isinstance(sync, list):
        for row in sync:
            try:
                a = float(row.get("start", row.get("inicio")))
                b = float(row.get("end", row.get("fim")))
            except (TypeError, ValueError):
                continue
            text = row.get("text") or row.get("texto") or row.get("line") or ""
            if b > a and str(text).strip():
                out.append({"start": a, "end": b, "text": str(text).strip()})
    return _infer_song_sections(out)


def _text_for_segment(seg: dict, lyric_lines: list[dict]) -> tuple[str, str]:
    explicit = str(seg.get("note") or "").strip()
    if explicit:
        return explicit, "timeline_note"
    try:
        a, b = float(seg["start"]), float(seg["end"])
    except (KeyError, TypeError, ValueError):
        return "", "none"
    ranked = []
    for line in lyric_lines:
        overlap = max(0.0, min(b, line["end"]) - max(a, line["start"]))
        if overlap <= 0:
            continue
        line_dur = max(0.05, line["end"] - line["start"])
        seg_dur = max(0.05, b - a)
        score = overlap / min(line_dur, seg_dur)
        ranked.append((score, overlap, line))
    if not ranked:
        return "", "none"
    ranked.sort(key=lambda x: (-x[0], -x[1], x[2]["start"]))
    best = ranked[0][2]
    return best["text"], "aligned_lyrics"


def _section_for_segment(seg: dict, lyric_lines: list[dict]) -> str:
    try:
        a, b = float(seg["start"]), float(seg["end"])
    except (KeyError, TypeError, ValueError):
        return "verse"
    ranked = []
    for line in lyric_lines:
        overlap = max(0.0, min(b, line["end"]) - max(a, line["start"]))
        if overlap > 0:
            ranked.append((overlap, line.get("section", "verse")))
    if not ranked:
        return "verse"
    ranked.sort(key=lambda item: -item[0])
    return str(ranked[0][1])


def _scene_inventory(catalog: dict) -> list[dict]:
    out = []
    for clip_name, clip in catalog.get("clips", {}).items():
        if not clip.get("eligible_for_semantic_selection"):
            continue
        clip_duration = float(clip.get("duration", 0.0))
        for scene in clip.get("scenes", []):
            # Cenas mortas (tail preto / splash de streaming sobre fundo preto)
            # nunca sao material narrativo e reprovam o porteiro de imagem.
            # Cena com legenda queimada/texto da fonte (porteiro fonte-limpa) tambem nunca entra.
            if scene.get("dead_scene") or scene.get("poluida"):
                continue
            row = copy.deepcopy(scene)
            row["clip"] = clip_name
            row["clip_duration"] = clip_duration
            out.append(row)
    return out


def _semantic_score(intent: dict, scene: dict) -> float:
    weights = intent["tag_weights"]
    scores = scene.get("tag_scores", {})
    total_w = sum(weights.values()) or 1.0
    matched = sum(
        float(weight) * float(scores.get(tag, 0.0))
        for tag, weight in weights.items()
    )
    return max(0.0, min(1.0, matched / total_w))


def _vision_semantic_score(intent: dict, scene: dict) -> tuple[float, dict]:
    targets = intent.get("semantic_targets") or []
    if not targets:
        return 0.0, {}
    scores = scene.get("semantic_scores") or {}
    weighted = []
    details = {}
    kind_weight = {"entity": 1.15, "action": 1.25, "context": 1.35}
    for target in targets:
        value = float(scores.get(target["id"], 0.0))
        weight = kind_weight.get(target.get("kind"), 1.0)
        weighted.append((value, weight))
        details[target["id"]] = round(value, 5)
    total = sum(w for _, w in weighted) or 1.0
    value = sum(v*w for v, w in weighted) / total
    return max(0.0, min(1.0, value)), details


def _duration_score(scene: dict, duration: float) -> float:
    available = float(scene.get("duration", 0.0))
    if available >= duration + 0.08:
        excess = available - duration
        return max(0.70, 1.0 - min(0.30, excess / 18.0))
    clip_remaining = max(
        0.0, float(scene.get("clip_duration", 0.0)) - float(scene.get("start", 0.0))
    )
    if clip_remaining >= duration + 0.03:
        return 0.62
    return max(0.0, clip_remaining / max(0.01, duration) * 0.45)


def _motion_continuity(previous_scene: dict | None, scene: dict) -> float:
    if not previous_scene:
        return 0.0
    a = str(previous_scene.get("motion_direction", "static"))
    b = str(scene.get("motion_direction", "static"))
    if a == b and a != "static":
        return 0.035
    if a == "static" or b == "static":
        return 0.01
    opposite = {"left": "right", "right": "left", "up": "down", "down": "up"}
    if opposite.get(a) == b:
        return -0.05
    return 0.025


def score_scene(
    intent: dict, scene: dict, duration: float,
    clip_use: dict | None = None, recent_clips: list[str] | None = None,
    scene_use: dict | None = None, previous_scene: dict | None = None,
) -> dict:
    clip_use = clip_use or {}
    recent_clips = recent_clips or []
    scene_use = scene_use or {}
    semantic = _semantic_score(intent, scene)
    vision_semantic, target_scores = _vision_semantic_score(intent, scene)
    target = float(intent["target_intensity"])
    intensity = 1.0 - abs(float(scene.get("intensity", 0.5)) - target)
    quality = float(scene.get("quality", 0.5))
    duration_fit = _duration_score(scene, duration)
    has_targets = bool(intent.get("semantic_targets"))

    if has_targets:
        raw = (
            0.46 * vision_semantic
            + 0.27 * semantic
            + 0.10 * intensity
            + 0.09 * quality
            + 0.08 * duration_fit
        )
    else:
        raw = (
            0.52 * semantic
            + 0.18 * intensity
            + 0.17 * quality
            + 0.13 * duration_fit
        )
    penalty = 0.0
    if has_targets:
        req = float(intent.get("required_semantic_score", 0.16))
        required = [t for t in intent.get("semantic_targets", []) if t.get("required")]
        required_scores = [target_scores.get(t["id"], 0.0) for t in required]
        if required_scores and min(required_scores) < req:
            penalty += 0.34 + (req - min(required_scores)) * 1.6
    clip = scene["clip"]
    if recent_clips:
        if clip == recent_clips[-1]:
            penalty += 0.24
        elif clip in recent_clips[-3:]:
            penalty += 0.10
    penalty += min(0.16, clip_use.get(clip, 0) * 0.035)
    penalty += min(0.24, scene_use.get(scene["id"], 0) * 0.16)
    continuity = _motion_continuity(previous_scene, scene)
    final = max(0.0, raw + continuity - penalty)

    return {
        "score": round(final, 5),
        "semantic": round(semantic, 5),
        "vision_semantic": round(vision_semantic, 5),
        "semantic_target_scores": target_scores,
        "intensity": round(intensity, 5),
        "quality": round(quality, 5),
        "duration_fit": round(duration_fit, 5),
        "motion_continuity": round(continuity, 5),
        "penalty": round(penalty, 5),
    }


def escolher_cena(
    intent: dict, inventory: list[dict], duration: float,
    clip_use: dict, recent_clips: list[str], scene_use: dict,
    previous_scene: dict | None = None,
) -> tuple[dict, dict]:
    if not inventory:
        raise ValueError("catalogo visual nao possui cenas elegiveis")
    ranked = []
    for scene in inventory:
        breakdown = score_scene(
            intent, scene, duration, clip_use, recent_clips, scene_use, previous_scene
        )
        ranked.append((breakdown["score"], scene, breakdown))
    ranked.sort(key=lambda x: (-x[0], -x[1].get("quality", 0.0), x[1]["clip"]))
    return ranked[0][1], ranked[0][2]


# Onde, dentro da cena, cada reuso comeca (fracao da folga). O 1o uso fica no centro;
# reusos pegam outro pedaco para o espectador nao ver o mesmo quadro duas vezes.
_POSICOES_REUSO = (0.5, 0.0, 1.0, 0.25, 0.75)


def _source_start(scene: dict, duration: float, uso: int = 0) -> float:
    start = float(scene.get("start", 0.0))
    end = float(scene.get("end", start))
    clip_duration = float(scene.get("clip_duration", end))
    if end - start >= duration + 0.08:
        folga = (end - start) - duration
        src = start + folga * _POSICOES_REUSO[uso % len(_POSICOES_REUSO)]
        src = max(start, min(src, end - duration))
    else:
        src = start
    return round(max(0.0, min(src, max(0.0, clip_duration - duration - 0.01))), 4)


def _merge_required_overlap_targets(
    intent: dict, seg: dict, lyric_lines: list[dict], manifesto: dict,
    all_segments: list[dict],
) -> None:
    """Injeta no intent os alvos semanticos obrigatorios das linhas cantadas
    que cruzam o segmento.

    A cobertura (`_coverage_report`) cobra os alvos `required` de toda linha que
    sobrepoe o segmento. Se o texto usado pelo matcher divergir dessas linhas, o
    matcher escolheria uma cena que a cobertura considera insuficiente. Ao unir
    esses alvos obrigatorios ao intent, `score_scene` passa a penalizar cenas
    que nao respondem ao trecho e a priorizar a melhor cena disponivel para o
    alvo. E generico: usa a mesma logica de sobreposicao e os rotulos do
    manifesto, sem regra especifica de musica/anime.
    """
    try:
        a, b = float(seg.get("start")), float(seg.get("end"))
    except (TypeError, ValueError):
        return
    existing_ids = {t.get("id") for t in intent.get("semantic_targets", [])}
    merged = list(intent.get("semantic_targets", []))
    for line in lyric_lines:
        overlap = max(0.0, min(b, line["end"]) - max(a, line["start"]))
        if overlap <= 0.03:
            continue
        # So assumimos os alvos obrigatorios de uma linha se ESTE segmento e o
        # principal responsavel por ela (maior sobreposicao). Caso contrario, um
        # segmento poderia herdar o alvo de uma linha vizinha e "roubar" a cena,
        # deixando a linha vizinha sem resposta visual. Linhas curtas que
        # cruzam dois segmentos ficam ancoradas no segmento dominante.
        if not _is_primary_segment_for_line(seg, line, all_segments):
            continue
        line_intent = interpretar_texto(
            line["text"], manifesto,
            section=str(line.get("section") or "verse"),
        )
        for target in line_intent.get("semantic_targets", []):
            if not target.get("required"):
                continue
            if target.get("id") in existing_ids:
                continue
            existing_ids.add(target.get("id"))
            merged.append(target)
    if merged and merged != intent.get("semantic_targets", []):
        intent["semantic_targets"] = merged


def _segment_line_overlap(seg: dict, line: dict) -> float:
    try:
        a, b = float(seg.get("start")), float(seg.get("end"))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(b, line["end"]) - max(a, line["start"]))


def _is_primary_segment_for_line(
    seg: dict, line: dict, all_segments: list[dict],
) -> bool:
    """True se `seg` e o segmento com a MAIOR sobreposicao com `line` entre
    todos os segmentos normais da timeline.

    Ancorar cada linha no seu segmento dominante evita que uma linha longa com
    alvo obrigatorio (ex.: Purple) "sequestre" tambem o segmento vizinho, cujo
    dono real e uma linha curta com outro alvo obrigatorio (ex.: Vermelho). A
    cobertura avalia o alvo pela melhor cena entre todos os segmentos que a
    linha cruza, entao basta um segmento por linha responder ao alvo.
    """
    this_overlap = _segment_line_overlap(seg, line)
    if this_overlap <= 0.03:
        return False
    best = this_overlap
    for other in all_segments:
        if other is seg:
            continue
        if str(other.get("type", "")) not in NORMAL_TYPES:
            continue
        ov = _segment_line_overlap(other, line)
        if ov > best:
            best = ov
    return this_overlap >= best - 1e-6


def planejar_timeline(
    projeto_dir: Path, timeline: dict, catalog: dict | None = None,
    manifesto: dict | None = None,
) -> dict:
    projeto_dir = Path(projeto_dir)
    manifesto = manifesto or _read_json(projeto_dir / "projeto.json", {}) or {}
    catalog = catalog or catalogar_projeto(projeto_dir)
    inventory = _scene_inventory(catalog)
    if not inventory:
        raise ValueError("nenhuma cena elegivel no Scene Intelligence")

    output = copy.deepcopy(timeline)
    clip_use, scene_use = {}, {}
    recent_clips = []
    decisions = []
    lyric_lines = _lyric_lines(projeto_dir)
    previous_scene = None

    for idx, seg in enumerate(output.get("segments", [])):
        typ = str(seg.get("type", ""))
        if typ not in NORMAL_TYPES:
            decisions.append({
                "index": idx, "status": "protected",
                "type": typ, "clip": seg.get("clip"),
            })
            previous_scene = None
            continue
        duration = float(seg.get("duration", float(seg["end"]) - float(seg["start"])))
        if duration <= 0.05:
            continue
        text, text_source = _text_for_segment(seg, lyric_lines)
        section = _section_for_segment(seg, lyric_lines)
        intent = interpretar_texto(text, manifesto, tipo=typ, section=section)
        # A cobertura cobra alvos obrigatorios de TODAS as linhas que cruzam o
        # segmento. Se o texto por-segmento (letra sincronizada, as vezes
        # contaminada/mal alinhada) nao trouxe esses alvos, o matcher escolheria
        # uma cena fraca e a cobertura reprovaria. Aqui unimos os alvos
        # obrigatorios das linhas sobrepostas ao intent para que o matcher
        # priorize uma cena que realmente responda ao trecho cantado.
        _merge_required_overlap_targets(
            intent, seg, lyric_lines, manifesto, output.get("segments", [])
        )
        scene, breakdown = escolher_cena(
            intent, inventory, duration, clip_use, recent_clips, scene_use,
            previous_scene=previous_scene,
        )
        src = _source_start(scene, duration, uso=scene_use.get(scene["id"], 0))
        seg["clip"] = scene["clip"]
        seg["src"] = src
        seg["scene_match"] = {
            "engine": "vx_semantic_scene_matcher",
            "scene_id": scene["id"],
            "score": breakdown["score"],
            "semantic_score": breakdown["semantic"],
            "vision_semantic_score": breakdown.get("vision_semantic", 0.0),
            "semantic_targets": intent.get("semantic_targets", []),
            "semantic_target_scores": breakdown.get("semantic_target_scores", {}),
            # Scores de visao reais da cena escolhida para TODOS os rotulos do
            # catalogo. A cobertura usa isto para avaliar alvos obrigatorios
            # mesmo quando o texto por-segmento (letra sincronizada) diverge da
            # linha canonica usada no relatorio de cobertura.
            "scene_semantic_scores": {
                str(k): round(float(v), 5)
                for k, v in (scene.get("semantic_scores") or {}).items()
            },
            "section": intent.get("section", "verse"),
            "intensity_score": breakdown["intensity"],
            "quality_score": breakdown["quality"],
            "motion_continuity": breakdown.get("motion_continuity", 0.0),
            "concepts": intent["concepts"],
            "requested_tags": intent["tag_weights"],
            "scene_tags": scene.get("tags", []),
            "scene_intensity": scene.get("intensity"),
            "target_intensity": intent["target_intensity"],
            "motion_direction": scene.get("motion_direction", "static"),
            "text_source": text_source,
            "lyric_text": text,
        }
        clip_use[scene["clip"]] = clip_use.get(scene["clip"], 0) + 1
        scene_use[scene["id"]] = scene_use.get(scene["id"], 0) + 1
        recent_clips.append(scene["clip"])
        previous_scene = scene
        decisions.append({
            "index": idx, "status": "matched", "type": typ,
            "text": text, "clip": scene["clip"], "src": src,
            "scene_id": scene["id"], **breakdown,
            "concepts": intent["concepts"],
            "scene_tags": scene.get("tags", []),
            "scene_semantic_labels": scene.get("semantic_labels", []),
            "semantic_targets": intent.get("semantic_targets", []),
            "section": intent.get("section", "verse"),
            "text_source": text_source,
        })

    coverage = _coverage_report(lyric_lines, output, manifesto)
    output["scene_intelligence"] = {
        "version": SCHEMA_VERSION,
        "engine": "vx_semantic_scene_matcher",
        "matched_segments": sum(1 for x in decisions if x.get("status") == "matched"),
        "catalog_scenes": len(inventory),
        "lyric_coverage": coverage,
    }
    return {
        "timeline": output,
        "decisions": decisions,
        "catalog": catalog,
        "coverage": coverage,
    }


def _segment_target_score(seg: dict, target_id: str) -> float:
    """Melhor score de visao de um segmento para um alvo semantico.

    Prioriza os scores reais da cena escolhida (`scene_semantic_scores`, que
    cobrem todos os rotulos do catalogo). Caimos para `semantic_target_scores`
    apenas por compatibilidade com estados/planos antigos, garantindo que a
    cobertura nao reprove um alvo obrigatorio so porque o texto por-segmento
    divergiu da linha canonica avaliada aqui.
    """
    match = seg.get("scene_match") or {}
    full = match.get("scene_semantic_scores") or {}
    if target_id in full:
        try:
            return float(full[target_id])
        except (TypeError, ValueError):
            return 0.0
    narrow = match.get("semantic_target_scores") or {}
    try:
        return float(narrow.get(target_id, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _coverage_report(lyric_lines: list[dict], timeline: dict, manifesto: dict) -> dict:
    uncovered = []
    semantic_misses = []
    required_checks = 0
    required_passes = 0
    required_score = float((manifesto.get("scene_semantics") or {}).get("required_score", 0.16))
    segments = timeline.get("segments", [])
    section_counts = {}
    for idx, line in enumerate(lyric_lines):
        section = str(line.get("section") or "verse")
        section_counts[section] = section_counts.get(section, 0) + 1
        matches = []
        for seg in segments:
            overlap = max(0.0, min(float(seg.get("end", 0)), line["end"]) - max(float(seg.get("start", 0)), line["start"]))
            if overlap > 0.03 and seg.get("scene_match"):
                matches.append(seg)
        if not matches:
            uncovered.append({"index": idx, "start": line["start"], "end": line["end"], "text": line["text"]})
            continue
        intent = interpretar_texto(line["text"], manifesto, section=section)
        for target in [x for x in intent.get("semantic_targets", []) if x.get("required")]:
            required_checks += 1
            best = max(_segment_target_score(seg, target["id"]) for seg in matches)
            if best >= required_score:
                required_passes += 1
            else:
                semantic_misses.append({"index": idx, "text": line["text"], "target": target["id"], "score": round(best, 5), "required": required_score})
    return {
        "total_lyric_lines": len(lyric_lines),
        "matched_lyric_lines": len(lyric_lines) - len(uncovered),
        "coverage_ratio": round((len(lyric_lines)-len(uncovered))/max(1, len(lyric_lines)), 5),
        "uncovered_lines": uncovered,
        "required_semantic_checks": required_checks,
        "required_semantic_passes": required_passes,
        "semantic_misses": semantic_misses,
        "sections": section_counts,
    }


def _has_downstream_visuals(timeline: dict) -> bool:
    """Estágios posteriores ao Scene Matcher que alteram a timeline legitimamente."""
    return any(
        s.get("type") in {"vx_cena_ia", "vx_title_card", "vx_end_card", "vx_manga_auto", "vx_graphics_auto"}
        for s in timeline.get("segments", [])
    )


def _has_graphics_auto(timeline: dict) -> bool:
    return any(
        s.get("type") == "vx_graphics_auto"
        for s in timeline.get("segments", [])
    )


def _has_scene_matches(timeline: dict) -> bool:
    return any("scene_match" in s for s in timeline.get("segments", []))


def _base_for_preview(projeto_dir: Path, current: dict) -> dict:
    if not _has_graphics_auto(current):
        return current
    gfx_state = _read_json(
        projeto_dir / "qa" / "vx_graphics_auto" / "state.json", {}
    ) or {}
    base = gfx_state.get("base_timeline")
    return base if isinstance(base, dict) else current


def executar(
    projeto_dir: Path, somente_planejar: bool = False,
    force_catalog: bool = False,
) -> dict:
    projeto_dir = Path(projeto_dir)
    timeline_path = projeto_dir / "timeline.json"
    timeline = _read_json(timeline_path, {}) or {}
    if not timeline.get("segments"):
        raise ValueError("timeline ausente ou vazia")
    manifesto = _read_json(projeto_dir / "projeto.json", {}) or {}

    catalog = catalogar_projeto(projeto_dir, force=force_catalog)
    qa_dir = projeto_dir / "qa" / "scene_matcher"
    plan_path = qa_dir / "plano.json"
    if int(catalog.get("eligible_clips", 0)) <= 0:
        result = {
            "project": projeto_dir.name,
            "status": "skipped_no_eligible_clips",
            "applied": False,
            "matched_segments": 0,
            "catalog": {
                "clips_total": catalog.get("clips_total", 0),
                "eligible_clips": 0,
                "scenes_total": catalog.get("scenes_total", 0),
                "cache": catalog.get("cache", {}),
            },
            "decisions": [],
        }
        _write_json(plan_path, result)
        return result
    catalog_hash = _hash_obj(catalog)
    state_path = qa_dir / "state.json"
    plan_path = qa_dir / "plano.json"
    state = _read_json(state_path, {}) or {}

    if _has_downstream_visuals(timeline) and not somente_planejar:
        result = {
            "project": projeto_dir.name,
            "status": "preserved_after_downstream_visuals",
            "applied": False,
            "reason": (
                "timeline ja contem VX Manga/Graphics Auto; selecao semantica deve "
                "ocorrer antes desses estagios. Regerar timeline-base para reprocessar."
            ),
            "catalog": {
                "clips_total": catalog.get("clips_total", 0),
                "eligible_clips": catalog.get("eligible_clips", 0),
                "scenes_total": catalog.get("scenes_total", 0),
                "cache": catalog.get("cache", {}),
            },
        }
        _write_json(plan_path, result)
        return result

    base = copy.deepcopy(_base_for_preview(projeto_dir, timeline))
    current_hash = _hash_obj(timeline)

    if (
        not somente_planejar
        and _has_scene_matches(timeline)
        and state.get("applied_hash") == current_hash
        and state.get("catalog_hash") == catalog_hash
    ):
        return {
            "project": projeto_dir.name,
            "status": "cached",
            "applied": False,
            "matched_segments": timeline.get("scene_intelligence", {}).get(
                "matched_segments", 0
            ),
            "catalog": {
                "clips_total": catalog.get("clips_total", 0),
                "eligible_clips": catalog.get("eligible_clips", 0),
                "scenes_total": catalog.get("scenes_total", 0),
                "cache": catalog.get("cache", {}),
            },
        }

    if (
        not somente_planejar
        and _has_scene_matches(timeline)
        and state.get("applied_hash") == current_hash
        and isinstance(state.get("base_timeline"), dict)
    ):
        base = copy.deepcopy(state["base_timeline"])
    elif (
        not somente_planejar and _has_scene_matches(timeline)
        and state.get("applied_hash") != current_hash
    ):
        raise RuntimeError(
            "timeline com Scene Matcher foi alterada externamente; "
            "falha fechada para nao sobrescrever edicoes desconhecidas"
        )

    plan = planejar_timeline(
        projeto_dir, base, catalog=catalog, manifesto=manifesto
    )
    public = {
        "project": projeto_dir.name,
        "status": "planned" if somente_planejar else "applied",
        "applied": not somente_planejar,
        "catalog": {
            "clips_total": catalog.get("clips_total", 0),
            "eligible_clips": catalog.get("eligible_clips", 0),
            "scenes_total": catalog.get("scenes_total", 0),
            "cache": catalog.get("cache", {}),
        },
        "matched_segments": plan["timeline"].get(
            "scene_intelligence", {}
        ).get("matched_segments", 0),
        "coverage": plan.get("coverage", {}),
        "decisions": plan["decisions"],
    }
    _write_json(plan_path, public)

    if somente_planejar:
        return public

    strict = bool((manifesto.get("scene_semantics") or {}).get("strict", False))
    coverage = plan.get("coverage", {})
    if strict and coverage.get("uncovered_lines"):
        raise RuntimeError("Scene Matcher: existem linhas cantadas sem resposta visual; veja qa/scene_matcher/plano.json")
    if strict and coverage.get("semantic_misses"):
        misses = coverage.get("semantic_misses", [])[:8]
        detail = "; ".join(f"{m['target']}={m['score']:.3f} :: {m['text']}" for m in misses)
        raise RuntimeError("Scene Matcher: material visual insuficiente para alvos semanticos obrigatorios: " + detail)

    audio_rel = timeline.get("audio") or manifesto.get("audio_fonte")
    if not audio_rel:
        raise ValueError("audio da timeline/manifesto ausente")
    audio_path = Path(audio_rel)
    if not audio_path.is_absolute():
        audio_path = projeto_dir / audio_path

    errors = validar_timeline(
        projeto_dir, plan["timeline"], audio_path, verificar_fontes=True
    )
    if errors:
        raise RuntimeError(
            "timeline reprovada apos Scene Matcher:\n" + "\n".join(errors[:20])
        )

    _write_json(timeline_path, plan["timeline"])
    _write_json(state_path, {
        "schema_version": SCHEMA_VERSION,
        "project": projeto_dir.name,
        "catalog_hash": catalog_hash,
        "base_timeline": base,
        "base_hash": _hash_obj(base),
        "applied_hash": _hash_obj(plan["timeline"]),
        "matched_segments": public["matched_segments"],
    })
    return public


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--planejar", action="store_true")
    parser.add_argument("--force-catalog", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        executar(
            Path(args.project),
            somente_planejar=args.planejar,
            force_catalog=args.force_catalog,
        ),
        ensure_ascii=False, indent=2,
    ))
