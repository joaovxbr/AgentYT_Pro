#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auditor_letra.py — porteiro LETRA x AUDIO (antes de sincronizar/renderizar).

Responde, com evidencia do audio, as tres perguntas que derrubaram o Gojo:

1. O ASR ouviu TODO o trecho cantado?  (voz no stem vocal sem palavras)
2. Cada linha da letra foi achada no audio, na ordem?  (linha sem evidencia)
3. Tem coisa cantada que NAO esta na letra?  (trecho cantado sem legenda,
   ex.: o Suno reordenou/pulou/trocou um bloco)

Alinhamento monotono (Needleman-Wunsch) token-a-token: refroes repetidos nao
"pulam" de ocorrencia como no SequenceMatcher. A letra autoral nunca e alterada;
o relatorio diz ONDE ela diverge do audio para o humano/Hermes decidir.

Porta: `estudio.py auditar-letra <slug>`; a esteira chama antes de `sincronia`.
Saida: qa/auditoria_letra.json + qa/auditoria_letra.md
"""
from __future__ import annotations

import json
from pathlib import Path

import sincronizar_letra as sl

# Limiares do porteiro (reprovam):
MIN_COBERTURA_LINHA = 0.45     # fracao de palavras da linha achadas no audio
MAX_LINHAS_SEM_AUDIO = 0       # linhas da letra sem nenhuma evidencia
MIN_PALAVRAS_EXTRA = 5         # bloco cantado fora da letra com >= N palavras
MIN_SIM_TOKEN = 0.50           # similaridade minima para contar palavra achada
MAX_CONF_RUIDO = 0.45          # bloco extra com confianca media abaixo = alucinacao ASR

# limiares centralizados em config/porteiros.json[auditar_letra] (sem override por projeto)
from _vx import config as _vx_config  # noqa: E402
_P = _vx_config.porteiro("auditar_letra", {
    "min_cobertura_linha": MIN_COBERTURA_LINHA, "max_linhas_sem_audio": MAX_LINHAS_SEM_AUDIO,
    "min_palavras_extra": MIN_PALAVRAS_EXTRA, "min_sim_token": MIN_SIM_TOKEN,
    "max_conf_ruido": MAX_CONF_RUIDO})
MIN_COBERTURA_LINHA = float(_P["min_cobertura_linha"])
MAX_LINHAS_SEM_AUDIO = int(_P["max_linhas_sem_audio"])
MIN_PALAVRAS_EXTRA = int(_P["min_palavras_extra"])
MIN_SIM_TOKEN = float(_P["min_sim_token"])
MAX_CONF_RUIDO = float(_P["max_conf_ruido"])


def carregar_letra(projeto: Path, manifesto: dict) -> list[str]:
    cfg = manifesto.get("letra")
    rel = None
    if isinstance(cfg, dict):
        rel = cfg.get("linhas") or cfg.get("arquivo")
    elif isinstance(cfg, str):
        rel = cfg
    caminho = projeto / (rel or "LETRA_LINHAS.txt")
    if not caminho.is_file():
        raise FileNotFoundError(f"letra ausente: {caminho}")
    return sl.extrair_linhas_suno(caminho.read_text(encoding="utf-8"))


def _excecoes_letra(excecoes: dict | None) -> list[str]:
    """Textos de linha aceitos como fala (exceção humana registrada no projeto)."""
    return [_norm_linha(x.get("texto", "")) for x in ((excecoes or {}).get("linhas_fala") or [])]


def _norm_linha(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _linha_excecionada(texto: str, textos: list[str]) -> bool:
    return bool(textos) and _norm_linha(texto) in textos


def auditar(linhas: list[str], words: list[dict],
            lacunas_voz: list[dict] | None = None, excecoes: dict | None = None) -> dict:
    words = sorted((w for w in words if w.get("start") is not None and str(w.get("word", "")).strip()),
                   key=lambda w: float(w["start"]))
    tokens, dono = [], []
    for i, linha in enumerate(linhas):
        for t in sl._tokens_linha(linha):
            if sl.normalizar(t):
                tokens.append(t)
                dono.append(i)
    mapping = sl._alinhar_tokens_monotono(tokens, words) if tokens and words else [None] * len(tokens)

    usados = set()
    por_linha = [[] for _ in linhas]
    for k, hit in enumerate(mapping):
        if hit and hit[1] >= MIN_SIM_TOKEN:
            por_linha[dono[k]].append(hit[0])
            usados.add(hit[0])

    relatorio_linhas = []
    for i, linha in enumerate(linhas):
        n = sum(1 for t in sl._tokens_linha(linha) if sl.normalizar(t))
        js = por_linha[i]
        cobertura = len(js) / n if n else 1.0
        relatorio_linhas.append({
            "indice": i, "texto": linha, "palavras": n,
            "achadas": len(js), "cobertura": round(cobertura, 3),
            "inicio": round(float(words[min(js)]["start"]), 2) if js else None,
            "fim": round(float(words[max(js)]["end"]), 2) if js else None,
        })

    # blocos cantados que nenhuma linha da letra reivindicou
    extras, bloco = [], []
    for j, w in enumerate(words):
        if j in usados:
            if len(bloco) >= MIN_PALAVRAS_EXTRA:
                extras.append(bloco)
            bloco = []
        else:
            bloco.append(w)
    if len(bloco) >= MIN_PALAVRAS_EXTRA:
        extras.append(bloco)
    cantado_fora, ruido_asr = [], []
    for b in extras:
        probs = [float(x["probability"]) for x in b if x.get("probability") is not None]
        conf = sum(probs) / len(probs) if probs else 1.0
        item = {
            "inicio": round(float(b[0]["start"]), 2), "fim": round(float(b[-1]["end"]), 2),
            "ouvido": " ".join(str(x["word"]).strip() for x in b),
            "confianca": round(conf, 3),
        }
        # Whisper "canta" sobre instrumental ("Tchau", "Legendas..."): confianca
        # media baixa = ruido do ASR, nao verso faltando na letra.
        (ruido_asr if conf < MAX_CONF_RUIDO else cantado_fora).append(item)

    # Excecao humana por linha (projetos/<slug>/qa/excecao_letra.json): so as linhas listadas,
    # com o mesmo texto, saem de "sem audio". Nao muda MAX_LINHAS_SEM_AUDIO nem o porteiro.
    excecoes_linha = _excecoes_letra(excecoes)
    sem_audio = [l for l in relatorio_linhas if l["achadas"] == 0
                 and not _linha_excecionada(l["texto"], excecoes_linha)]
    fracas = [l for l in relatorio_linhas if 0 < l["cobertura"] < MIN_COBERTURA_LINHA]
    lacunas_voz = lacunas_voz or []

    motivos = []
    if lacunas_voz:
        motivos.append(f"{len(lacunas_voz)} trecho(s) com voz e sem transcricao "
                       f"(rode: estudio.py transcrever <slug>)")
    if len(sem_audio) > MAX_LINHAS_SEM_AUDIO:
        motivos.append(f"{len(sem_audio)} linha(s) da letra nao encontradas no audio")
    if fracas:
        motivos.append(f"{len(fracas)} linha(s) com menos de "
                       f"{int(MIN_COBERTURA_LINHA*100)}% das palavras no audio")
    if cantado_fora:
        motivos.append(f"{len(cantado_fora)} trecho(s) cantado(s) que nao estao na letra")

    return {
        "aprovado": not motivos,
        "motivos": motivos,
        "linhas_total": len(linhas),
        "palavras_letra": len(tokens),
        "palavras_audio": len(words),
        "palavras_audio_casadas": len(usados),
        "lacunas_voz": lacunas_voz,
        "linhas_sem_audio": sem_audio,
        "linhas_fracas": fracas,
        "cantado_fora_da_letra": cantado_fora,
        "ruido_asr": ruido_asr,
        "linhas": relatorio_linhas,
    }


def _markdown(rel: dict, slug: str) -> str:
    st = "APROVADO" if rel["aprovado"] else "REPROVADO"
    out = [f"# Auditoria letra x áudio — {slug}: {st}", ""]
    out += [f"- {m}" for m in rel["motivos"]] or ["- sem divergências"]
    out += ["", f"Palavras da letra: {rel['palavras_letra']} | ouvidas: {rel['palavras_audio']} "
            f"| casadas: {rel['palavras_audio_casadas']}", ""]
    if rel["lacunas_voz"]:
        out += ["## Voz sem transcrição", ""]
        out += [f"- {x['inicio']}s – {x['fim']}s ({x['voz_s']}s)" for x in rel["lacunas_voz"]] + [""]
    if rel["cantado_fora_da_letra"]:
        out += ["## Cantado mas fora da letra (vai ficar sem legenda)", ""]
        out += [f"- {x['inicio']}s – {x['fim']}s: \"{x['ouvido']}\"" for x in rel["cantado_fora_da_letra"]] + [""]
    if rel.get("ruido_asr"):
        out += ["## Ruído do ASR (ignorado, confiança baixa)", ""]
        out += [f"- {x['inicio']}s – {x['fim']}s (conf {x['confianca']}): \"{x['ouvido']}\""
                for x in rel["ruido_asr"]] + [""]
    if rel["linhas_sem_audio"] or rel["linhas_fracas"]:
        out += ["## Linhas da letra não achadas / fracas", ""]
        for l in rel["linhas_sem_audio"] + rel["linhas_fracas"]:
            out.append(f"- [{l['cobertura']:.0%}] {l['texto']}")
        out.append("")
    out += ["## Linha a linha", "", "| # | Início | Fim | Cobertura | Texto |", "|---:|---:|---:|---:|---|"]
    for l in rel["linhas"]:
        out.append(f"| {l['indice']} | {l['inicio']} | {l['fim']} | {l['cobertura']:.0%} | {l['texto']} |")
    return "\n".join(out) + "\n"


def _ler_excecoes_letra(projeto: Path, slug: str) -> dict | None:
    """qa/excecao_letra.json do projeto (registro humano). Só vale para o slug dele."""
    arq = Path(projeto) / "qa" / "excecao_letra.json"
    if not arq.is_file():
        return None
    reg = json.loads(arq.read_text(encoding="utf-8"))
    return reg if reg.get("projeto") == slug else None


def executar(projeto: Path, manifesto: dict, slug: str) -> dict:
    import transcrever as tr
    projeto = Path(projeto)
    linhas = carregar_letra(projeto, manifesto)
    trans = projeto / (manifesto.get("palavras_vocal") or "entradas/transcricao.json")
    words = json.loads(trans.read_text(encoding="utf-8")).get("words", [])
    from _vx import projeto as vx_projeto
    vocal = vx_projeto.stem(projeto, "vocals", manifesto)
    lacunas = []
    if vocal.is_file():
        lacunas = tr.lacunas_vocais(words, tr.energia_vocal(vocal))
        # antes da 1a linha cantada: vocalise/ad-lib de intro nao tem letra
        primeira = min((float(w["start"]) for w in words), default=0.0)
        lacunas = [x for x in lacunas if x["fim"] > primeira + 0.5]
        # voz sem nenhuma letra pendente (vocalise/ad-lib/outro) nao reprova; so a que
        # deveria conter versos (mesma regra do transcrever). Linha nao cantada continua
        # sendo pega por 'linhas_sem_audio'.
        lacunas, _vocalises = tr.classificar_lacunas(lacunas, words, tr.tokens_da_letra(linhas))
    rel = auditar(linhas, words, lacunas, excecoes=_ler_excecoes_letra(projeto, slug))
    qa = projeto / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "auditoria_letra.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    (qa / "auditoria_letra.md").write_text(_markdown(rel, slug), encoding="utf-8")
    return rel
