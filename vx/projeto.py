"""Caminhos canonicos de um projeto, derivados do manifesto (`projeto.json`).

Problema que resolve: a esteira, a transcricao, a sincronia e o auditor de letra
montavam `entradas/<slug>_normalizado.wav` e `<slug>_normalizado_vocals.wav` na mao
e ignoravam `audio_fonte`. Um projeto com outro nome de audio quebrava em 9 lugares.

Regra: `audio_fonte` do manifesto vence; sem ele, `entradas/<slug>_normalizado.wav`.
Stems: `entradas/stems/<nome-do-audio-sem-extensao>_<tipo>.wav` (saida do Demucs).
"""
from __future__ import annotations

import json
from pathlib import Path

TIPOS_STEM = ("vocals", "drums", "bass", "other")


def manifesto(projeto: Path) -> dict:
    try:
        dados = json.loads((Path(projeto) / "projeto.json").read_text(encoding="utf-8-sig"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def audio(projeto: Path, m: dict | None = None) -> Path:
    projeto = Path(projeto)
    m = manifesto(projeto) if m is None else m
    rel = m.get("audio_fonte") or f"entradas/{projeto.name}_normalizado.wav"
    p = Path(rel)
    return p if p.is_absolute() else projeto / p


def stems_dir(projeto: Path) -> Path:
    return Path(projeto) / "entradas" / "stems"


def stem(projeto: Path, tipo: str, m: dict | None = None) -> Path:
    if tipo not in TIPOS_STEM:
        raise ValueError(f"stem invalido: {tipo}")
    return stems_dir(projeto) / f"{audio(projeto, m).stem}_{tipo}.wav"


def stems(projeto: Path, m: dict | None = None) -> list[Path]:
    return [stem(projeto, t, m) for t in TIPOS_STEM]
