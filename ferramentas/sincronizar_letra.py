#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sincronizar_letra.py — SISTEMA NOVO de sincronia WORD-LEVEL.

O problema antigo: casar a letra oficial com os TEMPOS DOS SEGMENTOS do Whisper
(blocos de 3-7s) deixava a legenda fora do tempo e trechos sem legenda.

A solucao: alinhar cada LINHA da letra oficial as PALAVRAS individuais cantadas
(word_timestamps do Whisper) por similaridade fonetica, e tirar o start/end da
linha da 1a e ultima palavra casada. Assim:
- cada linha entra exatamente quando comeca a ser cantada
- cada linha sai quando a ultima palavra dela termina
- nenhum trecho vocal fica sem legenda (validador de cobertura)

Uso:
    python sincronizar_letra.py <projeto_dir>
      le: <dir>/transcricao.json (words) + <dir>/LETRA_LINHAS.txt (uma linha por verso)
      gera: <dir>/letra_sincronizada.json  (start,end,text,keyword por linha)

LETRA_LINHAS.txt: a letra OFICIAL, uma frase cantada por linha, na ordem.
Marque a palavra-chave com <<PALAVRA>>.
"""
import sys, json, re, unicodedata
from pathlib import Path
from difflib import SequenceMatcher


# Tags cujo corpo é prosa (estilo/metadata), não verso cantado: o que vem depois
# delas até a próxima tag é ignorado por `extrair_linhas_suno`.
_BLOCO_NAO_LIRICO = ("style", "meta", "creditos", "credits", "descricao", "description")


def extrair_linhas_suno(texto):
    """Return only sung lyric lines; Suno bracket tags are directions.

    Prosa que VEM DEPOIS de uma tag não-lírica (`[Style of Music]` e afins) até a
    próxima tag é descrição de estilo, não verso cantado. Sem isso o parágrafo de
    style do `suno_lyrics.txt` virava "linha da letra": a transcrição canônica do
    Asta (05/10/2026) leu as 5 linhas de style e a legenda queimada saiu com
    "anime battle energy, male vocalist..." no master.
    """
    linhas, bloqueado = [], False
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("["):
            tag = normalizar(linha.strip("[]"))
            bloqueado = any(tag.startswith(b) for b in _BLOCO_NAO_LIRICO)
            continue
        if bloqueado:
            continue
        linhas.append(linha)
    return linhas


def vocabulario_do_manifesto(manifesto):
    """Grafia canonica de nomes do anime, vinda de `projeto.json -> vocabulario`.

    Formato: {"termos": ["Mangekyō", "Danzō", ...], "variantes": {"tomoes": "tomoe"}}.
    Cada termo casa com sua forma sem acento/maiuscula ("mangekyo" -> "Mangekyō").
    Antes o vocabulario do Sasuke era fixo no codigo e valia para todo anime.
    """
    voc = (manifesto or {}).get("vocabulario") or {}
    mapa = {normalizar(t): t for t in voc.get("termos", []) if normalizar(t)}
    mapa.update({normalizar(k): v for k, v in (voc.get("variantes") or {}).items() if normalizar(k)})
    return mapa


def corrigir_vocabulario_canonico(texto, vocabulario):
    """Normaliza so os nomes do vocabulario do projeto; nunca usa a grafia do ASR."""
    if not vocabulario:
        return texto

    def repl(match):
        raw = match.group(0)
        return vocabulario.get(normalizar(raw), raw)
    return re.sub(r"\b[\wÀ-ÿōŌ]+\b", repl, texto, flags=re.UNICODE)


def _tokens_linha(linha):
    return re.findall(r"[^\s]+", linha.strip())


def _similaridade(a, b):
    return SequenceMatcher(None, normalizar(a), normalizar(b), autojunk=False).ratio()


def _alinhar_tokens_monotono(tokens, words):
    """Needleman-Wunsch alignment, preserving order and explicit gaps."""
    n, m = len(tokens), len(words)
    gap = -0.62
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1): dp[i][0], bt[i][0] = i * gap, "up"
    for j in range(1, m + 1): dp[0][j], bt[0][j] = j * gap, "left"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sim = _similaridade(tokens[i - 1], words[j - 1]["word"])
            match = dp[i - 1][j - 1] + (2.0 * sim - .55)
            up = dp[i - 1][j] + gap
            left = dp[i][j - 1] + gap
            dp[i][j], bt[i][j] = max((match, "diag"), (up, "up"), (left, "left"), key=lambda x: x[0])
    mapping = [None] * n
    i, j = n, m
    while i or j:
        step = bt[i][j]
        if step == "diag":
            sim = _similaridade(tokens[i - 1], words[j - 1]["word"])
            if sim >= .24: mapping[i - 1] = (j - 1, sim)
            i -= 1; j -= 1
        elif step == "up": i -= 1
        else: j -= 1
    return mapping


def construir_transcricao_canonica(linhas_texto, observacoes):
    """Align expected lyrics to independent ASR observations without rewriting them.

    Expected spelling is immutable. ASR supplies timings/evidence only; absent evidence
    remains an explicit gap instead of receiving an invented timestamp.
    """
    tokens = [t for linha in linhas_texto for t in _tokens_linha(linha)]
    maps = []
    for obs in observacoes:
        ws = sorted(obs.get("words", []), key=lambda w: (float(w["start"]), float(w["end"])))
        maps.append((obs.get("source", "unknown"), ws, _alinhar_tokens_monotono(tokens, ws)))
    canonical = []
    prev_start = -1.0
    for idx, token in enumerate(tokens):
        evidence = []
        for source, ws, mapping in maps:
            hit = mapping[idx]
            if hit is None: continue
            j, sim = hit; w = ws[j]
            if float(w["end"]) <= float(w["start"]): continue
            evidence.append({"source": source, "observed": w["word"].strip(),
                             "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3),
                             "probability": w.get("probability"), "similarity": round(sim, 3)})
        usable = [e for e in evidence if e["start"] >= prev_start - .08]
        if usable:
            starts = sorted(e["start"] for e in usable); ends = sorted(e["end"] for e in usable)
            start = starts[len(starts)//2]; end = ends[len(ends)//2]
            agreement = max(starts) - min(starts) if len(starts) > 1 else None
            exact = sum(normalizar(e["observed"]) == normalizar(token) for e in usable)
            if len(usable) >= 2 and agreement <= .30 and exact: confidence = "high"
            elif exact or max(e["similarity"] for e in usable) >= .62: confidence = "medium"
            else: confidence = "low"
            prev_start = start
            canonical.append({"word": token, "start": start, "end": max(end, start + .02),
                              "confidence": confidence, "identified_in_audio": True,
                              "source": [e["source"] for e in usable], "agreement_seconds": agreement,
                              "evidence": usable})
        else:
            canonical.append({"word": token, "start": None, "end": None, "confidence": "gap",
                              "identified_in_audio": False, "source": [], "agreement_seconds": None,
                              "evidence": evidence})
    lines, k = [], 0
    for text in linhas_texto:
        count = len(_tokens_linha(text)); ws = canonical[k:k+count]; k += count
        timed = [w for w in ws if w["start"] is not None]
        lines.append({"text": text, "start": min((w["start"] for w in timed), default=None),
                      "end": max((w["end"] for w in timed), default=None), "words": ws,
                      "confidence": "gap" if not timed else min((w["confidence"] for w in timed),
                      key=lambda x: {"gap":0,"low":1,"medium":2,"high":3}[x])})
    return {"format": "canonical-lyrics-aligned-v1", "lines": lines, "words": canonical,
            "audit": {"expected_words": len(canonical),
                      "identified_words": sum(w["identified_in_audio"] for w in canonical),
                      "gaps": [w["word"] for w in canonical if not w["identified_in_audio"]],
                      "sources": [o.get("source", "unknown") for o in observacoes]}}


def normalizar(s):
    """minuscula, sem acento, so letras — pra casar fonetica aproximada."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


def alinhar(linhas_texto, palavras):
    """Alinha cada linha da letra a um intervalo de palavras do Whisper.

    Estrategia: junta todas as palavras da letra numa sequencia com marcador de
    fim-de-linha; alinha essa sequencia contra as palavras do Whisper com
    SequenceMatcher (por token normalizado); depois atribui a cada linha o
    intervalo [primeira palavra whisper casada, ultima] cobrindo suas palavras.
    """
    # tokens da letra: lista de (idx_linha, palavra_norm)
    letra_tokens = []
    for i, linha in enumerate(linhas_texto):
        for p in linha.split():
            pn = normalizar(p.replace("<<", "").replace(">>", ""))
            if pn:
                letra_tokens.append((i, pn))

    # Alinhamento monotono token-a-token (Needleman-Wunsch com similaridade
    # fonetica). O SequenceMatcher antigo, com refroes identicos repetidos,
    # casava blocos com a ocorrencia errada e "comia" versos inteiros.
    letra_raw = [t[1] for t in letra_tokens]
    mapping = _alinhar_tokens_monotono(letra_raw, palavras) if letra_raw and palavras else []
    letra_to_wh = [hit[0] if hit else None for hit in mapping] or [None] * len(letra_tokens)

    # intervalo por linha
    linhas_wh = {}
    for (li, _), wj in zip(letra_tokens, letra_to_wh):
        if wj is None:
            continue
        linhas_wh.setdefault(li, []).append(wj)

    # casamento POR TOKEN da linha (nao so o conjunto de indices): cada palavra exibida
    # recebe o tempo da palavra cantada que casou com ELA
    casados_linha = {}
    for (li, _), hit in zip(letra_tokens, mapping or [None] * len(letra_tokens)):
        casados_linha.setdefault(li, []).append(hit[0] if hit else None)

    resultado = []
    prev_end = 0.0
    for i, linha in enumerate(linhas_texto):
        wjs = linhas_wh.get(i)
        # keyword
        m = re.search(r"<<(.+?)>>", linha)
        kw = m.group(1) if m else None
        texto = linha.replace("<<", "").replace(">>", "").strip()
        if wjs:
            ini = palavras[min(wjs)]["start"]
            fim = palavras[max(wjs)]["end"]
            words = _palavras_da_linha(texto, casados_linha.get(i, []), palavras)
        else:
            # linha sem casamento: encaixa logo apos a anterior (fallback)
            ini = prev_end + 0.1
            fim = ini + 1.5
            words = _palavras_distribuidas(texto, ini, fim)
        resultado.append({"start": round(ini, 2), "end": round(fim, 2),
                           "text": texto, "keyword": kw, "words": words})
        prev_end = fim
    return resultado


def _palavras_da_linha(texto, casados, palavras):
    """Tempo de CADA palavra exibida da linha (POV/karaoke acendem palavra a palavra).

    `casados[k]` = indice da palavra Whisper casada com o k-esimo token com letras da linha
    (ou None). Incidente Douma (01/10/2026): a versao antiga dava o tempo pela POSICAO
    (1a palavra exibida <- 1o onset casado...). Um token sem par ("—", um "o" engolido)
    deslocava o resto e o POV acendia a palavra antes de ser cantada (18 de 36 linhas).
    Regras:
    - token so de pontuacao ("—") gruda na palavra anterior (nao tem tempo proprio);
    - palavra casada usa o tempo DELA, se nao voltar no tempo;
    - palavra sem par e interpolada entre as vizinhas casadas (origem "estimada").
    """
    brutos = texto.split()
    if not brutos:
        return []
    exibidos = []                      # [texto, idx_whisper|None]
    k = 0
    for tok in brutos:
        if not normalizar(tok):
            if exibidos:
                exibidos[-1][0] += " " + tok
            else:
                exibidos.append([tok, None])
            continue
        exibidos.append([tok, casados[k] if k < len(casados) else None])
        k += 1
    out = [{"text": t, "start": None, "end": None, "origem": "estimada"} for t, _ in exibidos]
    ultimo = -1.0
    for item, (_t, j) in zip(out, exibidos):
        if j is None:
            continue
        w = palavras[j]
        a, b = float(w["start"]), float(w["end"])
        if a < ultimo - 0.01:
            continue                   # casamento que volta no tempo: vira estimada
        if b - a < 0.02:
            # palavra "colapsada" do ASR (duracao zero; Douma 44,16 s: 6 palavras no mesmo
            # instante): nao tem tempo de verdade -> interpola entre as vizinhas
            continue
        item.update(start=round(a, 2), end=round(max(b, a + 0.05), 2), origem="asr")
        ultimo = a
    # interpola os buracos entre vizinhas casadas, proporcional ao tamanho da palavra
    n = len(out)
    i = 0
    while i < n:
        if out[i]["start"] is not None:
            i += 1
            continue
        j = i
        while j < n and out[j]["start"] is None:
            j += 1
        antes = out[i - 1]["end"] if i > 0 else None
        depois = out[j]["start"] if j < n else None
        if antes is None and depois is None:
            antes, depois = 0.0, 0.2 * (j - i)
        elif antes is None:
            antes = max(0.0, depois - 0.2 * (j - i))
        elif depois is None or depois <= antes:
            depois = antes + 0.2 * (j - i)
        pesos = [max(1, len(normalizar(out[x]["text"]))) for x in range(i, j)]
        total, t = sum(pesos), antes
        for x, p in zip(range(i, j), pesos):
            d = (depois - antes) * p / total
            out[x].update(start=round(t, 2), end=round(t + d, 2))
            t += d
        i = j
    return out


def validar_palavras(linhas_sync, palavras, sim_min=0.5):
    """Porteiro da sincronia POR PALAVRA (POV/karaoke). Lista de problemas; vazia = ok.

    - palavras de cada linha em ordem no tempo;
    - palavra com origem "asr" precisa parecer com a palavra cantada naquele instante
      (pega deslocamento: o POV acendendo "seu" quando o cantor canta "choro")."""
    por_inicio = {}
    for w in palavras:
        if w.get("start") is None or float(w.get("end", w["start"])) - float(w["start"]) < 0.02:
            continue                   # palavra colapsada do ASR nao e prova de nada
        por_inicio.setdefault(round(float(w["start"]), 2), []).append(str(w.get("word", "")))
    problemas = []
    for i, linha in enumerate(linhas_sync):
        ws = linha.get("words") or []
        for k, p in enumerate(ws):
            if p.get("start") is None:
                continue
            if k and ws[k - 1].get("start") is not None and float(p["start"]) < float(ws[k - 1]["start"]) - 0.01:
                problemas.append(f"linha {i + 1} '{linha.get('text', '')[:40]}': '{p['text']}' volta no tempo")
            if p.get("origem", "asr") != "asr":
                continue
            cantadas = por_inicio.get(round(float(p["start"]), 2))
            if not cantadas or max(_similaridade(p["text"], c) for c in cantadas) >= sim_min:
                continue
            # deslocamento = o que se canta ali e OUTRA palavra da linha (vizinha). Nome
            # mal ouvido pelo ASR ("Shinobu" -> "novo") tem o tempo certo e nao reprova.
            vizinhas = [ws[x]["text"] for x in range(max(0, k - 3), min(len(ws), k + 4)) if x != k]
            if any(_similaridade(v, c) >= 0.8 for v in vizinhas for c in cantadas):
                problemas.append(f"linha {i + 1} '{linha.get('text', '')[:40]}': '{p['text']}' "
                                 f"acende quando canta '{'/'.join(c.strip() for c in cantadas)}'")
    return problemas


def _palavras_distribuidas(texto, ini, fim):
    """Sem casamento Whisper: reparte [ini,fim] entre palavras por tamanho."""
    tokens = texto.split()
    if not tokens:
        return []
    total = sum(len(t) for t in tokens) or 1
    dur = max(0.0, fim - ini)
    out = []
    t = ini
    for tok in tokens:
        d = dur * (len(tok) / total)
        out.append({"text": tok, "start": round(t, 2), "end": round(t + d, 2)})
        t += d
    return out


def validar_cobertura(linhas_sync, palavras, gap_max=2.0):
    """checa se todo bloco de palavras cantadas tem legenda por perto."""
    cobertos = [(l["start"], l["end"]) for l in linhas_sync]
    buracos = []
    for w in palavras:
        t = w["start"]
        if not any(a - gap_max <= t <= b + gap_max for a, b in cobertos):
            buracos.append((round(t, 2), w["word"]))
    return buracos


def corrigir_sobreposicao(linhas):
    """garante que uma linha nao invade a proxima (corta no start da seguinte)."""
    for i in range(len(linhas) - 1):
        if linhas[i]["end"] > linhas[i + 1]["start"]:
            linhas[i]["end"] = round(max(linhas[i]["start"] + 0.5,
                                          linhas[i + 1]["start"] - 0.05), 2)
    return linhas


def main():
    d = Path(sys.argv[1])
    palavras = json.load(open(d / "transcricao.json"))["words"]
    linhas_txt = extrair_linhas_suno(
        (d / "LETRA_LINHAS.txt").read_text(encoding="utf-8"))
    sync = alinhar(linhas_txt, palavras)
    sync = corrigir_sobreposicao(sync)
    json.dump(sync, open(d / "letra_sincronizada.json", "w"),
              ensure_ascii=False, indent=1)
    buracos = validar_cobertura(sync, palavras)
    print(f"OK: {len(sync)} linhas sincronizadas WORD-LEVEL")
    print(f"Cobertura: {len(buracos)} palavras sem legenda por perto")
    if buracos:
        print("  buracos (trechos cantados sem legenda):")
        for t, w in buracos[:20]:
            print(f"    {t}s: {w}")
    else:
        print("  ✅ 100% coberto — toda palavra cantada tem legenda")
    # mostrar alinhamento
    print("\nLinhas:")
    for l in sync:
        print(f"  [{l['start']:6.2f}-{l['end']:6.2f}] {l['text'][:44]}")


if __name__ == "__main__":
    main()
