"""Direção visual declarativa por seção e categoria; não altera a fonte original."""
from __future__ import annotations

import re

import motion_match_director as motion_match

IMPACTO = {"RAGE", "FIGHT", "COMBAT", "ODM_COMBAT", "ROARING", "EXPLOSION",
           "TITAN_FORM", "CHARGE", "CLIMAX", "IMPACT"}


def criar(timeline: dict, transcricao: dict | None = None) -> dict:
    letras = (transcricao or {}).get("segments", [])
    planos = []
    for s in timeline["segments"]:
        categoria = s.get("cat", "").upper()
        # takes gerados ja carregam o proprio movimento de camera
        visual_locked = s.get("type") in {"vx_graphics_auto", "vx_manga_auto", "vx_cena_ia",
                                          "vx_title_card", "vx_end_card"}
        intenso = categoria in IMPACTO and not visual_locked
        linha = s.get("line")
        texto = letras[linha].get("text", "") if isinstance(linha, int) and linha < len(letras) else ""
        palavras = re.findall(r"[\wÀ-ÿ-]+", texto.upper())
        destaque = max(palavras, key=len) if palavras else ""
        planos.append({"start": s["start"], "end": s["end"], "clip": s["clip"],
                       "src": s["src"], "cat": categoria, "line": linha,
                       "type": s.get("type", ""),
                       "scene_match": s.get("scene_match", {}),
                       "preset": ("graphics_locked" if visual_locked else
                                  ("impacto" if intenso else ("respiro" if s["type"] != "lyric" else "narrativo"))),
                       "texto_impacto": destaque if intenso else "",
                       "camera": {"zoom_inicio": 1.0,
                                  "zoom_fim": 1.0 if visual_locked else (1.075 if intenso else 1.025)},
                       "efeitos": [] if visual_locked else (["flash"] if intenso else [])})
    return motion_match.enriquecer_plano(
        {"version": 2, "audio_duration": timeline["audio_duration"], "shots": planos}
    )
