#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pixel_sort_glitch.py — Transição de Datamosh / Pixel Sort Glitch de Alto Impacto.
Arrasta e distorce os pixels ao longo de vetores horizontais durante 3 a 5 frames
no momento exato do impacto ou corte de espada.
"""
from pathlib import Path
import sys

def gerar_filtro_pixel_sort_glitch(
    t_corte: float,
    duracao: float = 0.18,
    intensidade_pixels: int = 40
) -> str:
    """
    Retorna filtro FFmpeg que aplica pixel sorting e deslocamento de linhas nos frames do corte.
    """
    t_ini = round(t_corte, 3)
    t_fim = round(t_corte + duracao, 3)
    
    # Usa frei0r ou combinação nativa de displace/shear para simular o pixel sort
    filtro = (
        f"split=2[orig_px][layer_px];"
        f"[layer_px]rgbashift=rh={intensidade_pixels}:rv=0:bh=-{intensidade_pixels}:bv=0,"
        f"frei0r=filter_name=glitch0r:filter_params=0.8|0.9|0.5[sorted];"
        f"[orig_px][sorted]overlay=enable='between(t,{t_ini},{t_fim})'"
    )
    # Versão 100% nativa sem dependência de frei0r caso não esteja compilado:
    filtro_nativo = (
        f"split=2[orig_px][layer_px];"
        f"[layer_px]rgbashift=rh={intensidade_pixels}:rv=-4:bh=-{intensidade_pixels}:bv=4,"
        f"boxblur=luma_radius=12:luma_power=1:chroma_radius=0[sorted];"
        f"[orig_px][sorted]overlay=enable='between(t,{t_ini},{t_fim})'"
    )
    return filtro_nativo

if __name__ == "__main__":
    t = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    print(gerar_filtro_pixel_sort_glitch(t))
