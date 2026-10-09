#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
card_apresentacao_saber.py — Apresentação Monumental de Personagem com Efeito Saber / Neon Edge.
Fidelidade Masterclass ao take de 18s de referência:
- Texto 'S A S U K E' espaçado e colossal (330px) aparecendo perfeitamente atrás do corpo
- Contorno de neon Saber dourado intenso na silhueta
- Fundo escurecido e desfocado com vinheta dramática
- Animação de Snap Zoom dinâmico
"""
from pathlib import Path
import sys
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rembg import remove, new_session

FONTE_IMPACTO = Path("C:/Windows/Fonts/impact.ttf")

def criar_camadas_base_saber(
    frame_pil: Image.Image,
    nome_personagem: str,
    cor_texto: tuple = (220, 25, 30),
    cor_saber_glow: tuple = (255, 215, 60)
):
    w, h = 1920, 1080
    frame_res = frame_pil.convert("RGB").resize((w, h))

    print("[CARD SABER] Segmentando personagem via IA...")
    sessao = new_session("u2net")
    personagem_rgba = remove(frame_res, session=sessao)

    # 1. Fundo escuro com desfoque de profundidade
    fundo = frame_res.convert("RGBA").filter(ImageFilter.GaussianBlur(12))
    fundo_escuro = fundo.point(lambda p: int(p * 0.32))

    # 2. Texto Espaçado Monumental
    try:
        fonte = ImageFont.truetype(str(FONTE_IMPACTO), 330)
    except Exception:
        fonte = ImageFont.load_default()

    texto_espacado = " ".join(list(nome_personagem.upper()))

    camada_texto = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(camada_texto)
    bbox = t_draw.textbbox((0, 0), texto_espacado, font=fonte)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (w - tw) // 2
    ty = 160

    # Glow neon vermelho nas bordas das letras
    glow_texto = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gt_draw = ImageDraw.Draw(glow_texto)
    for dx in range(-15, 16, 3):
        for dy in range(-15, 16, 3):
            gt_draw.text((tx + dx, ty + dy), texto_espacado, font=fonte, fill=(255, 35, 35, 230))
    glow_texto = glow_texto.filter(ImageFilter.GaussianBlur(18))

    # Contorno e face sólida
    t_draw.text((tx, ty), texto_espacado, font=fonte, fill=(*cor_texto, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
    texto_final = Image.alpha_composite(glow_texto, camada_texto)

    # 3. Efeito Saber / Neon Edge na silhueta do personagem
    r, g, b, alpha = personagem_rgba.split()
    alpha_np = np.array(alpha)
    kernel_grosso = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (16, 16))
    dilatado = cv2.dilate(alpha_np, kernel_grosso, iterations=2)
    borda_saber = cv2.subtract(dilatado, alpha_np)

    saber_pil = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    borda_mask = Image.fromarray(borda_saber)
    saber_pil.paste((*cor_saber_glow, 255), (0, 0), borda_mask)
    saber_glow = saber_pil.filter(ImageFilter.GaussianBlur(12))
    saber_completo = Image.alpha_composite(saber_glow, saber_pil)

    # 4. Composição final em 4 camadas
    comp = Image.alpha_composite(fundo_escuro, texto_final)
    comp = Image.alpha_composite(comp, saber_completo)
    comp = Image.alpha_composite(comp, personagem_rgba)

    return comp

def renderizar_video_apresentacao_saber(
    frame_orig_path: str,
    nome_personagem: str,
    video_saida: str,
    duracao_s: float = 2.5,
    fps: int = 30
) -> str:
    frame_pil = Image.open(frame_orig_path)
    w, h = 1920, 1080

    comp_base = criar_camadas_base_saber(frame_pil, nome_personagem)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(video_saida, fourcc, fps, (w, h))

    total_frames = int(duracao_s * fps)
    print(f"[CARD SABER] Renderizando {total_frames} frames com Snap Zoom...")

    for f in range(total_frames):
        prog = f / max(1, total_frames - 1)
        if f < 10:
            p_zoom = 1.15 - (0.15 * (f / 10.0))
        else:
            p_zoom = 1.0 + (0.02 * math.sin(prog * math.pi))

        zw, zh = int(w * p_zoom), int(h * p_zoom)
        comp_z = comp_base.resize((zw, zh), Image.Resampling.BILINEAR)
        zx = (zw - w) // 2
        zy = (zh - h) // 2
        frame_final = comp_z.crop((zx, zy, zx + w, zy + h))

        frame_bgr = cv2.cvtColor(np.array(frame_final.convert("RGB")), cv2.COLOR_RGB2BGR)
        out.write(frame_bgr)

    out.release()
    print(f"[CARD SABER] Sucesso total: {video_saida}")
    return video_saida

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python card_apresentacao_saber.py <frame.jpg> '<NOME>' <saida.mp4>")
        sys.exit(1)
    renderizar_video_apresentacao_saber(sys.argv[1], sys.argv[2], sys.argv[3])
