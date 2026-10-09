#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
color_splash.py — Efeito de Desaturação Seletiva / Color Splash (Estilo Sin City / Anime Dark).
Converte todo o vídeo para preto e branco de alto contraste, mas preserva UMA cor isolada:
- vermelho: Sangue, olhos do Sharingan, manto da Akatsuki
- verde: Olhos do Eren Titã, chamas esmeralda
- azul/ciano: Olhos do Gojo, Modo Sábio, energia do Jin-Woo
- amarelo/dourado: Auras de Super Saiyajin, faíscas de raio
"""
from pathlib import Path
import sys

CORES_SPLASH = {
    "vermelho": {"chave_u": "128", "chave_v": "210", "tolerancia": "0.18"},
    "azul_ciano": {"chave_u": "200", "chave_v": "100", "tolerancia": "0.16"},
    "verde": {"chave_u": "90", "chave_v": "90", "tolerancia": "0.15"},
    "amarelo": {"chave_u": "75", "chave_v": "160", "tolerancia": "0.17"}
}

def gerar_filtro_color_splash(
    cor: str = "vermelho",
    t_inicio: float = 0.0,
    duracao: float = 2.0
) -> str:
    """
    Gera filtro FFmpeg que isola a cor selecionada e converte o restante para PB de alto contraste.
    """
    t_fim = t_inicio + duracao
    cfg = CORES_SPLASH.get(cor, CORES_SPLASH["vermelho"])
    
    # Isola o matiz cromático e mescla com a versão PB
    filtro = (
        f"split=2[color_orig][bw_layer];"
        f"[bw_layer]hue=s=0,eq=contrast=1.35:brightness=-0.04[monocromo];"
        f"[color_orig]colorkey=color=0x{cor[:2]}0000:similarity=0.3:blend=0.1[mask_color];"
        f"[monocromo][color_orig]overlay=enable='between(t,{t_inicio:.3f},{t_fim:.3f})'"
    )
    return filtro

if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "vermelho"
    print(gerar_filtro_color_splash(c, 5.0, 3.0))
