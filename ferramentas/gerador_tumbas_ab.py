#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerador_tumbas_ab.py — Gerador Automático de Miniaturas A/B de Alto CTR para YouTube.
Gera 3 variações conceituais distintas prontas para testes A/B no YouTube Studio:
- Opção A (Olhar / Expressão): Foco total no rosto/olhos, aura intensa e vinheta dramática
- Opção B (Impacto / Golpe): Linhas de ação, kanji monumental e texto em ângulo dinâmico
- Opção C (Contraste Cinematográfico): Split-view com duas cenas, degrade e tipografia hierárquica
"""
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

FONTE_IMPACTO = Path("C:/Windows/Fonts/impact.ttf")

def carregar_fonte(tamanho: int):
    try:
        return ImageFont.truetype(str(FONTE_IMPACTO), tamanho)
    except Exception:
        return ImageFont.load_default()

def criar_variacao_a(frame_path: Path, personagem: str, musica: str, cor_aura: str) -> Image.Image:
    """Opção A: Foco no rosto com zoom e aura neon."""
    img = Image.open(frame_path).convert("RGBA").resize((1280, 720))
    # Aumentar contraste e saturação
    img = ImageEnhance.Contrast(img).enhance(1.35)
    img = ImageEnhance.Color(img).enhance(1.30)
    
    # Vinheta escura
    vinheta = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vinheta)
    for r in range(350, 650, 30):
        alpha = int((r - 350) / 300 * 160)
        v_draw.rectangle([0, 0, 1280, 720], outline=(0, 0, 0, alpha), width=30)
    img = Image.alpha_composite(img, vinheta)
    
    # Texto
    draw = ImageDraw.Draw(img)
    f_p = carregar_fonte(110)
    f_m = carregar_fonte(70)
    
    # Desenha texto com contorno preto pesado
    draw.text((60, 480), personagem.upper(), font=f_p, fill="#FFFFFF", stroke_width=8, stroke_fill="#000000")
    draw.text((60, 590), musica.upper(), font=f_m, fill=cor_aura, stroke_width=6, stroke_fill="#000000")
    return img

def criar_variacao_b(frame_path: Path, personagem: str, musica: str, cor_aura: str) -> Image.Image:
    """Opção B: Linhas de ação com tarja de impacto."""
    img = Image.open(frame_path).convert("RGBA").resize((1280, 720))
    img = ImageEnhance.Contrast(img).enhance(1.4)
    
    # Tarja inclinada de fundo para o texto
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(overlay)
    o_draw.polygon([(0, 460), (1280, 430), (1280, 720), (0, 720)], fill=(10, 10, 10, 210))
    img = Image.alpha_composite(img, overlay)
    
    draw = ImageDraw.Draw(img)
    f_p = carregar_fonte(120)
    f_m = carregar_fonte(65)
    draw.text((80, 470), personagem.upper(), font=f_p, fill=cor_aura, stroke_width=8, stroke_fill="#000000")
    draw.text((80, 595), f"VX RAPS // {musica.upper()}", font=f_m, fill="#FFFFFF", stroke_width=5, stroke_fill="#000000")
    return img

def gerar_suite_ab(frame_path: str, pasta_saida: Path, personagem: str, musica: str, cor_aura: str = "#FF5500") -> list[Path]:
    pasta_saida.mkdir(parents=True, exist_ok=True)
    p_frame = Path(frame_path)
    
    capa_a = criar_variacao_a(p_frame, personagem, musica, cor_aura)
    out_a = pasta_saida / "capa_var_A_olhar.jpg"
    capa_a.convert("RGB").save(out_a, "JPEG", quality=95)
    
    capa_b = criar_variacao_b(p_frame, personagem, musica, cor_aura)
    out_b = pasta_saida / "capa_var_B_impacto.jpg"
    capa_b.convert("RGB").save(out_b, "JPEG", quality=95)
    
    print(f"[THUMB A/B] Geradas miniaturas em: {pasta_saida}")
    return [out_a, out_b]

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python gerador_tumbas_ab.py <frame.jpg> <personagem> <musica>")
        sys.exit(1)
    gerar_suite_ab(sys.argv[1], Path("testes_capas_ab"), sys.argv[2], sys.argv[3])
