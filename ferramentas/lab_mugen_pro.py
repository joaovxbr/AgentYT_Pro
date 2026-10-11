#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ferramentas/lab_mugen_pro.py — Motor de Efeitos de Nova Geração no Estilo MUGEN RAPS.
Implementa as tecnicas de alto impacto extraidas diretamente das referencias:
1. Fenda Orgânica das Sombras com contorno neon ondulante e olhos dos Shikigami (Kon).
2. Card Épico com Kanji Caligráfico Vertical (十種影法術) e tipografia Cinzel Bold.
3. Tipografia Frasal de Impacto com Speedlines convergentes e textura grit/shatter.
4. Profundidade 3D com Rim Light (aura de energia) sobre a cena real.
5. Legenda Cinzel MUGEN Pro com highlight neon ciano word-by-word.
"""
import os
import sys
import math
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "ferramentas"))

W, H = 1920, 1080
FPS = 30
COR_CIANO = (30, 160, 255)
COR_AZUL_PROFUNDO = (15, 60, 140)
COR_ROXO = (130, 45, 255)
COR_BRANCO = (250, 250, 255)

# Fontes
FONTE_CINZEL_BOLD = RAIZ / "ferramentas" / "fontes" / "Cinzel-Bold.ttf"
FONTE_CINZEL = RAIZ / "ferramentas" / "fontes" / "Cinzel-Variable.ttf"
FONTE_BEBAS = RAIZ / "ferramentas" / "fontes" / "BebasNeue-Regular.ttf"
FONTE_ANTON = RAIZ / "ferramentas" / "fontes" / "Anton-Regular.ttf"
FONTE_KANJI = Path("C:/Windows/Fonts/YuGothB.ttc")


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_out_back(t: float, s: float = 1.6) -> float:
    t = max(0.0, min(1.0, t)) - 1.0
    return t * t * ((s + 1.0) * t + s) + 1.0


def tratar_plate_cinematico(img: Image.Image, luz: float = 0.28, sat: float = 0.60,
                            zoom: float = 1.0, matiz_frio: bool = True) -> Image.Image:
    """Aplica color grading cinematografico escuro (70-75% preto) com matiz frio nas sombras."""
    if zoom > 1.001:
        w2, h2 = int(W / zoom), int(H / zoom)
        img = img.crop(((W - w2) // 2, (H - h2) // 2, (W + w2) // 2, (H + h2) // 2)).resize((W, H), Image.Resampling.BILINEAR)

    arr = np.asarray(img, dtype=np.float32)
    cinza = arr.mean(axis=2, keepdims=True)
    # dessaturacao + escurecimento profundo
    out = (cinza + (arr - cinza) * sat) * luz

    if matiz_frio:
        # injeta tom azul noturno suave nas baixas luzes
        out[..., 0] *= 0.85   # reduz vermelho
        out[..., 1] *= 0.95   # leve verde
        out[..., 2] *= 1.20   # amplia azul

    # Vinheta escura profunda nos cantos
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vin = np.clip(1.0 - 0.65 * np.clip(r - 0.25, 0, 1) ** 1.8, 0, 1)[..., None]
    out *= vin

    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def desenhar_olho_shikigami(canvas: Image.Image, ox: float, oy: float, scale: float = 1.0, alpha: float = 1.0):
    """Olhos luminosos do Lobo Divino (Kon) emergindo na escuridao lateral."""
    w, h = int(110 * scale), int(45 * scale)
    olho = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(olho)
    pts = [(int(6 * scale), int(22 * scale)), (int(55 * scale), int(6 * scale)),
           (int(104 * scale), int(22 * scale)), (int(55 * scale), int(38 * scale))]
    od.polygon(pts, fill=(255, 255, 255, int(245 * alpha)))
    # pupila/fenda horizontal sombria
    od.line([(int(6 * scale), int(22 * scale)), (int(104 * scale), int(22 * scale))],
            fill=(10, 15, 28, int(255 * alpha)), width=max(1, int(4 * scale)))

    # Glow azul/ciano ao redor do olho
    gw, gh = int(160 * scale), int(90 * scale)
    glow = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((int(15 * scale), int(15 * scale), int(145 * scale), int(75 * scale)),
               fill=(*COR_CIANO, int(180 * alpha)))
    glow = glow.filter(ImageFilter.GaussianBlur(int(12 * scale)))

    canvas.alpha_composite(glow, (int(ox - 25 * scale), int(oy - 22 * scale)))
    canvas.alpha_composite(olho, (int(ox), int(oy)))


def gerar_fenda_sombras(t_local: float, dur_take: float) -> tuple[Image.Image, list[tuple[float, float]]]:
    """Gera a mascara e o contorno neon organico da Fenda de Sombras do Megumi."""
    fenda_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fenda_layer)
    cx, cy = W // 2, H // 2

    # pulsacao e ondulacao organica com o tempo
    tempo_onda = t_local * 3.5
    pontos = []
    for deg in range(0, 360, 4):
        rad = math.radians(deg)
        deform = (math.sin(rad * 4 + tempo_onda) * 40 +
                  math.cos(rad * 7 - tempo_onda * 1.3) * 20 +
                  math.sin(rad * 11 + tempo_onda * 0.7) * 12)
        rx = W * 0.44 + deform
        ry = H * 0.34 + deform * 0.65
        px = cx + rx * math.cos(rad)
        py = cy + ry * math.sin(rad)
        pontos.append((px, py))
    pontos.append(pontos[0])

    # Contorno neon com gaussian blur volumetrico
    glow_contour = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gcd = ImageDraw.Draw(glow_contour)
    gcd.line(pontos, fill=(*COR_CIANO, 220), width=14)
    glow_contour = glow_contour.filter(ImageFilter.GaussianBlur(18))
    fenda_layer.alpha_composite(glow_contour)

    # Traco fino central brilhante
    fd.line(pontos, fill=(230, 248, 255, 255), width=3)

    return fenda_layer, pontos


def desenhar_speedlines(prog: float, intensidade: float = 1.0) -> Image.Image:
    """Raios cineticos de velocidade convergindo para o centro (estilo MUGEN RAPS #4/#9)."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(layer)
    cx, cy = W // 2, H // 2
    fase = int(prog * 12) % 3

    for ang_deg in range(fase, 360, 3):
        rad = math.radians(ang_deg)
        r_inner = 360 + (ang_deg * 37 % 140)
        r_outer = 1250
        x1 = cx + r_inner * math.cos(rad)
        y1 = cy + r_inner * math.sin(rad)
        x2 = cx + r_outer * math.cos(rad)
        y2 = cy + r_outer * math.sin(rad)
        al = int((20 + (ang_deg * 23 % 45)) * intensidade)
        sd.line([(x1, y1), (x2, y2)], fill=(40, 110, 210, al), width=2)

    return layer.filter(ImageFilter.GaussianBlur(1.5))


def render_card_dez_sombras(bg: Image.Image, t_rel: float, dur: float) -> Image.Image:
    """Card de Tecnica Epica: Fenda de Sombra + Olhos do Shikigami + Kanji Caligrafico + Cinzel Bold."""
    prog_in = ease_out(t_rel / 0.5)
    fade_out = 1.0 - ease_out((t_rel - (dur - 0.4)) / 0.4) if t_rel > (dur - 0.4) else 1.0
    alpha_total = min(prog_in, fade_out)

    canvas = bg.copy().convert("RGBA")

    # 1. Glow volumetrico no centro
    radial = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(radial)
    rd.ellipse((W//2 - 550, H//2 - 380, W//2 + 550, H//2 + 380), fill=(*COR_AZUL_PROFUNDO, int(140 * alpha_total)))
    radial = radial.filter(ImageFilter.GaussianBlur(130))
    canvas.alpha_composite(radial)

    # 2. Fenda Organica de Sombra e Contorno Neon
    fenda_img, _ = gerar_fenda_sombras(t_rel, dur)
    if alpha_total < 1.0:
        fenda_img.putalpha(fenda_img.getchannel("A").point(lambda p: int(p * alpha_total)))
    canvas.alpha_composite(fenda_img)

    # 3. Olhos do Lobo Divino (Kon) brilhando nas bordas escuras
    olho_alpha = min(1.0, ease_out((t_rel - 0.15) / 0.4)) * alpha_total
    if olho_alpha > 0:
        desenhar_olho_shikigami(canvas, 140, 520, 0.95, olho_alpha)
        desenhar_olho_shikigami(canvas, 250, 520, 0.95, olho_alpha)
        desenhar_olho_shikigami(canvas, W - 350, 520, 0.95, olho_alpha)
        desenhar_olho_shikigami(canvas, W - 240, 520, 0.95, olho_alpha)

    # 4. Kanji Caligrafico Vertical na lateral direita (十種影法術)
    font_kanji = ImageFont.truetype(str(FONTE_KANJI), 74)
    kanji_text = "十\n種\n影\n法\n術"
    kanji_lay = Image.new("RGBA", (140, 620), (0, 0, 0, 0))
    kd = ImageDraw.Draw(kanji_lay)
    # glow do kanji
    kglow = Image.new("RGBA", (140, 620), (0, 0, 0, 0))
    ImageDraw.Draw(kglow).multiline_text((20, 10), kanji_text, font=font_kanji, fill=(*COR_CIANO, int(200 * alpha_total)), spacing=18)
    kglow = kglow.filter(ImageFilter.GaussianBlur(16))
    kanji_lay.alpha_composite(kglow)
    # kanji preenchimento
    kd.multiline_text((22, 12), kanji_text, font=font_kanji, fill=(5, 10, 20, int(200 * alpha_total)), spacing=18)
    kd.multiline_text((20, 10), kanji_text, font=font_kanji, fill=(245, 250, 255, int(235 * alpha_total)), spacing=18)
    canvas.alpha_composite(kanji_lay, (int(W * 0.91), int(H * 0.22)))

    # 5. Topo: MEGUMI FUSHIGURO com tracking
    font_topo = ImageFont.truetype(str(FONTE_BEBAS), 54)
    txt_topo = "M E G U M I   F U S H I G U R O"
    bb_t = font_topo.getbbox(txt_topo)
    tw = bb_t[2] - bb_t[0]
    td = ImageDraw.Draw(canvas)
    td.text(((W - tw) // 2, int(H * 0.23)), txt_topo, font=font_topo, fill=(215, 235, 255, int(240 * alpha_total)))

    # 6. Titulo Principal: DEZ SOMBRAS (Cinzel Bold com Pop + Glow)
    font_main = ImageFont.truetype(str(FONTE_CINZEL_BOLD), 148)
    txt_main = "DEZ SOMBRAS"
    bb_m = font_main.getbbox(txt_main)
    mw, mh = bb_m[2] - bb_m[0], bb_m[3] - bb_m[1]

    # Escala pop na entrada (1.18 -> 1.0)
    escala = 1.0 + 0.18 * (1.0 - ease_out(t_rel / 0.45))
    text_canvas = Image.new("RGBA", (mw + 240, mh + 240), (0, 0, 0, 0))
    tcd = ImageDraw.Draw(text_canvas)

    # Glow azul espesso
    tglow = Image.new("RGBA", text_canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(tglow).text((120, 120), txt_main, font=font_main, fill=(*COR_CIANO, 255))
    tglow = tglow.filter(ImageFilter.GaussianBlur(34))
    text_canvas.alpha_composite(tglow)

    # Texto com contorno escuro forte
    tcd.text((120, 120), txt_main, font=font_main, fill=(255, 255, 255, 255),
             stroke_width=7, stroke_fill=(6, 10, 18, 255))

    if escala > 1.002:
        new_w, new_h = int(text_canvas.width * escala), int(text_canvas.height * escala)
        text_canvas = text_canvas.resize((new_w, new_h), Image.Resampling.BILINEAR)

    if alpha_total < 1.0:
        text_canvas.putalpha(text_canvas.getchannel("A").point(lambda p: int(p * alpha_total)))

    cx, cy = W // 2, int(H * 0.36)
    canvas.alpha_composite(text_canvas, (cx - text_canvas.width // 2, cy - text_canvas.height // 2))

    # 7. Regua horizontal central com pontuacao de luz
    regua_w = int(W * 0.26 * min(1.0, prog_in * 1.5))
    regua_y = int(H * 0.49)
    td.line([(W//2 - regua_w, regua_y), (W//2 + regua_w, regua_y)], fill=(*COR_CIANO, int(220 * alpha_total)), width=3)
    td.line([(W//2 - regua_w//2, regua_y), (W//2 + regua_w//2, regua_y)], fill=(255, 255, 255, int(255 * alpha_total)), width=2)

    # 8. Subtitulo do Verso
    font_sub = ImageFont.truetype(str(FONTE_CINZEL), 42)
    txt_sub = "INVOCA A SOMBRA  ·  DEIXA O CHAO SE ABRIR"
    bb_s = font_sub.getbbox(txt_sub)
    sw = bb_s[2] - bb_s[0]
    td.text(((W - sw) // 2, int(H * 0.52)), txt_sub, font=font_sub, fill=(195, 215, 240, int(225 * alpha_total)))

    # Flash branco rapido na entrada (0.08s)
    if t_rel < 0.08:
        fl_alpha = int(120 * (1.0 - t_rel / 0.08))
        canvas = Image.alpha_composite(canvas, Image.new("RGBA", (W, H), (255, 255, 255, fl_alpha)))

    return canvas.convert("RGB")


def render_card_impacto_frasal(bg: Image.Image, t_rel: float, dur: float) -> Image.Image:
    """Card de Rima Cinética: Speedlines Radiais + Frase Hierarquica com Textura Grit."""
    prog_in = ease_out(t_rel / 0.4)
    fade_out = 1.0 - ease_out((t_rel - (dur - 0.35)) / 0.35) if t_rel > (dur - 0.35) else 1.0
    alpha_total = min(prog_in, fade_out)

    canvas = bg.copy().convert("RGBA")

    # 1. Speedlines convergentes
    sp = desenhar_speedlines(t_rel, alpha_total)
    canvas.alpha_composite(sp)

    # 2. Brilho radial intenso azul/ciano no centro
    radial = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(radial)
    rd.ellipse((W//2 - 450, H//2 - 280, W//2 + 450, H//2 + 280), fill=(*COR_CIANO, int(95 * alpha_total)))
    radial = radial.filter(ImageFilter.GaussianBlur(100))
    canvas.alpha_composite(radial)

    cd = ImageDraw.Draw(canvas)

    # 3. Linha Superior: DEZ CAMINHOS (Bebas Neue 82px)
    font_cima = ImageFont.truetype(str(FONTE_BEBAS), 82)
    txt_cima = "DEZ CAMINHOS"
    bb_c = font_cima.getbbox(txt_cima)
    cw = bb_c[2] - bb_c[0]
    cd.text(((W - cw) // 2, int(H * 0.28)), txt_cima, font=font_cima, fill=(230, 245, 255, int(245 * alpha_total)))

    # 4. Palavra Central GIGANTE: NENHUM DELES (Anton 185px, inclinacao dinamica -2.5 deg)
    font_punch = ImageFont.truetype(str(FONTE_ANTON), 185)
    txt_punch = "NENHUM DELES"
    bb_p = font_punch.getbbox(txt_punch)
    pw, ph = bb_p[2] - bb_p[0], bb_p[3] - bb_p[1]

    punch_lay = Image.new("RGBA", (pw + 260, ph + 260), (0, 0, 0, 0))
    pcd = ImageDraw.Draw(punch_lay)

    # Glow vibrante
    pglow = Image.new("RGBA", punch_lay.size, (0, 0, 0, 0))
    ImageDraw.Draw(pglow).text((130, 130), txt_punch, font=font_punch, fill=(*COR_CIANO, 255))
    pglow = pglow.filter(ImageFilter.GaussianBlur(36))
    punch_lay.alpha_composite(pglow)

    # Preenchimento branco com stroke pesado
    pcd.text((130, 130), txt_punch, font=font_punch, fill=(255, 255, 255, 255),
             stroke_width=9, stroke_fill=(5, 8, 15, 255))

    # Leve rotacao de -2.5 graus para agressividade cinetica
    punch_rot = punch_lay.rotate(-2.5, resample=Image.Resampling.BILINEAR, expand=True)

    # Escala soco na batida
    soco = 1.0 + 0.15 * (1.0 - ease_out(t_rel / 0.3))
    if soco > 1.002:
        punch_rot = punch_rot.resize((int(punch_rot.width * soco), int(punch_rot.height * soco)), Image.Resampling.BILINEAR)

    if alpha_total < 1.0:
        punch_rot.putalpha(punch_rot.getchannel("A").point(lambda p: int(p * alpha_total)))

    canvas.alpha_composite(punch_rot, (W // 2 - punch_rot.width // 2, int(H * 0.44) - punch_rot.height // 2))

    # 5. Linha Inferior: VAI FUGIR com elipse de luz
    font_baixo = ImageFont.truetype(str(FONTE_BEBAS), 90)
    txt_baixo = "VAI FUGIR"
    bb_b = font_baixo.getbbox(txt_baixo)
    bw = bb_b[2] - bb_b[0]

    # Elipse de portal horizontal sob a palavra inferior
    el = Image.new("RGBA", (int(bw * 1.5), 36), (0, 0, 0, 0))
    eld = ImageDraw.Draw(el)
    eld.ellipse((0, 4, int(bw * 1.5), 32), fill=(*COR_CIANO, int(190 * alpha_total)))
    el = el.filter(ImageFilter.GaussianBlur(8))
    canvas.alpha_composite(el, (W // 2 - el.width // 2, int(H * 0.69)))

    cd.text(((W - bw) // 2, int(H * 0.64)), txt_baixo, font=font_baixo, fill=(245, 250, 255, int(250 * alpha_total)))

    # Flash na entrada
    if t_rel < 0.08:
        fl_alpha = int(110 * (1.0 - t_rel / 0.08))
        canvas = Image.alpha_composite(canvas, Image.new("RGBA", (W, H), (255, 255, 255, fl_alpha)))

    return canvas.convert("RGB")


def render_take_atras_profundo(bg_plate: Image.Image, sujeito_img: Image.Image,
                               mascara: Image.Image, t_rel: float, dur: float) -> Image.Image:
    """Take com o personagem na frente, aura neon e texto gigante COM CONTRASTE PROFUNDO atras."""
    prog_in = ease_out(t_rel / 0.45)
    fade_out = 1.0 - ease_out((t_rel - (dur - 0.35)) / 0.35) if t_rel > (dur - 0.35) else 1.0
    alpha_total = min(prog_in, fade_out)

    # 1. Plate de fundo escurecido e vinhetado (elimina a lavagem de ceu claro)
    fundo = tratar_plate_cinematico(bg_plate, luz=0.32, sat=0.55, matiz_frio=True).convert("RGBA")

    # 2. Texto gigante ATRAS do personagem: FUSHIGURO em escala ampla
    font_atras = ImageFont.truetype(str(FONTE_ANTON), 260)
    txt_atras = "FUSHIGURO"
    bb_a = font_atras.getbbox(txt_atras)
    aw, ah = bb_a[2] - bb_a[0], bb_a[3] - bb_a[1]

    txt_lay = Image.new("RGBA", (aw + 240, ah + 240), (0, 0, 0, 0))
    tad = ImageDraw.Draw(txt_lay)

    # Glow neon azul espesso
    aglow = Image.new("RGBA", txt_lay.size, (0, 0, 0, 0))
    ImageDraw.Draw(aglow).text((120, 120), txt_atras, font=font_atras, fill=(*COR_CIANO, 255))
    aglow = aglow.filter(ImageFilter.GaussianBlur(36))
    txt_lay.alpha_composite(aglow)

    # Texto com stroke escuro forte para NUNCA fundir com o fundo
    tad.text((120, 120), txt_atras, font=font_atras, fill=(245, 250, 255, 255),
             stroke_width=11, stroke_fill=(5, 8, 14, 255))

    if alpha_total < 1.0:
        txt_lay.putalpha(txt_lay.getchannel("A").point(lambda p: int(p * alpha_total)))

    fundo.alpha_composite(txt_lay, (W // 2 - txt_lay.width // 2, int(H * 0.35) - txt_lay.height // 2))

    # 3. Aura de energia amaldicoada (Rim Light) na borda do recorte do personagem
    masc_arr = np.asarray(mascara, dtype=np.float32) / 255.0
    masc_dil = mascara.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(8))
    rim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    arr_dil = np.asarray(masc_dil, dtype=np.float32) / 255.0
    borda = np.clip(arr_dil - masc_arr, 0, 1)
    rim_mask = Image.fromarray((borda * 240).astype(np.uint8))
    rim_color = Image.new("RGBA", (W, H), (*COR_CIANO, 255))
    rim.paste(rim_color, (0, 0), rim_mask)
    fundo.alpha_composite(rim)

    # 4. Personagem nitido na frente
    final = Image.composite(sujeito_img.convert("RGBA"), fundo, mascara)

    return final.convert("RGB")


def renderizar_legenda_mugen_overlay(canvas: Image.Image, linha_txt: str, palavra_ativa: str,
                                     t_linha: float, dur_linha: float) -> Image.Image:
    """Desenha a legenda Cinzel MUGEN Pro com destaque neon ciano na palavra cantada."""
    font_leg = ImageFont.truetype(str(FONTE_CINZEL), 48)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    import re
    palavras = linha_txt.upper().split()
    larguras = [d.textbbox((0, 0), p, font=font_leg)[2] - d.textbbox((0, 0), p, font=font_leg)[0] for p in palavras]
    espaco = 16
    total_w = sum(larguras) + espaco * (len(palavras) - 1)
    x_cursor = (W - total_w) // 2
    y_leg = H - 95

    p_ativa_clean = re.sub(r"[^\w]", "", palavra_ativa.upper())

    for p, w in zip(palavras, larguras):
        p_clean = re.sub(r"[^\w]", "", p)
        eh_ativa = bool(p_ativa_clean and (p_clean == p_ativa_clean or (len(p_clean) >= 4 and p_clean.startswith(p_ativa_clean[:4]))))

        if eh_ativa:
            # Glow neon ciano sob a palavra ativa
            glow_txt = Image.new("RGBA", (w + 100, 110), (0, 0, 0, 0))
            ImageDraw.Draw(glow_txt).text((50, 20), p, font=font_leg, fill=(*COR_CIANO, 255))
            glow_txt = glow_txt.filter(ImageFilter.GaussianBlur(16))
            overlay.alpha_composite(glow_txt, (x_cursor - 50, y_leg - 20))

            # Palavra ativa em ciano luminoso com stroke preto
            d.text((x_cursor, y_leg), p, font=font_leg, fill=(210, 245, 255, 255),
                   stroke_width=5, stroke_fill=(5, 8, 16, 255))
        else:
            # Palavras passivas em branco limpo com sombra
            d.text((x_cursor + 2, y_leg + 2), p, font=font_leg, fill=(0, 0, 0, 190))
            d.text((x_cursor, y_leg), p, font=font_leg, fill=(245, 245, 250, 235),
                   stroke_width=2, stroke_fill=(8, 8, 12, 230))

        x_cursor += w + espaco

    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def decodificar_trecho_video(caminho_video: Path, t_inicio: float, duracao: float, n_quadros: int) -> list[Image.Image]:
    """Extrai exatamente n_quadros de um clipe via ffmpeg pipe."""
    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", str(t_inicio),
        "-i", str(caminho_video),
        "-t", str(duracao),
        "-vf", f"scale={W}:{H},fps={FPS}",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-"
    ]
    p = subprocess.run(cmd, capture_output=True)
    raw = p.stdout
    frame_bytes = W * H * 3
    quadros = []
    for i in range(0, len(raw), frame_bytes):
        chunk = raw[i:i + frame_bytes]
        if len(chunk) == frame_bytes:
            arr = np.frombuffer(chunk, dtype=np.uint8).reshape((H, W, 3))
            quadros.append(Image.fromarray(arr))
            if len(quadros) >= n_quadros:
                break
    # preenche se faltou quadro
    while len(quadros) < n_quadros:
        quadros.append(quadros[-1] if quadros else Image.new("RGB", (W, H), (10, 15, 25)))
    return quadros[:n_quadros]


def gerar_previa_mugen_pro():
    """Gera a previa completa de 8 segundos no estilo MUGEN RAPS em alta definicao com NVENC."""
    slug = "megumi_shadows"
    dir_proj = RAIZ / "projetos" / slug
    dir_saida = dir_proj / "lab" / "previa_mugen_pro"
    dir_saida.mkdir(parents=True, exist_ok=True)

    print("== Gerando Previa MUGEN RAPS Pro (8 segundos) ==")
    t_global_inicio = 46.5
    dur_total = 8.0
    total_quadros = int(dur_total * FPS)

    # 1. Extrair audio do trecho
    audio_orig = dir_proj / "entradas" / f"{slug}_normalizado.wav"
    audio_trecho = dir_saida / "audio_8s.wav"
    cmd_audio = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", str(t_global_inicio),
        "-t", str(dur_total),
        "-i", str(audio_orig),
        "-acodec", "copy",
        str(audio_trecho)
    ]
    subprocess.run(cmd_audio, check=True)
    print("Audio sincronizado extraido:", audio_trecho)

    # 2. Carregar palavras e tempos do trecho
    dados_letra = json.loads((dir_proj / "letra_sincronizada.json").read_text(encoding="utf-8"))
    palavras_trecho = []
    linhas_trecho = []
    for l in dados_letra:
        if l["end"] >= t_global_inicio and l["start"] <= (t_global_inicio + dur_total):
            linhas_trecho.append(l)
            for w in l.get("words", []):
                palavras_trecho.append(w)

    def obter_palavra_ativa(t_abs: float) -> tuple[str, str]:
        """Retorna (linha_texto, palavra_ativa) para o instante t_abs."""
        linha_atual = ""
        for l in linhas_trecho:
            if l["start"] <= t_abs <= (l["end"] + 0.3):
                linha_atual = l["text"]
                break
        palavra_atual = ""
        for w in palavras_trecho:
            if w["start"] <= t_abs <= (w["end"] + 0.1):
                palavra_atual = w.get("word") or w.get("text", "")
                break
        return linha_atual, palavra_atual

    # 3. Decodificar clipes reais da timeline
    # Momento 1: 0.0s -> 3.3s (46.5 -> 49.8) - megumi_lobo_vermelho.mp4
    n_q1 = int(3.3 * FPS)
    q1 = decodificar_trecho_video(dir_proj / "clips_raw" / "megumi_lobo_vermelho.mp4", 1.13, 3.3, n_q1)

    # Momento 2: 3.3s -> 6.5s (49.8 -> 53.0) - megumi_investida.mp4
    n_q2 = int(3.2 * FPS)
    q2 = decodificar_trecho_video(dir_proj / "clips_raw" / "megumi_investida.mp4", 2.44, 3.2, n_q2)

    # Momento 3: 6.5s -> 8.0s (53.0 -> 54.5) - megumi_olhos_azuis.mp4 (plano individual épico)
    n_q3 = total_quadros - (n_q1 + n_q2)
    q3 = decodificar_trecho_video(dir_proj / "clips_raw" / "megumi_olhos_azuis.mp4", 1.0, 1.5, n_q3)

    print(f"Decodificados: Momento 1 ({len(q1)}q), Momento 2 ({len(q2)}q), Momento 3 ({len(q3)}q)")

    # 4. Pipeline ffmpeg NVENC para receber os frames renderizados
    video_saida = dir_saida / "previa_mugen_pro.mp4"
    cmd_encode = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}",
        "-r", str(FPS),
        "-i", "-",
        "-i", str(audio_trecho),
        "-c:v", "h264_nvenc",
        "-preset", "p7",
        "-cq", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "256k",
        "-shortest",
        str(video_saida)
    ]
    proc = subprocess.Popen(cmd_encode, stdin=subprocess.PIPE)

    quadros_amostra = []
    import rembg
    rembg_sessao = rembg.new_session("u2net")

    print("Renderizando quadros compostos...")
    for idx in range(total_quadros):
        t_sec = idx / FPS
        t_abs = t_global_inicio + t_sec
        linha_txt, palavra_ativa = obter_palavra_ativa(t_abs)

        if idx < n_q1:
            # --- MOMENTO 1: Card Épico Dez Sombras com Fenda, Olhos do Lobo e Kanji ---
            t_rel = t_sec
            dur_m1 = 3.3
            prog_bg = t_rel / dur_m1
            bg_tr = tratar_plate_cinematico(q1[idx], luz=0.25, sat=0.50, zoom=1.0 + 0.05 * prog_bg)
            frame_comp = render_card_dez_sombras(bg_tr, t_rel, dur_m1)

        elif idx < (n_q1 + n_q2):
            # --- MOMENTO 2: Card Frasal Cinético com Speedlines e Tipografia de Soco ---
            t_rel = t_sec - 3.3
            dur_m2 = 3.2
            prog_bg = t_rel / dur_m2
            bg_tr = tratar_plate_cinematico(q2[idx - n_q1], luz=0.22, sat=0.45, zoom=1.0 + 0.06 * prog_bg)
            frame_comp = render_card_impacto_frasal(bg_tr, t_rel, dur_m2)

        else:
            # --- MOMENTO 3: Profundidade 3D com Megumi Recortado e Rim Light ---
            t_rel = t_sec - 6.5
            dur_m3 = 1.5
            frame_cru = q3[idx - (n_q1 + n_q2)]
            # mascara via rembg no frame
            masc = rembg.remove(frame_cru, session=rembg_sessao, only_mask=True)
            sujeito = frame_cru.copy()
            frame_comp = render_take_atras_profundo(frame_cru, sujeito, masc, t_rel, dur_m3)

        # Queima a legenda Cinzel MUGEN Pro na faixa inferior
        if linha_txt:
            frame_comp = renderizar_legenda_mugen_overlay(frame_comp.convert("RGBA"), linha_txt, palavra_ativa, t_sec, dur_total).convert("RGB")

        # Salva amostras para folha de contato (em 1.0s, 2.5s, 4.0s, 5.5s, 7.2s)
        if idx in (int(1.0 * FPS), int(2.5 * FPS), int(4.0 * FPS), int(5.5 * FPS), int(7.2 * FPS)):
            quadros_amostra.append((round(t_sec, 1), frame_comp.copy()))

        proc.stdin.write(frame_comp.tobytes())

    proc.stdin.close()
    proc.wait()
    print("Vídeo renderizado com sucesso:", video_saida, f"({video_saida.stat().st_size / 1e6:.1f} MB)")

    # 5. Gerar Folha de Contato e Salvar Quadros
    for t_s, img in quadros_amostra:
        p_frame = dir_saida / f"frame_{t_s}s.png"
        img.save(p_frame)

    # Monta a folha horizontal
    folha_w = W
    tile_w = folha_w // len(quadros_amostra)
    tile_h = int(tile_w * (H / W))
    folha = Image.new("RGB", (folha_w, tile_h + 40), (8, 12, 18))
    fd = ImageDraw.Draw(folha)
    font_lbl = ImageFont.truetype(str(FONTE_BEBAS), 30)

    for i, (t_s, img) in enumerate(quadros_amostra):
        thumb = img.resize((tile_w, tile_h), Image.Resampling.BILINEAR)
        folha.paste(thumb, (i * tile_w, 40))
        fd.text((i * tile_w + 12, 6), f"t = {t_s}s", font=font_lbl, fill=(180, 210, 245))

    p_folha = dir_saida / "folha_mugen_pro.png"
    folha.save(p_folha)
    print("Folha de contato gerada:", p_folha)
    print("Concluído!")


if __name__ == "__main__":
    import json
    gerar_previa_mugen_pro()

