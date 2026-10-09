#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
impact_frames.py — Geração de Tipografia Cinematográfica de Impacto (Motion Graphics).
Renderiza frames de tipografia brutalista/mangá japonês no centro da tela para
momentos clímax (ex: "TATAKAE", "EXPANSÃO DE DOMÍNIO", "DESTRUIDOR", "ARISE").

Gera sequências PNG com canal Alpha (transparência) para overlay ou queima direta
com efeitos de escala, glow e kanjis de fundo.
"""
from pathlib import Path
import json
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONTE_IMPACTO = Path("C:/Windows/Fonts/impact.ttf")
FONTE_JAPONESA = Path("C:/Windows/Fonts/msgothic.ttc")

def criar_card_impacto(
    palavra: str,
    subtexto: str = "",
    kanji_fundo: str = "戦",
    cor_texto: str = "#FFFFFF",
    cor_aura: str = "#FF4500",
    largura: int = 1920,
    altura: int = 1080
) -> Image.Image:
    """
    Cria uma imagem RGBA com tipografia estilizada de anime/mangá.
    - Fundo com kanji gigante translúcido
    - Texto principal em escala monumental com contorno e aura
    - Barras decorativas e tarjas de aviso cinemático
    """
    canvas = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # 1. Kanji gigante no fundo (se disponível)
    if kanji_fundo and FONTE_JAPONESA.exists():
        try:
            fonte_kanji = ImageFont.truetype(str(FONTE_JAPONESA), 650)
            bbox_k = draw.textbbox((0, 0), kanji_fundo, font=fonte_kanji)
            kw = bbox_k[2] - bbox_k[0]
            kh = bbox_k[3] - bbox_k[1]
            kx = (largura - kw) // 2
            ky = (altura - kh) // 2
            draw.text((kx, ky), kanji_fundo, font=fonte_kanji, fill=(255, 69, 0, 45))
        except Exception:
            pass

    # 2. Fonte principal de impacto
    tamanho_fonte = 170 if len(palavra) <= 8 else 125
    try:
        fonte_principal = ImageFont.truetype(str(FONTE_IMPACTO), tamanho_fonte)
    except Exception:
        fonte_principal = ImageFont.load_default()

    bbox_p = draw.textbbox((0, 0), palavra.upper(), font=fonte_principal)
    pw = bbox_p[2] - bbox_p[0]
    ph = bbox_p[3] - bbox_p[1]
    px = (largura - pw) // 2
    py = (altura - ph) // 2

    # 3. Glow / Aura ao redor do texto
    glow_img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_img)
    # desenha contorno grosso na camada de glow
    for dx in range(-8, 9, 2):
        for dy in range(-8, 9, 2):
            if dx*dx + dy*dy <= 64:
                glow_draw.text((px + dx, py + dy), palavra.upper(), font=fonte_principal, fill=cor_aura)
    
    # desfoca o glow
    glow_blurred = glow_img.filter(ImageFilter.GaussianBlur(12))
    canvas = Image.alpha_composite(canvas, glow_blurred)
    draw = ImageDraw.Draw(canvas)

    # 4. Linhas decorativas cinemáticas (topo e base)
    espessura = 6
    margem_linha = 40
    y_linha_sup = py - margem_linha
    y_linha_inf = py + ph + margem_linha
    draw.rectangle([px - 60, y_linha_sup, px + pw + 60, y_linha_sup + espessura], fill=cor_aura)
    draw.rectangle([px - 60, y_linha_inf, px + pw + 60, y_linha_inf + espessura], fill=cor_aura)

    # 5. Texto de contorno preto profundo
    for dx in [-4, -2, 0, 2, 4]:
        for dy in [-4, -2, 0, 2, 4]:
            if dx != 0 or dy != 0:
                draw.text((px + dx, py + dy), palavra.upper(), font=fonte_principal, fill="#050505")

    # 6. Texto principal branco/destaque
    draw.text((px, py), palavra.upper(), font=fonte_principal, fill=cor_texto)

    # 7. Subtexto / técnica / anime
    if subtexto:
        try:
            fonte_sub = ImageFont.truetype(str(FONTE_IMPACTO), 38)
        except Exception:
            fonte_sub = ImageFont.load_default()
        bbox_s = draw.textbbox((0, 0), subtexto.upper(), font=fonte_sub)
        sw = bbox_s[2] - bbox_s[0]
        sx = (largura - sw) // 2
        sy = y_linha_inf + 18
        draw.text((sx, sy), subtexto.upper(), font=fonte_sub, fill="#EEEEEE")

    return canvas

def gerar_sequencia_animacao_impacto(
    palavra: str,
    pasta_saida: Path,
    subtexto: str = "",
    cor_aura: str = "#FF3300",
    frames_totais: int = 15
) -> list[Path]:
    """
    Gera uma sequência de PNGs de animação de entrada com Zoom-in abrupto (Snap Impact).
    Frames 1-3: Escala de 1.4x para 1.0x (impacto soco).
    Frames 4-12: Sustentação com leve respiração / micro-vibração.
    Frames 13-15: Dissolução / Fade out rápido.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)
    card_base = criar_card_impacto(palavra, subtexto=subtexto, cor_aura=cor_aura)
    largura, altura = card_base.size

    caminhos = []
    for f in range(frames_totais):
        # Curva de escala
        if f < 4:
            # Snap zoom: 1.35x -> 1.0x
            prog = f / 3.0
            escala = 1.35 - (0.35 * prog)
            alpha_mult = 0.7 + (0.3 * prog)
        elif f < frames_totais - 3:
            # Mantém com leve vibração
            escala = 1.0 + 0.01 * math.sin(f * 2.0)
            alpha_mult = 1.0
        else:
            # Fade out
            prog = (f - (frames_totais - 3)) / 3.0
            escala = 1.0 - 0.05 * prog
            alpha_mult = max(0.0, 1.0 - prog)

        novo_w = int(largura * escala)
        novo_h = int(altura * escala)
        redimensionado = card_base.resize((novo_w, novo_h), Image.Resampling.LANCZOS)

        # Recortar ou colar centralizado no frame 1920x1080
        frame_final = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
        ox = (largura - novo_w) // 2
        oy = (altura - novo_h) // 2

        if ox >= 0 and oy >= 0:
            frame_final.paste(redimensionado, (ox, oy), redimensionado)
        else:
            # Se for maior que o canvas, recorta o centro
            rx = (novo_w - largura) // 2
            ry = (novo_h - altura) // 2
            cropped = redimensionado.crop((rx, ry, rx + largura, ry + altura))
            frame_final.paste(cropped, (0, 0), cropped)

        # Aplicar transparência
        if alpha_mult < 1.0:
            r, g, b, a = frame_final.split()
            a = a.point(lambda p: int(p * alpha_mult))
            frame_final.putalpha(a)

        out_path = pasta_saida / f"impact_{f:03d}.png"
        frame_final.save(out_path, "PNG")
        caminhos.append(out_path)

    return caminhos

if __name__ == "__main__":
    import sys
    palavra_teste = sys.argv[1] if len(sys.argv) > 1 else "TATAKAE"
    out_dir = Path("teste_impacto")
    gerar_sequencia_animacao_impacto(palavra_teste, out_dir, subtexto="EREN YEAGER // TITAN DE ATAQUE")
    print(f"Sucesso: gerados frames de impacto para '{palavra_teste}' em {out_dir}")
