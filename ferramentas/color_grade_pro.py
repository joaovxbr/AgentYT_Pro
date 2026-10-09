#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
color_grade_pro.py — Sistema de LUTs e Color Grading Cinemático Dinâmico para Anime AMVs.
Aplica receitas de cor adaptadas para cada arquétipo de anime:
- cursed_energy (Jujutsu / Sukuna): Azul profundo + tons vermelhos de sangue saturados
- titan_fire (Attack on Titan / Eren): Âmbar alaranjado, alto contraste e vinheta quente
- dark_shadow (Solo Leveling / Jin-Woo): Tons frios, roxo monarca, ciano luminoso nos olhos
- demon_blood (Kimetsu / Akaza): Magenta, sombras escuras e picos de iluminação dramática
"""
from pathlib import Path

RECEITAS_COLOR_GRADE = {
    "cursed_energy": {
        "eq": "contrast=1.28:brightness=-0.03:saturation=1.45",
        "curves": "red='0/0 0.25/0.20 0.5/0.55 1/1':blue='0/0 0.3/0.38 0.7/0.78 1/0.95'",
        "vignette": "0.75"
    },
    "titan_fire": {
        "eq": "contrast=1.32:brightness=0.01:saturation=1.38",
        "curves": "red='0/0 0.4/0.50 0.8/0.88 1/1':green='0/0 0.5/0.48 1/0.92':blue='0/0 0.5/0.40 1/0.80'",
        "vignette": "0.70"
    },
    "dark_shadow": {
        "eq": "contrast=1.38:brightness=-0.04:saturation=1.20",
        "curves": "blue='0/0 0.25/0.32 0.6/0.75 1/0.95':red='0/0 0.25/0.18 0.6/0.50 1/0.92':green='0/0 0.5/0.45 1/0.90'",
        "vignette": "0.72"
    },
    "demon_blood": {
        "eq": "contrast=1.30:brightness=-0.02:saturation=1.50",
        "curves": "red='0/0 0.3/0.35 0.7/0.82 1/1':blue='0/0 0.4/0.45 0.8/0.85 1/0.90'",
        "vignette": "0.72"
    },
    "cinematic_clean": {
        "eq": "contrast=1.22:brightness=0.0:saturation=1.25",
        "curves": "red='0/0 0.5/0.52 1/1':blue='0/0 0.5/0.49 1/0.98'",
        "vignette": "0.85"
    }
}

def obter_filtro_color_grade(estilo: str = "cinematic_clean") -> str:
    """
    Retorna a string de filtros FFmpeg para o color grading desejado.
    """
    rec = RECEITAS_COLOR_GRADE.get(estilo, RECEITAS_COLOR_GRADE["cinematic_clean"])
    filtros = [
        f"eq={rec['eq']}",
        f"curves={rec['curves']}",
        f"vignette=angle={rec['vignette']}"
    ]
    return ",".join(filtros)

if __name__ == "__main__":
    import sys
    estilo = sys.argv[1] if len(sys.argv) > 1 else "titan_fire"
    print(f"Filtro para [{estilo}]:\n{obter_filtro_color_grade(estilo)}")
