#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ritmo.py — a grade musical do canal.

Mede o BPM e o beat do audio FINAL (nunca o original) por onset de energia +
autocorrelacao do envelope (FFT, O(n log n) — nada de np.correlate O(n^2), que
trava em faixas longas). Propoe uma grade de corte: uma fronteira por linha
cantada, encaixada no beat mais proximo.

    🔴 A letra diz QUAL imagem; o beat diz QUANDO ela entra.

Se a confianca da grade for < 0,25, NAO encaixa nada — grade errada e pior que
grade nenhuma.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np


@dataclass
class Grade:
    bpm: float
    periodo: float          # segundos por beat
    fase: float             # offset do primeiro downbeat
    confianca: float        # 0..1
    duracao: float


def _decodificar_mono(caminho: Path, sr: int = 22050) -> np.ndarray:
    """Decodifica o audio para mono float32 via ffmpeg -> wav temporario."""
    ff = shutil.which("ffmpeg") or "ffmpeg"
    tmp = Path(caminho).with_suffix(".ritmo.tmp.wav")
    subprocess.run(
        [ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(caminho),
         "-ac", "1", "-ar", str(sr), "-f", "wav", str(tmp)],
        check=True,
    )
    try:
        with wave.open(str(tmp), "rb") as w:
            n = w.getnframes()
            raw = w.readframes(n)
            sw = w.getsampwidth()
        if sw == 2:
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            x = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return x


def _envelope(x: np.ndarray, sr: int, hop: int = 256) -> np.ndarray:
    """Envelope de energia por janela (flux positivo)."""
    n_frames = len(x) // hop
    if n_frames == 0:
        return np.zeros(0, dtype=np.float32)
    seg = x[:n_frames * hop].reshape(n_frames, hop)
    e = np.sqrt(np.mean(seg * seg, axis=1) + 1e-9).astype(np.float32)
    flux = np.diff(e, prepend=e[:1])
    flux[flux < 0] = 0.0
    return flux


def _autocorr_fft(f: np.ndarray) -> np.ndarray:
    n = len(f)
    n2 = 1 << (int(np.ceil(np.log2(2 * n))))
    F = np.fft.rfft(f - f.mean(), n2)
    ac = np.fft.irfft(F * np.conj(F), n2)[:n]
    return ac


def medir_grade(caminho_audio: Path, sr: int = 22050) -> Grade:
    x = _decodificar_mono(Path(caminho_audio), sr)
    duracao = len(x) / sr
    hop = 256
    flux = _envelope(x, sr, hop)
    fps = sr / hop

    ac = _autocorr_fft(flux)
    # faixa de BPM plausivel para trap/rap: 70..180 bpm
    lag_min = int(fps * 60.0 / 180.0)
    lag_max = int(fps * 60.0 / 70.0)
    lag_max = min(lag_max, len(ac) - 1)
    if lag_max <= lag_min + 1:
        return Grade(0, 0, 0, 0.0, duracao)
    janela = ac[lag_min:lag_max]
    melhor_lag = lag_min + int(np.argmax(janela))
    periodo = melhor_lag / fps
    bpm = 60.0 / periodo if periodo > 0 else 0.0

    # confianca = pico relativo da autocorrelacao
    pico = ac[melhor_lag]
    base = np.median(np.abs(ac[lag_min:lag_max])) + 1e-9
    confianca = float(np.clip((pico / (base * 6.0)), 0.0, 1.0))

    # fase: posicao do primeiro grande onset dentro do primeiro periodo
    n_um_periodo = melhor_lag
    if n_um_periodo > 1 and n_um_periodo < len(flux):
        fase = float(np.argmax(flux[:n_um_periodo]) / fps)
    else:
        fase = 0.0

    return Grade(round(bpm, 1), round(periodo, 4), round(fase, 3),
                 round(confianca, 3), round(duracao, 2))


def encaixar(tempos: List[float], grade: Grade,
             tolerancia: float = 0.11) -> List[Optional[float]]:
    """Encaixa cada tempo no beat mais proximo, dentro da tolerancia (+-110 ms).

    Se a confianca da grade for < 0,25, devolve None em tudo (nao encaixa).
    """
    if grade.confianca < 0.25 or grade.periodo <= 0:
        return [None] * len(tempos)
    saida: List[Optional[float]] = []
    for t in tempos:
        k = round((t - grade.fase) / grade.periodo)
        beat = grade.fase + k * grade.periodo
        saida.append(round(beat, 3) if abs(beat - t) <= tolerancia else None)
    return saida
