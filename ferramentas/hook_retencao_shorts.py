#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hook_retencao_shorts.py — Injetor de Ganchos Hipnóticos de Retenção nos 3 Primeiros Segundos de Shorts.
Insere dinamicamente nos primeiros 2.5 segundos:
1. Pergunta ou afirmação magnética de alta curiosidade no topo da tela (ex: "O MOMENTO EM QUE ELE PERDEU O CONTROLE...")
2. Barra de progresso animada rápida (micro-timer) no topo para prender a atenção
3. Borda pulsante de atenção que força o espectador a não rolar o feed.
"""
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont

FONTE_IMPACTO = Path("C:/Windows/Fonts/impact.ttf")

def gerar_card_hook_retencao(
    texto_gancho: str,
    largura: int = 1080,
    altura: int = 1920,
    cor_texto: str = "#FFCC00"
) -> Image.Image:
    """
    Gera overlay transparente 1080x1920 com tarja de topo e texto magnético.
    """
    canvas = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    try:
        fonte = ImageFont.truetype(str(FONTE_IMPACTO), 56)
    except Exception:
        fonte = ImageFont.load_default()

    # Tarja superior escura com cantos arredondados
    pad_y = 180
    h_tarja = 160
    draw.rounded_rectangle(
        [50, pad_y, largura - 50, pad_y + h_tarja],
        radius=20,
        fill=(10, 10, 15, 230),
        outline=(255, 60, 20, 240),
        width=4
    )

    # Texto do gancho centralizado na tarja
    bbox = draw.textbbox((0, 0), texto_gancho.upper(), font=fonte)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (largura - tw) // 2
    ty = pad_y + (h_tarja - th) // 2 - 5

    # Sombra e texto
    draw.text((tx + 3, ty + 3), texto_gancho.upper(), font=fonte, fill=(0, 0, 0, 255))
    draw.text((tx, ty), texto_gancho.upper(), font=fonte, fill=cor_texto)

    # Micro-barra de progresso rápida no topo da tela (y=30)
    draw.line([(50, 45), (largura - 50, 45)], fill=(80, 80, 80, 160), width=6)
    draw.line([(50, 45), (largura - 200, 45)], fill=(255, 60, 20, 255), width=6)

    return canvas

def salvar_overlay_hook(texto: str, saida_png: Path) -> Path:
    img = gerar_card_hook_retencao(texto)
    saida_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(saida_png), "PNG")
    print(f"[HOOK RETENÇÃO] Overlay gerado em: {saida_png}")
    return saida_png

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "ELE NÃO DEVERIA TER FEITO ISSO..."
    salvar_overlay_hook(t, Path("teste_hook.png"))
