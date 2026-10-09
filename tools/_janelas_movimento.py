#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acha JANELAS DE MOVIMENTO nas fontes aprovadas de clips_raw.

Por que existe: escolher `de`/`ate` no olho (folha de contato) pega plano parado —
bonito no still, inutil no AMV. `auditar_fonte` reprova >35% congelado e o clipe
volta. Aqui a janela e escolhida pela MESMA metrica do porteiro (`dif` entre
quadros vizinhos, `imagem.analisar`), entao o que sai daqui ja nasce aprovavel.

Uso:
    python tools/_janelas_movimento.py <clipe.mp4> [--janela 8] [--top 6]
    python tools/_janelas_movimento.py --lote            # todos os reprovados

Le a metrica direto dos quadros amostrados; nao chama o porteiro (que reprova em
bloco) — devolve o ranking para o humano escolher.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import _vx  # noqa: F401  (instala ffmpeg no PATH)
import render_dispatch as rd  # noqa: E402

FPS = 2.0            # mesma taxa de amostra do porteiro
LARG, ALT = 320, 180  # resolucao de analise (barata)
LIMIAR_CONGELADO = 0.6


def _quadros(video: Path):
    cmd = [rd.ffmpeg_bin(), "-v", "error", "-i", str(video),
           "-vf", f"fps={FPS},scale={LARG}:{ALT}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.run(cmd, capture_output=True)
    tam = LARG * ALT * 3
    q = [p.stdout[i:i + tam] for i in range(0, len(p.stdout) - tam + 1, tam)]
    return np.frombuffer(b"".join(q), np.uint8).reshape(len(q), ALT, LARG, 3).astype(np.float32)


def movimento(video: Path) -> np.ndarray:
    """`dif[t]` = variacao media entre o quadro t-1 e t. Baixo = congelado."""
    f = _quadros(video)
    n = len(f)
    if n < 2:
        return np.zeros(n, np.float32)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2, 3))
    return np.concatenate([[d.mean() if len(d) else 0.0], d]).astype(np.float32)


def janelas(video: Path, largura_s: float = 8.0, top: int = 6) -> list[dict]:
    dif = movimento(video)
    n = len(dif)
    if n == 0:
        return []
    w = max(1, int(largura_s * FPS))
    if w >= n:
        w = n
    # media movel: media de dif dentro da janela
    cs = np.concatenate([[0.0], np.cumsum(dif)])
    out = []
    for ini in range(0, n - w + 1):
        m = float((cs[ini + w] - cs[ini]) / w)
        cong = float((dif[ini:ini + w] < LIMIAR_CONGELADO).mean() * 100)
        out.append({"de": round(ini / FPS, 1), "ate": round((ini + w) / FPS, 1),
                    "movimento": round(m, 3), "congelado_pct": round(cong, 1)})
    # sem sobreposicao: guloso pelo maior movimento
    out.sort(key=lambda j: -j["movimento"])
    escolhidas: list[dict] = []
    for j in out:
        if all(j["ate"] <= e["de"] or j["de"] >= e["ate"] for e in escolhidas):
            escolhidas.append(j)
        if len(escolhidas) >= top:
            break
    return sorted(escolhidas, key=lambda j: j["de"])


def _resolver_alvo(a: str, base: Path) -> Path:
    """Aceita caminho absoluto, relativo a raiz, nome solto ou ja com .mp4."""
    p = Path(a)
    if p.is_absolute() and p.is_file():
        return p
    for cand in (ROOT / p, base / p, base / (p.stem + ".mp4")):
        if cand.is_file():
            return cand
    if p.suffix.lower() != ".mp4":
        p = p.with_suffix(".mp4")
    return p


def main(argv: list[str]) -> int:
    base = ROOT / "projetos" / "megumi_shadows" / "clips_raw"
    largura, top = 8.0, 6
    if "--janela" in argv:
        largura = float(argv[argv.index("--janela") + 1])
    if "--top" in argv:
        top = int(argv[argv.index("--top") + 1])

    # so sao alvos os argumentos que NAO sao flags nem valores de flag
    consumidos = set()
    for flag in ("--janela", "--top"):
        if flag in argv:
            i = argv.index(flag)
            consumidos.update({i, i + 1})
    bruto = [a for i, a in enumerate(argv[1:], start=1)
             if i not in consumidos and not a.startswith("--")]

    if "--lote" in argv:
        alvos = sorted(base.glob("*.mp4"))
    else:
        alvos = [_resolver_alvo(a, base) for a in bruto]
    for v in alvos:
        if not v.is_file():
            print(f"?? {v}: nao existe")
            continue
        dif = movimento(v)
        dur = len(dif) / FPS
        print(f"\n=== {v.stem}  {dur:.1f}s  movimento medio {dif.mean():.2f}  "
              f"congelado {float((dif < LIMIAR_CONGELADO).mean() * 100):.1f}%")
        for j in janelas(v, largura, top):
            print(f"   {j['de']:7.1f} - {j['ate']:7.1f}  mov {j['movimento']:6.3f}  "
                  f"cong {j['congelado_pct']:5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
