#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intro_card.py — intro automatica + end card para videos do VX RAPS.

Adiciona:
  1. Intro do assets/intro/ no inicio de cada video
  2. End card (3s) com personagem, anime e @VXRaps no final

Uso como biblioteca:
    from intro_card import montar_com_intro_e_card

    montar_com_intro_e_card(
        video_saida=corte_path,
        personagem="GOJO",
        anime="JUJUTSU KAISEN",
        cor="#4169E1",
    )

Uso como CLI:
    python intro_card.py <video_entrada> <video_saida> --personagem GOJO --anime "JJK" --cor "#4169E1"
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_dispatch as rd  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

RAIZ = Path(__file__).resolve().parents[1]
INTRO_PATH = RAIZ / "assets" / "intro" / "Eu_preciso_criar_INTRO_para_o.mp4"


# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------

def _achar_fonte(nomes: list[str]) -> Path | None:
    candidatas = [
        Path("C:/Windows/Fonts"),
        Path.home() / ".local/share/fonts",
        Path(__file__).resolve().parent / "fontes",
    ]
    for base in candidatas:
        for nome in nomes:
            for ext in (".ttf", ".otf", ".TTF", ".OTF"):
                p = base / f"{nome}{ext}"
                if p.exists():
                    return p
        for nome in nomes:
            for p in base.glob(f"{nome}*"):
                if p.suffix.lower() in (".ttf", ".otf"):
                    return p
    return None


def _fonte_titulo(tamanho: int):
    p = _achar_fonte(["Cinzel-Bold", "Cinzel", "Trajan", "TrajanPro"])
    if not p:
        p = _achar_fonte(["arialbd", "Arial-Bold", "Arial"])
    return ImageFont.truetype(str(p), tamanho) if p else ImageFont.load_default()


def _fonte_sub(tamanho: int):
    p = _achar_fonte(["BebasNeue", "Bebas", "Anton", "Oswald"])
    if not p:
        p = _achar_fonte(["arial", "Arial"])
    return ImageFont.truetype(str(p), tamanho) if p else ImageFont.load_default()


# ---------------------------------------------------------------------------
# Gerar end card (imagem -> video de 3s)
# ---------------------------------------------------------------------------

def _gerar_end_card(
    personagem: str,
    anime: str,
    cor_hex: str,
    destino_png: Path,
    largura: int = 1080,
    altura: int = 1920,
) -> Path:
    """Gera a imagem do end card."""
    if Image is None:
        raise RuntimeError("Pillow necessario para gerar end card")

    cor = tuple(int(cor_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

    base = Image.new("RGB", (largura, altura), (10, 10, 12))
    dr = ImageDraw.Draw(base)

    # faixa decorativa colorida no topo
    faixa_altura = 8
    dr.rectangle([(0, 0), (largura, faixa_altura)], fill=cor)

    # faixa decorativa colorida embaixo
    dr.rectangle([(0, altura - faixa_altura), (largura, altura)], fill=cor)

    # nome do personagem (grande, centralizado)
    nome_upper = personagem.upper()
    f_nome = _fonte_titulo(90)
    bbox = dr.textbbox((0, 0), nome_upper, font=f_nome)
    tw = bbox[2] - bbox[0]
    x_nome = (largura - tw) // 2
    y_nome = int(altura * 0.35)
    # sombra
    dr.text((x_nome + 3, y_nome + 3), nome_upper, font=f_nome, fill=(0, 0, 0))
    dr.text((x_nome, y_nome), nome_upper, font=f_nome, fill=(255, 255, 255))

    # linha decorativa sob o nome
    linha_y = y_nome + (bbox[3] - bbox[1]) + 20
    linha_larg = min(tw + 60, largura - 200)
    linha_x = (largura - linha_larg) // 2
    dr.rectangle(
        [(linha_x, linha_y), (linha_x + linha_larg, linha_y + 4)],
        fill=cor,
    )

    # nome do anime (menor, abaixo da linha)
    anime_upper = anime.upper()
    f_anime = _fonte_sub(52)
    bbox_a = dr.textbbox((0, 0), anime_upper, font=f_anime)
    tw_a = bbox_a[2] - bbox_a[0]
    x_anime = (largura - tw_a) // 2
    y_anime = linha_y + 30
    dr.text((x_anime + 2, y_anime + 2), anime_upper, font=f_anime, fill=(0, 0, 0))
    dr.text((x_anime, y_anime), anime_upper, font=f_anime, fill=(*cor, ))

    # @VXRaps no rodape — mais abaixo e mais discreto (cinza medio, nao branco)
    f_vx = _fonte_sub(34)
    texto_vx = "@VXRaps"
    bbox_vx = dr.textbbox((0, 0), texto_vx, font=f_vx)
    tw_vx = bbox_vx[2] - bbox_vx[0]
    x_vx = (largura - tw_vx) // 2
    y_vx = int(altura * 0.88)
    dr.text((x_vx + 2, y_vx + 2), texto_vx, font=f_vx, fill=(0, 0, 0))
    dr.text((x_vx, y_vx), texto_vx, font=f_vx, fill=(120, 120, 130))

    # salva
    destino_png.parent.mkdir(parents=True, exist_ok=True)
    base.save(str(destino_png), quality=95)
    return destino_png


def _sondar(caminho: Path) -> tuple[int, int, float]:
    """Le largura, altura e fps REAIS do video. Cai no 1080x1920@30 se falhar.

    Usa `avg_frame_rate` (fps medio de verdade) e nao `r_frame_rate`, que num
    arquivo com timebase estranha reporta um valor nominal diferente do real.
    """
    try:
        r = subprocess.run(
            [rd.ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,avg_frame_rate",
             "-of", "default=nw=1:nk=1", str(caminho)],
            capture_output=True, text=True, timeout=20,
        )
        linhas = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        largura, altura = int(linhas[0]), int(linhas[1])
        num, _, den = linhas[2].partition("/")
        fps = float(num) / float(den or 1)
        if not (largura and altura and fps > 0):
            raise ValueError("sonda vazia")
        return (largura, altura, round(fps, 3))
    except Exception:
        return (1080, 1920, 30.0)


def _card_para_video(card_png: Path, saida: Path, duracao: float = 3.0,
                     largura: int = 1080, altura: int = 1920,
                     fps: float = 30.0) -> Path:
    """Converte a imagem do card em video com audio mudo.

    `fps` e `largura`/`altura` TEM de casar com o video principal. O concat
    demuxer usa os parametros do primeiro arquivo e DESCARTA em silencio as
    partes que nao casam — o card entrava no audio e desaparecia do video.
    """
    ff = shutil.which("ffmpeg") or "ffmpeg"
    # saida temporaria para evitar conflito de leitura/escrita no mesmo arquivo
    saida_tmp = saida.with_suffix(".tmp.mp4")
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", f"{fps:g}", "-i", str(card_png),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", str(duracao),
        "-vf", f"scale={largura}:{altura},format=yuv420p",
        "-r", f"{fps:g}",
    ] + rd.video_args() + [
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(saida_tmp),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    saida_tmp.replace(saida)
    return saida


# ---------------------------------------------------------------------------
# Montagem final: intro + video + end card
# ---------------------------------------------------------------------------

def montar_com_intro_e_card(
    video_entrada: Path,
    video_saida: Path,
    personagem: str,
    anime: str,
    cor: str = "#00F0A0",
    duracao_card: float = 3.0,
    com_intro: bool = True,
) -> Path:
    """Junta intro + video + end card num unico arquivo.

    Args:
        video_entrada: video original (corte ja feito)
        video_saida: destino final
        personagem: nome do personagem pro card
        anime: nome do anime pro card
        cor: cor hex pro card
        duracao_card: duracao do end card em segundos
        com_intro: se False, so adiciona o end card (sem intro)
    """
    video_entrada = Path(video_entrada)
    video_saida = Path(video_saida)
    video_saida.parent.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg") or "ffmpeg"

    # O concat demuxer herda os parametros do PRIMEIRO arquivo e descarta em
    # silencio as partes que nao casam. Mede o video principal uma vez e
    # normaliza intro e card para o mesmo tamanho E o mesmo fps.
    largura, altura, fps = _sondar(video_entrada)

    with tempfile.TemporaryDirectory() as tmpdir:
        # partes para concatenar
        partes: list[Path] = []

        # 1) intro (opcional) — normalizada para o tamanho e o fps do corte
        if com_intro and INTRO_PATH.exists():
            intro_rescalado = Path(tmpdir) / "intro_escalado.mp4"
            subprocess.run([
                ff, "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(INTRO_PATH),
                "-vf", f"scale={largura}:{altura}:"
                       f"force_original_aspect_ratio=increase,"
                       f"crop={largura}:{altura},fps={fps:g},format=yuv420p",
                "-r", f"{fps:g}",
            ] + rd.video_args() + [
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                str(intro_rescalado),
            ], check=True, capture_output=True, timeout=120)
            partes.append(intro_rescalado)

        # 2) video principal
        partes.append(video_entrada)

        # 3) end card — mesmo tamanho e fps, senao o concat o joga fora
        card_png = Path(tmpdir) / "end_card.png"
        _gerar_end_card(personagem, anime, cor, card_png,
                        largura=largura, altura=altura)

        card_video = Path(tmpdir) / "end_card.mp4"
        _card_para_video(card_png, card_video, duracao_card,
                         largura=largura, altura=altura, fps=fps)
        partes.append(card_video)

        # concatenar com ffmpeg concat demuxer
        lista_txt = Path(tmpdir) / "lista.txt"
        with open(lista_txt, "w", encoding="utf-8") as f:
            for p in partes:
                # usar caminho absoluto com / para compatibilidade
                caminho = str(p.resolve()).replace("\\", "/")
                f.write(f"file '{caminho}'\n")

        cmd = [
            ff, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(lista_txt),
        ] + rd.video_args() + [
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(video_saida),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg concat falhou:\n{r.stderr[-500:]}")

    # duracao final
    r = subprocess.run(
        [ff, "-hide_banner", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(video_saida)],
        capture_output=True, text=True, timeout=15,
    )
    try:
        dur_final = float(r.stdout.strip())
    except ValueError:
        dur_final = 0

    print(f"  [intro_card] {video_saida.name}  dur={dur_final:.1f}s  "
          f"(intro={'sim' if com_intro else 'nao'} + card={duracao_card}s)")
    return video_saida


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="intro_card.py")
    p.add_argument("entrada")
    p.add_argument("saida")
    p.add_argument("--personagem", required=True)
    p.add_argument("--anime", required=True)
    p.add_argument("--cor", default="#00F0A0")
    p.add_argument("--sem-intro", dest="sem_intro", action="store_true")
    p.add_argument("--dur-card", type=float, default=3.0, dest="dur_card")
    a = p.parse_args(argv)

    montar_com_intro_e_card(
        Path(a.entrada), Path(a.saida),
        a.personagem, a.anime, a.cor,
        duracao_card=a.dur_card,
        com_intro=not a.sem_intro,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
