#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bass_shake.py — Detecção de sub-grave (808/kick) e geração de shakes reativos.
Isola frequências sub-grave (<120Hz) do áudio musical e cria comandos FFmpeg de
distorção, aberração cromática e tremor sismico exatamente no impacto dos graves.
"""
from pathlib import Path
import json
import sys
import numpy as np
import librosa

def extrair_picos_subgrave(audio_path: str, limite_hz: float = 120.0, hop_length: int = 512) -> list[dict]:
    """
    Carrega o áudio, aplica filtro passa-baixa para isolar sub-grave (<120Hz)
    e detecta os instantes de pico (drops de 808 e bumbos pesados).
    """
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    
    # Espectrograma linear
    D = np.abs(librosa.stft(y, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr)
    
    # Máscara para sub-grave (<120Hz)
    idx_sub = freqs <= limite_hz
    sub_energy = np.sum(D[idx_sub, :], axis=0)
    
    # Onset strength no sub-grave
    sub_energy_norm = (sub_energy - np.min(sub_energy)) / (np.max(sub_energy) - np.min(sub_energy) + 1e-6)
    
    # Detecção de picos com limite adaptativo
    media = np.mean(sub_energy_norm)
    std = np.std(sub_energy_norm)
    limiar = media + 1.4 * std
    
    picos_idx = librosa.util.peak_pick(
        sub_energy_norm,
        pre_max=3, post_max=3,
        pre_avg=5, post_avg=5,
        delta=limiar * 0.4, wait=int(0.25 * sr / hop_length) # mín 0.25s entre graves
    )
    
    tempos = librosa.frames_to_time(picos_idx, sr=sr, hop_length=hop_length)
    
    eventos = []
    for t, idx in zip(tempos, picos_idx):
        intensidade = float(sub_energy_norm[idx])
        eventos.append({
            "tempo": round(float(t), 3),
            "intensidade": round(intensidade, 3),
            "duracao": 0.16 # ~5 frames de impacto
        })
        
    return eventos

def gerar_filtro_ffmpeg_bass_shake(
    eventos_grave: list[dict],
    duracao_total: float,
    largura: int = 1920,
    altura: int = 1080,
) -> str:
    """
    Gera expressão de filtro FFmpeg (crop + scale + rgbashift) com triggers de tempo
    ativados nos momentos exatos dos graves.
    """
    if not eventos_grave:
        return "null"

    condicoes = []
    for ev in eventos_grave:
        t_ini = ev["tempo"]
        t_fim = t_ini + ev["duracao"]
        condicoes.append(f"between(t,{t_ini:.3f},{t_fim:.3f})")

    trigger_expr = "+".join(condicoes)

    # Shake com aberração cromática leve (RGB split) no pico do grave
    filtro = (
        f"split=2[base][shake_layer];"
        f"[shake_layer]rgbashift=rh=8:rv=-4:bh=-8:bv=4[split_rgb];"
        f"[split_rgb]crop=in_w-30:in_h-30:15+15*sin(t*50):15+15*cos(t*50),scale={largura}:{altura}:flags=fast_bilinear[shaken];"
        f"[base][shaken]overlay=enable='{trigger_expr}'"
    )
    return filtro

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python bass_shake.py <audio.wav>")
        sys.exit(1)
    evs = extrair_picos_subgrave(sys.argv[1])
    print(f"Total de impactos sub-grave (808) detectados: {len(evs)}")
    if evs:
        print("Primeiros 5 impactos:", json.dumps(evs[:5], indent=2))
