#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baixar_clipes.py — traz o material visual bruto para clips_raw/ (yt-dlp).

E biblioteca; a porta e `estudio.py clipes <slug>`. As fontes vivem no
MANIFESTO (projeto.json -> "clips_fontes"), nunca no codigo:

    "clips_fontes": [
      {"nome": "eren_rumbling", "url": "https://youtu.be/XXXX",
       "de": 12.0, "ate": 40.0, "nota": "rumbling andando"},
      ...
    ]

Para cada fonte: baixa a melhor qualidade <=1080p, corta [de,ate] se dado,
normaliza para 1920x1080@30 (enquadra, nunca corta o rosto: pad sobre fundo
borrado) e grava clips_raw/<nome>.mp4. Depois audita cada clipe (abre, duracao
plausivel, nao e tela morta). Nao decide timeline — so entrega o material.

🔴 Pureza canonica e responsabilidade de quem escolhe a URL + do porteiro de
imagem no render. Aqui so garantimos que o arquivo existe e tem imagem.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import render_dispatch as rd


def _ytdlp_bin() -> str:
    return shutil.which("yt-dlp") or "yt-dlp"


def _baixar_fonte(url: str, destino_bruto: Path, *, de: Optional[float] = None,
                  ate: Optional[float] = None) -> Path:
    """Baixa a URL (<=1080p, mp4). Se de/ate dados, baixa so a secao (mais rapido)."""
    cmd = [_ytdlp_bin(), "-f", "bv*[height<=1080]+ba/b[height<=1080]",
           "--merge-output-format", "mp4", "-o", str(destino_bruto)]
    if de is not None and ate is not None:
        # baixa apenas a secao pedida; *de-ate em segundos
        cmd += ["--download-sections", f"*{de}-{ate}", "--force-keyframes-at-cuts"]
    cmd += [url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not destino_bruto.exists():
        raise RuntimeError(f"yt-dlp falhou para {url}:\n{(r.stderr or '')[-500:]}")
    return destino_bruto


def _normalizar(bruto: Path, destino: Path, *, de: Optional[float] = None,
                ate: Optional[float] = None) -> Path:
    """Enquadra em 1920x1080@30 sobre fundo borrado (nunca center-crop no rosto)."""
    entradas = []
    # se baixamos por --download-sections, o corte ja foi feito; senao corta aqui
    baixou_secao = de is not None and ate is not None
    if not baixou_secao and de is not None:
        entradas += ["-ss", str(de)]
        if ate is not None:
            entradas += ["-t", str(ate - de)]
    entradas += ["-i", str(bruto)]
    vf = ("[0:v]split=2[b][f];"
          "[b]scale=1920:1080:force_original_aspect_ratio=increase,"
          "crop=1920:1080,gblur=sigma=28[bg];"
          "[f]scale=1920:1080:force_original_aspect_ratio=decrease[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v]")
    rd.encode(str(destino), entradas, filtro_complexo=vf,
              mapa=["-map", "[v]"], args_audio=["-an"], silencioso=True)
    return destino


def baixar(fontes: list[dict], destino_dir: Path) -> list[dict]:
    """Baixa e normaliza cada fonte. Devolve lista de resultados por clipe."""
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    resultados = []
    for i, fonte in enumerate(fontes):
        nome = fonte.get("nome") or f"clip_{i:02d}"
        url = fonte["url"]
        de, ate = fonte.get("de"), fonte.get("ate")
        destino = destino_dir / f"{nome}.mp4"
        res = {"nome": nome, "url": url, "arquivo": str(destino), "erro": None}
        # ja existe e abre? pula (re-baixar toda vez desperdica banda/tempo).
        if destino.exists() and _dur(destino) > 0.1:
            res["dur"] = _dur(destino)
            res["pulado"] = True
            resultados.append(res)
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="vx_dl_") as tmp:
                bruto = Path(tmp) / f"{nome}_bruto.mp4"
                _baixar_fonte(url, bruto, de=de, ate=ate)
                # se baixou secao, nao recorta de novo; so normaliza
                _normalizar(bruto, destino,
                            de=(None if (de is not None and ate is not None) else de),
                            ate=(None if (de is not None and ate is not None) else ate))
            res["dur"] = _dur(destino)
        except Exception as e:  # noqa: BLE001
            res["erro"] = str(e)
        resultados.append(res)
    return resultados


def _dur(caminho: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(caminho)], capture_output=True, text=True)
    try:
        return round(float((r.stdout or "0").strip()), 2)
    except ValueError:
        return 0.0
