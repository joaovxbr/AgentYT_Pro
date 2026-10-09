#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renderizador VX Graphics Pro de cenas de impacto e tipografia cinetica."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

import render_dispatch as rd
from audio_reactive_fx import pulso_no_tempo
from background_fx_engine import render_background_frame, render_energy_ring
from font_manager import font_pairing
from kinetic_typography import (
    hex_rgb,
    render_texto_cinetico,
    render_underline,
    smoothstep,
)
from style_preset_engine import montar_spec_design, normalizar

WIDTH, HEIGHT, FPS = 1920, 1080, 30


def _manifesto(projeto_dir: Path) -> dict:
    p = projeto_dir / "projeto.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def enriquecer_spec(spec: dict, projeto_dir: Path) -> dict:
    if spec.get("engine") == "vx_graphics_pro" and spec.get("style"):
        return dict(spec)
    manifesto = _manifesto(projeto_dir)
    base = montar_spec_design(
        palavra=spec.get("keyword_dominante", "IMPACTO"),
        slug=spec.get("slug", projeto_dir.name),
        manifesto=manifesto,
        texto_secundario=spec.get("texto_secundario", ""),
        duracao=spec.get("duracao", 1.8),
        energia=spec.get("energia", 0.85),
        preset=spec.get("preset", "auto"),
        layout=spec.get("layout", "auto"),
    )
    for chave in ("id", "tempo_inicio", "suporte", "transicao_in", "transicao_out"):
        if chave in spec:
            base[chave] = spec[chave]
    return base


def _fit_secondary(texto: str, font_path: str, max_width: int, start=68):
    probe = Image.new("L", (16, 16))
    d = ImageDraw.Draw(probe)
    size = start
    while size >= 34:
        font = ImageFont.truetype(font_path, size)
        bb = d.textbbox((0, 0), texto, font=font, stroke_width=2)
        if bb[2] - bb[0] <= max_width:
            return font
        size -= 3
    return ImageFont.truetype(font_path, 34)


def _secondary_layer(texto: str, font_path: str, theme: dict, progresso: float,
                     layout: str, keyword: str = "", highlight: str | None = None) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    if not texto:
        return layer
    font = _fit_secondary(texto, font_path, int(WIDTH * 0.72))
    d = ImageDraw.Draw(layer)
    words = texto.split()
    space = d.textlength(" ", font=font)
    widths = [d.textlength(w, font=font) for w in words]
    total = sum(widths) + space * max(0, len(words) - 1)
    x = (WIDTH - int(total)) // 2
    y = int(HEIGHT * (0.72 if layout != "impact_fullscreen" else 0.78))
    alpha = int(235 * smoothstep(min(1.0, max(0.0, (progresso - 0.12) / 0.28))))
    accent = hex_rgb(highlight or theme.get("secondary", "#00E5FF"))
    key = normalizar(keyword)
    for word, ww in zip(words, widths):
        active = bool(key and normalizar(word) == key)
        if active:
            glow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            ImageDraw.Draw(glow).text((x, y), word, font=font, fill=(*accent, alpha),
                                      stroke_width=3, stroke_fill=(*accent, alpha))
            layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(12)))
        ImageDraw.Draw(layer).text(
            (x, y), word, font=font,
            fill=(*accent, alpha) if active else (238, 238, 238, alpha),
            stroke_width=3, stroke_fill=(5, 5, 8, alpha))
        x += int(ww + space)
    return layer


def _support_layer(texto: str, font_path: str, theme: dict, progresso: float):
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    if not texto:
        return layer
    font = ImageFont.truetype(font_path, 30)
    d = ImageDraw.Draw(layer)
    label = texto.upper()
    bb = d.textbbox((0, 0), label, font=font)
    tw = bb[2] - bb[0]
    alpha = int(150 * smoothstep(min(1.0, progresso / 0.45)))
    cor = hex_rgb(theme.get("primary", "#7B1FA2"))
    d.rounded_rectangle(
        ((WIDTH-tw)//2-22, int(HEIGHT*.84)-8,
         (WIDTH+tw)//2+22, int(HEIGHT*.84)+44),
        radius=12, fill=(4, 4, 8, int(alpha*.56)),
        outline=(*cor, alpha), width=2)
    d.text(((WIDTH-tw)//2, int(HEIGHT*.84)), label, font=font,
           fill=(230, 230, 235, alpha))
    return layer


def _flash_layer(frame_idx: int, energia: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    if frame_idx > 2:
        return layer
    alpha = int((3 - frame_idx) / 3 * 150 * energia)
    return Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, alpha))


def renderizar_frame(spec: dict, frame_idx: int, total_frames: int,
                     fonts: dict) -> Image.Image:
    progresso = frame_idx / max(1, total_frames - 1)
    energia = float(spec.get("energia", 0.85))
    tempo_local = frame_idx / FPS
    beat_pulse = pulso_no_tempo(spec.get("beat_events", []), tempo_local)
    theme = spec["theme_config"]
    style = spec["style"]
    layout = spec.get("layout", "hero_center")

    frame = render_background_frame(spec, frame_idx, total_frames, (WIDTH, HEIGHT))
    if layout == "energy_ring":
        ring = render_energy_ring(
            (WIDTH, HEIGHT), frame_idx, total_frames,
            style.get("glow", theme.get("secondary", "#00E5FF")), energia)
        frame = Image.alpha_composite(frame, ring)

    texto, meta = render_texto_cinetico(
        spec["keyword_dominante"],
        fonts["dominant"]["arquivo"],
        style, theme, progresso, frame_idx, energia,
        (WIDTH, HEIGHT), layout, beat_pulse=beat_pulse)
    frame = Image.alpha_composite(frame, texto)

    staged_mode = style.get("animation") in (
        "write_on", "letter_reveal", "outline_fill", "trace_write")
    underline_prog = max(0.0, min(1.0, (progresso - 0.48) / 0.30)) if staged_mode else progresso
    secondary_prog = max(0.0, min(1.0, (progresso - 0.44) / 0.34)) if staged_mode else progresso
    support_prog = max(0.0, min(1.0, (progresso - 0.58) / 0.28)) if staged_mode else progresso

    if style.get("underline"):
        underline = render_underline(
            (WIDTH, HEIGHT), meta["bbox"],
            style.get("glow", theme.get("secondary", "#00E5FF")),
            underline_prog, energia)
        frame = Image.alpha_composite(frame, underline)

    sec = _secondary_layer(
        spec.get("texto_secundario", ""),
        fonts["secondary"]["arquivo"], theme, secondary_prog, layout,
        keyword=spec.get("keyword_dominante", ""), highlight=style.get("glow"))
    frame = Image.alpha_composite(frame, sec)

    support = _support_layer(
        spec.get("suporte", ""),
        fonts["support"]["arquivo"], theme, support_prog)
    frame = Image.alpha_composite(frame, support)

    if spec.get("audio_reactive", {}).get("flash"):
        frame = Image.alpha_composite(frame, _flash_layer(frame_idx, energia))
    if beat_pulse > 0.18:
        beat_alpha = min(72, int(64 * beat_pulse * energia))
        frame = Image.alpha_composite(
            frame, Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, beat_alpha)))
    return frame.convert("RGB")


def renderizar_cena_impacto(spec: dict, projeto_dir: Path, output_mp4: Path) -> Path:
    """Renderiza uma cena VX Graphics Pro e salva o plano visual ao lado do MP4."""
    projeto_dir = Path(projeto_dir)
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    spec = enriquecer_spec(spec, projeto_dir)
    total_frames = max(1, round(float(spec["duracao"]) * FPS))
    preset_nome = spec.get("preset", "")
    identidade = "ninja_lore" if preset_nome in (
        "neon_royal", "neon_write_on", "neon_letter_reveal",
        "neon_outline_fill", "neon_trace", "cinematic_gold") else "anime_trap"
    fonts = font_pairing(identidade)

    with tempfile.TemporaryDirectory(prefix="vx_graphics_") as tmp:
        pasta = Path(tmp)
        for frame_idx in range(total_frames):
            frame = renderizar_frame(spec, frame_idx, total_frames, fonts)
            frame.save(
                pasta / f"frame_{frame_idx:05d}.jpg",
                "JPEG", quality=94, subsampling=0, optimize=False)
        rd.encode(
            saida=str(output_mp4),
            entradas=["-framerate", str(FPS), "-i", str(pasta / "frame_%05d.jpg")],
            args_audio=["-an"],
            args_extra=["-r", str(FPS)],
            cq="17",
            silencioso=False,
        )

    plano = output_mp4.with_suffix(".design.json")
    plano.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_mp4


if __name__ == "__main__":
    # Laboratorio: python render_impact_scene.py <slug> <PALAVRA> ["frase de apoio"]
    import sys
    if len(sys.argv) < 3:
        sys.exit("Uso: python render_impact_scene.py <slug> <PALAVRA> [\"frase\"]")
    slug, palavra = sys.argv[1], sys.argv[2]
    frase = sys.argv[3] if len(sys.argv) > 3 else ""
    projeto = Path(__file__).resolve().parents[1] / "projetos" / slug
    spec = montar_spec_design(palavra, slug, _manifesto(projeto), frase, 1.8, 0.92)
    spec["suporte"] = "VX RAPS"
    out = projeto / "saidas" / f"vx_graphics_{palavra.lower()}.mp4"
    print(renderizar_cena_impacto(spec, projeto, out))
