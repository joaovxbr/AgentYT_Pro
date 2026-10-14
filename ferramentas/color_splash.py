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
    "vermelho": {"color": "red", "similarity": 0.22, "blend": 0.05},
    "carmesim": {"color": "0x8B0000", "similarity": 0.25, "blend": 0.05},
    "azul_ciano": {"color": "0x00D0FF", "similarity": 0.22, "blend": 0.05},
    "verde": {"color": "0x00FF00", "similarity": 0.22, "blend": 0.05},
    "amarelo": {"color": "0xFFD700", "similarity": 0.22, "blend": 0.05},
    "roxo": {"color": "0x9900FF", "similarity": 0.22, "blend": 0.05},
}


def gerar_filtro_color_splash(
    cor: str = "vermelho",
    t_inicio: float = 0.0,
    duracao: float = 2.0,
    contraste: float = 1.30,
) -> str:
    """Gera filtro FFmpeg que isola a cor selecionada via chromahold e converte o restante para PB.

    Totalmente compatível com pipeline linear (-vf) e aceleração por hardware (NVENC).
    """
    t_fim = t_inicio + duracao
    cfg = CORES_SPLASH.get(cor, CORES_SPLASH["vermelho"])
    c = cfg["color"]
    sim = cfg["similarity"]
    blend = cfg["blend"]

    filtro = (
        f"chromahold=color={c}:similarity={sim}:blend={blend}:"
        f"enable='between(t,{t_inicio:.3f},{t_fim:.3f})',"
        f"eq=contrast={contraste:.2f}:enable='between(t,{t_inicio:.3f},{t_fim:.3f})'"
    )
    return filtro

if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "vermelho"
    print(gerar_filtro_color_splash(c, 5.0, 3.0))
