#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chroma_auto.py — cena de TELA VERDE vira cena composta: fundo do projeto + personagem
recortado pelo chroma + AURA de energia no contorno pulsando no 808.

Pedido do usuario (Douma, 30/09/2026): packs de "twixtor/manga" trazem o personagem sobre
fundo verde de chroma key; o video saiu com a tela verde. "Quando for assim, crie uma cena,
coloque o contorno de energia e uma pulsacao."

Como decide (automatico):
- `fonte-limpa` grava a linha do tempo de chroma de cada clipe (qa/fonte_limpa.json).
- Cada segmento de footage real da timeline cuja janela de fonte tem >= `chroma_fracao_cena`
  de quadros de tela verde e SUBSTITUIDO por um take `vx_chroma` renderizado aqui.
Render por quadro:
- mascara = nao-verde (HSV), com despill (tira o verde que vaza na borda) e borda suavizada;
- fundo = cenario do projeto (artes_ia/fundo_*.png) com pan lento e tinta da cor do
  projeto; sem cenario, degrade escuro da cor;
- aura = borda da mascara (dilatacao - mascara) em 2 camadas de brilho, cor da letra/projeto,
  pulso nos picos de 808 (audio_reactive_fx) + respiracao lenta;
- push-in leve, grao e vinheta (motion_lab._acabamento).
Porta: estudio.py chroma-auto <slug>   (etapa da esteira logo depois de cenas-auto)
"""
from __future__ import annotations

import copy
import json
import math
import re
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter

import _vx  # noqa: F401
from _vx import cache as vx_cache, config as vx_config, projeto as vx_projeto

RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"
TIPO = "vx_chroma"
FPS = 30
PADRAO = {"enabled": True, "chroma_fracao_cena": 0.5, "aura_forca": 1.0, "fundo_luz": 0.55}


def _json(p: Path, padrao=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return padrao


def _hash(obj) -> str:
    # Hash canonico do nucleo (vx/cache.hash_obj). Ver decisao 008.
    return vx_cache.hash_obj(obj)


# ---------------------------------------------------------------------------
# Funcoes puras (testadas)
# ---------------------------------------------------------------------------

def mascara_chroma(q: np.ndarray, feather: float = 1.5) -> Image.Image:
    """Alfa do personagem (255) sobre tela verde (0), com borda suave."""
    import cv2
    hsv = cv2.cvtColor(q, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    verde = (h >= 40) & (h <= 85) & (s >= 90) & (v >= 60)
    alfa = np.where(verde, 0, 255).astype(np.uint8)
    alfa = cv2.morphologyEx(alfa, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))   # tira pontinhos
    m = Image.fromarray(alfa, "L")
    return m.filter(ImageFilter.GaussianBlur(feather)) if feather else m


def despill(q: np.ndarray) -> np.ndarray:
    """Tira o verde que vaza no personagem: G nunca passa do maior entre R e B."""
    a = q.astype(np.int16)
    g = np.minimum(a[..., 1], np.maximum(a[..., 0], a[..., 2]))
    out = a.copy()
    out[..., 1] = g
    return out.astype(np.uint8)


def borda_aura(mascara: Image.Image, espessura: int = 7) -> Image.Image:
    """Faixa logo FORA do contorno do personagem (onde a aura brilha)."""
    W, H = mascara.size
    peq = mascara.resize((W // 4, H // 4), Image.Resampling.BILINEAR).point(lambda p: 255 if p > 110 else 0)
    borda = ImageChops.subtract(peq.filter(ImageFilter.MaxFilter(espessura)), peq)
    return borda.resize((W, H), Image.Resampling.BILINEAR)


def forca_aura(t: float, pulso: float, base: float = 0.6) -> float:
    """Respiracao lenta (0,8 Hz) + soco no 808."""
    return max(0.0, base + 0.18 * math.sin(t * 2 * math.pi * 0.8) + 0.55 * pulso)


def segmentos_chroma(timeline: dict, linhas: dict, fracao_min: float, chroma_min: float) -> list[int]:
    """Indices dos segmentos de footage real cuja janela de fonte e majoritariamente tela verde."""
    from vx.composicao import TIPOS_DERIVADOS
    idx = []
    for i, s in enumerate(timeline.get("segments") or []):
        if not s.get("clip") or s.get("type") in TIPOS_DERIVADOS or s.get("type") == TIPO:
            continue
        linha = linhas.get(Path(str(s["clip"])).name) or []
        a = float(s["src"])
        b = a + float(s["end"]) - float(s["start"])
        dentro = [v for t, v in linha if a - 0.25 <= t <= b + 0.25]
        if dentro and float(np.mean([v >= chroma_min for v in dentro])) >= fracao_min:
            idx.append(i)
    return idx


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _fundo_base(d: Path, W: int, H: int, cor: tuple, luz: float) -> Image.Image:
    cand = sorted((d / "artes_ia").glob("fundo_*.png"))
    if cand:
        from PIL import ImageOps
        img = ImageOps.fit(Image.open(cand[-1]).convert("RGB"), (int(W * 1.12), int(H * 1.12)), Image.Resampling.LANCZOS)
        a = np.asarray(img, np.float32)
        tinta = np.asarray(cor, np.float32) * (a.mean(axis=2, keepdims=True) / 255)
        a = (a * 0.8 + tinta * 0.35) * luz
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    yy = np.linspace(0, 1, int(H * 1.12), dtype=np.float32)[:, None, None]
    a = np.asarray(cor, np.float32) * (0.12 + 0.25 * (1 - np.abs(yy - 0.55) * 1.5))
    return Image.fromarray(np.repeat(np.clip(a, 0, 255).astype(np.uint8), int(W * 1.12), axis=1))


def renderizar_take(d: Path, manifesto: dict, seg: dict, destino: Path, cfg: dict) -> Path:
    import render_dispatch as rd
    import motion_lab as ml
    from audio_reactive_fx import carregar_picos, pulso_no_tempo, relativos
    from timeline_clipe import fonte
    lab = ml.carregar_cfg(manifesto=manifesto)
    W, H = lab["largura"], lab["altura"]
    dur = float(seg["end"]) - float(seg["start"])
    n = max(1, round(dur * FPS))
    quadros = ml._decodificar(fonte(d, seg["clip"]), float(seg["src"]), dur, {**lab, "fps": FPS})
    while len(quadros) < n:
        quadros.append(quadros[-1])
    quadros = quadros[:n]
    cor_hex = ml.cor_da_letra(seg.get("note", ""), lab.get("cores") or {}) or \
        (manifesto.get("cor") or {}).get("destaque_claro") or (manifesto.get("cor") or {}).get("destaque", "#00E5FF")
    cor = ml._rgb(cor_hex)
    fundo = _fundo_base(d, W, H, cor, float(cfg["fundo_luz"]))
    try:
        picos = relativos(carregar_picos(d, manifesto), float(seg["start"]), dur)
    except Exception:
        picos = []
    acabar = ml._acabamento(lab)
    with tempfile.TemporaryDirectory(prefix="vx_chroma_") as tmp:
        pasta = Path(tmp)
        for i, arr in enumerate(quadros):
            t = i / FPS
            prog = t / max(0.1, dur)
            dx = int((fundo.width - W) * (0.2 + 0.6 * prog))
            base = fundo.crop((dx, (fundo.height - H) // 2, dx + W, (fundo.height - H) // 2 + H)).convert("RGBA")
            mascara = mascara_chroma(arr)
            forca = forca_aura(t, pulso_no_tempo(picos, t)) * float(cfg["aura_forca"])
            borda = borda_aura(mascara)
            for raio, ganho in ((6, 1.9), (22, 1.3)):
                alfa = borda.filter(ImageFilter.GaussianBlur(raio)).point(lambda p, g=ganho: min(255, int(p * g * forca)))
                aura = Image.new("RGBA", (W, H), (*cor, 0))
                aura.putalpha(alfa)
                base = Image.alpha_composite(base, aura)
            sujeito = Image.fromarray(despill(arr)).convert("RGBA")
            quadro = Image.composite(sujeito, base, mascara).convert("RGB")
            quadro = ml.transformar(quadro, 1.0 + 0.04 * prog, 0, 0)
            acabar(quadro).save(pasta / f"f_{i:05d}.png", compress_level=1)
        rd.encode(saida=str(destino), entradas=["-framerate", str(FPS), "-i", str(pasta / "f_%05d.png")],
                  mapa=["-map", "0:v:0"], args_audio=["-an"], args_extra=["-r", str(FPS), "-frames:v", str(n)],
                  cq="17", silencioso=True)
    return destino


def executar(slug: str) -> dict:
    import fonte_limpa as fl
    d = PROJETOS / slug
    manifesto = _json(d / "projeto.json", {}) or {}
    cfg = vx_config.secao("chroma_auto", PADRAO, manifesto)
    qa = d / "qa" / "vx_chroma"
    qa.mkdir(parents=True, exist_ok=True)
    timeline = _json(d / "timeline.json", {}) or {}
    if not cfg.get("enabled", True):
        return {"slug": slug, "status": "desligado", "takes": 0}
    fc = fl.cfg()
    alvos = segmentos_chroma(timeline, fl.linhas_chroma(d), float(cfg["chroma_fracao_cena"]), float(fc["chroma_min"]))
    out_dir = d / "clips_raw" / "vx_chroma"
    out_dir.mkdir(parents=True, exist_ok=True)
    feitos = []
    novo = copy.deepcopy(timeline)
    for k, i in enumerate(alvos, 1):
        seg = timeline["segments"][i]
        spec = {"clip": seg["clip"], "src": seg["src"], "start": seg["start"], "end": seg["end"],
                "note": seg.get("note", ""), "cfg": cfg}
        nome = re.sub(r"[^a-z0-9]+", "_", Path(seg["clip"]).stem.lower())[:30]
        destino = out_dir / f"{k:02d}_{nome}_{float(seg['src']):.1f}s.mp4"
        spec_arq = destino.with_suffix(".spec.json")
        if not (destino.is_file() and _json(spec_arq) == json.loads(json.dumps(spec, default=str))):
            renderizar_take(d, manifesto, seg, destino, cfg)
            spec_arq.write_text(json.dumps(spec, ensure_ascii=False, default=str), encoding="utf-8")
        novo["segments"][i] = {**seg, "clip": str(destino.relative_to(d)).replace("\\", "/"), "src": 0.0,
                               "type": TIPO, "graphics_locked": True,
                               "chroma": {"fonte": seg["clip"], "src": seg["src"], "tipo_original": seg.get("type")}}
        feitos.append({"start": seg["start"], "end": seg["end"], "fonte": seg["clip"], "src": seg["src"],
                       "take": novo["segments"][i]["clip"]})
    if feitos:
        (d / "timeline.json").write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding="utf-8")
    rel = {"slug": slug, "status": "applied" if feitos else "sem_tela_verde", "takes": len(feitos), "itens": feitos,
           "applied_hash": _hash(novo)}
    (qa / "state.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    return rel
