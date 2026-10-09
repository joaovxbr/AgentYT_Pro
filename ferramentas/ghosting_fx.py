#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ghosting_fx.py — Efeito de Eco Visual / Frame Ghosting Cinemático.
Baseado no efeito visto aos 35s do vídeo de referência:
Cria uma sobreposição temporal de frames defasados (ghost trails) com desfoque e baixa opacidade,
transmitindo sensação de transe, vertigem ou impacto rítmico pesado.
"""
from pathlib import Path
import sys

def gerar_filtro_ghosting(t_inicio: float, duracao: float = 1.5, num_ecos: int = 2) -> str:
    """
    Retorna a cadeia de filtros FFmpeg que gera cópias defasadas temporalmente via lagfun / tmix.
    """
    t_fim = round(t_inicio + duracao, 3)
    
    # O filtro lagfun do FFmpeg gera o rastro / eco visual de frames passados
    # decay=0.82 cria um eco visível que se dissipa suavemente
    filtro = (
        f"split=2[base_g][echo_layer];"
        f"[echo_layer]lagfun=decay=0.85[ghosted];"
        f"[base_g][ghosted]blend=all_mode='screen':all_opacity=0.6:enable='between(t,{t_inicio:.3f},{t_fim:.3f})'"
    )
    return filtro

if __name__ == "__main__":
    t = float(sys.argv[1]) if len(sys.argv) > 1 else 35.0
    print(gerar_filtro_ghosting(t))
