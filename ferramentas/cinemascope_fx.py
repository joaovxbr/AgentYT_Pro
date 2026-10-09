#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cinemascope_fx.py — Letterbox Cinematográfico Dinâmico (Proporção 2.39:1 / Anamórfico).
Adiciona barras pretas cinematográficas com transições dinâmicas:
- Abertura de cortina / barra expandindo na intro
- Pulsos de abertura nos refrões e drops
- Suporte a efeito "Pop-Out" 3D
"""
from pathlib import Path

def gerar_filtro_cinemascope(altura_barra: int = 140, animacao_intro: bool = True, dur_intro: float = 3.0) -> str:
    """
    Gera expressão FFmpeg para criar barras de cinemascope superior e inferior.
    Em 1920x1080, barras de 140px deixam a área útil em 1920x800 (proporção exata 2.40:1).
    """
    if animacao_intro:
        # As barras descem suavemente nos primeiros 'dur_intro' segundos
        t_expr = f"min(1.0,t/{dur_intro:.2f})"
        h_expr = f"trunc({altura_barra}*{t_expr})"
        # drawbox superior e inferior
        filtro = (
            f"drawbox=x=0:y=0:w=iw:h='{h_expr}':color=black:t=fill,"
            f"drawbox=x=0:y='ih-{h_expr}':w=iw:h='{h_expr}':color=black:t=fill"
        )
    else:
        filtro = (
            f"drawbox=x=0:y=0:w=iw:h={altura_barra}:color=black:t=fill,"
            f"drawbox=x=0:y=ih-{altura_barra}:w=iw:h={altura_barra}:color=black:t=fill"
        )
    return filtro

if __name__ == "__main__":
    print(gerar_filtro_cinemascope(140, animacao_intro=True))
