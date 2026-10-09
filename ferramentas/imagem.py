#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""imagem.py — o segundo porteiro: TEM imagem no quadro entregue?

    🔴 Tela preta nao e plano.

Mede o master inteiro a ~6 fps e reprova:
    morto        luz < 14 e detalhe < 16    -> bloco >= 1,0 s, ou > 1 % do video
    quase-morto  luz < 24 e detalhe < 22    -> > 5 %
    congelado    vizinhos quase iguais       -> bloco >= 1,0 s, > 6 %
    pagina       branco sem cor > 55% quadro -> > 0,5 s (line-art de manga num AMV)

Ele NAO le texto. Cartela de terceiro, marca d'agua e legenda de dublagem se
provam com o OLHO, na folha `qa/imagem_suspeitos.png` — a folha e a prova; o
numero e so o indice dela.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

from _vx import config as _vx_config

# Limites que REPROVAM o master. Centralizados em config/porteiros.json[imagem_master];
# nunca ha override por projeto (um projeto nao afrouxa QA). Ver cerebro/decisoes/002.
LIMITES_MASTER = _vx_config.porteiro("imagem_master", {
    "max_bloco_morto_s": 1.0, "max_pct_morto": 1.0, "max_pct_quase": 5.0,
    "max_pct_congelado": 6.0, "max_pagina_s": 0.5,
})

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


FPS_AMOSTRA = 6
LARGURA = 160
ALTURA = 90


@dataclass
class RelatorioImagem:
    aprovado: bool
    duracao: float
    seg_morto: float
    pct_morto: float
    seg_quase: float
    pct_quase: float
    seg_congelado: float
    pct_congelado: float
    seg_pagina: float
    maior_bloco_morto: float
    suspeitos: List[float] = field(default_factory=list)  # segundos
    motivos: List[str] = field(default_factory=list)
    folha: Optional[str] = None


def _amostrar(caminho: Path):
    """Extrai frames a FPS_AMOSTRA em rawvideo rgb24 reduzido. Gera array (N,H,W,3)."""
    ff = shutil.which("ffmpeg") or "ffmpeg"
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-i", str(caminho),
         "-vf", f"fps={FPS_AMOSTRA},scale={LARGURA}:{ALTURA}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    buf = proc.stdout
    frame_bytes = LARGURA * ALTURA * 3
    n = len(buf) // frame_bytes
    if n == 0:
        return np.empty((0, ALTURA, LARGURA, 3), dtype=np.uint8)
    arr = np.frombuffer(buf[:n * frame_bytes], dtype=np.uint8)
    return arr.reshape(n, ALTURA, LARGURA, 3)


def mascara_pagina(frames: np.ndarray) -> np.ndarray:
    """Mascara 'pagina clara sem cor / line-art' — o criterio do proprio gate.

    Um quadro conta quando >55% dos pixels sao claros e sem cor E o desvio-padrao
    (detalhe) fica < 26/255. Mesma formula de `analisar`; fica separada para o
    catalogo de cenas marcar as mesmas janelas que o QA reprovaria (Asta,
    05/10/2026: fades brancos de clipe oficiais chegaram ao master com 3,0s).

    Aceita frames (N,H,W,3) ja reduzidos. Devolve mascara booleana (N,).
    """
    if len(frames) == 0:
        return np.zeros(0, dtype=bool)
    f = np.asarray(frames, dtype=np.float32)
    h = f.shape[1]
    f_util = f[:, int(h * 0.15):int(h * 0.85), :, :]
    detalhe = f_util.mean(axis=3).std(axis=(1, 2))
    mx = f.max(axis=3)
    mn = f.min(axis=3)
    branco = ((mn > 170) & ((mx - mn) < 30)).mean(axis=(1, 2))
    return (branco > 0.55) & (detalhe < 26)


def analisar(caminho: Path, pasta_qa: Optional[Path] = None,
             excluir_intro: float = 0.0,
             excluir_outro: float = 0.0) -> RelatorioImagem:
    """Analise de imagem do master.

    Args:
        caminho: arquivo de video
        pasta_qa: pasta para folha de contato
        excluir_intro: segundos iniciais para excluir da contagem (intro intencional)
        excluir_outro: segundos finais para excluir (outro intencional)
    """
    frames = _amostrar(Path(caminho))
    n = len(frames)
    if n == 0:
        return RelatorioImagem(False, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                               motivos=["nao foi possivel decodificar o video"])

    dt = 1.0 / FPS_AMOSTRA
    duracao = n * dt

    # exclusao de intro/outro intencional
    intro_frames = int(excluir_intro * FPS_AMOSTRA)
    outro_frames = int(excluir_outro * FPS_AMOSTRA)
    if intro_frames > 0 or outro_frames > 0:
        frames = frames[intro_frames: len(frames) - outro_frames if outro_frames > 0 else len(frames)]
        n = len(frames)
        if n == 0:
            return RelatorioImagem(True, round(duracao, 2), 0, 0, 0, 0, 0, 0, 0, 0,
                                   motivos=["video inteiro excluido (intro/outro)"])
    f = frames.astype(np.float32)

    # Quando ha letterbox/cinemascope (barras pretas de 140px no topo e base de 1080px),
    # a proporcao real das barras e 140/1080 = ~13%. Cortamos 15% para isolar a area util com folga.
    h_f = f.shape[1]
    y1 = int(h_f * 0.15)
    y2 = int(h_f * 0.85)
    f_util = f[:, y1:y2, :, :]

    luz = f_util.mean(axis=(1, 2, 3))                       # brilho medio por frame
    # detalhe = desvio-padrao espacial (proxy de "tem coisa na tela")
    detalhe = f_util.mean(axis=3).std(axis=(1, 2))
    # cor = saturacao media (max-min por pixel)
    mx = f.max(axis=3)
    mn = f.min(axis=3)
    sat = (mx - mn).mean(axis=(1, 2))

    # Restore documented thresholds; never weaken the gate to approve a render.
    morto = (luz < 14) & (detalhe < 16)
    quase = (luz < 24) & (detalhe < 22)
    # pagina real (line-art/tela vazia) e clara E SEM detalhe. Um flash de explosao
    # com personagens/legenda por cima tem 'detalhe' alto -> nao e pagina.
    # Mesma formula em `mascara_pagina` (o catalogo de cenas marca essas janelas).
    pagina = mascara_pagina(frames)

    # congelado: diferenca media entre frames vizinhos quase nula
    dif = np.zeros(n, dtype=np.float32)
    if n > 1:
        d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2, 3))
        dif[1:] = d
    congelado = dif < 0.6
    congelado[0] = False

    def blocos(mask):
        """Lista de (inicio_seg, dur_seg) de runs True."""
        out = []
        i = 0
        while i < n:
            if mask[i]:
                j = i
                while j < n and mask[j]:
                    j += 1
                out.append((i * dt, (j - i) * dt))
                i = j
            else:
                i += 1
        return out

    b_morto = blocos(morto)
    b_congelado = blocos(congelado)
    b_pagina = blocos(pagina)

    seg_morto = float(morto.sum() * dt)
    seg_quase = float(quase.sum() * dt)
    seg_congelado = float(congelado.sum() * dt)
    seg_pagina = float(pagina.sum() * dt)
    maior_bloco_morto = max((d for _, d in b_morto), default=0.0)

    pct_morto = seg_morto / duracao * 100
    pct_quase = seg_quase / duracao * 100
    pct_congelado = seg_congelado / duracao * 100

    L = LIMITES_MASTER  # config/porteiros.json[imagem_master]
    motivos: List[str] = []
    if maior_bloco_morto >= L["max_bloco_morto_s"]:
        motivos.append(f"bloco de tela morta de {maior_bloco_morto:.1f}s (>= {L['max_bloco_morto_s']} s)")
    if pct_morto > L["max_pct_morto"]:
        motivos.append(f"{pct_morto:.1f}% de tela morta (> {L['max_pct_morto']} %)")
    if pct_quase > L["max_pct_quase"]:
        motivos.append(f"{pct_quase:.1f}% quase-morto (> {L['max_pct_quase']} %)")
    if pct_congelado > L["max_pct_congelado"]:
        motivos.append(f"{pct_congelado:.1f}% congelado (> {L['max_pct_congelado']} %)")
    if seg_pagina > L["max_pagina_s"]:
        motivos.append(f"{seg_pagina:.1f}s de pagina clara sem cor / line-art (> {L['max_pagina_s']} s)")

    aprovado = not motivos

    # suspeitos para a folha de contato: inicio dos piores blocos
    susp = []
    for ini, _d in sorted(b_morto, key=lambda x: -x[1])[:6]:
        susp.append(round(ini, 2))
    for ini, _d in sorted(b_pagina, key=lambda x: -x[1])[:4]:
        susp.append(round(ini, 2))
    for ini, _d in sorted(b_congelado, key=lambda x: -x[1])[:3]:
        susp.append(round(ini, 2))
    susp = sorted(set(susp))

    folha_path = None
    if pasta_qa is not None and susp:
        folha_path = _folha_contato(Path(caminho), susp, pasta_qa)

    return RelatorioImagem(
        aprovado=aprovado, duracao=round(duracao, 2),
        seg_morto=round(seg_morto, 2), pct_morto=round(pct_morto, 2),
        seg_quase=round(seg_quase, 2), pct_quase=round(pct_quase, 2),
        seg_congelado=round(seg_congelado, 2), pct_congelado=round(pct_congelado, 2),
        seg_pagina=round(seg_pagina, 2),
        maior_bloco_morto=round(maior_bloco_morto, 2),
        suspeitos=susp, motivos=motivos, folha=str(folha_path) if folha_path else None,
    )


def _folha_contato(video: Path, segundos: List[float], pasta_qa: Path) -> Optional[Path]:
    """Extrai um frame HD por segundo suspeito e monta uma folha 4-colunas."""
    if Image is None:
        return None
    pasta_qa.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg") or "ffmpeg"
    miniaturas = []
    for i, s in enumerate(segundos):
        alvo = pasta_qa / f"_susp_{i:02d}.jpg"
        subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(s),
             "-i", str(video), "-frames:v", "1", "-vf", "scale=480:270",
             "-q:v", "3", str(alvo)],
            check=False,
        )
        if alvo.exists():
            miniaturas.append((s, alvo))

    if not miniaturas:
        return None

    cols = 4
    rows = (len(miniaturas) + cols - 1) // cols
    cw, ch = 480, 270 + 24
    folha = Image.new("RGB", (cols * cw, rows * ch), (18, 18, 18))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(folha)
    for idx, (s, path) in enumerate(miniaturas):
        try:
            im = Image.open(path).convert("RGB")
        except Exception:
            continue
        r, c = divmod(idx, cols)
        x, y = c * cw, r * ch
        folha.paste(im, (x, y + 24))
        dr.text((x + 6, y + 6), f"#{idx}  t={s:.2f}s", fill=(0, 240, 160))
    destino = pasta_qa / "imagem_suspeitos.png"
    folha.save(destino)
    # limpa temporarios
    for _s, p in miniaturas:
        try:
            p.unlink()
        except OSError:
            pass
    return destino


# ---------------------------------------------------------------------------
# Auditoria de FONTE (clipe bruto) — diferente do porteiro do master.
#
# Um clipe twixtor/AMV usa slow-motion de proposito: quadros quase-iguais nao
# sao defeito, sao o efeito. O porteiro do master reprova >6% congelado; para a
# materia-prima isso barraria slow-mo legitimo. Aqui o criterio e outro: so
# reprova o que e mesmo INUTIL para montar — tela morta de verdade, ou clipe
# quase inteiro parado (fala estatica, cartela). Slow-mo passa.
# ---------------------------------------------------------------------------

@dataclass
class RelatorioFonte:
    nome: str
    aprovado: bool
    duracao: float
    pct_morto: float
    pct_congelado: float
    seg_pagina: float
    motivos: List[str] = field(default_factory=list)


# limiares de FONTE (mais tolerantes que os do master)
FONTE_MORTO_MAX = 2.0        # % de tela morta real tolerada
FONTE_CONGELADO_MAX = 35.0   # % — acima disso o clipe e estatico, nao slow-mo
FONTE_PAGINA_MAX = 2.0       # s de line-art/pagina clara


def auditar_fonte(caminho: Path, nome: str = None) -> RelatorioFonte:
    """Audita um clipe BRUTO com limiares de materia-prima (tolera slow-mo)."""
    caminho = Path(caminho)
    nome = nome or caminho.stem
    rel = analisar(caminho)
    motivos = []
    if rel.pct_morto > FONTE_MORTO_MAX:
        motivos.append(f"{rel.pct_morto:.1f}% de tela morta (> {FONTE_MORTO_MAX:.0f}%)")
    if rel.maior_bloco_morto >= 1.5:
        motivos.append(f"bloco morto de {rel.maior_bloco_morto:.1f}s (>= 1,5s)")
    if rel.pct_congelado > FONTE_CONGELADO_MAX:
        motivos.append(f"{rel.pct_congelado:.1f}% congelado (> {FONTE_CONGELADO_MAX:.0f}% "
                       f"— clipe estatico, nao slow-mo)")
    if rel.seg_pagina > FONTE_PAGINA_MAX:
        motivos.append(f"{rel.seg_pagina:.1f}s de pagina/line-art (> {FONTE_PAGINA_MAX:.0f}s)")
    return RelatorioFonte(
        nome=nome, aprovado=not motivos, duracao=rel.duracao,
        pct_morto=rel.pct_morto, pct_congelado=rel.pct_congelado,
        seg_pagina=rel.seg_pagina, motivos=motivos,
    )
