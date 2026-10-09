#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Titulos — Title Card de abertura e End Card de encerramento do corpo do AMV.

Ordem de producao:
    cenas-auto -> cenas-ia -> titulos -> manga-auto -> graficos-auto -> planejar

Contrato do canal (AGENTS.md): Intro oficial -> Title Card -> AMV -> Outro.
- Title Card: primeiros ``title_dur`` s do corpo (antes da 1a frase cantada), arte IA
  da capa com push-in + tipografia (faixa, personagem, anime, kanji) com fade.
- End Card: ultimos ``end_dur`` s, fundo IA escurecido + marca/CTA, fade para preto.
- O fade de audio (entrada/saida) e aplicado no master por compositor_master_gpu.
- Identidade 100% do manifesto; idempotente com state.json; falha fechada se a
  timeline aplicada for editada por fora; sem ComfyUI cai para frame real do anime.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from _vx import cache as vx_cache, config as vx_config
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import cenas_ia_pipeline as cia
import gerador_imagem_local as gil
import render_dispatch as rd
from manga_auto_pipeline import _replace_interval
from semantic_vision import imagem_ia_cfg
from timeline_clipe import fonte as fonte_clip, validar as validar_timeline

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projetos"
FONTES = Path(__file__).resolve().parent / "fontes"
SCHEMA_VERSION = 1
RENDER_VERSION = 1
TIPO_TITULO, TIPO_FIM = "vx_title_card", "vx_end_card"
DOWNSTREAM = {"vx_manga_auto", "vx_graphics_auto"}
DEFAULTS = {"enabled": True, "title_dur": 5.0, "end_dur": 5.0, "cta": "INSCREVA-SE NO CANAL",
            "marca": "VX RAPS", "handle": "@VXRaps", "min_folga_voz": 0.4}
W, H, FPS = 1920, 1080, 30


def _cfg(manifest: dict) -> dict:
    # codigo < config/estudio.json[titulos] < projeto.json[titulos]
    return vx_config.secao("titulos", DEFAULTS, manifest)


def _hash(d) -> str:
    # Hash canonico do nucleo (vx/cache.hash_obj). Ver decisao 008.
    return vx_cache.hash_obj(d)


def _fonte(nome: str, tam: int):
    for n in (nome, "BebasNeue-Regular.ttf"):
        p = FONTES / n
        if p.is_file():
            return ImageFont.truetype(str(p), tam)
    return ImageFont.load_default()


def _rgb(h: str, padrao=(123, 31, 162)):
    h = (h or "").lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else padrao
    except ValueError:
        return padrao


def _texto_centro(img, y, texto, fonte, cor, glow=None, tracking=0):
    d = ImageDraw.Draw(img)
    if tracking:
        texto = (" " * tracking).join(texto)
    w = d.textlength(texto, font=fonte)
    x = (W - w) / 2
    if glow:
        g = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).text((x, y), texto, font=fonte, fill=glow + (220,))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(18)))
    d.text((x + 4, y + 5), texto, font=fonte, fill=(0, 0, 0, 170))
    d.text((x, y), texto, font=fonte, fill=cor + (255,))
    return y + fonte.getbbox(texto)[3]


def arte_titulo(manifest: dict, destino: Path) -> Path:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    acento = _rgb((manifest.get("cor") or {}).get("destaque"))
    claro = _rgb((manifest.get("cor") or {}).get("destaque_claro"), (0, 229, 255))
    anime = str(manifest.get("anime", "")).split("(")[0].strip().upper()
    faixa = str(manifest.get("faixa", "")).upper()
    y = _texto_centro(img, 330, "VX RAPS APRESENTA", _fonte("BebasNeue-Regular.ttf", 46), (215, 215, 222), tracking=1)
    f_tit = _fonte("Cinzel-Bold.ttf", 200 if len(faixa) <= 10 else 140)
    y = _texto_centro(img, y + 30, faixa, f_tit, (255, 255, 255), glow=acento)
    d = ImageDraw.Draw(img)
    d.rectangle(((W - 520) // 2, y + 36, (W + 520) // 2, y + 41), fill=claro + (255,))
    sub = f"{str(manifest.get('personagem', '')).upper()}  \u2022  {anime}"
    _texto_centro(img, y + 66, sub, _fonte("BebasNeue-Regular.ttf", 60), claro)
    kanji = imagem_ia_cfg(manifest).get("kanji") or []
    jp = Path("C:/Windows/Fonts/msgothic.ttc")
    if kanji and jp.is_file():
        fk = ImageFont.truetype(str(jp), 54)
        for i, ch in enumerate(str(kanji[0])[:8]):
            d.text((W - 150, 240 + i * 66), ch, font=fk, fill=(240, 240, 240, 150))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino)
    return destino


def arte_fim(manifest: dict, cfg: dict, destino: Path) -> Path:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    acento = _rgb((manifest.get("cor") or {}).get("destaque"))
    claro = _rgb((manifest.get("cor") or {}).get("destaque_claro"), (0, 229, 255))
    y = _texto_centro(img, 330, str(cfg["marca"]).upper(), _fonte("Anton-Regular.ttf", 190), (255, 255, 255), glow=acento)
    y = _texto_centro(img, y + 40, str(cfg["cta"]).upper(), _fonte("BebasNeue-Regular.ttf", 74), claro, tracking=0)
    faixa = str(manifest.get("faixa", "")).upper()
    _texto_centro(img, y + 40, f"{cfg['handle']}  \u2022  {faixa}", _fonte("BebasNeue-Regular.ttf", 52), (220, 220, 228))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino)
    return destino


def _render(fundo: Path, arte: Path, saida: Path, dur: float, movimento: str, fim: bool) -> Path:
    frames = max(2, int(round(dur * FPS)))
    design = {"v": RENDER_VERSION, "fundo": fundo.name, "arte": hashlib.sha256(arte.read_bytes()).hexdigest(),
              "frames": frames, "mov": movimento, "fim": fim}
    side = saida.with_suffix(".design.json")
    if saida.is_file() and saida.stat().st_size and cia._read_json(side) == design:
        return saida
    mov = cia.filtro_movimento(movimento, frames).replace(",format=yuv420p", "")
    escurecer = "eq=brightness=-0.16:saturation=0.85" if fim else "eq=brightness=-0.08"
    fade_txt = (f"fade=t=in:st=0.35:d=0.9:alpha=1,fade=t=out:st={dur - 0.7:.3f}:d=0.6:alpha=1" if not fim
                else "fade=t=in:st=0.25:d=0.8:alpha=1")
    final = f",fade=t=out:st={dur - 1.2:.3f}:d=1.2" if fim else ",fade=t=in:st=0:d=0.5"
    fc = (f"[0:v]{mov},{escurecer}[bg];"
          f"[1:v]format=rgba,{fade_txt}[tx];"
          f"[bg][tx]overlay=0:0:format=auto{final},format=yuv420p[v]")
    rd.encode(str(saida), ["-i", str(fundo), "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(arte)],
              filtro_complexo=fc, mapa=["-map", "[v]"], args_audio=["-an"],
              args_extra=["-frames:v", str(frames), "-r", str(FPS)], silencioso=True)
    cia._write_json(side, design)
    return saida


def _frame_real(project: Path, timeline: dict, t: float, destino: Path) -> Path:
    """Fallback sem ComfyUI: frame do anime no instante t da timeline."""
    import subprocess
    seg = next(s for s in timeline["segments"] if float(s["start"]) <= t < float(s["end"]))
    src = float(seg["src"]) + t - float(seg["start"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([rd.ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{src:.3f}", "-i",
                    str(fonte_clip(project, seg["clip"])), "-frames:v", "1", str(destino)], check=True)
    return destino


def planejar(slug: str, timeline: dict | None = None) -> dict:
    project = PROJECTS / slug
    manifest = cia._read_json(project / "projeto.json", {}) or {}
    timeline = copy.deepcopy(timeline) if timeline is not None else (cia._read_json(project / "timeline.json", {}) or {})
    cfg = _cfg(manifest)
    segs = timeline.get("segments", [])
    if not cfg["enabled"] or not segs:
        return {"status": "disabled" if segs else "sem_timeline", "items": [], "config": cfg}
    fim_audio = float(timeline.get("audio_duration") or segs[-1]["end"])
    cantados = [s for s in segs if s.get("type") == "lyric"]
    primeira = float(cantados[0]["start"]) if cantados else fim_audio
    ultima = float(cantados[-1]["end"]) if cantados else 0.0
    items = []
    t_dur = min(float(cfg["title_dur"]), primeira - float(cfg["min_folga_voz"]))
    if t_dur >= 2.5:
        items.append({"tipo": TIPO_TITULO, "start": 0.0, "end": round(round(t_dur * FPS) / FPS, 6)})
    e_dur = min(float(cfg["end_dur"]), fim_audio - ultima - float(cfg["min_folga_voz"]))
    if e_dur >= 2.5:
        ini = round(round((fim_audio - e_dur) * FPS) / FPS, 6)
        items.append({"tipo": TIPO_FIM, "start": ini, "end": round(fim_audio, 6)})
    for it in items:
        it["duration"] = round(it["end"] - it["start"], 6)
    return {"status": "planned", "items": items, "config": cfg}


def executar(slug: str, somente_planejar: bool = False) -> dict:
    project = PROJECTS / slug
    qa = project / "qa" / "vx_titulos"
    qa.mkdir(parents=True, exist_ok=True)
    state = cia._read_json(qa / "state.json", {}) or {}
    current = cia._read_json(project / "timeline.json", {}) or {}
    manifest = cia._read_json(project / "projeto.json", {}) or {}
    tipos = {s.get("type") for s in current.get("segments", [])}
    if tipos & DOWNSTREAM:
        return {"status": "preserved_after_downstream_visuals", "applied": False}
    if tipos & {TIPO_TITULO, TIPO_FIM}:
        if state.get("applied_hash") == _hash(current):
            return {"status": "cached", "applied": False}
        raise RuntimeError("timeline com VX Titulos foi alterada externamente; falha fechada")
    plano = planejar(slug, current)
    cia._write_json(qa / "plano.json", plano)
    if somente_planejar or not plano["items"]:
        return {**plano, "applied": False}
    cfg = plano["config"]

    fundos = {}
    try:
        # ComfyUI sob demanda: capa/fundo ja escolhidos nao sobem o ComfyUI
        with gil.sessao_comfy():
            fundos[TIPO_TITULO] = gil.gerar_melhor(project, "capa", variacoes=4)
            fundos[TIPO_FIM] = gil.gerar_melhor(project, "fundo", variacoes=3)
    except (gil.ComfyIndisponivel, RuntimeError, TimeoutError) as exc:
        print(f"[VX TITULOS] sem arte IA ({exc}); usando frames reais do anime")
    out = project / "clips_raw" / "vx_titulos"
    for it in plano["items"]:
        eh_fim = it["tipo"] == TIPO_FIM
        fundo = fundos.get(it["tipo"]) or _frame_real(
            project, current, it["start"] + it["duration"] / 2, out / f"{it['tipo']}_fundo.png")
        arte = (arte_fim(manifest, cfg, out / "end_card_texto.png") if eh_fim
                else arte_titulo(manifest, out / "title_card_texto.png"))
        take = _render(Path(fundo), arte, out / f"{it['tipo']}.mp4", it["duration"],
                       "pull_out" if eh_fim else "push_in", eh_fim)
        it["clip"] = str(take.relative_to(project)).replace("\\", "/")
        it["fundo"] = str(Path(fundo).relative_to(project)).replace("\\", "/")

    timeline = copy.deepcopy(current)
    segs = timeline["segments"]
    for it in plano["items"]:
        seg = {"start": it["start"], "end": it["end"], "duration": it["duration"], "clip": it["clip"],
               "src": 0.0, "type": it["tipo"], "categoria": "titulos",
               "note": "VX Title Card" if it["tipo"] == TIPO_TITULO else "VX End Card"}
        segs = _replace_interval(segs, it["start"], it["end"], seg)
    timeline["segments"] = segs
    timeline["total_segmentos"] = len(segs)
    audio = cia._audio_path(project, timeline, manifest)
    erros = validar_timeline(project, timeline, audio, verificar_fontes=True)
    if erros:
        raise RuntimeError("timeline VX Titulos invalida:\n" + "\n".join(erros[:20]))
    cia._write_json(project / "timeline.json", timeline)
    pub = {**plano, "status": "applied", "applied": True}
    cia._write_json(qa / "plano.json", pub)
    cia._write_json(qa / "state.json", {"schema_version": SCHEMA_VERSION, "base_timeline": current,
                                        "applied_hash": _hash(timeline), "plan": pub})
    return pub
