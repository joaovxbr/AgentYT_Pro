#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Shorts — pacote vertical automatico (YouTube Shorts / TikTok / Reels) a partir da timeline.

Porta: python estudio.py shorts <slug> [--n 3] [--dur 30] [--planejar]

- Escolhe os trechos pela letra + energia: cada short comeca numa frase cantada e
  termina no fim de uma frase; favorece refrao, energia RMS e takes especiais
  (cenas IA, manga, graphics) dentro da janela; sem sobreposicao entre shorts.
- Gancho automatico = frase mais intensa do trecho (semantic_scene_matcher), ou
  projeto.json -> shorts.ganchos (lista) quando o diretor quiser escrever.
- Fonte limpa (sem legenda queimada) renderizada da propria timeline + plano de camera,
  depois layout POV oficial (cena no meio, gancho no topo, letra word-by-word).
- Palavras de destaque vem do manifesto (scene_semantics + faixa), nunca hardcoded.
- Saida: saidas/shorts/NN_<slug>_<inicio>s.mp4 + saidas/shorts/pacote.json.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pov_lyrics_official as pov
import semantic_scene_matcher as sm
from publicacao_doc import frase_natural
from semantic_vision import scene_semantics_cfg
from style_preset_engine import normalizar

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projetos"
ESPECIAIS_TIPOS = {"vx_cena_ia", "vx_manga_auto", "vx_graphics_auto"}
FONTE_ACAO = "Black Ops One"
FONTE_TITULO = "Bangers"


def _json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def fonte_letra(project: Path) -> Path:
    for nome in ("transcricao_canonica.json", "letra_sincronizada.json"):
        p = project / nome
        if p.is_file():
            return p
    raise FileNotFoundError("sem transcricao_canonica.json nem letra_sincronizada.json")


def palavras_especiais(manifest: dict) -> dict:
    """Tecnicas/golpes do manifesto -> fonte de acao; titulo da faixa -> fonte de titulo."""
    out = {}
    for row in (scene_semantics_cfg(manifest).get("labels") or []):
        if str(row.get("kind")) != "action":
            continue
        for nome in [row.get("name", ""), *(row.get("aliases") or [])]:
            n = pov.norm(str(nome))
            if n and " " not in n and len(n) >= 4:
                out[n] = FONTE_ACAO
    for w in pov.norm(str(manifest.get("faixa", ""))).split():
        if len(w) >= 4:
            out[w] = FONTE_TITULO
    return out


def _energia(audio: Path, passo: float = 0.5) -> list[float]:
    import librosa
    import numpy as np
    y, sr = librosa.load(str(audio), sr=22050, mono=True)
    hop = int(sr * passo)
    rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    m = float(np.max(rms)) or 1.0
    return [float(x) / m for x in rms]


def planejar(slug: str, n: int = 3, dur: float = 30.0, energia: list[float] | None = None) -> dict:
    project = PROJECTS / slug
    manifest = _json(project / "projeto.json", {}) or {}
    timeline = _json(project / "timeline.json", {}) or {}
    linhas = [l for l in pov.canonical_lines(fonte_letra(project)) if str(l.get("text", "")).strip()]
    if not linhas:
        raise ValueError("letra sincronizada vazia")
    audio_dur = float(timeline.get("audio_duration") or linhas[-1]["end"])
    if energia is None:
        audio = project / (manifest.get("audio_fonte") or f"entradas/{slug}_normalizado.wav")
        energia = _energia(audio)
    passo = audio_dur / max(1, len(energia))
    contagem = {}
    for l in linhas:
        k = normalizar(l["text"])
        contagem[k] = contagem.get(k, 0) + 1
    especiais = [(float(s["start"]), float(s["end"])) for s in timeline.get("segments", [])
                 if s.get("type") in ESPECIAIS_TIPOS]

    candidatos = []
    for i, ini_linha in enumerate(linhas):
        a = float(ini_linha["start"]) - 0.25
        if a < 0:
            continue
        # fim = ultima frase que termina dentro de dur (+1s de folga)
        fim_idx = None
        for j in range(i, len(linhas)):
            if float(linhas[j]["end"]) - a <= dur + 1.0:
                fim_idx = j
            else:
                break
        if fim_idx is None or fim_idx - i < 2:
            continue
        b = min(audio_dur, float(linhas[fim_idx]["end"]) + 0.6)
        if b - a < dur * 0.7:
            continue
        janela = linhas[i:fim_idx + 1]
        e = energia[int(a / passo):max(int(a / passo) + 1, int(b / passo))]
        en = sum(e) / max(1, len(e))
        refrao = sum(1 for l in janela if contagem[normalizar(l["text"])] > 1) / len(janela)
        esp = sum(1 for x, y in especiais if x >= a and y <= b)
        intensidades = [(sm.interpretar_texto(l["text"], manifest)["target_intensity"], l) for l in janela]
        score = 0.55 * en + 0.25 * refrao + 0.20 * min(1.0, esp / 2)
        ranking = [l["text"] for _, l in sorted(intensidades, key=lambda x: -x[0])]
        candidatos.append({"start": round(a, 3), "end": round(b, 3), "duration": round(b - a, 3),
                           "score": round(score, 5), "energia": round(en, 4),
                           "refrao": round(refrao, 3), "takes_especiais": esp,
                           "linhas_rank": list(dict.fromkeys(ranking)),
                           "primeira_linha": ini_linha["text"]})

    selecionados = []
    for c in sorted(candidatos, key=lambda x: (-x["score"], x["start"])):
        if any(c["start"] < s["end"] and c["end"] > s["start"] for s in selecionados):
            continue
        selecionados.append(c)
        if len(selecionados) >= n:
            break
    selecionados.sort(key=lambda x: x["start"])
    manuais = ((manifest.get("shorts") or {}).get("ganchos") or [])
    usadas = set()
    for k, c in enumerate(selecionados):
        # frase mais intensa do trecho que ainda nao virou gancho de outro short
        linha = next((t for t in c.pop("linhas_rank") if normalizar(t) not in usadas), c["primeira_linha"])
        usadas.add(normalizar(linha))
        c["linha_gancho"] = linha
        c["gancho"] = str(manuais[k]) if k < len(manuais) else linha.upper()
    return {"slug": slug, "candidatos": len(candidatos), "selected": selecionados}


def metadados(manifest: dict, item: dict) -> dict:
    pers = manifest.get("personagem", "")
    anime = str(manifest.get("anime", "")).split("(")[0].strip()
    faixa = manifest.get("faixa", "")
    tag = lambda s: "#" + "".join(ch for ch in normalizar(s).title() if ch.isalnum())
    hashtags = " ".join(dict.fromkeys([tag(pers), tag(anime), "#VXRaps", "#RapAnime", "#Shorts"]))
    gancho = item["gancho"].rstrip(".!")
    return {
        "titulo": f"{gancho} | {pers} #Shorts"[:100],
        "descricao": f"\u201c{frase_natural(item['linha_gancho'], manifest)}\u201d \u2014 trecho de {faixa} (VX RAPS). "
                     f"Clipe completo no canal @VXRaps.\n{hashtags}",
        "tiktok": f"{gancho} \U0001F525 {faixa} \u2014 VX RAPS {hashtags.replace('#Shorts', '#amv #anime')}",
    }


def executar(slug: str, n: int = 3, dur: float = 30.0, somente_planejar: bool = False) -> dict:
    import render_clipe as rc
    project = PROJECTS / slug
    manifest = _json(project / "projeto.json", {}) or {}
    timeline = _json(project / "timeline.json", {}) or {}
    plano = planejar(slug, n=n, dur=dur)
    if somente_planejar:
        return plano
    audio = project / (timeline.get("audio") or manifest.get("audio_fonte") or f"entradas/{slug}_normalizado.wav")
    out_dir = project / "saidas" / "shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.mp4"):
        old.unlink()
    especiais = palavras_especiais(manifest)
    canon = fonte_letra(project)
    anime = str(manifest.get("anime", "")).split("(")[0].strip()
    cor = (manifest.get("cor") or {}).get("destaque", "#7D2BFF")
    pacote = []
    with tempfile.TemporaryDirectory(prefix="vx_shorts_") as td:
        for k, item in enumerate(plano["selected"], 1):
            fonte = Path(td) / f"fonte_{k}.mp4"
            rc.previa(project, timeline, audio, fonte, item["start"], item["duration"], ass=None)
            saida = out_dir / f"{k:02d}_{slug}_{int(item['start'])}s.mp4"
            pov.render(fonte, canon, saida, item["start"], item["gancho"], anime,
                       manifest.get("faixa", ""), cor, item["duration"], especiais=especiais)
            pacote.append({**item, "arquivo": saida.name, **metadados(manifest, item)})
    (out_dir / "pacote.json").write_text(json.dumps({"slug": slug, "shorts": pacote}, indent=2,
                                                    ensure_ascii=False), encoding="utf-8")
    return {"slug": slug, "saida": str(out_dir), "shorts": pacote}
