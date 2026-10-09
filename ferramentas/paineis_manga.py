#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paineis_manga.py — Efeito Split-Screen Dinâmico em Painéis de Quadrinho / Mangá Japonês.
Divide a tela em múltiplos quadros simultâneos com bordas pretas espessas e linhas de corte:
- Modo 2_paineis_v: Divisão vertical esquerda/direita (ex: close no olhar + golpe do titã)
- Modo 2_paineis_h: Divisão horizontal topo/base (ex: olhos em close em cima + marcha do exército embaixo)
- Modo 3_paineis_shonen: Painel diagonal estilo página de mangá de ação
"""
from pathlib import Path
import sys

def mascaras_diagonais(w, h, progresso, borda=12):
    """Two moving polygon panels, separated by a real diagonal gutter."""
    import numpy as np
    y,x=np.mgrid[:h,:w]
    boundary=w*(.42+.14*progresso)+(y-h/2)*.32
    return ((x<boundary-borda/2)*255).astype('uint8'), ((x>boundary+borda/2)*255).astype('uint8')


def mascaras_3_paineis(w, h, progresso, borda=12):
    """Three moving polygon panels, separated by two diagonal gutters."""
    import numpy as np
    y, x = np.mgrid[:h, :w]
    b1 = w * (0.28 + 0.10 * progresso) + (y - h / 2) * 0.28
    b2 = w * (0.62 + 0.10 * progresso) + (y - h / 2) * 0.28
    m1 = ((x < b1 - borda / 2) * 255).astype('uint8')
    m2 = (((x > b1 + borda / 2) & (x < b2 - borda / 2)) * 255).astype('uint8')
    m3 = ((x > b2 + borda / 2) * 255).astype('uint8')
    return m1, m2, m3


def gerar_filtro_paineis_manga(
    modo: str = "2_paineis_h",
    espessura_borda: int = 12,
    cor_borda: str = "black"
) -> str:
    """
    Retorna o filtro FFmpeg para compor 2 vídeos diferentes em painéis de mangá estilizados.
    """
    if modo == "2_paineis_h":
        # Divide em 1920x540 topo e 1920x540 base com linha divisória de mangá
        h_metade = 540 - (espessura_borda // 2)
        filtro = (
            f"[0:v]scale=1920:1080:flags=fast_bilinear,crop=1920:{h_metade}:0:0[topo];"
            f"[1:v]scale=1920:1080:flags=fast_bilinear,crop=1920:{h_metade}:0:1080-{h_metade}[base];"
            f"[topo][base]vstack=inputs=2[stacked];"
            f"[stacked]pad=1920:1080:0:0:{cor_borda}[paineis]"
        )
    elif modo == "2_paineis_v":
        # Divide em 960x1080 esquerda e 960x1080 direita
        w_metade = 960 - (espessura_borda // 2)
        filtro = (
            f"[0:v]scale=1920:1080:flags=fast_bilinear,crop={w_metade}:1080:(1920-{w_metade})/2:0[esq];"
            f"[1:v]scale=1920:1080:flags=fast_bilinear,crop={w_metade}:1080:(1920-{w_metade})/2:0[dir];"
            f"[esq][dir]hstack=inputs=2[stacked];"
            f"[stacked]pad=1920:1080:0:0:{cor_borda}[paineis]"
        )
    else:
        # Fallback simples
        filtro = "[0:v]null[paineis]"

    return filtro

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "2_paineis_h"
    print(gerar_filtro_paineis_manga(modo))
