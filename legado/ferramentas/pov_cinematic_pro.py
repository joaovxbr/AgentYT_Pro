#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX POV Cinematic Pro: evolução do preset oficial para Shorts 60 FPS."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_dispatch as rd
from legenda import filtro_subtitles
import pov_lyrics_bottom_v2 as base
import pov_lyrics_official as official

W, H = 1080, 1920
SCENE_Y = 620
SCENE_H = 608
LYRIC_Y = 1125
FPS = 60


def build_ass(canonical: Path, dest: Path, start: float, dur: float) -> Path:
    """Reusa a tipografia oficial, mas coloca a legenda dentro da cena principal."""
    old_y = official.LYRIC_Y
    official.LYRIC_Y = LYRIC_Y
    try:
        return official.build_ass(canonical, dest, start, dur)
    finally:
        official.LYRIC_Y = old_y


def _hero_window(start: float, hero_abs_start: float, hero_abs_end: float, dur: float) -> tuple[float, float]:
    a = max(0.0, hero_abs_start - start)
    b = min(dur, hero_abs_end - start)
    return a, max(a, b)


def render(source: Path, canonical: Path, hero_image: Path, output: Path,
           start: float, gancho: str, anime: str, tema: str,
           cor: str = '#7D2BFF', dur: float = 35.0,
           hero_abs_start: float = 62.18, hero_abs_end: float = 65.40) -> Path:
    """Render 9:16 em 60 FPS com Hero Shot pontual e áudio original contínuo."""
    output.parent.mkdir(parents=True, exist_ok=True)
    hero_a, hero_b = _hero_window(start, hero_abs_start, hero_abs_end, dur)
    with tempfile.TemporaryDirectory(prefix='vx_pov_cinematic_') as td:
        td = Path(td)
        overlay = base.make_overlay(td / 'overlay.png', gancho, anime, tema, cor)
        ass = build_ass(canonical, td / 'lyrics.ass', start, dur)
        sub = filtro_subtitles(ass)
        hero_enable = f"between(t,{hero_a:.3f},{hero_b:.3f})"
        fc = (
            f'[0:v]fps={FPS},split=2[bg][fg];'
            f'[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
            f'gblur=sigma=32:steps=3,eq=brightness=-0.27:saturation=0.92[b];'
            f'[fg]scale=1080:608:force_original_aspect_ratio=decrease,'
            f'pad=1080:608:(ow-iw)/2:(oh-ih)/2[s];'
            f'[b][s]overlay=0:{SCENE_Y}[v0];'
            f'[2:v]scale=1188:669:force_original_aspect_ratio=increase,crop=1188:669,'
            f'zoompan=z=min(zoom+0.0007\\,1.075):x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2):'
            f'd=1:s=1080x608:fps={FPS},eq=contrast=1.10:saturation=1.14:brightness=-0.02[hero];'
            f'[v0][hero]overlay=0:{SCENE_Y}:enable=\'{hero_enable}\'[vhero];'
            f'[vhero][1:v]overlay=0:0:format=auto[v1];'
            f'[v1]{sub},format=yuv420p[vout]'
        )
        rd.encode(
            str(output),
            ['-i', str(source), '-i', str(overlay),
             '-loop', '1', '-framerate', str(FPS), '-i', str(hero_image)],
            filtro_complexo=fc,
            mapa=['-map', '[vout]', '-map', '0:a:0'],
            args_audio=['-c:a', 'aac', '-b:a', '256k', '-ar', '48000'],
            args_extra=['-r', str(FPS), '-t', str(dur), '-shortest'],
        )
    return output


def render_sasuke_test(root: Path) -> Path:
    proj = root / 'projetos' / 'sasuke'
    outdir = proj / 'saidas' / 'shorts_20260928'
    return render(
        source=outdir / 'source_clean_34.95_35s.mp4',
        canonical=proj / 'transcricao_canonica.json',
        hero_image=root / 'temp_ato3_assets' / 'amaterasu_140.png',
        output=outdir / '13_VX_POV_CINEMATIC_PRO_TESTE.mp4',
        start=34.95,
        gancho='O ÓDIO DESPERTOU O VINGADOR',
        anime='Naruto Shippuden',
        tema='Vingador',
        cor='#7B1FA2',
        dur=35.0,
    )


if __name__ == '__main__':
    render_sasuke_test(Path(__file__).resolve().parents[1])
