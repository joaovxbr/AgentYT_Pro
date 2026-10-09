#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""transcrever.py — o relogio da VOZ: alinhamento word-level do audio (Whisper).

Gera `entradas/transcricao.json` no formato que o resto da esteira consome:

    {
      "language": "pt",
      "duration": 174.01,
      "words":    [{"word": "Eu", "start": 12.54, "end": 12.71}, ...],
      "segments": [{"start":..., "end":..., "text":..., "words":[...]}, ...]
    }

E biblioteca — quem chama e a porta de criacao (`estudio.py transcrever <slug>`).
Nao gera legenda nem casa com a letra oficial; isso e do sincronizar_letra.py.
Aqui so extraimos o ONSET de cada palavra cantada, que e a fonte de verdade do
tempo. A letra oficial entra depois, no alinhamento.

Usa faster-whisper (rapido em CPU). Modelo configuravel; 'medium' e o padrao
por equilibrar precisao de onset e tempo de CPU numa faixa de ~3 min.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


MODELO_PADRAO = "medium"


def _garantir_dlls_cuda() -> None:
    """No Windows, expoe as DLLs CUDA empacotadas no torch ao processo.

    O ctranslate2 (faster-whisper) procura cublas64_12.dll/cudnn no PATH; sem um
    CUDA Toolkit global instalado (caso desta maquina), as unicas copias vivem em
    torch/lib. Registrar a pasta via add_dll_directory antes de carregar o modelo
    evita 'Library cublas64_12.dll is not found' quando device=cuda.
    """
    if os.name != "nt":
        return
    try:
        import torch  # noqa: F401  (import carrega as DLLs no processo)
        return
    except Exception:
        pass
    pasta = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages" / "torch" / "lib"
    if pasta.is_dir() and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(pasta))


def transcrever(
    audio: Path,
    destino: Path,
    *,
    modelo: str = MODELO_PADRAO,
    idioma: str = "pt",
    initial_prompt: Optional[str] = None,
) -> dict:
    """Transcreve `audio` com word_timestamps e grava `destino` (JSON).

    initial_prompt: passe a letra oficial (texto cru) para o Whisper ancorar o
    vocabulario proprio (nomes: Eren, titan, Rumbling...) e errar menos onset.
    """
    from faster_whisper import WhisperModel

    audio = Path(audio)
    if not audio.exists():
        raise FileNotFoundError(f"audio ausente: {audio}")

    # CPU: int8 e o melhor custo/beneficio; se houver GPU CUDA, float16 na GPU.
    _garantir_dlls_cuda()
    device, compute = _melhor_dispositivo()
    modelo_w = WhisperModel(modelo, device=device, compute_type=compute)

    segmentos, info = modelo_w.transcribe(
        str(audio),
        language=idioma,
        word_timestamps=True,
        initial_prompt=initial_prompt,
        vad_filter=False,   # a musica nao tem silencio longo; VAD cortaria vocal
        beam_size=5,
    )

    words = []
    segs_out = []
    for seg in segmentos:
        seg_words = []
        for w in (seg.words or []):
            item = {
                "word": w.word.strip(),
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
            }
            if item["word"]:
                words.append(item)
                seg_words.append(item)
        segs_out.append({
            "start": round(float(seg.start), 3),
            "end": round(float(seg.end), 3),
            "text": seg.text.strip(),
            "words": seg_words,
        })

    dados = {
        "language": info.language,
        "duration": round(float(info.duration), 3),
        "modelo": modelo,
        "words": words,
        "segments": segs_out,
    }
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return dados


def carregar_modelo(modelo="large-v3"):
    from faster_whisper import WhisperModel
    _garantir_dlls_cuda(); device, compute = _melhor_dispositivo()
    return WhisperModel(modelo, device=device, compute_type=compute, local_files_only=True)


def transcrever_chunked(audio: Path, *, modelo="large-v3", idioma="pt", prompt=None,
                        chunk_seconds=30.0, overlap=3.0, inicio=0.0, fim=None,
                        model=None) -> dict:
    """Offline overlapping ASR with independent chunks and absolute word times.

    `inicio`/`fim` limitam a janela (usado para retranscrever so uma lacuna);
    `model` permite reaproveitar o WhisperModel ja carregado.
    """
    import subprocess, tempfile
    audio=Path(audio)
    model=model or carregar_modelo(modelo)
    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(audio)]))
    if fim is not None:
        duration=min(duration,float(fim))
    words=[]; segments=[]; start=max(0.0,float(inicio)); primeiro=start
    with tempfile.TemporaryDirectory() as td:
        while start < duration:
            length=min(chunk_seconds,duration-start); chunk=Path(td)/f'c_{start:.2f}.wav'
            subprocess.run(['ffmpeg','-v','error','-y','-ss',str(start),'-t',str(length),'-i',str(audio),'-ac','1','-ar','16000',str(chunk)],check=True)
            segs,_=model.transcribe(str(chunk),language=idioma,word_timestamps=True,
                initial_prompt=prompt,vad_filter=False,beam_size=5,condition_on_previous_text=False)
            keep_from=start if start==primeiro else start+overlap/2
            for seg in segs:
                sw=[]
                for w in seg.words or []:
                    item={'word':w.word.strip(),'start':round(start+float(w.start),3),
                          'end':round(start+float(w.end),3),'probability':float(w.probability)}
                    # Nao filtrar por probabilidade aqui: nomes de anime (Hollow
                    # Purple, Gojo) saem com prob baixa e sao reais. O ruido
                    # (alucinacao sobre instrumental) e tratado por BLOCO no
                    # auditor_letra (confianca media), nunca palavra a palavra.
                    if item['word'] and item['start']>=keep_from: words.append(item);sw.append(item)
                if sw: segments.append({'start':sw[0]['start'],'end':sw[-1]['end'],'text':' '.join(x['word'] for x in sw),'words':sw})
            start += chunk_seconds-overlap
    # overlap dedupe: keep higher-probability near-identical observations
    dedup=[]
    for w in sorted(words,key=lambda x:(x['start'],-x['probability'])):
        if dedup and abs(w['start']-dedup[-1]['start'])<.12 and w['word'].lower()==dedup[-1]['word'].lower():
            if w['probability']>dedup[-1]['probability']: dedup[-1]=w
        else: dedup.append(w)
    return {'language':idioma,'duration':duration,'modelo':modelo,'chunk_seconds':chunk_seconds,
            'overlap':overlap,'condition_on_previous_text':False,'words':dedup,'segments':segments}


def energia_vocal(audio: Path, janela: float = 0.5) -> list[tuple[float, float]]:
    """RMS (dBFS) por janela do stem vocal: [(inicio_s, db), ...].

    Decodifica via ffmpeg para mono 16 kHz float32, sem depender de libs de audio.
    """
    import subprocess
    import numpy as np
    ff = __import__("shutil").which("ffmpeg") or "ffmpeg"
    raw = subprocess.run(
        [ff, "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "16000",
         "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    n = max(1, int(16000 * janela))
    out = []
    for i in range(0, len(x), n):
        bloco = x[i:i + n]
        if not len(bloco):
            break
        rms = float(np.sqrt(np.mean(bloco.astype(np.float64) ** 2)))
        out.append((round(i / 16000, 3), 20 * np.log10(max(rms, 1e-9))))
    return out


import re as _re

# Frases que o Whisper "inventa" sobre trechos instrumentais (vem do treino em
# videos do YouTube). Aparecem com confianca ALTA, entao so um filtro explicito
# resolve. Nunca sao letra de um AMV.
_ALUCINACOES = _re.compile(
    r"inscrev|sininho|notifica[cç]|deixe (o )?seu like|obrigad[oa] por assistir|"
    r"legendas? (pela|por)|amara\.org|tchau|at[eé] a pr[oó]xima|subscribe|thanks for watching",
    _re.IGNORECASE)


def palavra_confiavel(w: dict) -> bool:
    """Palavra degenerada: confianca ~0 e esticada (Whisper 'arrasta' 1 token por segundos)."""
    p = w.get("probability")
    if p is None:
        return True
    dur = float(w.get("end", 0)) - float(w.get("start", 0))
    return not (p < 0.15 or (p < 0.30 and dur > 1.2))


def palavra_em_silencio(w: dict, energia_db) -> bool:
    """Palavra que o ASR inventou sobre silencio do stem vocal: nivel RMS da janela abaixo de
    -55 dBFS e confianca baixa (<0.8) ou duracao zero. Caso Zeref 08/10/2026: 5 palavras de
    alucinacao no ultimo segundo (364.9-366.3 s, vocal em -82 dBFS) reprovavam o auditor-letra.
    Palavra cantada tem voz no stem: nunca cai nesta regra."""
    if energia_db is None:
        return False
    a, b = float(w.get("start", 0)), float(w.get("end", 0))
    db = energia_db(a, max(b, a + 0.2))
    p = w.get("probability")
    dur = b - a
    return db < -55.0 and ((p is not None and float(p) < 0.8) or dur <= 0.05)


def limpar_alucinacoes(dados: dict, energia_db=None) -> int:
    """Remove segmentos de alucinacao conhecida e palavras degeneradas. Retorna n removidas.
    `energia_db(a, b)` (opcional) devolve o nivel do stem vocal em dBFS: palavras que caem em
    silencio com baixa confianca tambem saem (ver palavra_em_silencio)."""
    fora = set()
    for seg in dados.get("segments", []):
        if _ALUCINACOES.search(seg.get("text", "")):
            for w in seg.get("words", []):
                fora.add((w["start"], w["word"]))
    antes = len(dados.get("words", []))
    dados["words"] = [w for w in dados.get("words", [])
                      if (w["start"], w["word"]) not in fora and palavra_confiavel(w)
                      and not palavra_em_silencio(w, energia_db)]
    dados["segments"] = [s for s in dados.get("segments", []) if not _ALUCINACOES.search(s.get("text", ""))]
    return antes - len(dados["words"])


def lacunas_vocais(words: list[dict], energia: list[tuple[float, float]], *,
                   janela: float = 0.5, limiar_db: float | None = None,
                   min_lacuna: float = 4.0) -> list[dict]:
    """Trechos onde o stem vocal TEM voz mas a transcricao NAO tem palavra.

    E o defeito que o auditor antigo nao via: o Whisper as vezes pula dezenas de
    segundos cantados; sem palavras, a letra desses versos nao tem relogio e a
    legenda some. Limiar adaptativo: 12 dB abaixo do percentil 90 da voz.
    """
    import numpy as np
    if not energia:
        return []
    dbs = np.array([d for _, d in energia])
    limiar = limiar_db if limiar_db is not None else float(np.percentile(dbs, 90) - 12.0)
    # palavra degenerada nao conta como "voz transcrita"
    cobertos = sorted((float(w["start"]) - 0.6, min(float(w["end"]), float(w["start"]) + 1.2) + 0.6)
                      for w in words if w.get("start") is not None and palavra_confiavel(w))

    def coberto(t):
        return any(a <= t <= b for a, b in cobertos)

    lacunas, ini, ativo = [], None, 0.0
    for t, db in energia:
        vazio = db >= limiar and not coberto(t + janela / 2)
        if vazio:
            if ini is None:
                ini, ativo = t, 0.0
            ativo += janela
            fim = t + janela
        elif ini is not None and not (db < limiar and not coberto(t + janela / 2)):
            # voz transcrita (ou fim do trecho) fecha a lacuna
            if ativo >= min_lacuna:
                lacunas.append({"inicio": round(ini, 2), "fim": round(fim, 2),
                                "voz_s": round(ativo, 2)})
            ini = None
    if ini is not None and ativo >= min_lacuna:
        lacunas.append({"inicio": round(ini, 2), "fim": round(fim, 2), "voz_s": round(ativo, 2)})
    return lacunas


def preencher_lacunas(audio: Path, dados: dict, energia: list, *, modelo="large-v3",
                      idioma="pt", margem=1.5, model=None) -> list[dict]:
    """Retranscreve SO as lacunas de voz, sem prompt, e injeta as palavras.

    O prompt com a letra ajuda a grafia, mas faz o Whisper pular trechos (ele
    "acha" que ja cantou aquilo). Cada lacuna vira uma janela isolada, sem
    prompt, em blocos menores. Retorna as lacunas que continuaram vazias.
    """
    lacunas = lacunas_vocais(dados["words"], energia)
    if not lacunas:
        return []
    model = model or carregar_modelo(modelo)
    for lac in lacunas:
        a, b = max(0.0, lac["inicio"] - margem), lac["fim"] + margem
        extra = transcrever_chunked(audio, modelo=modelo, idioma=idioma, prompt=None,
                                    chunk_seconds=15.0, overlap=3.0, inicio=a, fim=b,
                                    model=model)
        limpar_alucinacoes(extra)
        novos = [w for w in extra["words"] if lac["inicio"] - 0.3 <= w["start"] <= lac["fim"] + 0.3]
        if novos:
            # troca o lixo da 1a passada nessa janela pelas palavras novas
            velhos = [w for w in dados["words"]
                      if not (lac["inicio"] - 0.3 <= w["start"] <= lac["fim"] + 0.3)]
            dados["words"] = sorted(velhos + novos, key=lambda w: w["start"])
            dados["segments"] = sorted(
                dados.get("segments", []) + [s for s in extra["segments"]
                                             if lac["inicio"] - 0.3 <= s["start"] <= lac["fim"] + 0.3],
                key=lambda s: s["start"])
            dados.setdefault("lacunas_preenchidas", []).append(
                {"inicio": lac["inicio"], "fim": lac["fim"], "palavras": len(novos)})
    return lacunas_vocais(dados["words"], energia)


def tokens_da_letra(linhas: list[str]) -> list[str]:
    import sincronizar_letra as sl
    return [t for linha in linhas for t in sl._tokens_linha(linha)]


def letra_pendente(lac: dict, words: list[dict], tokens: list[str]) -> list[str]:
    """Tokens da letra que DEVERIAM estar nesta lacuna e nao tem palavra do ASR.

    Alinhamento monotono letra x ASR: pega o ultimo token casado antes da lacuna e o
    primeiro depois; o que ficou sem casar no meio e letra pendente. Lista vazia =
    a voz da lacuna nao e letra (vocalise, ad-lib, coro de fundo, outro que some).
    Caso real: Douma 156-164 s = vocalise depois da ultima linha (nao reprovar);
    Douma 30-35 s = 3 linhas do verso 1 sem relogio (reprovar / 3a passada).
    """
    import sincronizar_letra as sl
    if not tokens:
        return []
    ws = sorted((w for w in words if palavra_confiavel(w)), key=lambda w: float(w["start"]))
    # so casamento de verdade (sim >= 0.6): o alinhador aceita 0.24 e casava "o"/"de" soltos,
    # escondendo 3 linhas pendentes do Douma (30-35 s) como se fosse vocalise.
    mapa = [h if h and h[1] >= 0.6 else None for h in sl._alinhar_tokens_monotono(tokens, ws)]
    antes = max((i for i, h in enumerate(mapa) if h and float(ws[h[0]]["start"]) < lac["inicio"]), default=-1)
    depois = min((i for i, h in enumerate(mapa) if h and float(ws[h[0]]["start"]) > lac["fim"]),
                 default=len(tokens))
    return [tokens[i] for i in range(antes + 1, depois) if mapa[i] is None]


def janela_da_letra_pendente(lac: dict, words: list[dict], tokens: list[str],
                             folga: float = 0.4, max_janela: float = 28.0) -> tuple[float, float]:
    """Janela de retranscricao = da ultima palavra CASADA com a letra antes da lacuna ate a
    primeira casada depois. Regressao Douma (30/09/2026): a lacuna de energia era 30,5-35,5 s,
    mas as 3 linhas pendentes iam de 29,1 a 42 s; recortar so a lacuna comecava no meio da
    frase e o Whisper nao reconhecia nada. Com a janela 26,2-42,4 s ele transcreve tudo."""
    import sincronizar_letra as sl
    ws = sorted((w for w in words if palavra_confiavel(w)), key=lambda w: float(w["start"]))
    mapa = [h if h and h[1] >= 0.6 else None for h in sl._alinhar_tokens_monotono(tokens, ws)] if tokens else []
    antes = [float(ws[h[0]]["end"]) for h in mapa if h and float(ws[h[0]]["start"]) < lac["inicio"]]
    depois = [float(ws[h[0]]["start"]) for h in mapa if h and float(ws[h[0]]["start"]) > lac["fim"]]
    a = (max(antes) - folga) if antes else lac["inicio"] - 1.5
    b = (min(depois) + folga) if depois else lac["fim"] + 1.5
    a, b = max(0.0, min(a, lac["inicio"] - 0.5)), max(b, lac["fim"] + 0.5)
    if b - a > max_janela:                       # nunca uma janela enorme (Whisper se perde)
        centro = (lac["inicio"] + lac["fim"]) / 2
        a, b = max(0.0, centro - max_janela / 2), centro + max_janela / 2
    return round(a, 2), round(b, 2)


def classificar_lacunas(lacunas: list[dict], words: list[dict], tokens: list[str],
                        min_tokens: int = 2) -> tuple[list[dict], list[dict]]:
    """(lacunas com letra pendente -> reprovam, lacunas so de vocalise -> ok)."""
    com, sem = [], []
    for lac in lacunas:
        pend = letra_pendente(lac, words, tokens)
        (com if len(pend) >= min_tokens else sem).append({**lac, "letra_pendente": pend})
    return com, sem


def aceitar_passada_guiada(novos: list[dict], esperados: list[str], energia: list[tuple[float, float]],
                           limiar_db: float, min_casamento: float = 0.5, min_prob: float = 0.45) -> bool:
    """A 3a passada usa as frases pendentes como prompt, e o Whisper as vezes 'copia' o
    prompt sobre silencio. So aceita se: (1) >= metade dos esperados casou, (2) a
    confianca media das casadas e razoavel e (3) as palavras caem onde ha voz."""
    import sincronizar_letra as sl
    if not novos or not esperados:
        return False
    mapa = sl._alinhar_tokens_monotono(esperados, sorted(novos, key=lambda w: float(w["start"])))
    casados = [h for h in mapa if h and h[1] >= 0.6]   # casamento de verdade, nao so "parecido"
    if len(casados) < 3 or len(casados) / len(esperados) < min_casamento:
        return False
    ordenados = sorted(novos, key=lambda w: float(w["start"]))
    probs = [float(ordenados[j].get("probability") or 0) for j, _s in casados]
    if sum(probs) / len(probs) < min_prob:
        return False
    def voz(t):
        return any(a <= t < a + 0.5 and db >= limiar_db for a, db in energia)
    return sum(voz(float(w["start"])) for w in novos) / len(novos) >= 0.7


def trecho_explicado(novos: list[dict], esperados: list[str]) -> tuple[float, float]:
    """[inicio, fim] das palavras novas que casaram (sim >= 0.6) com a letra pendente."""
    import sincronizar_letra as sl
    ordenados = sorted(novos, key=lambda w: float(w["start"]))
    casados = [ordenados[h[0]] for h in sl._alinhar_tokens_monotono(esperados, ordenados) if h and h[1] >= 0.6]
    if not casados:
        return (0.0, -1.0)
    return (float(casados[0]["start"]) - 0.05, float(casados[-1]["end"]) + 0.05)


def passada_guiada(audio: Path, dados: dict, energia: list, linhas: list[str], *, modelo="large-v3",
                   idioma="pt", model=None, margem=1.0) -> list[dict]:
    """3a passada: retranscreve cada lacuna que ainda tem letra pendente, com SO as frases
    pendentes como prompt (a letra autoral e a grafia; o audio decide se foram cantadas).
    Aceita o resultado apenas se passar em `aceitar_passada_guiada`."""
    import numpy as np
    tokens = tokens_da_letra(linhas)
    if not energia or not tokens:
        return []
    limiar = float(np.percentile([d for _, d in energia], 90) - 12.0)
    com, _sem = classificar_lacunas(lacunas_vocais(dados["words"], energia), dados["words"], tokens)
    if not com:
        return []
    primeira = min((float(w["start"]) for w in dados["words"]), default=0.0)
    # antes do 1o verso e vocalise de intro (mesma regra do porteiro); poucas palavras pendentes
    # nao justificam retranscrever (Douma: 'a a a' de vocalise foi aceito e apagou a 1a linha)
    com = [x for x in com if x["fim"] > primeira + 0.5 and len(x["letra_pendente"]) >= 4]
    if not com:
        return classificar_lacunas(lacunas_vocais(dados["words"], energia), dados["words"], tokens)[0]
    model = model or carregar_modelo(modelo)
    for lac in com:
        a, b = janela_da_letra_pendente(lac, dados["words"], tokens)
        # janela inteira num bloco so (sem cortar frase no meio); sem prompt primeiro, com as
        # frases pendentes se a 1a tentativa nao passar no aceite
        for prompt in (None, " ".join(lac["letra_pendente"])):
            extra = transcrever_chunked(audio, modelo=modelo, idioma=idioma, prompt=prompt,
                                        chunk_seconds=max(8.0, b - a + 0.1), overlap=0.0, inicio=a, fim=b,
                                        model=model)
            limpar_alucinacoes(extra)
            novos = [w for w in extra["words"] if a <= w["start"] <= b]
            aceito = aceitar_passada_guiada(novos, lac["letra_pendente"], energia, limiar)
            if aceito:
                break
        dados.setdefault("passada_guiada", []).append(
            {"inicio": lac["inicio"], "fim": lac["fim"], "janela": [a, b], "pendentes": len(lac["letra_pendente"]),
             "palavras": len(novos), "aceita": aceito, "com_prompt": bool(prompt)})
        if aceito:
            # troca SO o trecho que a passada nova explicou (das palavras que casaram com a letra
            # pendente); fora dele vale a transcricao anterior. Regressao Douma: a janela ia ate
            # o meio do refrao e apagava "eu vim te libertar".
            s0, s1 = trecho_explicado(novos, lac["letra_pendente"])
            velhos = [w for w in dados["words"] if not (s0 <= float(w["start"]) <= s1)]
            usados = [w for w in novos if s0 <= float(w["start"]) <= s1]
            dados["words"] = sorted(velhos + usados, key=lambda w: w["start"])
            dados["segments"] = sorted([s for s in dados.get("segments", []) if not (s0 <= s["start"] <= s1)] + [
                s for s in extra["segments"] if s0 <= s["start"] <= s1], key=lambda s: s["start"])
            dados["passada_guiada"][-1]["trecho_trocado"] = [round(s0, 2), round(s1, 2)]
    return classificar_lacunas(lacunas_vocais(dados["words"], energia), dados["words"], tokens)[0]


def _melhor_dispositivo() -> tuple[str, str]:
    """Escolhe GPU CUDA se houver; senao CPU int8."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def auditar(dados: dict, dur_audio: float | None = None) -> list[str]:
    """Cheques de sanidade do resultado. Lista vazia = ok."""
    erros = []
    words = dados.get("words") or []
    if not words:
        return ["transcricao sem palavras"]
    # onsets monotonicos e finitos
    prev = -1.0
    for i, w in enumerate(words):
        s, e = w.get("start"), w.get("end")
        if s is None or e is None:
            erros.append(f"palavra {i} ({w.get('word')!r}) sem start/end")
            continue
        if not (s <= e):
            erros.append(f"palavra {i} ({w.get('word')!r}) com start>end ({s}>{e})")
        if s < prev - 0.05:
            erros.append(f"palavra {i} ({w.get('word')!r}) retrocede no tempo ({s} < {prev})")
        prev = max(prev, s)
    # cobertura ao fim do audio
    if dur_audio:
        ultima = words[-1]["end"]
        if ultima > dur_audio + 1.0:
            erros.append(f"ultima palavra em {ultima}s passa do audio ({dur_audio}s)")
    return erros


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("uso: transcrever.py <audio.wav> <destino.json> [modelo]")
        raise SystemExit(1)
    modelo = sys.argv[3] if len(sys.argv) > 3 else MODELO_PADRAO
    d = transcrever(Path(sys.argv[1]), Path(sys.argv[2]), modelo=modelo)
    print(f"transcrito: {len(d['words'])} palavras -> {sys.argv[2]}")
