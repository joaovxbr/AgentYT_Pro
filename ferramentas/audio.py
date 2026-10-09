#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audio.py — porteiro de AUDIO do canal VX RAPS.

Mede loudness (LUFS), true peak (dBTP), e clareza vocal do master.
O master do canal deve ter loudness entre -16 e -10 LUFS (padrao YouTube)
e true peak abaixo de -1.0 dBTP.

Comandos (CLI):
    python audio.py <arquivo>           # analise completa do audio
    python audio.py <arquivo> --json    # saida em JSON

Porteiro:
    LUFS < -16          -> muito baixo (YouTube vai amplificar e distorcer)
    LUFS > -10          -> muito alto (YouTube vai comprimir e clipar)
    true peak > -1.0    -> clipa no YouTube
    clareza vocal < 0.3 -> vocal abafado ou mascarado
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Alvos do canal (baseados em padrao YouTube + experimento)
# ---------------------------------------------------------------------------

LUFS_MIN = -16.0
LUFS_MAX = -10.0
LUFS_ALVO = -14.0
TRUE_PEAK_MAX = -1.0    # dBTP
CLAREZA_MIN = 0.3       # proxy de energia vocal (ratio 1-4kHz / total)

# limiares centralizados em config/porteiros.json[audio] (sem override por projeto)
from _vx import config as _vx_config  # noqa: E402
_P = _vx_config.porteiro("audio", {"lufs_min": LUFS_MIN, "lufs_max": LUFS_MAX, "lufs_alvo": LUFS_ALVO,
                                   "true_peak_max": TRUE_PEAK_MAX, "clareza_min": CLAREZA_MIN})
LUFS_MIN, LUFS_MAX, LUFS_ALVO = float(_P["lufs_min"]), float(_P["lufs_max"]), float(_P["lufs_alvo"])
TRUE_PEAK_MAX, CLAREZA_MIN = float(_P["true_peak_max"]), float(_P["clareza_min"])


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class RelatorioAudio:
    aprovado: bool
    lufs: float
    lufs_range: float          # delta entre min e max (quanto mais alto, mais dinamico)
    true_peak_dbtp: float
    sample_rate: int
    duracao: float
    clareza_vocal: float       # 0..1
    motivos: list[str]


# ---------------------------------------------------------------------------
# Medicoes via ffmpeg (loudness ITU-R BS.1770)
# ---------------------------------------------------------------------------

MEDICAO_FALHOU = (None, None, None)


def _medir_loudness(caminho: Path):
    """Roda ffmpeg loudnorm em modo de medicao.

    Retorna (lufs, lufs_range, true_peak_dbtp) ou MEDICAO_FALHOU. Antes devolvia
    (0, 0, 0) na falha e o porteiro APROVAVA em silencio (0 LUFS nao era testado).
    """
    ff = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ff, "-hide_banner", "-nostats",
        "-i", str(caminho),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    # loudnorm imprime o JSON no stderr no fim do processamento
    stderr = r.stderr or ""
    # encontrar o bloco JSON
    idx = stderr.rfind("{")
    if idx < 0:
        return MEDICAO_FALHOU
    fim = stderr.rfind("}") + 1
    if fim <= idx:
        return MEDICAO_FALHOU
    try:
        dados = json.loads(stderr[idx:fim])
        lufs = float(dados["input_i"])
        lufs_range = float(dados.get("input_lra", 0))  # loudness range (LU)
        tp = float(dados["input_tp"])  # true peak em dBTP
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return MEDICAO_FALHOU
    # -inf = silencio total: tambem nao e uma medicao aprovavel
    if not (np.isfinite(lufs) and np.isfinite(tp)):
        return MEDICAO_FALHOU
    return round(lufs, 2), round(lufs_range, 2), round(tp, 2)


def _medir_sample_rate(caminho: Path) -> int:
    """Obtem o sample rate do audio via ffprobe."""
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate",
        "-of", "default=nk=1:nw=1",
        str(caminho),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def _medir_clareza_vocal(caminho: Path) -> float:
    """Proxy de clareza vocal: ratio de energia na faixa 1-4kHz vs total.

    Vocal humano tem energia concentrada em 1-4kHz. Se essa faixa esta fraca
    em relacao ao total, o vocal esta abafado ou mascarado pelo instrumental.
    """
    ff = shutil.which("ffmpeg") or "ffmpeg"
    fd, tmp_nome = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    tmp_wav = Path(tmp_nome)
    try:
        # decodifica 10 segundos do meio do audio
        subprocess.run([
            ff, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", "30", "-t", "10",
            "-i", str(caminho),
            "-ac", "1", "-ar", "16000", "-f", "wav", str(tmp_wav),
        ], capture_output=True, timeout=30)

        if not tmp_wav.exists():
            return 0.5  # default neutro

        with wave.open(str(tmp_wav), "rb") as w:
            n = w.getnframes()
            raw = w.readframes(n)

        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        sr = 16000

        if len(x) < sr:
            return 0.5

        # FFT
        n_fft = min(len(x), sr * 4)  # max 4 segundos
        fft = np.abs(np.fft.rfft(x[:n_fft]))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

        # energia total
        energia_total = float(np.mean(fft ** 2) + 1e-10)
        # energia na faixa vocal (1-4 kHz)
        mascara_vocal = (freqs >= 1000) & (freqs <= 4000)
        energia_vocal = float(np.mean(fft[mascara_vocal] ** 2) + 1e-10)

        clareza = energia_vocal / energia_total
        return round(float(np.clip(clareza, 0.0, 1.0)), 3)
    except Exception:
        return 0.5
    finally:
        try:
            tmp_wav.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Analise principal
# ---------------------------------------------------------------------------

def analisar(caminho: Path) -> RelatorioAudio:
    """Analise completa de audio do master."""
    caminho = Path(caminho)
    if not caminho.exists():
        return RelatorioAudio(
            aprovado=False, lufs=0, lufs_range=0, true_peak_dbtp=0,
            sample_rate=0, duracao=0, clareza_vocal=0,
            motivos=[f"arquivo nao encontrado: {caminho}"],
        )

    # duracao via ffprobe
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    r = subprocess.run([
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1", str(caminho),
    ], capture_output=True, text=True, timeout=15)
    try:
        duracao = round(float(r.stdout.strip()), 2)
    except ValueError:
        duracao = 0.0

    sample_rate = _medir_sample_rate(caminho)
    lufs, lufs_range, tp = _medir_loudness(caminho)
    clareza = _medir_clareza_vocal(caminho)

    motivos = []
    if lufs is None:
        # falha fechada: sem medicao nao ha como afirmar que o master esta ok
        motivos.append("medicao de loudness/true peak falhou (ffmpeg loudnorm sem resultado)")
        lufs, lufs_range, tp = 0.0, 0.0, 0.0
    else:
        if lufs < LUFS_MIN:
            motivos.append(f"loudness muito baixo: {lufs:.1f} LUFS (< {LUFS_MIN})")
        if lufs > LUFS_MAX:
            motivos.append(f"loudness muito alto: {lufs:.1f} LUFS (> {LUFS_MAX})")
        if tp > TRUE_PEAK_MAX:
            motivos.append(f"true peak alto: {tp:.1f} dBTP (> {TRUE_PEAK_MAX})")
    if clareza < CLAREZA_MIN:
        motivos.append(f"clareza vocal baixa: {clareza:.2f} (< {CLAREZA_MIN})")

    aprovado = not motivos

    return RelatorioAudio(
        aprovado=aprovado,
        lufs=lufs, lufs_range=lufs_range,
        true_peak_dbtp=tp,
        sample_rate=sample_rate,
        duracao=duracao,
        clareza_vocal=clareza,
        motivos=motivos,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="audio.py")
    p.add_argument("arquivo")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    rel = analisar(Path(a.arquivo))
    if a.json:
        print(json.dumps({
            "aprovado": rel.aprovado,
            "lufs": rel.lufs,
            "lufs_range": rel.lufs_range,
            "true_peak_dbtp": rel.true_peak_dbtp,
            "sample_rate": rel.sample_rate,
            "duracao": rel.duracao,
            "clareza_vocal": rel.clareza_vocal,
            "motivos": rel.motivos,
        }, indent=2, ensure_ascii=False))
        return 0 if rel.aprovado else 1

    print(f"== audio: {Path(a.arquivo).name} ==")
    print(f"  loudness:   {rel.lufs:.1f} LUFS  (alvo: {LUFS_ALVO})")
    print(f"  true peak:  {rel.true_peak_dbtp:.1f} dBTP  (max: {TRUE_PEAK_MAX})")
    print(f"  sample rate: {rel.sample_rate} Hz")
    print(f"  duracao:    {rel.duracao}s")
    print(f"  clareza vocal: {rel.clareza_vocal:.2f}  (min: {CLAREZA_MIN})")
    if rel.aprovado:
        print("  APROVADO")
        return 0
    print("  REPROVADO:")
    for m in rel.motivos:
        print(f"    - {m}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
