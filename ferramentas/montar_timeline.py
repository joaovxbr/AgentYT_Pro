#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""montar_timeline.py — gera timeline.json cobrindo a musica sem lacunas.

Biblioteca; a porta e `estudio.py timeline <slug>`. Regras:

  - A letra_sincronizada.json da os tempos das linhas CANTADAS (lyric).
  - Os vaos (antes da 1a linha, entre linhas, e depois da ultima ate o fim do
    audio) viram segmentos 'gap'/'intro'/'outro'.
  - Cada segmento recebe um clipe de clips_raw, variando (nunca o mesmo clipe
    duas vezes seguidas) e respeitando a duracao da fonte: o offset 'src' anda
    dentro do clipe e reinicia quando chega perto do fim.
  - Cobre exatamente 0 .. duracao(audio); o validador exige isso.

A escolha de clipe aqui e simples e reproduzivel; a decisao editorial fina
(qual cena casa com qual verso) e da selecao_cenas depois. Aqui garantimos uma
timeline VALIDA e sem lacuna, que e o que o render exige.
"""
from __future__ import annotations

import json
from pathlib import Path

from timeline_clipe import duracao
from scene_intelligence import is_generated_asset


def _clipes_disponiveis(clips_dir: Path) -> list[dict]:
    clipes = []
    for p in sorted(clips_dir.glob("*.mp4")):
        if is_generated_asset(p):
            continue
        clipes.append({"nome": p.name, "dur": duracao(p)})
    return clipes


def _proximo_clipe(clipes, usados_seq, dur_seg, cursores):
    """Escolhe um clipe != do ultimo usado, com espaco suficiente a partir do cursor.

    Retorna (nome, src_inicio). Se nenhum clipe tem espaco continuo, reinicia o
    cursor do melhor candidato (src=0).
    """
    ultimo = usados_seq[-1] if usados_seq else None
    # ordena candidatos: primeiro os que NAO sao o ultimo, com mais folga
    def folga(c):
        return c["dur"] - cursores.get(c["nome"], 0.0)
    candidatos = [c for c in clipes if c["nome"] != ultimo] or clipes
    # prefere quem tem folga >= dur_seg; entre eles, o de maior folga
    com_espaco = [c for c in candidatos if folga(c) >= dur_seg + 0.05]
    if com_espaco:
        escolha = max(com_espaco, key=folga)
        src = cursores.get(escolha["nome"], 0.0)
    else:
        # ninguem tem folga continua: pega o de maior duracao e reinicia
        escolha = max(candidatos, key=lambda c: c["dur"])
        src = 0.0
    return escolha["nome"], src


EDICAO_PADRAO = {
    "max_plano_lyric": 2.6,    # AMV trap: corte a cada ~1.5-2.6 s na parte cantada
    "max_plano_outros": 3.2,   # intro/gap/outro respiram um pouco mais
    "min_plano": 0.9,
    "janela_snap": 0.35,       # fracao do passo em que um pico de 808 "puxa" o corte
    "fps": 30,
}


def subdividir(janelas: list[dict], batidas: list[float], cfg: dict | None = None) -> list[dict]:
    """Quebra janelas longas em planos menores, cortando no pico de 808 mais proximo.

    Mantem tipo/linha/texto em cada pedaco (o Scene Matcher escolhe uma cena
    diferente para cada um). Sem batidas, divide em partes iguais.
    """
    import math
    c = {**EDICAO_PADRAO, **(cfg or {})}
    fps = float(c["fps"])
    batidas = sorted(float(t) for t in batidas or [])
    out = []
    for j in janelas:
        a, b = float(j["start"]), float(j["end"])
        lim = float(c["max_plano_lyric"] if j["tipo"] == "lyric" else c["max_plano_outros"])
        if b - a <= lim:
            out.append(j)
            continue
        n = math.ceil((b - a) / lim)
        passo = (b - a) / n
        cortes, anterior = [], a
        for k in range(1, n):
            alvo = a + passo * k
            perto = [t for t in batidas if abs(t - alvo) <= passo * float(c["janela_snap"])]
            t = min(perto, key=lambda x: abs(x - alvo)) if perto else alvo
            t = round(t * fps) / fps
            if t - anterior >= float(c["min_plano"]) and b - t >= float(c["min_plano"]):
                cortes.append(t)
                anterior = t
        limites = [a, *cortes, b]
        for x, y in zip(limites, limites[1:]):
            out.append({**j, "start": x, "end": y})
    return out


def montar(projeto: Path, sync: list, audio: Path, batidas: list[float] | None = None,
           edicao: dict | None = None) -> dict:
    clips_dir = projeto / "clips_raw"
    clipes = _clipes_disponiveis(clips_dir)
    if not clipes:
        raise ValueError("nenhum clipe em clips_raw/")
    dur_audio = duracao(audio)

    # 1) monta a lista de janelas temporais (lyric + gaps) cobrindo 0..dur_audio
    janelas = []
    cursor = 0.0
    for i, linha in enumerate(sync):
        ini_raw = float(linha["start"])
        fim = float(linha["end"])

        # O alinhamento word-level pode produzir micro-gaps/overlaps de poucos
        # frames entre linhas. Para a timeline de edição, fronteiras abaixo de
        # 150 ms são "snapadas" ao cursor anterior; gaps maiores viram segmento.
        delta = ini_raw - cursor
        if delta > 0.15:
            janelas.append({"tipo": "intro" if i == 0 else "gap",
                            "start": cursor, "end": ini_raw,
                            "line": None, "text": ""})
            ini = ini_raw
        else:
            ini = cursor

        # Linha degenerada/inteiramente coberta por overlap anterior: ignora.
        if fim <= ini + 0.001:
            continue

        janelas.append({"tipo": "lyric", "start": ini, "end": fim,
                        "line": i, "text": linha.get("text", "")})
        cursor = fim
    if dur_audio - cursor > 0.15:
        janelas.append({"tipo": "outro", "start": cursor, "end": dur_audio,
                        "line": None, "text": ""})

    # ajusta a ultima janela para casar EXATO com o fim do audio
    if janelas:
        janelas[-1]["end"] = dur_audio
    if edicao is not False:
        janelas = subdividir(janelas, batidas or [], edicao if isinstance(edicao, dict) else None)

    # 2) atribui clipes por janela, variando e respeitando a fonte
    cursores = {}     # src atual por clipe
    usados_seq = []
    segments = []
    for j in janelas:
        dur_seg = j["end"] - j["start"]
        nome, src = _proximo_clipe(clipes, usados_seq, dur_seg, cursores)
        segments.append({
            "type": j["tipo"],
            "line": j["line"],
            "start": round(j["start"], 3),
            "end": round(j["end"], 3),
            "clip": nome,
            "src": round(src, 3),
            "cat": "ACTION" if j["tipo"] == "lyric" else "MOOD",
            "note": j["text"][:60],
            "duration": round(dur_seg, 3),
        })
        cursores[nome] = src + dur_seg
        usados_seq.append(nome)

    return {
        "audio_duration": round(dur_audio, 3),
        "audio": None,  # preenchido pela porta (caminho relativo do manifesto)
        "segments": segments,
    }
