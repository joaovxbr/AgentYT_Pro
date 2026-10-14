#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Motion Match Director — direção de cortes baseada em movimento real.

Não tenta enfeitar todo corte. A prioridade é continuidade invisível:
1) casar direção de movimento quando possível;
2) usar hard cut limpo como padrão;
3) reservar flash/zoom para transições realmente justificadas;
4) nunca aplicar FX extra sobre vx_graphics_auto/graphics_locked.
"""
from __future__ import annotations

from copy import deepcopy

VALID_DIRS = {"left", "right", "up", "down", "static"}
OPPOSITE = {
    "left": "right",
    "right": "left",
    "up": "down",
    "down": "up",
    "static": "static",
}

IMPACT_TAGS = {
    "impact", "fight", "destruction", "electric", "fire",
    "power", "energy", "speed",
}
MOTION_TAGS = {"action", "fight", "speed", "impact", "energy", "destruction"}
PORTRAIT_TAGS = {"portrait", "closeup", "emotional", "center_subject"}


def _scene_meta(shot: dict) -> dict:
    meta = shot.get("scene_match") or {}
    direction = str(
        meta.get("motion_direction")
        or shot.get("motion_direction")
        or "static"
    ).lower()
    if direction not in VALID_DIRS:
        direction = "static"
    tags = set(meta.get("scene_tags") or shot.get("scene_tags") or [])
    try:
        intensity = float(meta.get("scene_intensity", shot.get("scene_intensity", 0.5)))
    except (TypeError, ValueError):
        intensity = 0.5
    return {
        "direction": direction,
        "tags": tags,
        "intensity": max(0.0, min(1.0, intensity)),
    }


def _locked(shot: dict) -> bool:
    return (
        shot.get("preset") == "graphics_locked"
        or shot.get("type") == "vx_graphics_auto"
    )


def _same_motion(a: str, b: str) -> bool:
    return a != "static" and a == b


def _portrait_pair(tags_a: set[str], tags_b: set[str]) -> bool:
    return bool(tags_a & PORTRAIT_TAGS) and bool(tags_b & PORTRAIT_TAGS)


def _impact_pair(tags_a: set[str], tags_b: set[str], intensity: float) -> bool:
    return intensity >= 0.70 and bool((tags_a | tags_b) & IMPACT_TAGS)


def decidir_transicao(
    prev_shot: dict,
    next_shot: dict,
    last_fx_time: float = -999.0,
    drops_grave: list[float] | None = None,
) -> dict:
    """Escolhe a linguagem do corte entre dois shots."""
    boundary = float(prev_shot.get("end", next_shot.get("start", 0.0)))

    if _locked(prev_shot) or _locked(next_shot):
        return {
            "type": "hard_cut",
            "direction": "static",
            "duration": 0.0,
            "strength": 0.0,
            "reason": "graphics_locked",
            "boundary": boundary,
        }

    a = _scene_meta(prev_shot)
    b = _scene_meta(next_shot)
    avg_intensity = (a["intensity"] + b["intensity"]) / 2.0
    same = _same_motion(a["direction"], b["direction"])
    opposite = (
        a["direction"] != "static"
        and b["direction"] == OPPOSITE.get(a["direction"])
    )

    # Detecção de drop de grave 808/kick alinhado ao corte
    if drops_grave:
        tem_drop_grave = any(abs(d - boundary) <= 0.14 for d in drops_grave)
        if tem_drop_grave and (
            avg_intensity >= 0.60
            or b["intensity"] >= 0.70
            or bool((a["tags"] | b["tags"]) & IMPACT_TAGS)
        ):
            return {
                "type": "snap_impact",
                "direction": a["direction"] if a["direction"] != "static" else b["direction"],
                "duration": 0.12,
                "strength": round(min(0.95, 0.70 + 0.20 * avg_intensity), 3),
                "reason": "bass_drop_808",
                "boundary": boundary,
            }

    motion_relevant = bool((a["tags"] | b["tags"]) & MOTION_TAGS)
    if same and motion_relevant and avg_intensity >= 0.58:
        return {
            "type": "match_cut",
            "direction": a["direction"],
            "duration": 0.0,
            "strength": round(0.58 + 0.24 * avg_intensity, 3),
            "reason": "same_motion_direction_high_energy",
            "boundary": boundary,
        }

    close_pair = "closeup" in a["tags"] and "closeup" in b["tags"]
    if close_pair and avg_intensity <= 0.58:
        return {
            "type": "zoom_match",
            "direction": "static",
            "duration": 0.0,
            "strength": 0.42,
            "reason": "portrait_to_portrait",
            "boundary": boundary,
        }

    cooldown_ok = boundary - last_fx_time >= 5.5
    if cooldown_ok and _impact_pair(a["tags"], b["tags"], avg_intensity):
        strength = 0.56 + (0.16 if opposite else 0.0)
        return {
            "type": "flash_cut",
            "direction": a["direction"] if a["direction"] != "static" else b["direction"],
            "duration": 0.075 if avg_intensity < 0.86 else 0.10,
            "strength": round(min(0.78, strength), 3),
            "reason": "impact_bridge_opposite_motion" if opposite else "impact_bridge",
            "boundary": boundary,
        }

    return {
        "type": "hard_cut",
        "direction": "static",
        "duration": 0.0,
        "strength": 0.0,
        "reason": "clean_cut_default",
        "boundary": boundary,
    }


def _align_camera(shot: dict, direction: str, role: str, transition_type: str) -> None:
    cam = shot.setdefault("camera", {})
    if direction in VALID_DIRS and direction != "static":
        cam["pan"] = direction
        cam["motion_match"] = True

    z0 = float(cam.get("zoom_inicio", 1.0))
    z1 = float(cam.get("zoom_fim", 1.025))
    if transition_type == "match_cut":
        if role == "out":
            cam["zoom_fim"] = round(max(z1, z0 + 0.022), 4)
        else:
            cam["zoom_inicio"] = round(max(1.0, min(z0, 1.018)), 4)
    elif transition_type == "flash_cut":
        if role == "out":
            cam["zoom_fim"] = round(max(z1, z0 + 0.035), 4)
    elif transition_type == "snap_impact":
        cam["motion_match"] = True
        if role == "out":
            cam["zoom_fim"] = round(max(z1, z0 + 0.040), 4)
        else:
            cam["zoom_inicio"] = 1.15
            cam["zoom_fim"] = round(max(1.0, min(z1, 1.025)), 4)


def _zoom_match(prev_shot: dict, next_shot: dict) -> None:
    a = prev_shot.setdefault("camera", {})
    b = next_shot.setdefault("camera", {})
    a0 = float(a.get("zoom_inicio", 1.0))
    a["zoom_fim"] = round(max(float(a.get("zoom_fim", 1.025)), a0 + 0.035), 4)
    b["zoom_inicio"] = 1.035
    b["zoom_fim"] = round(max(1.0, float(b.get("zoom_fim", 1.02))), 4)
    a["motion_match"] = True
    b["motion_match"] = True


def enriquecer_plano(plano: dict, drops_grave: list[float] | None = None) -> dict:
    out = deepcopy(plano)
    shots = out.get("shots", [])
    transitions = []
    last_fx_time = -999.0

    for shot in shots:
        shot.setdefault("transition_in", {"type": "none"})
        shot.setdefault("transition_out", {"type": "none"})

    for i in range(len(shots) - 1):
        prev_shot, next_shot = shots[i], shots[i + 1]
        tr = decidir_transicao(prev_shot, next_shot, last_fx_time, drops_grave=drops_grave)

        prev_shot["transition_out"] = {
            "type": tr["type"],
            "duration": tr["duration"],
            "strength": tr["strength"],
            "direction": tr["direction"],
            "reason": tr["reason"],
        }
        next_shot["transition_in"] = {
            "type": tr["type"],
            "duration": tr["duration"],
            "strength": tr["strength"],
            "direction": tr["direction"],
            "reason": tr["reason"],
        }

        if tr["type"] == "match_cut":
            # O movimento deve vir do próprio material, não de pan artificial.
            # Apenas registramos o match; a câmera original continua limpa.
            pass
        elif tr["type"] == "zoom_match":
            _zoom_match(prev_shot, next_shot)
        elif tr["type"] == "flash_cut":
            _align_camera(prev_shot, tr["direction"], "out", tr["type"])
            last_fx_time = tr["boundary"]
        elif tr["type"] == "snap_impact":
            _align_camera(prev_shot, tr["direction"], "out", tr["type"])
            _align_camera(next_shot, tr["direction"], "in", tr["type"])
            last_fx_time = tr["boundary"]

        transitions.append(tr)

    out["motion_match"] = {
        "version": 1,
        "engine": "vx_motion_match_director",
        "transitions": transitions,
        "counts": {
            name: sum(1 for x in transitions if x["type"] == name)
            for name in ("match_cut", "zoom_match", "flash_cut", "snap_impact", "hard_cut")
        },
        "philosophy": "clean_cuts_first_effects_only_when_justified",
    }
    return out
