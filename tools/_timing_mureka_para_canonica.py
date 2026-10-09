#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Converte os tempos do Mureka (linha a linha) em transcricao_canonica.json.

O Mureka entrega `start`/`end` de cada linha cantada (ms). Isso e timing real do
gerador, nao estimativa de ASR: melhor que Whisper para a sincronia. O sincronizar
usa este arquivo e PULA o alinhamento estatistico.

As palavras de cada linha sao distribuidas por proporcao de caracteres dentro da
linha (os tempos por palavra nao vem do Mureka; o karaoke POV precisa delas).
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PROJ = RAIZ / "projetos" / "megumi_shadows"
TEMPOS = PROJ / "entradas" / "_mureka_letra_tempos.json"
LINHAS = PROJ / "LETRA_LINHAS.txt"
SAIDA = PROJ / "transcricao_canonica.json"

# tags de secao nao sao cantadas
_BLOCO = re.compile(r"^\[.*\]$")


def _palavras(texto: str) -> list[str]:
    return [p for p in re.split(r"\s+", texto.strip()) if p]


def main() -> int:
    segs = json.loads(TEMPOS.read_text(encoding="utf-8"))
    letra = [l.strip() for l in LINHAS.read_text(encoding="utf-8").splitlines() if l.strip()]

    # achata rows cantadas (descarta as tags [Refrao])
    rows: list[dict] = []
    for s in segs:
        for r in s.get("rows", []):
            if _BLOCO.match(r["text"].strip()):
                continue
            rows.append(r)

    if len(rows) != len(letra):
        print(f"AVISO: mureka tem {len(rows)} versos, letra tem {len(letra)} linhas", file=sys.stderr)
        n = min(len(rows), len(letra))
        rows, letra = rows[:n], letra[:n]
        print(f"       alinhando as primeiras {n}", file=sys.stderr)

    linhas = []
    for r, texto_letra in zip(rows, letra):
        ini = float(r["start"]) / 1000.0
        fim = float(r["end"]) / 1000.0
        if fim <= ini:
            continue
        # grafia autoral vence (LETRA_LINHAS); o Mureka so da o tempo
        toks = _palavras(texto_letra)
        if not toks:
            continue
        pesos = [max(len(t), 1) for t in toks]
        total_peso = sum(pesos)
        dur = fim - ini
        words = []
        cursor = ini
        for t, p in zip(toks, pesos):
            wdur = dur * (p / total_peso)
            wend = min(cursor + wdur, fim)
            words.append({
                "word": t,
                "start": round(cursor, 3),
                "end": round(max(wend, cursor + 0.02), 3),
            })
            cursor = wend
        if words:
            words[-1]["end"] = round(fim, 3)
        linhas.append({
            "text": texto_letra,
            "start": round(ini, 3),
            "end": round(fim, 3),
            "words": words,
        })

    saida = {
        "lines": linhas,
        "model": "Mureka V9.5 (timing do gerador)",
        "lyrics_source": "LETRA_LINHAS.txt",
        "method": "start/end por linha do Mureka; palavras distribuidas por proporcao de caracteres",
        "song_id": 165358575091713,
        "share_key": "RoX6K7FboLyEb4chc4bJHK",
    }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"transcricao_canonica.json: {len(linhas)} linhas -> {SAIDA}")
    nw = sum(len(l['words']) for l in linhas)
    print(f"  {nw} palavras com tempo distribuido")
    # sanidade: monotonicidade
    prev = -1.0
    ruins = 0
    for l in linhas:
        if l["start"] < prev - 0.05:
            ruins += 1
        prev = l["start"]
    print(f"  linhas fora de ordem: {ruins}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
