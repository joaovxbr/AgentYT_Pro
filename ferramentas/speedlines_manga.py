#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
speedlines_manga.py — Geração de Linhas de Ação e Speedlines procedurais de Mangá.
Cria flashes de linhas de velocidade radiais ou horizontais para transmitir aceleração
máxima, golpes de espada ou esquivas supersônicas em animes.
"""
from pathlib import Path
import math
import random
from PIL import Image, ImageDraw

def gerar_textura_speedlines_radial(
    largura: int = 1920,
    altura: int = 1080,
    linhas_totais: int = 140,
    cor_linha: str = "#FFFFFF",
    opacidade: int = 160
) -> Image.Image:
    """
    Gera um overlay transparente de linhas radiais convergindo para o centro (estilo impacto shonen).
    """
    canvas = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    cx, cy = largura // 2, altura // 2
    raio_max = math.hypot(cx, cy)
    raio_min = int(largura * 0.18) # Deixa o centro/rosto limpo

    rgba_cor = (255, 255, 255, opacidade)

    for _ in range(linhas_totais):
        angulo = random.uniform(0, 2 * math.pi)
        comprimento = random.uniform(raio_min, raio_max)
        espessura = random.randint(2, 6)

        x1 = cx + math.cos(angulo) * random.uniform(raio_min, raio_min * 1.5)
        y1 = cy + math.sin(angulo) * random.uniform(raio_min, raio_min * 1.5)

        x2 = cx + math.cos(angulo) * (comprimento + 200)
        y2 = cy + math.sin(angulo) * (comprimento + 200)

        draw.line([(x1, y1), (x2, y2)], fill=rgba_cor, width=espessura)

    return canvas

def gerar_pacote_speedlines_animadas(pasta_saida: Path, quantidade_frames: int = 6) -> list[Path]:
    """
    Gera múltiplos frames aleatórios de speedlines para criar efeito de animação a 30fps.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i in range(quantidade_frames):
        img = gerar_textura_speedlines_radial()
        p = pasta_saida / f"speedline_{i:02d}.png"
        img.save(p, "PNG")
        caminhos.append(p)
    return caminhos

if __name__ == "__main__":
    out_dir = Path("teste_speedlines")
    frames = gerar_pacote_speedlines_animadas(out_dir)
    print(f"Sucesso: gerados {len(frames)} frames de speedlines em {out_dir}")
