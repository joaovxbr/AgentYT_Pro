#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Graphics Pro: fundos e FX procedurais para takes de impacto."""
from __future__ import annotations

import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from kinetic_typography import hex_rgb


def _vertical_gradient(size, top, bottom):
    w, h = size
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    a = np.array(top, dtype=np.float32)[None, None, :]
    b = np.array(bottom, dtype=np.float32)[None, None, :]
    arr = (a * (1 - y) + b * y).astype(np.uint8)
    arr = np.repeat(arr, w, axis=1)
    alpha = np.full((h, w, 1), 255, dtype=np.uint8)
    return Image.fromarray(np.concatenate([arr, alpha], axis=2), "RGBA")


def _radial_glow(base: Image.Image, cor, centro, raio, alpha=150):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = centro
    for r in range(raio, 10, -28):
        frac = 1.0 - r / raio
        a = int(alpha * frac * frac)
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(*cor, a))
    return Image.alpha_composite(base, layer.filter(ImageFilter.GaussianBlur(18)))


def _speedlines(base: Image.Image, frame_idx: int, cor=(255, 255, 255), alpha=70):
    w, h = base.size
    cx, cy = w // 2, int(h * 0.46)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    offset = (frame_idx * 0.7) % 6
    for ang in np.arange(offset, 360 + offset, 6):
        rad = math.radians(float(ang))
        inner = 80 + int(28 * math.sin(rad * 5 + frame_idx * 0.11))
        x1 = cx + int(inner * math.cos(rad))
        y1 = cy + int(inner * math.sin(rad))
        x2 = cx + int(1400 * math.cos(rad))
        y2 = cy + int(1400 * math.sin(rad))
        d.line((x1, y1, x2, y2), fill=(*cor, alpha), width=2)
    return Image.alpha_composite(base, layer)


def _lightning(base: Image.Image, frame_idx: int, cor, energia: float):
    if frame_idx % 9 not in (0, 1, 2):
        return base
    rng = random.Random(731 + frame_idx // 3)
    w, h = base.size
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bolts = 2 if energia > 0.75 else 1
    for b in range(bolts):
        side = -1 if b % 2 == 0 else 1
        x = int(w * (0.16 if side < 0 else 0.84))
        y = -30
        pts = [(x, y)]
        for _ in range(9):
            x += rng.randint(-65, 65)
            y += rng.randint(70, 125)
            pts.append((x, y))
        d.line(pts, fill=(*cor, 230), width=5)
        d.line(pts, fill=(255, 255, 255, 245), width=2)
    glow = layer.filter(ImageFilter.GaussianBlur(18))
    return Image.alpha_composite(Image.alpha_composite(base, glow), layer)


def _particles(base: Image.Image, frame_idx: int, tipo: str, cor, energia: float):
    if tipo in ("", "none", None):
        return base
    w, h = base.size
    rng = random.Random(1907 + frame_idx)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    n = int(24 + 34 * energia)
    for i in range(n):
        x = rng.randrange(0, w)
        drift = frame_idx * (2 + i % 4)
        y = (rng.randrange(0, h + 300) - drift) % (h + 220) - 110
        r = rng.randint(1, 4)
        if tipo == "embers":
            c = (255, rng.randint(70, 170), 30)
        elif tipo == "digital":
            c = (60, 220, 255)
            d.rectangle((x, y, x + rng.randint(8, 28), y + 2), fill=(*c, rng.randint(80, 190)))
            continue
        elif tipo == "paper_dust":
            c = (230, 226, 210)
        else:
            c = cor
        d.ellipse((x-r, y-r, x+r, y+r), fill=(*c, rng.randint(80, 220)))
    return Image.alpha_composite(base, layer.filter(ImageFilter.GaussianBlur(0.7)))


def render_background_frame(spec: dict, frame_idx: int, total_frames: int,
                            size=(1920, 1080)) -> Image.Image:
    w, h = size
    theme = spec.get("theme_config", {})
    style = spec.get("style", {})
    modo = spec.get("background", style.get("background", "void_eclipse"))
    energia = float(spec.get("energia", 0.8))
    primary = hex_rgb(theme.get("primary", "#7B1FA2"))
    secondary = hex_rgb(theme.get("secondary", "#00E5FF"))
    danger = hex_rgb(theme.get("danger", "#E53935"))
    p = frame_idx / max(1, total_frames - 1)

    if modo == "blood_eclipse":
        base = _vertical_gradient(size, (5, 2, 7), (24, 0, 4))
        cor = danger
    elif modo == "fire_smoke":
        base = _vertical_gradient(size, (7, 3, 2), (35, 8, 1))
        cor = hex_rgb("#FF6A18")
    elif modo == "storm_radial":
        base = _vertical_gradient(size, (2, 8, 20), (8, 3, 22))
        cor = secondary
    elif modo == "royal_dark":
        base = _vertical_gradient(size, (11, 8, 4), (28, 18, 5))
        cor = hex_rgb("#FFCB52")
    else:
        base = _vertical_gradient(size, (6, 5, 12), (18, 8, 28))
        cor = primary

    pulse = 0.82 + 0.18 * math.sin(p * math.pi * 4) ** 2
    raio = int(min(w, h) * (0.39 + 0.04 * pulse))
    base = _radial_glow(base, cor, (w // 2, int(h * 0.46)), raio,
                        alpha=int(125 + 65 * energia))

    if modo in ("void_eclipse", "blood_eclipse", "royal_dark"):
        ring = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ring)
        rr = int(300 + 18 * math.sin(p * math.pi * 4))
        d.ellipse((w//2-rr, int(h*.46)-rr, w//2+rr, int(h*.46)+rr),
                  fill=(*cor, 28), outline=(*cor, 100), width=3)
        base = Image.alpha_composite(base, ring.filter(ImageFilter.GaussianBlur(5)))

    if modo == "speedlines_manga":
        base = _speedlines(base, frame_idx, (245, 245, 245), 88)
    elif modo == "storm_radial":
        base = _speedlines(base, frame_idx, secondary, 32)
        base = _lightning(base, frame_idx, secondary, energia)
    elif modo == "void_noise":
        rng = np.random.default_rng(9000 + frame_idx // 2)
        noise = rng.integers(0, 32, (h, w, 1), dtype=np.uint8)
        tint = np.zeros((h, w, 4), dtype=np.uint8)
        tint[:, :, :3] = noise
        tint[:, :, 3] = 34
        base = Image.alpha_composite(base, Image.fromarray(tint, "RGBA"))

    base = _particles(base, frame_idx, style.get("particles", "energy"), cor, energia)

    vign = Image.new("L", size, 0)
    vd = ImageDraw.Draw(vign)
    vd.ellipse((-int(w*.12), -int(h*.35), int(w*1.12), int(h*1.35)), fill=225)
    vign = vign.filter(ImageFilter.GaussianBlur(150))
    dark = Image.new("RGBA", size, (0, 0, 0, 150))
    dark.putalpha(Image.eval(vign, lambda x: 255 - x))
    return Image.alpha_composite(base, dark)


def render_energy_ring(size, frame_idx: int, total_frames: int, cor_hex: str,
                       energia: float) -> Image.Image:
    w, h = size
    p = frame_idx / max(1, total_frames - 1)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cor = hex_rgb(cor_hex)
    radius = int(250 + 55 * math.sin(p * math.pi * 5) ** 2)
    alpha = int(90 + 100 * energia)
    d.ellipse((w//2-radius, int(h*.46)-radius, w//2+radius, int(h*.46)+radius),
              outline=(*cor, alpha), width=5)
    d.ellipse((w//2-radius-15, int(h*.46)-radius-15,
               w//2+radius+15, int(h*.46)+radius+15),
              outline=(*cor, alpha//3), width=2)
    return Image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(16)), layer)
