#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Graphics Pro: tipografia cinetica frame a frame em Pillow."""
from __future__ import annotations

import math
import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter

_TRACE_CACHE = {}


def hex_rgb(valor: str, fallback=(255, 255, 255)) -> tuple[int, int, int]:
    try:
        h = (valor or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (x - 1.0) ** 3 + c1 * (x - 1.0) ** 2


def estado_animacao(animacao: str, progresso: float, frame_idx: int, energia: float,
                    beat_pulse: float = 0.0) -> dict:
    p = max(0.0, min(1.0, progresso))
    entrada = min(1.0, p / 0.22)
    scale = 1.0
    alpha = 255
    dx = dy = 0
    chroma = 0

    if animacao in ("slam_in", "scale_punch"):
        k = ease_out_back(entrada)
        scale = 0.66 + 0.34 * k
        if animacao == "slam_in":
            dy = int((1.0 - smoothstep(entrada)) * -100)
    elif animacao == "neon_flicker":
        scale = 0.93 + 0.07 * ease_out_back(entrada)
        if frame_idx < 10:
            pattern = (0.18, 1.0, 0.36, 0.92, 0.25, 1.0, 0.72, 1.0, 0.9, 1.0)
            alpha = int(255 * pattern[frame_idx])
    elif animacao == "write_on":
        escrita = smoothstep(min(1.0, p / 0.72))
        scale = 0.985 + 0.015 * escrita
    elif animacao == "letter_reveal":
        escrita = smoothstep(min(1.0, p / 0.68))
        scale = 0.975 + 0.025 * escrita
    elif animacao == "outline_fill":
        escrita = smoothstep(min(1.0, p / 0.62))
        scale = 0.985 + 0.015 * escrita
    elif animacao == "trace_write":
        escrita = smoothstep(min(1.0, p / 0.72))
        scale = 0.985 + 0.015 * escrita
    elif animacao in ("glitch_pop", "rgb_glitch_pop"):
        scale = 0.78 + 0.22 * ease_out_back(entrada)
        if frame_idx < 7:
            dx = (4, -12, 9, -5, 3, -2, 0)[frame_idx]
            dy = (0, 3, -2, 1, -1, 0, 0)[frame_idx]
            chroma = int((1.0 - frame_idx / 7.0) * 16)

    pulse = 1.0 + math.exp(-p * 7.5) * 0.035 * energia
    if p > 0.28:
        pulse += math.sin(p * math.pi * 8.0) * 0.008 * energia
    scale *= pulse * (1.0 + 0.055 * max(0.0, beat_pulse))
    chroma += int(7 * max(0.0, beat_pulse))
    return {"scale": scale, "alpha": alpha, "dx": dx, "dy": dy, "chroma": chroma}


def ajustar_fonte(texto: str, fonte_path: str, max_width: int, max_height: int,
                   inicial: int = 430, minimo: int = 48) -> ImageFont.FreeTypeFont:
    tamanho = inicial
    probe = Image.new("L", (32, 32))
    draw = ImageDraw.Draw(probe)
    while tamanho >= minimo:
        font = ImageFont.truetype(fonte_path, tamanho)
        bb = draw.textbbox((0, 0), texto, font=font, stroke_width=2)
        if bb[2] - bb[0] <= max_width and bb[3] - bb[1] <= max_height:
            return font
        tamanho -= 8
    return ImageFont.truetype(fonte_path, minimo)


def _camada_texto(texto: str, fonte, style: dict, theme: dict, alpha: int = 255) -> Image.Image:
    fill = hex_rgb(style.get("fill", theme.get("accent", "#FFFFFF")))
    outline = hex_rgb(style.get("outline", "#050505"), (5, 5, 5))
    glow = hex_rgb(style.get("glow", theme.get("primary", "#7B1FA2")))
    shadow = hex_rgb(style.get("shadow", "#000000"), (0, 0, 0))
    ow = int(style.get("outline_width", 9))
    radius = int(style.get("glow_radius", 22))

    dummy = Image.new("RGBA", (16, 16))
    bb = ImageDraw.Draw(dummy).textbbox((0, 0), texto, font=fonte, stroke_width=ow)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    pad = max(70, radius * 3 + ow * 2)
    size = (w + pad * 2, h + pad * 2)
    origin = (pad - bb[0], pad - bb[1])

    mask = Image.new("RGBA", size, (0, 0, 0, 0))
    md = ImageDraw.Draw(mask)
    md.text(origin, texto, font=fonte, fill=(*glow, alpha),
            stroke_width=max(2, ow // 2), stroke_fill=(*glow, alpha))
    glow_far = mask.filter(ImageFilter.GaussianBlur(max(2, radius)))
    glow_near = mask.filter(ImageFilter.GaussianBlur(max(1, radius // 3)))

    result = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).text(
        (origin[0] + 10, origin[1] + 14), texto, font=fonte,
        fill=(*shadow, int(alpha * 0.76)), stroke_width=ow,
        stroke_fill=(*shadow, int(alpha * 0.76)))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(7))
    result = Image.alpha_composite(result, shadow_layer)
    result = Image.alpha_composite(result, glow_far)
    result = Image.alpha_composite(result, glow_near)

    crisp = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(crisp).text(
        origin, texto, font=fonte, fill=(*fill, alpha),
        stroke_width=ow, stroke_fill=(*outline, alpha))
    return Image.alpha_composite(result, crisp)


def _aplicar_write_on(layer: Image.Image, progresso: float, style: dict) -> tuple[Image.Image, int | None]:
    """Revela o texto da esquerda para a direita com borda macia e retorna a ponta luminosa."""
    dur = max(0.15, float(style.get("write_duration", 0.66)))
    frac = smoothstep(min(1.0, max(0.0, progresso / dur)))
    if frac >= 0.999:
        return layer, None

    edge = int(layer.width * frac)
    soft = max(6, int(style.get("write_softness", 28)))
    reveal = Image.new("L", layer.size, 0)
    rd = ImageDraw.Draw(reveal)
    full = max(0, edge - soft)
    if full > 0:
        rd.rectangle((0, 0, full, layer.height), fill=255)
    if edge > full:
        span = max(1, edge - full)
        for px in range(full, min(layer.width, edge + 1)):
            a = int(255 * (1.0 - (px - full) / span))
            rd.line((px, 0, px, layer.height), fill=max(0, min(255, a)))

    alpha = ImageChops.multiply(layer.getchannel("A"), reveal)
    out = layer.copy()
    out.putalpha(alpha)
    return out, edge


def _aplicar_letter_reveal(layer: Image.Image, texto: str, fonte,
                           progresso: float, style: dict) -> tuple[Image.Image, int | None]:
    """Revela caracteres em degraus, com uma pequena transicao dentro da letra atual."""
    dur = max(0.18, float(style.get("letter_duration", 0.64)))
    local = max(0.0, min(1.0, progresso / dur))
    if local >= 0.999 or not texto:
        return layer, None

    dummy = Image.new("L", (16, 16))
    d = ImageDraw.Draw(dummy)
    ow = int(style.get("outline_width", 8))
    radius = int(style.get("glow_radius", 28))
    bb = d.textbbox((0, 0), texto, font=fonte, stroke_width=ow)
    pad = max(70, radius * 3 + ow * 2)
    origin_x = pad - bb[0]
    pos = local * len(texto)
    completos = min(len(texto), int(pos))
    parcial = pos - completos
    prefixo = texto[:completos]
    px = d.textlength(prefixo, font=fonte)
    if completos < len(texto):
        char_w = max(1.0, d.textlength(texto[:completos + 1], font=fonte) - px)
        px += char_w * smoothstep(parcial)
    edge = int(origin_x + px + ow * 2)

    mask = Image.new("L", layer.size, 0)
    md = ImageDraw.Draw(mask)
    md.rectangle((0, 0, max(0, edge), layer.height), fill=255)
    alpha = ImageChops.multiply(layer.getchannel("A"), mask)
    out = layer.copy()
    out.putalpha(alpha)
    return out, edge


def _camada_outline_fill_animada(texto: str, fonte, style: dict, theme: dict,
                                  progresso: float, alpha: int = 255) -> Image.Image:
    """Acende contorno/glow primeiro e injeta o preenchimento depois."""
    fill = hex_rgb(style.get("fill", theme.get("accent", "#FFFFFF")))
    outline = hex_rgb(style.get("outline", "#050505"), (5, 5, 5))
    glow = hex_rgb(style.get("glow", theme.get("primary", "#7B1FA2")))
    ow = int(style.get("outline_width", 9))
    radius = int(style.get("glow_radius", 22))

    dummy = Image.new("RGBA", (16, 16))
    dd = ImageDraw.Draw(dummy)
    bb = dd.textbbox((0, 0), texto, font=fonte, stroke_width=ow)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    pad = max(70, radius * 3 + ow * 2)
    size = (w + pad * 2, h + pad * 2)
    origin = (pad - bb[0], pad - bb[1])

    outline_dur = max(0.12, float(style.get("outline_duration", 0.42)))
    fill_dur = max(0.12, float(style.get("fill_duration", 0.30)))
    outline_p = smoothstep(min(1.0, progresso / outline_dur))
    fill_start = outline_dur * 0.72
    fill_p = smoothstep(min(1.0, max(0.0, (progresso - fill_start) / fill_dur)))

    result = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ga = int(alpha * outline_p)
    ImageDraw.Draw(glow_layer).text(
        origin, texto, font=fonte, fill=(*glow, 0),
        stroke_width=max(2, ow // 2), stroke_fill=(*glow, ga))
    result = Image.alpha_composite(result, glow_layer.filter(ImageFilter.GaussianBlur(radius)))
    result = Image.alpha_composite(result, glow_layer.filter(ImageFilter.GaussianBlur(max(1, radius // 3))))

    crisp = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(crisp).text(
        origin, texto, font=fonte, fill=(*fill, int(alpha * fill_p)),
        stroke_width=ow, stroke_fill=(*outline, ga))
    return Image.alpha_composite(result, crisp)


def _trace_geometry(texto: str, fonte, style: dict):
    ow = int(style.get("outline_width", 8))
    radius = int(style.get("glow_radius", 30))
    key = (texto, str(getattr(fonte, "path", "")), int(fonte.size), ow, radius)
    cached = _TRACE_CACHE.get(key)
    if cached is not None:
        return cached

    dummy = Image.new("L", (16, 16))
    dd = ImageDraw.Draw(dummy)
    bb = dd.textbbox((0, 0), texto, font=fonte, stroke_width=ow)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    pad = max(70, radius * 3 + ow * 2)
    size = (w + pad * 2, h + pad * 2)
    origin = (pad - bb[0], pad - bb[1])
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).text(origin, texto, font=fonte, fill=255, stroke_width=1, stroke_fill=255)
    arr = np.asarray(mask, dtype=np.uint8)
    contours, _ = cv2.findContours(arr, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    parts = []
    for contour in contours:
        if len(contour) < 12 or cv2.contourArea(contour) < 10:
            continue
        pts = contour[:, 0, :]
        step = max(1, len(pts) // 450)
        pts = pts[::step]
        if len(pts) < 2:
            continue
        pts = np.vstack([pts, pts[0]])
        diff = np.diff(pts.astype(np.float32), axis=0)
        seg = np.sqrt((diff * diff).sum(axis=1))
        length = float(seg.sum())
        x, y, bw, bh = cv2.boundingRect(contour)
        parts.append((x, y, pts, seg, length))
    parts.sort(key=lambda item: (item[0], item[1]))
    total = sum(item[4] for item in parts) or 1.0
    result = (size, parts, total)
    if len(_TRACE_CACHE) > 64:
        _TRACE_CACHE.clear()
    _TRACE_CACHE[key] = result
    return result


def _camada_trace_write(texto: str, fonte, style: dict, theme: dict,
                        progresso: float, energia: float, alpha: int = 255) -> Image.Image:
    """Percorre o contorno real dos glifos com uma ponta de neon e preenche ao final."""
    full = _camada_texto(texto, fonte, style, theme, alpha)
    size, parts, total = _trace_geometry(texto, fonte, style)
    if full.size != size:
        size = full.size

    trace_dur = max(0.20, float(style.get("trace_duration", 0.68)))
    trace_p = smoothstep(min(1.0, max(0.0, progresso / trace_dur)))
    target = total * trace_p
    fill_after = max(0.0, min(0.88, float(style.get("fill_after", 0.56))))
    fill_p = smoothstep(min(1.0, max(0.0, (progresso - fill_after) / max(0.08, 1.0 - fill_after))))

    base = full.copy()
    base_alpha = base.getchannel("A").point(lambda px: int(px * fill_p))
    base.putalpha(base_alpha)

    trace = Image.new("RGBA", size, (0, 0, 0, 0))
    td = ImageDraw.Draw(trace)
    cor = hex_rgb(style.get("glow", theme.get("primary", "#C86DFF")))
    width = max(2, int(style.get("trace_width", 5)))
    remaining = target
    tip = None
    for _, _, pts, segs, length in parts:
        if remaining <= 0:
            break
        if remaining >= length:
            seq = [tuple(map(int, p)) for p in pts]
            td.line(seq, fill=(*cor, 245), width=width, joint="curve")
            tip = seq[-1]
            remaining -= length
            continue
        used = 0.0
        seq = [tuple(map(float, pts[0]))]
        for i, slen in enumerate(segs):
            slen = float(slen)
            if used + slen <= remaining:
                seq.append(tuple(map(float, pts[i + 1])))
                used += slen
                continue
            frac = 0.0 if slen <= 1e-6 else (remaining - used) / slen
            p0 = pts[i].astype(np.float32)
            p1 = pts[i + 1].astype(np.float32)
            p = p0 + (p1 - p0) * max(0.0, min(1.0, frac))
            seq.append((float(p[0]), float(p[1])))
            break
        if len(seq) >= 2:
            seq_i = [(int(x), int(y)) for x, y in seq]
            td.line(seq_i, fill=(*cor, 250), width=width, joint="curve")
            tip = seq_i[-1]
        break

    if tip is not None and trace_p < 0.995:
        r = max(7, int(9 + energia * 7))
        td.ellipse((tip[0]-r, tip[1]-r, tip[0]+r, tip[1]+r), fill=(255, 255, 255, 250))
    glow_far = trace.filter(ImageFilter.GaussianBlur(max(8, int(style.get("glow_radius", 30) * 0.72))))
    glow_near = trace.filter(ImageFilter.GaussianBlur(5))
    return Image.alpha_composite(Image.alpha_composite(Image.alpha_composite(base, glow_far), glow_near), trace)


def _write_head(canvas_size, x: int, y: int, cor_hex: str, energia: float) -> Image.Image:
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    cor = hex_rgb(cor_hex)
    d = ImageDraw.Draw(layer)
    r = max(7, int(10 + energia * 7))
    d.ellipse((x-r, y-r, x+r, y+r), fill=(255, 255, 255, 245))
    d.line((x-42, y, x+42, y), fill=(*cor, 220), width=3)
    d.line((x, y-24, x, y+24), fill=(255, 255, 255, 180), width=2)
    glow = layer.filter(ImageFilter.GaussianBlur(18))
    return Image.alpha_composite(glow, layer)


def render_texto_cinetico(
    texto: str,
    fonte_path: str,
    style: dict,
    theme: dict,
    progresso: float,
    frame_idx: int,
    energia: float,
    canvas_size=(1920, 1080),
    layout: str = "hero_center",
    beat_pulse: float = 0.0,
) -> tuple[Image.Image, dict]:
    largura, altura = canvas_size
    max_w = int(largura * (0.88 if layout == "impact_fullscreen" else 0.82))
    max_h = int(altura * 0.40)
    font = ajustar_fonte(texto, fonte_path, max_w, max_h)
    animacao = style.get("animation", "scale_punch")
    estado = estado_animacao(animacao, progresso, frame_idx, energia, beat_pulse)
    if animacao == "outline_fill":
        layer = _camada_outline_fill_animada(texto, font, style, theme, progresso, estado["alpha"])
    elif animacao == "trace_write":
        layer = _camada_trace_write(texto, font, style, theme, progresso, energia, estado["alpha"])
    else:
        layer = _camada_texto(texto, font, style, theme, estado["alpha"])

    scale = max(0.4, estado["scale"])
    if abs(scale - 1.0) > 0.002:
        layer = layer.resize(
            (max(1, int(layer.width * scale)), max(1, int(layer.height * scale))),
            Image.Resampling.LANCZOS)

    write_head_x = None
    if animacao == "write_on":
        layer, write_head_x = _aplicar_write_on(layer, progresso, style)
    elif animacao == "letter_reveal":
        layer, write_head_x = _aplicar_letter_reveal(layer, texto, font, progresso, style)

    if layout == "lyric_punchline":
        centro_y = int(altura * 0.43)
    elif layout == "impact_fullscreen":
        centro_y = int(altura * 0.49)
    else:
        centro_y = int(altura * 0.46)
    x = (largura - layer.width) // 2 + estado["dx"]
    y = centro_y - layer.height // 2 + estado["dy"]

    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    chroma = max(int(style.get("chromatic", 0)), estado["chroma"])
    if chroma and frame_idx < 10:
        a = max(0, int(140 * (1.0 - frame_idx / 10.0)))
        red = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        cyan = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        text_alpha = layer.getchannel("A").point(lambda px: int(px * a / 255))
        tint_r = Image.new("RGBA", layer.size, (255, 35, 60, 0))
        tint_c = Image.new("RGBA", layer.size, (0, 225, 255, 0))
        tint_r.putalpha(text_alpha)
        tint_c.putalpha(text_alpha)
        red.alpha_composite(tint_r, (x + chroma, y))
        cyan.alpha_composite(tint_c, (x - chroma, y))
        canvas = Image.alpha_composite(canvas, red)
        canvas = Image.alpha_composite(canvas, cyan)
    canvas.alpha_composite(layer, (x, y))
    if write_head_x is not None and write_head_x > 8:
        head_x = max(0, min(largura - 1, x + write_head_x))
        head_y = max(0, min(altura - 1, y + int(layer.height * 0.56)))
        head = _write_head(
            canvas_size, head_x, head_y,
            style.get("glow", theme.get("primary", "#A044FF")), energia)
        canvas = Image.alpha_composite(canvas, head)

    meta = {"bbox": (x, y, x + layer.width, y + layer.height), "font_size": font.size,
            "write_head_x": write_head_x}
    return canvas, meta


def render_underline(canvas_size, bbox, cor_hex: str, progresso: float, energia: float) -> Image.Image:
    largura, altura = canvas_size
    x1, _, x2, y2 = bbox
    margem = int((x2 - x1) * 0.10)
    x1 += margem
    x2 -= margem
    y = min(altura - 100, y2 - 30)
    reveal = smoothstep(min(1.0, progresso / 0.38))
    xf = int(x1 + (x2 - x1) * reveal)
    line = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if xf <= x1:
        return line
    cor = hex_rgb(cor_hex)
    d = ImageDraw.Draw(line)
    d.line((x1, y, xf, y), fill=(*cor, 235), width=max(5, int(7 + energia * 5)))
    r = int(8 + energia * 8)
    d.ellipse((xf-r, y-r, xf+r, y+r), fill=(255, 255, 255, 240))
    glow = line.filter(ImageFilter.GaussianBlur(16))
    return Image.alpha_composite(glow, line)
