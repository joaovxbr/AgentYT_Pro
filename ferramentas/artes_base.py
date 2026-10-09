#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""artes_base.py — biblioteca de composicao de arte do canal VX RAPS.

As primitivas que viviam nos 8 `artes_<personagem>.py` moram aqui. A composicao
e UMA so, dirigida pelo projeto.json. Produz as tres pecas:

    <slug>_capa_youtube.jpg        1280x720   (miniatura)
    <slug>_banner_canal.jpg        2560x1440  (banner)
    <slug>_capa_streaming_3000.jpg 3000x3000  (capa quadrada)

Regras que a arte cobra:
- personagem de um lado, coluna de texto do outro, scrim escuro sob o texto;
- ponto focal na area mais clara; frame real do MP4 (nunca IA);
- margem segura de 80 px; canto inf. direito livre (selo de duracao);
- Cinzel caixa alta no titulo; palavra de destaque na cor do personagem;
- previa do card de 210 px salva em /tmp para conferencia.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont


# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------

def _dir_fontes_candidatas() -> List[Path]:
    cands = [
        Path.home() / ".local/share/fonts",
        Path("C:/Windows/Fonts"),
        Path(__file__).resolve().parent / "fontes",
    ]
    return [c for c in cands if c.exists()]


def _achar_fonte(nomes: List[str]) -> Optional[Path]:
    for base in _dir_fontes_candidatas():
        for nome in nomes:
            for ext in (".ttf", ".otf", ".TTF", ".OTF"):
                p = base / f"{nome}{ext}"
                if p.exists():
                    return p
        # busca por prefixo
        for nome in nomes:
            for p in base.glob(f"{nome}*"):
                if p.suffix.lower() in (".ttf", ".otf"):
                    return p
    return None


def fonte_titulo(tamanho: int) -> ImageFont.FreeTypeFont:
    p = _achar_fonte(["Cinzel", "Cinzel-Bold", "Trajan", "TrajanPro"])
    if not p:
        p = _achar_fonte(["arialbd", "Arial-Bold", "Arial", "DejaVuSans-Bold"])
    return ImageFont.truetype(str(p), tamanho) if p else ImageFont.load_default()


def fonte_sub(tamanho: int) -> ImageFont.FreeTypeFont:
    p = _achar_fonte(["BebasNeue", "Bebas", "Anton", "Oswald"])
    if not p:
        p = _achar_fonte(["arial", "Arial", "DejaVuSans"])
    return ImageFont.truetype(str(p), tamanho) if p else ImageFont.load_default()


# ---------------------------------------------------------------------------
# Frames do MP4
# ---------------------------------------------------------------------------

def extrair_frame(video: Path, segundo: float, destino: Path,
                  recortar_legenda: bool = True) -> Path:
    """Extrai 1 frame HD do MP4 num dado segundo. Corta a faixa de legenda na
    origem (as fontes tem legenda queimada em y~885)."""
    ff = shutil.which("ffmpeg") or "ffmpeg"
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(segundo),
         "-i", str(video), "-frames:v", "1", "-q:v", "2", str(destino)],
        check=True,
    )
    if recortar_legenda:
        im = Image.open(destino).convert("RGB")
        w, h = im.size
        # corta ~150px do topo e ~195px do rodape (onde vive a legenda de dublagem)
        corte_topo = int(h * 0.02)
        corte_base = int(h * 0.18)
        im = im.crop((0, corte_topo, w, h - corte_base))
        im.save(destino, quality=95)
    return destino


# ---------------------------------------------------------------------------
# Primitivas de composicao
# ---------------------------------------------------------------------------

def cobrir(im: Image.Image, largura: int, altura: int,
           foco_x: float = 0.5, foco_y: float = 0.42) -> Image.Image:
    """Escala e recorta a imagem para cobrir (largura x altura) mantendo foco."""
    im = im.convert("RGB")
    w, h = im.size
    escala = max(largura / w, altura / h)
    nw, nh = int(w * escala + 0.5), int(h * escala + 0.5)
    im = im.resize((nw, nh), Image.LANCZOS)
    x = int((nw - largura) * foco_x)
    y = int((nh - altura) * foco_y)
    x = max(0, min(x, nw - largura))
    y = max(0, min(y, nh - altura))
    return im.crop((x, y, x + largura, y + altura))


def fundo_borrado(im: Image.Image, largura: int, altura: int,
                  sigma: int = 28, escurecer: float = 0.55) -> Image.Image:
    bg = cobrir(im, largura, altura)
    bg = bg.filter(ImageFilter.GaussianBlur(sigma))
    bg = ImageEnhance.Brightness(bg).enhance(escurecer)
    return bg


def realce_clipe(im: Image.Image) -> Image.Image:
    im = ImageEnhance.Contrast(im).enhance(1.08)
    im = ImageEnhance.Color(im).enhance(1.15)
    return im


def scrim(base: Image.Image, caixa: Tuple[int, int, int, int],
          opacidade: int = 170) -> None:
    """Faixa escura semi-transparente sob texto (para legibilidade)."""
    over = Image.new("RGBA", base.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(over)
    dr.rectangle(caixa, fill=(0, 0, 0, opacidade))
    base.alpha_composite(over)


def scrim_gradiente(base: Image.Image, largura_escura: int,
                    opacidade: int = 200) -> None:
    """Gradiente horizontal escuro->transparente da ESQUERDA para a direita.
    Elimina a emenda reta do scrim retangular: a transicao e suave ao longo
    de toda a largura_escura, entao nao ha borda visivel."""
    W, H = base.size
    grad = Image.new("L", (W, 1), 0)
    px = grad.load()
    fim = max(1, largura_escura)
    for x in range(W):
        if x <= fim * 0.55:
            a = opacidade
        elif x < fim:
            # decai suave da zona cheia ate 0 no fim da faixa
            t = (x - fim * 0.55) / (fim - fim * 0.55)
            a = int(opacidade * (1 - t))
        else:
            a = 0
        px[x, 0] = a
    mask = grad.resize((W, H))
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    over = Image.composite(black, over, mask)
    base.alpha_composite(over)


def _largura_texto(dr, texto, fonte) -> int:
    b = dr.textbbox((0, 0), texto, font=fonte)
    return b[2] - b[0]


def cabe(dr, texto: str, largura_max: int, criar_fonte, corpo_ini: int,
         corpo_min: int = 22) -> ImageFont.FreeTypeFont:
    """Reduz o corpo da fonte ate o texto caber na largura."""
    corpo = corpo_ini
    while corpo > corpo_min:
        f = criar_fonte(corpo)
        if _largura_texto(dr, texto, f) <= largura_max:
            return f
        corpo -= 2
    return criar_fonte(corpo_min)


def texto_sombra(dr, xy, texto, fonte, cor=(255, 255, 255),
                 sombra=(0, 0, 0), desloc=3, anchor=None) -> None:
    x, y = xy
    dr.text((x + desloc, y + desloc), texto, font=fonte, fill=sombra, anchor=anchor)
    dr.text((x, y), texto, font=fonte, fill=cor, anchor=anchor)


# ---------------------------------------------------------------------------
# Composicoes
# ---------------------------------------------------------------------------

@dataclass
class DadosArte:
    slug: str
    titulo_linhas: List[str]        # ex.: ["O REI DAS", "MALDICOES"]
    personagem: str                 # ex.: "SUKUNA"
    anime: str                      # ex.: "JUJUTSU KAISEN"
    cor_destaque: str               # "#RRGGBB"
    frame_capa: Image.Image
    frame_banner: Image.Image
    palavra_destaque: Optional[str] = None


def _cor(hex_str: str):
    return ImageColor.getrgb(hex_str)


def _fade_borda_esquerda(fig: Image.Image, fracao: float = 0.35) -> Image.Image:
    """Aplica fade alpha na borda esquerda da figura (0 na ponta, 255 no fim).

    Gera um gradiente 1xN e faz resize para a altura — evita o loop
    pixel-a-pixel em Python (centenas de milhares de iteracoes por peca).
    """
    fig = fig.convert("RGBA")
    fade_w = max(1, int(fig.width * fracao))
    linha = Image.new("L", (fig.width, 1), 255)
    px = linha.load()
    for x in range(fade_w):
        px[x, 0] = int(255 * (x / fade_w))
    fmask = linha.resize((fig.width, fig.height))
    fig.putalpha(fmask)
    return fig


def compor_capa_youtube(d: DadosArte) -> Image.Image:
    W, H = 1280, 720
    base = Image.new("RGBA", (W, H))
    # fundo borrado escuro
    base.paste(fundo_borrado(d.frame_banner, W, H).convert("RGBA"), (0, 0))
    # personagem nitido ocupando a metade direita, com borda esquerda em fade
    fig = realce_clipe(cobrir(d.frame_capa, int(W * 0.56), H, foco_x=0.5, foco_y=0.38))
    # fade na borda esquerda da figura (funde com o fundo, sem emenda reta)
    fig = _fade_borda_esquerda(fig)
    base.alpha_composite(fig, (W - fig.width, 0))
    # gradiente suave da esquerda para assentar o texto (sem emenda)
    scrim_gradiente(base, int(W * 0.60), opacidade=175)

    dr = ImageDraw.Draw(base)
    margem = 80
    col_larg = int(W * 0.50) - margem
    y = 150
    for i, linha in enumerate(d.titulo_linhas):
        f = cabe(dr, linha.upper(), col_larg, fonte_titulo, 96, 44)
        destaque = (d.palavra_destaque and
                    d.palavra_destaque.upper() in linha.upper())
        cor = _cor(d.cor_destaque) if destaque else (255, 255, 255)
        texto_sombra(dr, (margem, y), linha.upper(), f, cor=cor, desloc=4)
        b = dr.textbbox((0, 0), linha.upper(), font=f)
        y += (b[3] - b[1]) + 14

    fsub = cabe(dr, f"{d.personagem} - {d.anime}", col_larg, fonte_sub, 44, 24)
    texto_sombra(dr, (margem, y + 12), f"{d.personagem} - {d.anime}", fsub,
                 cor=_cor(d.cor_destaque), desloc=3)
    # assinatura discreta (longe do canto inf. direito = selo de duracao)
    fass = fonte_sub(30)
    texto_sombra(dr, (margem, H - margem - 4), "@VXRaps", fass,
                 cor=(230, 230, 230), desloc=2)
    return base.convert("RGB")


def compor_banner(d: DadosArte) -> Image.Image:
    W, H = 2560, 1440
    base = Image.new("RGBA", (W, H))
    base.paste(fundo_borrado(d.frame_banner, W, H, sigma=40).convert("RGBA"), (0, 0))
    fig = realce_clipe(cobrir(d.frame_banner, int(W * 0.6), H, foco_x=0.55, foco_y=0.4))
    fig = _fade_borda_esquerda(fig)
    base.alpha_composite(fig, (W - fig.width, 0))
    scrim_gradiente(base, int(W * 0.62), opacidade=165)
    dr = ImageDraw.Draw(base)
    # YouTube safe area central: ~508px de margem lateral, faixa vertical 508-935
    # texto DENTRO da safe area (x 507-2053, y 508-931 em 2560x1440)
    margem = 520
    col = 1500  # largura ampla: cabe o titulo sem encolher no meio da palavra
    # medir altura total pra centralizar verticalmente na safe area
    fs = [cabe(dr, l.upper(), col, fonte_titulo, 150, 90) for l in d.titulo_linhas]
    sub_txt = f"{d.personagem} · {d.anime}"
    fsub = cabe(dr, sub_txt, col, fonte_sub, 66, 40)
    # medir altura REAL de cada bloco pela bbox (top,bottom) do proprio glifo
    def h_real(txt, f):
        b = dr.textbbox((0, 0), txt, font=f)
        return b[3] - b[1], b[1]  # altura util e offset do topo
    h_tits = [h_real(l.upper(), f) for l, f in zip(d.titulo_linhas, fs)]
    h_sub, off_sub = h_real(sub_txt, fsub)
    gap_linha, gap_sub = 28, 40
    # ANCORAR DE BAIXO: subtitulo termina em y=890 (garantido < 931 da safe area)
    y_sub_baseline = 890
    y_sub_top = y_sub_baseline - h_sub
    # empilhar titulos ACIMA do subtitulo, de baixo pra cima
    ys = []
    y_cursor = y_sub_top - gap_sub
    for (ht, offt) in reversed(h_tits):
        y_cursor -= ht
        ys.insert(0, y_cursor)
        y_cursor -= gap_linha
    # desenhar titulos (compensando o offset do topo da bbox)
    for (linha, f, (ht, offt), ytop) in zip(d.titulo_linhas, fs, h_tits, ys):
        texto_sombra(dr, (margem, ytop - offt), linha.upper(), f,
                     cor=(255, 255, 255), desloc=6)
    # subtitulo branco
    texto_sombra(dr, (margem, y_sub_top - off_sub), sub_txt, fsub,
                 cor=(240, 240, 240), desloc=4)
    return base.convert("RGB")


def compor_capa_streaming(d: DadosArte) -> Image.Image:
    W = H = 3000
    base = Image.new("RGBA", (W, H))
    base.paste(fundo_borrado(d.frame_capa, W, H, sigma=60).convert("RGBA"), (0, 0))
    # quadro inteiro na metade de cima (nunca decapitar em 1:1)
    quadro = realce_clipe(d.frame_capa.convert("RGB"))
    qw, qh = quadro.size
    esc = min(W / qw, (H * 0.62) / qh)
    quadro = quadro.resize((int(qw * esc), int(qh * esc)), Image.LANCZOS)
    base.paste(quadro.convert("RGBA"), ((W - quadro.width) // 2, int(H * 0.06)))
    scrim(base, (0, int(H * 0.70), W, H), opacidade=190)
    dr = ImageDraw.Draw(base)
    margem = 180
    y = int(H * 0.73)
    for linha in d.titulo_linhas:
        f = cabe(dr, linha.upper(), W - 2 * margem, fonte_titulo, 230, 110)
        w_ = _largura_texto(dr, linha.upper(), f)
        texto_sombra(dr, ((W - w_) // 2, y), linha.upper(), f,
                     cor=(255, 255, 255), desloc=6)
        b = dr.textbbox((0, 0), linha.upper(), font=f)
        y += (b[3] - b[1]) + 26
    fsub = cabe(dr, d.personagem, W - 2 * margem, fonte_sub, 120, 60)
    w_ = _largura_texto(dr, d.personagem, fsub)
    texto_sombra(dr, ((W - w_) // 2, y + 20), d.personagem, fsub,
                 cor=_cor(d.cor_destaque), desloc=4)
    return base.convert("RGB")


def previa_card_210(capa_youtube: Image.Image, destino: Path) -> Path:
    """Reduz a capa ao tamanho do card menor (210x118) para conferir legibilidade."""
    card = capa_youtube.resize((210, 118), Image.LANCZOS)
    destino.parent.mkdir(parents=True, exist_ok=True)
    card.save(destino)
    return destino
