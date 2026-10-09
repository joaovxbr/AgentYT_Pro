#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Publicacao — documento completo de titulo/descricao para o lancamento.

Chamado por `estudio.py lancamento <slug>`; gera `saidas/PUBLICACAO.md` e devolve os
mesmos dados para o pacote_lancamento.json.

Tudo vem do projeto (manifesto, letra canonica, timeline, shorts); nada de personagem
no codigo. Overrides opcionais em projeto.json -> lancamento:
    titulo, descricao, tags, creditos (lista), links (dict nome->url), comentario_fixado.

Limites do YouTube verificados: titulo <= 100, descricao <= 5000, tags <= 500 caracteres,
capitulos (1o em 0:00, >= 3, cada um >= 10 s), hashtags <= 15.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import semantic_scene_matcher as sm

LIM_TITULO, LIM_DESC, LIM_TAGS, MIN_CAP = 100, 5000, 500, 10.0
TIPOS_FIM = {"vx_end_card"}


def _json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def mmss(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


def _hashtag(texto: str) -> str:
    return "#" + "".join(ch for ch in str(texto).title() if ch.isalnum())


def _limpa_hashtags(texto: str) -> str:
    return re.sub(r"(\s*#\w+)+\s*$", "", texto.strip()).strip()


def nomes_proprios(m: dict) -> set:
    """Tokens que devem ficar capitalizados: personagem, anime, faixa e rotulos do manifesto."""
    fontes = [m.get("personagem", ""), str(m.get("anime", "")).split("(")[0], m.get("faixa", "")]
    for r in (m.get("scene_semantics") or {}).get("labels", []):
        fontes.append(r.get("name", ""))
    out = set()
    for f in fontes:
        for w in re.findall(r"[\w?-?]+", str(f)):
            if len(w) >= 3 and w[0].isupper():
                out.add(sm.normalizar(w))
    return out


def frase_natural(texto: str, m: dict) -> str:
    """'DO C?U CAI O TROV?O O Kirin RUGIU' -> 'Do c?u cai o trov?o, o Kirin rugiu'-like: caixa de frase
    com nomes proprios preservados (sem inventar pontuacao)."""
    nomes = nomes_proprios(m)
    palavras = str(texto).strip().split()
    out = []
    for i, w in enumerate(palavras):
        base = w.lower()
        if sm.normalizar(w) in nomes:
            base = base[:1].upper() + base[1:]
        elif i == 0:
            base = base[:1].upper() + base[1:]
        out.append(base)
    return " ".join(out)


def secoes(linhas: list[dict]) -> list[dict]:
    """Agrupa frases consecutivas por secao (verse/refrain) e nomeia Verso N / Refrão / Final."""
    blocos = []
    for l in linhas:
        sec = l.get("section", "verse")
        if blocos and blocos[-1]["section"] == sec:
            blocos[-1]["linhas"].append(l)
        else:
            blocos.append({"section": sec, "linhas": [l]})
    ultimo_refrao = max((i for i, b in enumerate(blocos) if b["section"] == "refrain"), default=-1)
    n_verso = 0
    for i, b in enumerate(blocos):
        if b["section"] == "refrain":
            b["nome"] = "Refrão"
        elif ultimo_refrao >= 0 and i > ultimo_refrao:
            b["nome"] = "Final"
        else:
            n_verso += 1
            b["nome"] = f"Verso {n_verso}"
        b["start"] = float(b["linhas"][0]["start"])
        b["end"] = float(b["linhas"][-1]["end"])
    return blocos


def capitulos(blocos: list[dict], offset: float, fim_card: float | None, duracao: float) -> list[dict]:
    """Capitulos do YouTube: 0:00 Intro, uma entrada por secao (curtas fundem na anterior)."""
    caps = [{"t": 0.0, "nome": "Intro"}]
    for b in blocos:
        t = b["start"] + offset
        nome = b["nome"]
        if nome == caps[-1]["nome"].split(" \u2014 ")[0]:
            continue                       # mesma secao depois de uma fusao
        if t - caps[-1]["t"] < MIN_CAP:
            continue                       # secao curta demais: fica no capitulo anterior
        primeira = str(b["linhas"][0]["text"]).strip()
        caps.append({"t": t, "nome": f"{nome} \u2014 {primeira}" if nome != "Refrão" else nome})
    if fim_card is not None:
        t = fim_card + offset
        if t - caps[-1]["t"] >= MIN_CAP and duracao - t >= 1.0:
            caps.append({"t": t, "nome": "Encerramento"})
    return caps


def _letra(blocos: list[dict]) -> str:
    partes = []
    for b in blocos:
        txt = [str(l["text"]).strip() for l in b["linhas"]]
        if b["section"] == "refrain":
            txt = [t.upper() for t in txt]
        partes.append(f"[{b['nome']}]\n" + "\n".join(txt))
    return "\n\n".join(partes)


def _cabe_tags(candidatas: list[str]) -> list[str]:
    out, total, vistos = [], 0, set()
    for t in candidatas:
        t = str(t).strip()
        k = t.lower()
        if not t or k in vistos:
            continue
        custo = len(t) + (2 if " " in t else 0) + (1 if out else 0)   # aspas + virgula
        if total + custo > LIM_TAGS:
            continue
        out.append(t)
        vistos.add(k)
        total += custo
    return out


def gerar(projeto_dir: Path, intro_s: float, duracao_master: float, shorts: dict | None = None) -> dict:
    projeto_dir = Path(projeto_dir)
    slug = projeto_dir.name
    m = _json(projeto_dir / "projeto.json", {}) or {}
    lanc = m.get("lancamento") or {}
    pers = str(m.get("personagem", slug))
    primeiro = pers.split()[0] if pers else slug
    anime = str(m.get("anime", "")).split("(")[0].strip()
    faixa = str(m.get("faixa", slug))
    timeline = _json(projeto_dir / "timeline.json", {}) or {}

    linhas = sm._lyric_lines(projeto_dir)
    blocos = secoes(linhas)
    fim_card = next((float(s["start"]) for s in timeline.get("segments", []) if s.get("type") in TIPOS_FIM), None)
    caps = capitulos(blocos, intro_s, fim_card, duracao_master)

    # frases de destaque: refrao mais forte e verso mais intenso
    refrao = next((str(b["linhas"][0]["text"]) for b in blocos if b["section"] == "refrain"), faixa)
    intenso = max((l for l in linhas), key=lambda l: sm.interpretar_texto(l["text"], m)["target_intensity"],
                  default={"text": faixa})["text"]

    tecnicas = [r.get("name") for r in (m.get("scene_semantics") or {}).get("labels", [])
                if r.get("kind") == "action" and r.get("name")]
    entidades = [r.get("name") for r in (m.get("scene_semantics") or {}).get("labels", [])
                 if r.get("kind") == "entity" and r.get("name") and r.get("name") != pers]

    # ---- titulos ----
    principal = lanc.get("titulo") or f"{pers.upper()} \u2013 {faixa} | Rap de {anime} | VX RAPS"
    opcoes = [principal,
              f"RAP DO {primeiro.upper()} \U0001F525 {faixa} | {anime} | VX RAPS",
              f"{frase_natural(refrao, m)} \u2013 Rap do {pers} ({anime})",
              f"{faixa} \u2013 {pers} | Rap Geek de {anime} \u26A1"]
    titulos = [{"titulo": t, "caracteres": len(t), "ok": len(t) <= LIM_TITULO}
               for t in dict.fromkeys(x for x in opcoes if x)]

    # ---- tags / hashtags ----
    tags = _cabe_tags([*(lanc.get("tags") or []), pers, f"rap do {primeiro.lower()}", f"{pers} rap",
                       anime, f"rap {anime}", faixa, "VX RAPS", "rap anime", "anime rap", "rap geek",
                       "trap geek", "AMV", *tecnicas, *entidades])
    hashtags = list(dict.fromkeys([_hashtag(pers), _hashtag(anime), "#VXRaps", "#RapAnime",
                                   "#RapGeek", _hashtag(faixa)]))[:15]

    # ---- descricao ----
    gancho = _limpa_hashtags(lanc.get("descricao") or
                             f"\u201c{faixa}\u201d \u2014 rap inspirado em {pers} ({anime}).")
    creditos = lanc.get("creditos") or ["M\u00fasica e letra: VX RAPS",
                                        "Edi\u00e7\u00e3o, cenas e motion: VX Studio"]
    links = lanc.get("links") or {}
    blocos_desc = [
        gancho,
        "\U0001F514 Inscreva-se e ative o sininho: @VXRaps",
        "\u23F1\uFE0F CAP\u00cdTULOS\n" + "\n".join(f"{mmss(c['t'])} {c['nome']}" for c in caps),
    ]
    if links:
        blocos_desc.append("\U0001F3A7 OU\u00c7A / SIGA\n" + "\n".join(f"{k}: {v}" for k, v in links.items()))
    blocos_desc += [
        f"\U0001F4DD LETRA \u2014 {faixa}\n\n" + _letra(blocos),
        "\U0001F3A4 CR\u00c9DITOS\n" + "\n".join(creditos) +
        f"\nPersonagens e cenas de {anime} pertencem aos seus respectivos detentores. Obra de f\u00e3 / homenagem.",
        " ".join(hashtags),
    ]
    descricao = "\n\n".join(blocos_desc)
    if len(descricao) > LIM_DESC:   # corta a letra primeiro, nunca os capitulos
        blocos_desc = [b for b in blocos_desc if not b.startswith("\U0001F4DD")]
        descricao = "\n\n".join(blocos_desc)

    comentario = lanc.get("comentario_fixado") or (
        f"\U0001F525 Qual parte bateu mais forte: \u201c{frase_natural(refrao, m)}\u201d ou "
        f"\u201c{frase_natural(intenso, m)}\u201d? \U0001F447\nE qual personagem voc\u00eas querem no pr\u00f3ximo rap da VX RAPS?")

    problemas = []
    if len(principal) > LIM_TITULO:
        problemas.append("titulo principal > 100")
    if len(descricao) > LIM_DESC:
        problemas.append("descricao > 5000")
    if len(caps) < 3:
        problemas.append("menos de 3 capitulos (YouTube nao exibe)")

    doc = {"titulos": titulos, "titulo_escolhido": principal, "descricao": descricao,
           "descricao_caracteres": len(descricao), "capitulos": caps, "tags": tags,
           "tags_caracteres": sum(len(t) for t in tags) + len(tags) - 1, "hashtags": hashtags,
           "comentario_fixado": comentario, "problemas": problemas}
    (projeto_dir / "saidas" / "PUBLICACAO.md").write_text(_markdown(m, doc, shorts or {}, slug), encoding="utf-8")
    return doc


def _markdown(m: dict, d: dict, shorts: dict, slug: str) -> str:
    faixa, pers = m.get("faixa", ""), m.get("personagem", "")
    anime = str(m.get("anime", "")).split("(")[0].strip()
    L = [f"# Publicação — {pers} · {faixa}", ""]
    L += ["## Vídeo principal (YouTube)", "", "### Título (use o 1º; os outros são para teste A/B)", ""]
    for i, t in enumerate(d["titulos"], 1):
        L.append(f"{i}. `{t['titulo']}` — {t['caracteres']}/100{'' if t['ok'] else ' ⚠️ LONGO'}")
    L += ["", f"### Descrição ({d['descricao_caracteres']}/5000 caracteres) — copie o bloco inteiro", "",
          "```text", d["descricao"], "```", "",
          f"### Tags ({d['tags_caracteres']}/500 caracteres) — cole no campo Tags", "",
          "```text", ", ".join(d["tags"]), "```", "",
          "### Comentário fixado", "", "```text", d["comentario_fixado"], "```", "",
          "### Configuração do upload", "",
          f"- Miniatura: `saidas/{slug}_capa_ia.jpg` (1280x720)",
          "- Categoria: Música · Idioma do vídeo: Português (Brasil)",
          "- Público: não é conteúdo para crianças",
          "- Tela final: usar os últimos 5 s (End Card) com vídeo recomendado + botão de inscrição",
          "- Capítulos: já estão na descrição (primeiro em 0:00)",
          "- Playlist: Raps de " + anime, ""]
    lista = shorts.get("shorts") or []
    if lista:
        L += ["## Shorts / TikTok / Reels", ""]
        for s in lista:
            L += [f"### {s.get('arquivo', '')}", "",
                  f"**YouTube Shorts — título:** `{s.get('titulo', '')}`", "",
                  "**Descrição:**", "", "```text", s.get("descricao", ""), "```", "",
                  "**TikTok / Reels — legenda:**", "", "```text", s.get("tiktok", ""), "```", ""]
    if d["problemas"]:
        L += ["## ⚠️ Pendências", ""] + [f"- {p}" for p in d["problemas"]] + [""]
    return "\n".join(L)
