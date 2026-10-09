#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""critico_imagem.py — VX Image Critic: escolhe a melhor variacao gerada, sem olho humano.

Pontua cada imagem com OpenCLIP (mesmo modelo do Scene Intelligence):
- alinhamento: imagem x intencao da cena (tags/prompt);
- identidade: imagem x personagem/anime do manifesto (so quando a cena tem personagem);
- qualidade: "ilustracao anime detalhada" contra blur/anatomia quebrada/texto/marca d'agua;
- exposicao: penaliza quadro escuro/estourado demais para AMV.

O ranking e relativo entre variacoes da MESMA cena; os valores nao sao nota absoluta.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageStat

MODELO = "ViT-B-32"
PRETREINO = "laion2b_s34b_b79k"
QUALIDADE_POS = "a high quality, detailed, sharp anime key visual illustration"
QUALIDADE_NEG = (
    "a blurry low quality image",
    "an anime drawing with deformed anatomy, extra fingers and broken hands",
    "an image with text, letters, logo or watermark",
    "a messy distorted noisy picture",
)
PESOS = {"alinhamento": 1.0, "identidade": 0.7, "qualidade": 0.05, "exposicao": 0.04}

_cache: Dict[str, object] = {}


def _carregar():
    if "model" not in _cache:
        import open_clip
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        model, _, prep = open_clip.create_model_and_transforms(MODELO, pretrained=PRETREINO, device=dev)
        model.eval()
        _cache.update(model=model, prep=prep, tok=open_clip.get_tokenizer(MODELO), dev=dev, torch=torch)
    return _cache


def exposicao(img: Image.Image) -> float:
    """1.0 para luma media 45-170; cai linearmente fora disso."""
    m = ImageStat.Stat(img.convert("L")).mean[0]
    if 45 <= m <= 170:
        return 1.0
    return max(0.0, 1.0 - (45 - m) / 45 if m < 45 else 1.0 - (m - 170) / 85)


def pontuar(imagens: List[Path], intencao: str, identidade: Optional[str] = None) -> List[dict]:
    """Retorna [{path, final, alinhamento, identidade, qualidade, exposicao}] do melhor ao pior."""
    if not imagens:
        return []
    c = _carregar()
    torch, model = c["torch"], c["model"]
    textos = [intencao, identidade or intencao, QUALIDADE_POS, *QUALIDADE_NEG]
    pils = [Image.open(p).convert("RGB") for p in imagens]
    with torch.no_grad():
        t = model.encode_text(c["tok"](textos).to(c["dev"]))
        t = t / t.norm(dim=-1, keepdim=True)
        x = torch.stack([c["prep"](im) for im in pils]).to(c["dev"])
        f = model.encode_image(x)
        f = f / f.norm(dim=-1, keepdim=True)
        sims = (f @ t.T).float().cpu()
    out = []
    for i, p in enumerate(imagens):
        s = sims[i]
        qual = float(torch.softmax(s[2:] * 100.0, dim=0)[0])
        row = {
            "path": str(p),
            "alinhamento": round(float(s[0]), 5),
            "identidade": round(float(s[1]), 5) if identidade else 0.0,
            "qualidade": round(qual, 5),
            "exposicao": round(exposicao(pils[i]), 4),
        }
        row["final"] = round(sum(PESOS[k] * row[k] for k in PESOS), 5)
        out.append(row)
    out.sort(key=lambda r: -r["final"])
    return out


def liberar() -> None:
    if "torch" in _cache:
        torch = _cache["torch"]
        _cache.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
