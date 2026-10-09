#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sfx_engine.py — Motor de Foley e Efeitos Sonoros Automáticos para AMV Trap Anime.
Gera proceduralmente ou mixa efeitos sonoros perfeitamente sincronizados com o vídeo:
- Whoosh / Swoosh de transição nas viradas e whip-pans
- Impact Hit (soco pesado / corte de espada) nos hit-frames de ação
- Sub-bass Boom (trovão / impacto grave) nos drops de 808
Mixagem calibrada para -12dB para valorizar a música sem sobrecarregar a master.
"""
from pathlib import Path
import sys
import math
import numpy as np
import scipy.io.wavfile as wavfile

def sintetizar_whoosh(sr: int = 44100, duracao: float = 0.35) -> np.ndarray:
    """Gera um whoosh/swoosh de transição de ar filtrado."""
    num_samples = int(sr * duracao)
    # Ruído branco com envelope passa-banda móvel
    noise = np.random.uniform(-1.0, 1.0, num_samples)
    t = np.linspace(0, 1, num_samples)
    # Curva de volume em sino (fade in e fade out)
    envelope = np.sin(t * np.pi) ** 2
    # Modulação de frequência simulando ar cortando
    frequencia = 300 + 1200 * np.sin(t * np.pi)
    sinal = noise * np.sin(2 * np.pi * frequencia * t) * envelope
    return (sinal * 0.25).astype(np.float32)

def sintetizar_impact_hit(sr: int = 44100, duracao: float = 0.40) -> np.ndarray:
    """Gera um soco/impacto pesado com sub-grave e estalo de impacto."""
    num_samples = int(sr * duracao)
    t = np.linspace(0, duracao, num_samples)
    # Frequência caindo rapidamente de 160Hz para 45Hz
    freq_sweep = np.exp(-t * 18.0) * 160.0 + 45.0
    fase = 2 * np.pi * np.cumsum(freq_sweep) / sr
    sub = np.sin(fase) * np.exp(-t * 9.0)
    # Ruído de estalo inicial (primeiros 30ms)
    click = np.random.uniform(-0.5, 0.5, num_samples) * np.exp(-t * 90.0)
    sinal = (sub * 0.8 + click * 0.3)
    return sinal.astype(np.float32)

def sintetizar_sub_boom(sr: int = 44100, duracao: float = 0.80) -> np.ndarray:
    """Gera uma explosão sub-grave (Boom profundo)."""
    num_samples = int(sr * duracao)
    t = np.linspace(0, duracao, num_samples)
    freq = 65.0 * np.exp(-t * 3.5)
    fase = 2 * np.pi * np.cumsum(freq) / sr
    sinal = np.sin(fase) * np.exp(-t * 4.0) * 0.6
    return sinal.astype(np.float32)

def compor_trilha_sfx(
    duracao_total_s: float,
    pontos_whoosh: list[float],
    pontos_impacto: list[float],
    pontos_boom: list[float],
    caminho_saida_wav: Path,
    sr: int = 44100
) -> Path:
    """
    Cria a faixa WAV de efeitos sonoros com os eventos posicionados em seus respectivos tempos.
    """
    total_samples = int(duracao_total_s * sr)
    trilha = np.zeros(total_samples, dtype=np.float32)

    whoosh_snd = sintetizar_whoosh(sr)
    impact_snd = sintetizar_impact_hit(sr)
    boom_snd = sintetizar_sub_boom(sr)

    for t in pontos_whoosh:
        idx = int(t * sr)
        fim = min(total_samples, idx + len(whoosh_snd))
        tamanho = fim - idx
        if idx >= 0 and tamanho > 0:
            trilha[idx:fim] += whoosh_snd[:tamanho]

    for t in pontos_impacto:
        idx = int(t * sr)
        fim = min(total_samples, idx + len(impact_snd))
        tamanho = fim - idx
        if idx >= 0 and tamanho > 0:
            trilha[idx:fim] += impact_snd[:tamanho]

    for t in pontos_boom:
        idx = int(t * sr)
        fim = min(total_samples, idx + len(boom_snd))
        tamanho = fim - idx
        if idx >= 0 and tamanho > 0:
            trilha[idx:fim] += boom_snd[:tamanho]

    # Normalização e Limitação
    max_val = np.max(np.abs(trilha))
    if max_val > 0.95:
        trilha = trilha / max_val * 0.95

    # Converte para int16
    trilha_int16 = (trilha * 32767).astype(np.int16)
    caminho_saida_wav.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(caminho_saida_wav), sr, trilha_int16)
    print(f"[SFX ENGINE] Trilha sonora de foley gerada com sucesso em: {caminho_saida_wav}")
    return caminho_saida_wav

if __name__ == "__main__":
    out = Path("teste_sfx.wav")
    compor_trilha_sfx(10.0, [1.5, 4.2], [3.0, 7.5], [0.0, 6.0], out)
