#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
transicoes_vfx.py — Transições dinâmicas de AMV / Flow Anime.
Gera filtros complexos de FFmpeg com GPU / NVENC para transições de impacto:
- whip_pan (chicote horizontal / directional blur)
- zoom_in_punch (snap zoom com aceleração de entrada)
- glitch_rgb (separação de canais com aberração cromática rápida)
- flash_cut (corte explosivo com bloom/flash branco de 2 frames)
"""
from pathlib import Path
import json

def gerar_filtro_transicao(tipo: str, t_corte: float, duracao: float = 0.25) -> str:
    """
    Retorna a cadeia de filtros FFmpeg ativada no intervalo [t_corte - duracao/2, t_corte + duracao/2].
    """
    t_ini = round(max(0.0, t_corte - duracao / 2.0), 3)
    t_fim = round(t_corte + duracao / 2.0, 3)
    tempo_rel = f"(t-{t_ini})/{duracao}"
    
    if tipo == "whip_pan":
        # Deslocamento horizontal ultra-rápido simulando puxada de câmera
        return (
            f"split=2[orig_w][blur_w];"
            f"[blur_w]crop=in_w-100:in_h:50+50*sin({tempo_rel}*3.1415):0,scale=1920:1080[panned];"
            f"[orig_w][panned]overlay=enable='between(t,{t_ini},{t_fim})'"
        )
        
    elif tipo == "zoom_in_punch":
        # Snap zoom rápido para dentro e retorno imediato
        zoom_expr = f"1.0+0.35*sin({tempo_rel}*3.1415)"
        return (
            f"split=2[orig_z][layer_z];"
            f"[layer_z]scale=1920*({zoom_expr}):1080*({zoom_expr}):flags=fast_bilinear,"
            f"crop=1920:1080:(in_w-1920)/2:(in_h-1080)/2[zoomed];"
            f"[orig_z][zoomed]overlay=enable='between(t,{t_ini},{t_fim})'"
        )
        
    elif tipo == "glitch_rgb":
        # RGB split e distorção em 3 a 5 frames
        return (
            f"split=2[orig_g][layer_g];"
            f"[layer_g]rgbashift=rh=14:rv=-6:bh=-14:bv=6:gh=0:gv=0[shifted];"
            f"[orig_g][shifted]overlay=enable='between(t,{t_ini},{t_fim})'"
        )
        
    elif tipo == "flash_cut":
        # Flash branco com queda exponencial
        return (
            f"split=2[orig_f][layer_f];"
            f"[layer_f]eq=brightness=0.35:contrast=1.3[flashed];"
            f"[orig_f][flashed]overlay=enable='between(t,{t_ini},{t_fim})'"
        )
        
    return "null"

def compilar_cadeia_transicoes(pontos_corte: list[dict]) -> list[str]:
    """
    Recebe uma lista de cortes [{'tempo': 12.4, 'tipo': 'whip_pan'}, ...]
    e retorna uma lista de filtros FFmpeg prontos para concatenar.
    """
    filtros = []
    for corte in pontos_corte:
        t = corte["tempo"]
        tipo = corte.get("tipo", "whip_pan")
        dur = corte.get("duracao", 0.22)
        f = gerar_filtro_transicao(tipo, t, dur)
        if f != "null":
            filtros.append(f)
    return filtros

if __name__ == "__main__":
    exemplo = [
        {"tempo": 5.4, "tipo": "whip_pan"},
        {"tempo": 10.2, "tipo": "zoom_in_punch"},
        {"tempo": 15.8, "tipo": "glitch_rgb"}
    ]
    filtros = compilar_cadeia_transicoes(exemplo)
    print(f"Cadeia gerada com {len(filtros)} transições.")
    for idx, flt in enumerate(filtros):
        print(f"[{idx+1}] {flt}")
