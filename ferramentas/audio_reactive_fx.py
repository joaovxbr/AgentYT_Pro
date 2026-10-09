#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Graphics Pro: cache de picos 808 e envelope reativo por cena."""
from __future__ import annotations

import json
from pathlib import Path

from bass_shake import extrair_picos_subgrave


def resolver_audio(projeto: Path, manifesto: dict) -> Path | None:
    candidatos = []
    fonte = manifesto.get("audio_fonte")
    if fonte:
        p = Path(fonte)
        candidatos.append(p if p.is_absolute() else projeto / p)
    candidatos += [
        projeto / "entradas" / f"{projeto.name}_normalizado.wav",  # padrao de vx/projeto.audio
        projeto / "audio.wav",
        projeto / "entradas" / "audio.wav",
    ]
    for p in candidatos:
        if p.exists():
            return p
    return None


def _fingerprint(path: Path) -> dict:
    st = path.stat()
    return {"path": str(path.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def carregar_picos(projeto: Path, manifesto: dict, forcar: bool = False) -> list[dict]:
    audio = resolver_audio(projeto, manifesto)
    if not audio:
        return []
    qa = projeto / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    cache = qa / "vx_graphics_bass_peaks.json"
    fp = _fingerprint(audio)

    if cache.exists() and not forcar:
        try:
            dados = json.loads(cache.read_text(encoding="utf-8"))
            if dados.get("fingerprint") == fp:
                return list(dados.get("eventos", []))
        except Exception:
            pass

    eventos = extrair_picos_subgrave(str(audio))
    cache.write_text(json.dumps({
        "fingerprint": fp,
        "audio": str(audio),
        "eventos": eventos,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return eventos


def relativos(eventos: list[dict], inicio: float | None, duracao: float) -> list[dict]:
    if inicio is None:
        return []
    ini = float(inicio)
    fim = ini + float(duracao)
    saida = []
    for ev in eventos:
        t = float(ev.get("tempo", -1))
        if ini <= t <= fim:
            saida.append({
                "tempo": round(t - ini, 4),
                "intensidade": float(ev.get("intensidade", 0.0)),
                "duracao": float(ev.get("duracao", 0.16)),
            })
    return saida


def pulso_no_tempo(eventos: list[dict], tempo_local: float) -> float:
    """Envelope 0..1.25 com ataque imediato e decay curto depois do kick/808."""
    pico = 0.0
    for ev in eventos or []:
        dt = tempo_local - float(ev.get("tempo", 0.0))
        janela = max(0.08, float(ev.get("duracao", 0.16)) * 1.4)
        if 0.0 <= dt <= janela:
            intensidade = float(ev.get("intensidade", 0.0))
            env = intensidade * (1.0 - dt / janela) ** 1.7
            pico = max(pico, env)
    return min(1.25, pico)
