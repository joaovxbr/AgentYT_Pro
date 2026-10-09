#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
neon_overlay_fx.py — Motion Graphics de Neon Reativo à Letra (Overlay Cinematográfico).
Gera camadas visuais espetaculares sincronizadas com cada palavra/verso da música:

1. Traços de neon que "riscam" a cena acompanhando o flow da voz (light streaks)
2. Molduras / underline de neon glow por baixo das palavras destacadas
3. Partículas de energia que emanam da palavra atual
4. Pulsos de brilho (glow flash) sincronizados com onsets de palavra
5. Assinatura de energia (waveform / squiggle) desenhando conforme o MC canta

Tudo gerado como sequência PNG RGBA (canal alfa) para overlay em modo screen/add
sobre o vídeo, sem cobrir o personagem — apenas realça a cena como motion graphics.
"""
from pathlib import Path
import json
import math
import random
from PIL import Image, ImageDraw, ImageFilter

FONTE_IMPACTO = Path("C:/Windows/Fonts/impact.ttf")


def _cor_hex_para_rgb(cor_hex: str) -> tuple:
    h = cor_hex.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def desenhar_traco_neon(
    draw: ImageDraw.ImageDraw,
    x1: int, y1: int, x2: int, y2: int,
    cor: tuple,
    espessura: int = 6,
    segmentos: int = 12
):
    """Desenha um traço de neon com leve tremor orgânico (como caneta luminosa)."""
    pts = []
    for i in range(segmentos + 1):
        t = i / segmentos
        px = x1 + (x2 - x1) * t
        py = y1 + (y2 - y1) * t
        # tremor perpendicular pequeno
        jitter = math.sin(t * math.pi * 3) * 4
        pts.append((px, py + jitter))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i+1]], fill=(*cor, 255), width=espessura)


def gerar_frame_neon(
    largura: int,
    altura: int,
    progresso: float,
    cor: tuple,
    modo: str = "underline",
    palavra_x: int = 960,
    palavra_y: int = 900,
    palavra_w: int = 300,
    intensidade: float = 1.0
) -> Image.Image:
    """
    Gera um frame de overlay neon RGBA transparente.
    progresso: 0.0 a 1.0 (o quanto do efeito ja foi desenhado)
    modo: 'underline', 'streak', 'particles', 'pulse', 'corner_frame'
    """
    canvas = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    if modo == "underline":
        # Linha de neon que se desenha por baixo da palavra atual
        y = palavra_y + 70
        x_ini = palavra_x - palavra_w // 2
        x_fim_total = palavra_x + palavra_w // 2
        x_fim = int(x_ini + (x_fim_total - x_ini) * progresso)
        if x_fim > x_ini:
            draw.line([(x_ini, y), (x_fim, y)], fill=(*cor, 255), width=8)
            # ponto de energia na ponta
            draw.ellipse([x_fim - 8, y - 8, x_fim + 8, y + 8], fill=(255, 255, 255, 255))

    elif modo == "streak":
        # Traços de luz diagonais atravessando a cena (velocidade)
        n = int(6 * intensidade)
        for i in range(n):
            base_y = (i / max(1, n)) * altura
            x_start = int(-200 + (largura + 400) * progresso)
            desenhar_traco_neon(draw, x_start, int(base_y), x_start + 250, int(base_y + 60), cor, espessura=5)

    elif modo == "corner_frame":
        # Molduras de canto estilo HUD futurista
        m = 60
        comp = int(220 * progresso)
        # canto superior esquerdo
        draw.line([(m, m), (m + comp, m)], fill=(*cor, 255), width=6)
        draw.line([(m, m), (m, m + comp)], fill=(*cor, 255), width=6)
        # canto inferior direito
        draw.line([(largura - m, altura - m), (largura - m - comp, altura - m)], fill=(*cor, 255), width=6)
        draw.line([(largura - m, altura - m), (largura - m, altura - m - comp)], fill=(*cor, 255), width=6)

    elif modo == "particles":
        # Partículas de energia emanando da palavra
        n = int(25 * intensidade)
        for _ in range(n):
            ang = random.uniform(0, 2 * math.pi)
            dist = random.uniform(20, 120) * progresso
            px = palavra_x + math.cos(ang) * dist
            py = palavra_y + math.sin(ang) * dist
            r = random.randint(2, 5)
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(*cor, random.randint(140, 240)))

    elif modo == "pulse":
        # Anel de pulso de energia expandindo
        raio = int(200 * progresso)
        alpha = int(max(0, 220 * (1.0 - progresso)))
        if raio > 5:
            draw.ellipse([palavra_x - raio, palavra_y - raio, palavra_x + raio, palavra_y + raio],
                         outline=(*cor, alpha), width=6)

    # Aplica glow (desfoque somado à camada original)
    glow = canvas.filter(ImageFilter.GaussianBlur(10))
    resultado = Image.alpha_composite(glow, canvas)
    return resultado


def gerar_sequencia_neon_para_verso(
    pasta_saida: Path,
    duracao_s: float,
    cor_hex: str = "#00E5FF",
    modo: str = "underline",
    palavra_x: int = 960,
    palavra_y: int = 900,
    palavra_w: int = 400,
    fps: int = 30
) -> list[Path]:
    """
    Gera a sequência de frames PNG do efeito neon para uma palavra/verso.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)
    cor = _cor_hex_para_rgb(cor_hex)
    total_frames = max(1, int(duracao_s * fps))
    caminhos = []

    for f in range(total_frames):
        prog = min(1.0, (f / max(1, total_frames - 1)) * 1.5)  # desenha rápido nos primeiros 2/3
        intensidade = 1.0
        frame = gerar_frame_neon(1920, 1080, prog, cor, modo=modo,
                                 palavra_x=palavra_x, palavra_y=palavra_y,
                                 palavra_w=palavra_w, intensidade=intensidade)
        out = pasta_saida / f"neon_{f:04d}.png"
        frame.save(out, "PNG")
        caminhos.append(out)

    return caminhos


if __name__ == "__main__":
    import sys
    modo = sys.argv[1] if len(sys.argv) > 1 else "underline"
    out_dir = Path(f"teste_neon_{modo}")
    frames = gerar_sequencia_neon_para_verso(out_dir, 1.5, modo=modo)
    print(f"Gerados {len(frames)} frames de neon '{modo}' em {out_dir}")
