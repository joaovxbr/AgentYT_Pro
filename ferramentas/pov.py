#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pov.py — o corte POV para Shorts do YouTube.

O formato de gancho: uma caixa de POV no alto faz a pergunta, a cena entra
embaixo, e o fundo e o proprio video desfocado (nunca preto).

    🔴 No POV o gancho e o PRIMEIRO frame. Intro antes dele mata o formato.

Layout 1080x1920 (todas as faixas ocupadas — Short nao tem terco de sobra):

    +------------------------------+  0
    |   fundo desfocado do proprio |
    |   video (sigma 35)           |
    |  +------------------------+  |  ~330
    |  | POV - ANIME // TEMA    |  |         caixa com borda na cor
    |  | O gancho em uma frase  |  |         do personagem
    |  +------------------------+  |
    |------------------------------|  656    linha fina de acento
    |                              |
    |      A CENA (1080x608)       |         o 16:9 inteiro, nunca cortado
    |                              |
    |------------------------------|  1264
    |   MUGEN RAPS - @handle       |  ~1330
    |   fundo desfocado            |
    +------------------------------+  1920

Uso como biblioteca:

    import pov
    pov.gerar_pov(master, inicio=63.5, dur=34.5, saida=...,
                  anime="DEMON SLAYER", tema="RESPIRACAO DO SOL",
                  gancho="Voce se achava um Deus ate encontrar o Yoriichi...",
                  cor="#FF8C00")

Uso pelo estudio (a porta de criacao):

    python estudio.py pov <slug> --de 63.5 --dur 34.5 \\
        --gancho "Voce se achava um Deus ate encontrar o Yoriichi..." \\
        [--tema "RESPIRACAO DO SOL"] [--handle @VXRaps] [--com-intro]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_dispatch as rd  # noqa: E402
from legenda import filtro_subtitles  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None


# ---------------------------------------------------------------------------
# Geometria do quadro
#
# O Short tem 1920 px de altura e nenhum de sobra. A referencia que inspirou
# este layout gastava o terco de cima em preto puro; aqui todas as faixas
# carregam alguma coisa — fundo desfocado, caixa ou cena.
# ---------------------------------------------------------------------------

LARGURA = 1080
ALTURA = 1920

# A cena entra centralizada: 16:9 em 1080 de largura da 608 de altura.
# Centralizar deixa a caixa acima e a marca abaixo com folga igual.
CENA_LARGURA = 1080
CENA_ALTURA_16X9 = 608
CENA_Y = (ALTURA - CENA_ALTURA_16X9) // 2      # 656

# A caixa de POV encosta na cena por baixo, em vez de flutuar no topo.
# Colada nela o olho faz pergunta -> resposta num movimento so.
CAIXA_MARGEM_X = 44
CAIXA_FOLGA_ACIMA_DA_CENA = 36
CAIXA_PADDING = 30
CAIXA_RAIO = 22
CAIXA_BORDA = 3
CAIXA_FUNDO = (12, 14, 18, 214)               # preto quase opaco
CAIXA_ALTURA_MAX = 420                         # nao invade o topo do quadro

# Marca: logo abaixo da cena, fora da zona que a UI do Shorts cobre.
MARCA_FOLGA_ABAIXO_DA_CENA = 54

# Linhas finas de acento que separam a cena do fundo.
LINHA_ESPESSURA = 3
LINHA_ALPHA = 185

# Tipografia
ROTULO_TAMANHO = 34
GANCHO_TAMANHO = 46
MARCA_TAMANHO = 30
ENTRELINHA = 1.30

ROTULO_COR = (196, 198, 204)
GANCHO_COR = (245, 246, 248)
MARCA_COR = (150, 152, 158)

# Duracao. O piso de 30 s e o mesmo do corte vertical canonico: corte curto
# nao entrega o punchline. O teto e o limite do Shorts.
DURACAO_MINIMA = 30.0
DURACAO_MAXIMA_SHORTS = 180.0

# Fundo: desfoque forte e escurecido, para a cena ser o unico foco.
FUNDO_SIGMA = 35
FUNDO_BRILHO = -0.18

SEPARADOR = "//"
MARCADOR_ROTULO = "POV"
PONTO = "\u2022"


# ---------------------------------------------------------------------------
# Fontes (mesma convencao do intro_card.py)
# ---------------------------------------------------------------------------

def _achar_fonte(nomes: List[str]) -> Optional[Path]:
    bases = [
        Path("C:/Windows/Fonts"),
        Path.home() / ".local/share/fonts",
        Path(__file__).resolve().parent / "fontes",
    ]
    for base in bases:
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


def _fonte_rotulo(tamanho: int):
    p = _achar_fonte(["BebasNeue", "Bebas", "Oswald", "Anton", "arialbd"])
    return ImageFont.truetype(str(p), tamanho) if p else ImageFont.load_default()


def _fonte_gancho(tamanho: int):
    p = _achar_fonte(["segoeui", "Lato-Regular", "OpenSans-Regular", "arial"])
    return ImageFont.truetype(str(p), tamanho) if p else ImageFont.load_default()


def _hex_para_rgb(cor_hex: str) -> tuple:
    s = (cor_hex or "").lstrip("#").strip()
    if len(s) != 6:
        return (255, 140, 0)
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 140, 0)


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def _quebrar(dr, texto: str, fonte, largura_max: int) -> List[str]:
    """Quebra o texto em linhas que cabem em largura_max."""
    linhas: List[str] = []
    atual = ""
    for palavra in (texto or "").split():
        teste = f"{atual} {palavra}".strip()
        if dr.textlength(teste, font=fonte) <= largura_max or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _altura_linha(fonte, tamanho: int) -> int:
    return int(tamanho * ENTRELINHA)


# ---------------------------------------------------------------------------
# A sobreposicao: caixa de POV + linhas + marca, num PNG so
# ---------------------------------------------------------------------------

def _montar_sobreposicao(
    gancho: str,
    anime: str,
    tema: str,
    marca: str,
    handle: str,
    cor_hex: str,
    destino_png: Path,
) -> Path:
    """Desenha a camada de cima inteira num PNG 1080x1920 com alpha.

    Um unico overlay no ffmpeg em vez de tres: menos passes de filtro, e a
    posicao da caixa pode depender da altura do texto (o que drawtext nao faz).
    """
    if Image is None:
        raise RuntimeError("Pillow necessario para montar a camada do POV")

    cor = _hex_para_rgb(cor_hex)
    camada = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    dr = ImageDraw.Draw(camada)

    f_rotulo = _fonte_rotulo(ROTULO_TAMANHO)
    f_gancho = _fonte_gancho(GANCHO_TAMANHO)
    f_marca = _fonte_rotulo(MARCA_TAMANHO)

    largura_caixa = LARGURA - CAIXA_MARGEM_X * 2
    largura_texto = largura_caixa - CAIXA_PADDING * 2

    # --- rotulo: "POV * ANIME // TEMA" -------------------------------------
    partes = [p for p in (anime.strip().upper(), tema.strip().upper()) if p]
    rotulo_resto = f" {SEPARADOR} ".join(partes)

    # --- gancho, quebrado para caber ---------------------------------------
    linhas_gancho = _quebrar(dr, gancho, f_gancho, largura_texto)

    h_rotulo = _altura_linha(f_rotulo, ROTULO_TAMANHO)
    h_gancho = _altura_linha(f_gancho, GANCHO_TAMANHO)
    altura_caixa = min(
        CAIXA_PADDING * 2 + h_rotulo + int(h_gancho * 0.25)
        + h_gancho * len(linhas_gancho),
        CAIXA_ALTURA_MAX,
    )

    # a caixa encosta na cena por baixo
    caixa_y1 = CENA_Y - CAIXA_FOLGA_ACIMA_DA_CENA
    caixa_y0 = caixa_y1 - altura_caixa
    caixa_x0 = CAIXA_MARGEM_X
    caixa_x1 = LARGURA - CAIXA_MARGEM_X

    dr.rounded_rectangle(
        [caixa_x0, caixa_y0, caixa_x1, caixa_y1],
        radius=CAIXA_RAIO,
        fill=CAIXA_FUNDO,
        outline=cor + (255,),
        width=CAIXA_BORDA,
    )

    # rotulo: "POV" na cor do personagem, o resto em cinza claro
    x = caixa_x0 + CAIXA_PADDING
    y = caixa_y0 + CAIXA_PADDING
    dr.text((x, y), MARCADOR_ROTULO, font=f_rotulo, fill=cor + (255,))
    x += int(dr.textlength(MARCADOR_ROTULO, font=f_rotulo))
    if rotulo_resto:
        sep = f" {PONTO} "
        dr.text((x, y), sep, font=f_rotulo, fill=ROTULO_COR + (200,))
        x += int(dr.textlength(sep, font=f_rotulo))
        dr.text((x, y), rotulo_resto, font=f_rotulo, fill=ROTULO_COR + (255,))

    # gancho
    x_texto = caixa_x0 + CAIXA_PADDING
    y += h_rotulo + int(h_gancho * 0.25)
    for linha in linhas_gancho:
        if y + h_gancho > caixa_y1 - CAIXA_PADDING // 2:
            break
        dr.text((x_texto, y), linha, font=f_gancho, fill=GANCHO_COR + (255,))
        y += h_gancho

    # --- linhas de acento em volta da cena ---------------------------------
    for linha_y in (CENA_Y, CENA_Y + CENA_ALTURA_16X9):
        dr.rectangle([0, linha_y, LARGURA, linha_y + LINHA_ESPESSURA],
                     fill=cor + (LINHA_ALPHA,))

    # --- marca, abaixo da cena --------------------------------------------
    texto_marca = f"{marca.strip().upper()}  {PONTO}  {handle.strip()}"
    tw = dr.textlength(texto_marca, font=f_marca)
    dr.text(((LARGURA - tw) / 2,
             CENA_Y + CENA_ALTURA_16X9 + MARCA_FOLGA_ABAIXO_DA_CENA),
            texto_marca, font=f_marca, fill=MARCA_COR + (255,))

    destino_png.parent.mkdir(parents=True, exist_ok=True)
    camada.save(str(destino_png))
    return destino_png


# ---------------------------------------------------------------------------
# Audio: o mesmo limiter do corte canonico
# ---------------------------------------------------------------------------

AF_LIMITER = (
    "aresample=192000:resampler=soxr,"
    "alimiter=limit=0.7674:attack=5:release=60:level=0,"
    "aresample=48000:resampler=soxr"
)


def _true_peak(caminho: Path) -> str:
    r = subprocess.run(
        [rd.ffmpeg_bin(), "-hide_banner", "-i", str(caminho),
         "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r'"input_tp"\s*:\s*"?(-?\d+\.?\d*)"?', r.stderr or "")
    return m.group(1) if m else "?"


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------

def gerar_pov(
    master: Path,
    inicio: float,
    dur: float,
    saida: Path,
    gancho: str,
    anime: str = "",
    tema: str = "",
    cor: str = "#FF8C00",
    marca: str = "VX RAPS",
    handle: str = "@VXRaps",
    personagem: str = "",
    com_intro: bool = False,
    com_card: bool = True,
    ass: Optional[Path] = None,
    ass_shift: float = 0.0,
) -> Path:
    """Gera o corte POV 9:16 para Shorts.

    `com_intro` vem desligado de proposito: no POV o gancho tem de ser o
    primeiro frame. Ligar a intro empurra a pergunta para depois do terceiro
    segundo, que e onde o Short ja perdeu o espectador.
    """
    master, saida = Path(master), Path(saida)
    if not master.exists():
        raise SystemExit(f"master ausente: {master}")
    if not (gancho or "").strip():
        raise SystemExit("RECUSADO: POV sem gancho e so um corte com moldura. "
                         "Escreva a frase que faz a pergunta.")
    if dur <= DURACAO_MINIMA:
        raise SystemExit(
            f"RECUSADO: dur={dur:.1f}s <= {DURACAO_MINIMA:.0f}s. "
            "Corte curto nao entrega o punchline. Pegue um trecho MAIOR da "
            "letra — nao baixe a constante.")
    if dur > DURACAO_MAXIMA_SHORTS:
        raise SystemExit(
            f"RECUSADO: dur={dur:.1f}s > {DURACAO_MAXIMA_SHORTS:.0f}s, "
            "o teto do Shorts. Acima disso o YouTube trata como video longo.")

    saida.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        camada = _montar_sobreposicao(
            gancho=gancho, anime=anime, tema=tema, marca=marca,
            handle=handle, cor_hex=cor,
            destino_png=Path(tmp) / "camada_pov.png",
        )

        # fundo desfocado do proprio video + a cena inteira por cima,
        # e a camada de POV como ultima passada.
        # legenda karaoke queimada na CENA (nao no fundo). O .ass e escalado
        # pelo subtitles ao tamanho da cena; PlayRes do .ass (1920x1080) mapeia
        # para o 16:9 da cena, entao a legenda cai onde deve.
        sub_fg = ""
        if ass is not None:
            # helper central: escapa caminho + fontsdir (Cinzel do repo)
            sub_fg = f",{filtro_subtitles(Path(ass))}"

        fc = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
            f"crop={LARGURA}:{ALTURA},"
            f"gblur=sigma={FUNDO_SIGMA}:steps=3,"
            f"eq=brightness={FUNDO_BRILHO}[bgb];"
            f"[fg]scale={CENA_LARGURA}:-2,"
            f"eq=contrast=1.08:saturation=1.15:brightness=0.02,"
            f"unsharp=5:5:0.8:5:5:0.0{sub_fg}[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:{CENA_Y}[v0];"
            f"[v0][1:v]overlay=0:0:format=auto[vout]"
        )

        rd.encode(
            saida=str(saida),
            entradas=["-ss", f"{inicio}", "-t", f"{dur}", "-i", str(master),
                      "-i", str(camada)],
            filtro_complexo=fc,
            mapa=["-map", "[vout]", "-map", "0:a:0"],
            args_audio=["-af", AF_LIMITER, "-c:a", "aac",
                        "-b:a", "256k", "-ar", "48000"],
        )

    tp = _true_peak(saida)
    print(f"  [pov] {saida.name}  dur={dur:.1f}s  "
          f"true peak={tp} dBTP (alvo <= -1,0)")

    if com_card and personagem and anime:
        try:
            import intro_card as ic
            final = saida.with_name(saida.stem + "_final" + saida.suffix)
            ic.montar_com_intro_e_card(
                video_entrada=saida, video_saida=final,
                personagem=personagem, anime=anime, cor=cor,
                com_intro=com_intro,
            )
            final.replace(saida)
        except Exception as e:
            print(f"  [pov] aviso: intro/card falhou ({e}), POV sem card")

    return saida


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="corte POV 9:16 para Shorts")
    p.add_argument("master")
    p.add_argument("saida")
    p.add_argument("--de", type=float, required=True)
    p.add_argument("--dur", type=float, required=True)
    p.add_argument("--gancho", required=True)
    p.add_argument("--anime", default="")
    p.add_argument("--tema", default="")
    p.add_argument("--cor", default="#FF8C00")
    p.add_argument("--marca", default="VX RAPS")
    p.add_argument("--handle", default="@VXRaps")
    p.add_argument("--personagem", default="")
    p.add_argument("--com-intro", dest="com_intro", action="store_true")
    p.add_argument("--sem-card", dest="sem_card", action="store_true")
    a = p.parse_args(argv)

    gerar_pov(Path(a.master), a.de, a.dur, Path(a.saida),
              gancho=a.gancho, anime=a.anime, tema=a.tema, cor=a.cor,
              marca=a.marca, handle=a.handle, personagem=a.personagem,
              com_intro=a.com_intro, com_card=not a.sem_card)
    print(f"pronto: {a.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
