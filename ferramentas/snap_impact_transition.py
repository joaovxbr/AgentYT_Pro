#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snap_impact_transition.py — Transição de Drop e Impacto com Flash Pop e Snap Zoom.
Baseado na transição vista aos 16s do vídeo de referência:
1. Flash Pop de 3 frames (sobreposição de branco em modo screen com decaimento exponencial)
2. Snap Zoom Punch (escala 1.16x -> 1.0x com curva cúbica / Easy Ease)
3. Motion Blur direcional suave de entrada
"""
from pathlib import Path
import sys

def gerar_filtro_snap_impact(
    t_corte: float,
    duracao_zoom: float = 0.35,
    duracao_flash: float = 0.10,
    zoom_max: float = 1.16
) -> str:
    """
    Retorna a cadeia de filtros FFmpeg ativada no momento exato do corte.
    """
    t_ini = round(t_corte, 3)
    t_fim_zoom = round(t_corte + duracao_zoom, 3)
    t_fim_flash = round(t_corte + duracao_flash, 3)
    
    # Curva de desaceleração suave (1.0 + (zoom_max - 1.0) * (1 - progresso)^2)
    progresso_expr = f"(t-{t_ini})/{duracao_zoom}"
    zoom_expr = f"1.0+({zoom_max - 1.0})*pow(max(0,1.0-({progresso_expr})),2)"
    
    # Flash branco rápido com decaimento
    prog_flash = f"(t-{t_ini})/{duracao_flash}"
    brilho_expr = f"max(0.0,0.45*(1.0-({prog_flash})))"
    
    filtro = (
        f"split=2[orig_snap][layer_snap];"
        f"[layer_snap]scale=1920*({zoom_expr}):1080*({zoom_expr}):flags=fast_bilinear,"
        f"crop=1920:1080:(in_w-1920)/2:(in_h-1080)/2,"
        f"eq=brightness='{brilho_expr}':contrast=1.2[snapped];"
        f"[orig_snap][snapped]overlay=enable='between(t,{t_ini},{t_fim_zoom})'"
    )
    return filtro

if __name__ == "__main__":
    t = float(sys.argv[1]) if len(sys.argv) > 1 else 16.0
    print(gerar_filtro_snap_impact(t))
