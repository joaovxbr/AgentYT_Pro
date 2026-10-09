#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compositor NVENC: cor, ASS e mix; intro obrigatoria por padrao."""
from pathlib import Path
import json
import math
import subprocess
import tempfile
import render_dispatch as rd

RAIZ = Path(__file__).resolve().parents[1]
INTRO_OFICIAL = RAIZ / "assets/intro/Eu_preciso_criar_INTRO_para_o.mp4"


def inspecionar_midia(path):
    result = subprocess.run(
        [rd.ffprobe_bin(), "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        raise ValueError(f"Midia invalida: {path}\n{result.stderr[-1000:]}")
    info = json.loads(result.stdout)
    tipos = {s.get("codec_type") for s in info.get("streams", [])}
    duracao = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(duracao) or duracao <= 0:
        raise ValueError(f"Duracao invalida: {path}")
    return tipos, duracao


def compilar_e_renderizar_master_completo(
    slug: str, video_bruto_path: Path, audio_wav_path: Path,
    ass_legenda_path: Path, sfx_wav_path: Path = None,
    color_grade_estilo: str = "titan_fire", saida_master_path: Path = None,
    incluir_intro: bool = True,
) -> Path:
    from color_grade_pro import obter_filtro_color_grade
    from cinemascope_fx import gerar_filtro_cinemascope
    from legenda import filtro_ass

    video, audio, ass = map(Path, (video_bruto_path, audio_wav_path, ass_legenda_path))
    saida = Path(saida_master_path or f"master_{slug}_final.mp4").resolve()
    fontes = [video, audio, ass]
    if incluir_intro:
        fontes.append(INTRO_OFICIAL)
    if sfx_wav_path is not None:
        sfx_wav_path = Path(sfx_wav_path)
        fontes.append(sfx_wav_path)
    for path in fontes:
        if not path.is_file():
            raise FileNotFoundError(f"Entrada obrigatoria ausente: {path}")
        if path.resolve() == saida:
            raise ValueError("Saida nao pode sobrescrever uma entrada")
    tipos_v, dur_v = inspecionar_midia(video)
    tipos_a, dur_a = inspecionar_midia(audio)
    if "video" not in tipos_v or "audio" not in tipos_a:
        raise ValueError("Video e audio precisam dos streams correspondentes")
    if dur_v + 0.1 < dur_a:
        raise ValueError("Video bruto menor que a musica; corrija a timeline")
    if sfx_wav_path is not None and "audio" not in inspecionar_midia(sfx_wav_path)[0]:
        raise ValueError("SFX sem stream de audio")
    intro_duration = 0.0
    if incluir_intro:
        tipos_i, intro_duration = inspecionar_midia(INTRO_OFICIAL)
        if not {"video", "audio"}.issubset(tipos_i):
            raise ValueError("Intro oficial precisa de video e audio")
    inputs = ["-i", str(video), "-i", str(audio)]
    normalize = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
                 "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p")
    grade = obter_filtro_color_grade(color_grade_estilo)
    cinema = gerar_filtro_cinemascope(140, animacao_intro=True)
    graph = [f"[0:v]{normalize},trim=duration={dur_a},setpts=PTS-STARTPTS,"
             f"{grade},{cinema},{filtro_ass(ass)}[mv]",
             f"[1:a]aresample=48000,aformat=channel_layouts=stereo,"
             f"atrim=duration={dur_a},asetpts=PTS-STARTPTS[music]"]
    if sfx_wav_path is not None:
        inputs += ["-i", str(sfx_wav_path)]
        graph += ["[2:a]aresample=48000,aformat=channel_layouts=stereo,"
                  "asetpts=PTS-STARTPTS,volume=0.2511886432[sfx]",
                  "[music][sfx]amix=inputs=2:duration=first:normalize=0[ma]"]
    else:
        graph += ["[music]anull[ma]"]
    if incluir_intro:
        idx = 3 if sfx_wav_path is not None else 2
        inputs += ["-i", str(INTRO_OFICIAL)]
        graph += [f"[{idx}:v]{normalize},trim=duration={intro_duration},setpts=PTS-STARTPTS[iv]",
                  f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
                  f"apad,atrim=duration={intro_duration},asetpts=PTS-STARTPTS[ia]",
                  "[iv][ia][mv][ma]concat=n=2:v=1:a=1[v][a]"]
    else:
        graph += ["[mv]null[v]", "[ma]anull[a]"]
    saida.parent.mkdir(parents=True, exist_ok=True)
    # Validate before promoting; preserve an existing master even if probe fails.
    with tempfile.TemporaryDirectory(prefix="compositor_", dir=saida.parent) as work:
        candidato = Path(work) / "master.mp4"
        rd.encode(str(candidato), inputs, filtro_complexo=";".join(graph),
                  mapa=["-map", "[v]", "-map", "[a]"], cq="17",
                  args_extra=["-r", "30", "-fps_mode", "cfr"])
        tipos, dur = inspecionar_midia(candidato)
        if not {"video", "audio"}.issubset(tipos) or abs(dur - dur_a - intro_duration) > 0.2:
            raise RuntimeError("Master com streams ou duracao divergentes")
        candidato.replace(saida)
    print(f"[COMPOSITOR] Master {'com intro' if incluir_intro else 'sem intro'}: {saida}")
    return saida


# Loudness + true peak do master final.
# 1) loudnorm normaliza para -14 LUFS (centro do porteiro -16..-10 e alvo do
#    YouTube), evitando que a mistura intro (branding) + corpo caia abaixo de
#    -16 LUFS e reprove o gate de audio. TP=-1.5 ja segura o pico.
# 2) o limitador com oversampling 4x (192 kHz) e teto -2 dBFS (0.7943) absorve o
#    overshoot do AAC (~0.8 dB) e mantem o master abaixo de -1.0 dBTP.
LIMITADOR_TRUE_PEAK = ("loudnorm=I=-14:TP=-1.5:LRA=11,aresample=192000,"
                       "alimiter=limit=0.7943:attack=1:release=60:level=disabled,aresample=48000")


FADE_IN_MUSICA = 1.2
FADE_OUT_MUSICA = 2.5


def concatenar_intro(video_path, saida_path):
    """Concatena a intro oficial e um corpo ja finalizado, via NVENC."""
    video, saida = Path(video_path).resolve(), Path(saida_path).resolve()
    for path in (video, INTRO_OFICIAL):
        if not path.is_file():
            raise FileNotFoundError(f"Entrada obrigatoria ausente: {path}")
        if path.resolve() == saida:
            raise ValueError("Saida nao pode sobrescrever entrada")
    vt, vd = inspecionar_midia(video)
    it, duration = inspecionar_midia(INTRO_OFICIAL)
    if not {"video", "audio"}.issubset(vt & it):
        raise ValueError("Intro e corpo precisam de video e audio")
    normalize = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
                 "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,"
                 "setpts=PTS-STARTPTS")
    graph = (f"[0:v]{normalize}[iv];[1:v]{normalize}[mv];"
             f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,"
             f"atrim=duration={duration},asetpts=PTS-STARTPTS[ia];"
             f"[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,"
             f"atrim=duration={vd},asetpts=PTS-STARTPTS,"
             # musica entra suave no Title Card e sai com o End Card (AGENTS: musica continua)
             f"afade=t=in:st=0:d={FADE_IN_MUSICA},"
             f"afade=t=out:st={max(0.0, vd - FADE_OUT_MUSICA):.3f}:d={FADE_OUT_MUSICA}[ma];"
             "[iv][ia][mv][ma]concat=n=2:v=1:a=1[v][ac];"
             f"[ac]{LIMITADOR_TRUE_PEAK}[a]")
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="intro_", dir=saida.parent) as work:
        candidato = Path(work) / "master.mp4"
        rd.encode(str(candidato), ["-i", str(INTRO_OFICIAL), "-i", str(video)],
                  filtro_complexo=graph, mapa=["-map", "[v]", "-map", "[a]"],
                  cq="17", args_extra=["-r", "30", "-fps_mode", "cfr"])
        tipos, dur = inspecionar_midia(candidato)
        if not {"video", "audio"}.issubset(tipos) or abs(dur - vd - duration) > .2:
            raise RuntimeError("Concatenacao com streams ou duracao invalidos")
        candidato.replace(saida)
    return saida
