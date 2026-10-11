#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion_lab.py — LABORATORIO de tipografia em movimento sobre a cena REAL do anime.

EM TESTE: nao entra na esteira nem no master. Gera previas curtas em
`projetos/<slug>/lab/motion/` para aprovacao visual (cerebro/editorial.md).

Por que nao fica "colado" (motivo da rejeicao do overlay antigo):
- texto ATRAS do personagem (recorte rembg) -> profundidade;
- a cena vira "plate": escurece/dessatura + push-in lento, o personagem fica mais vivo;
- o texto acompanha a camera (phase correlation entre quadros) com paralaxe;
- cor do brilho vem da propria cena; grao e vinheta por cima de tudo.

Le: timeline.json, letra_sincronizada.json, clips_raw/*, audio (projeto.json), picos de 808.
Grava: lab/motion/<estilo>_<de>s.mp4 + lab/motion/<estilo>_<de>s.json.
Parametros: assets/design/motion_lab.json.
"""
from __future__ import annotations

import copy
import functools
import json
import math
import random
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import _vx  # noqa: F401  (ponte para vx/)
from vx import projeto as vx_projeto
from vx.composicao import TIPOS_DERIVADOS
from semantic_vision import imagem_ia_cfg

RAIZ = Path(__file__).resolve().parents[1]
CFG_ARQ = RAIZ / "assets" / "design" / "motion_lab.json"

PADRAO = {
    "fps": 30, "largura": 1920, "altura": 1080,
    "recorte": {"modelo": "isnet-anime", "lado": 512, "suavizacao": 0.55, "feather": 3},
    "plate": {"escurecer": 0.72, "saturacao": 0.82, "push_in": 0.05, "sujeito_brilho": 0.96},
    "tracking": {"fator": 0.6, "suavizacao": 0.8, "max_px": 80},
    "grao": 0.03, "vinheta": 0.35,
    "fontes": {
        "impacto": "ferramentas/fontes/Anton-Regular.ttf",
        "apoio": "ferramentas/fontes/BebasNeue-Regular.ttf",
        "glitch": "ferramentas/fontes/BlackOpsOne-Regular.ttf",
        "maquina": "ferramentas/fontes/FjallaOne-Regular.ttf",
        "kanji": "C:/Windows/Fonts/YuGothB.ttc",
    },
    "kanji": {}, "kanji_padrao": "力", "cores": {},
    "estilos": ["atras_personagem", "palavra_por_palavra", "glitch_slice",
                "kanji_fundo", "maquina_escrever"],
}

STOP = {"a", "o", "e", "de", "da", "do", "das", "dos", "que", "me", "te", "se", "um", "uma",
        "no", "na", "nos", "nas", "em", "eu", "tu", "ele", "ela", "nao", "pra", "pro", "por",
        "com", "sem", "meu", "minha", "seu", "sua", "mais", "mas", "so", "ja", "quando",
        "como", "isso", "esse", "essa", "ate", "the", "and", "you", "i"}


# ---------------------------------------------------------------------------
# Configuracao e dados (funcoes puras, testadas)
# ---------------------------------------------------------------------------

def _mesclar(base: dict, extra: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if k.startswith("_"):
            continue
        out[k] = _mesclar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def carregar_cfg(arquivo: Path = CFG_ARQ, manifesto: dict | None = None) -> dict:
    """Padrao do codigo < assets/design/motion_lab.json < projeto.json[motion_lab]."""
    try:
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    return _mesclar(_mesclar(PADRAO, dados), (manifesto or {}).get("motion_lab"))


def normalizar(txt: str) -> str:
    s = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum() or c == " ").strip()


def e_real(seg: dict) -> bool:
    """Segmento de footage real do anime (nao take gerado)."""
    return bool(seg.get("clip")) and seg.get("type") not in TIPOS_DERIVADOS \
        and not str(seg.get("clip", "")).replace("\\", "/").split("/")[0].startswith("vx_")


def trechos_fonte(timeline: dict, de: float, dur: float) -> list[dict]:
    """Pedacos de footage real que cobrem [de, de+dur] (tempos relativos ao inicio).

    Take gerado no meio da janela e substituido pela continuacao do plano real anterior.
    """
    fim = de + dur
    segs = sorted(timeline.get("segments") or [], key=lambda s: float(s["start"]))
    out: list[dict] = []
    anterior = None
    for s in segs:
        a, b = float(s["start"]), float(s["end"])
        if e_real(s):
            if b <= de:
                anterior = s
                continue
        if b <= de or a >= fim:
            continue
        ini, ate = max(a, de), min(b, fim)
        base = s if e_real(s) else anterior
        if base is None:
            continue
        src = float(base["src"]) + (ini - float(base["start"]))
        if out and out[-1]["clip"] == base["clip"] and out[-1]["_base"] is base:
            out[-1]["t_fim"] = round(ate - de, 4)
        else:
            out.append({"clip": base["clip"], "src": round(src, 4), "t_ini": round(ini - de, 4),
                        "t_fim": round(ate - de, 4), "_base": base})
        if e_real(s):
            anterior = s
    for o in out:
        o.pop("_base", None)
    return out


SEG_POR_LETRA_FINAL = 0.09   # ultima palavra costuma ser sustentada; ASR encurta (incidente tormento)


def fim_da_linha(ln: dict, proxima: float | None = None) -> float:
    """Fim real de uma linha para exibir texto: max(fim da linha, fim da ultima palavra,
    inicio da ultima palavra + duracao minima pelas letras), sem invadir a proxima linha."""
    fim = float(ln["end"])
    words = ln.get("words") or []
    if words:
        ult = words[-1]
        fim = max(fim, float(ult["end"]),
                  float(ult["start"]) + SEG_POR_LETRA_FINAL * max(4, len(str(ult["text"]))))
    if proxima is not None:
        fim = min(fim, max(float(ln["end"]), proxima - 0.05))
    return fim


def linhas_no_trecho(sync: list[dict], de: float, dur: float,
                     so_linha: str | None = None) -> list[dict]:
    """Linhas cantadas que tocam a janela, com tempos relativos a `de`.
    `end` ja e o fim real (fim_da_linha): a ultima palavra nunca some antes da hora.

    `so_linha`: entrega SO a linha que o take sabe que escreve (`design.json ->
    line_text`). Sem isso a janela puxa as linhas vizinhas que apenas ENCOSTAM
    nela, e `linha_ativa` troca a frase no meio do take: vazamento de CAUDA (a
    linha seguinte assume cedo) e de CABECA (a anterior ainda esta segurada
    quando o take comeca). Asta, 05/10/2026: 'O TOURO NEGRO' virava 'FACA' em
    54.8s (linha seguinte comeca 54.54s) e 'O' acendia na linha errada em 27.0s.
    O lab (sem take) nao passa `so_linha` e continua vendo a janela inteira.
    """
    out = []
    alvo = normalizar(so_linha) if so_linha else None
    sync = sorted(sync or [], key=lambda l: float(l["start"]))
    for k, ln in enumerate(sync):
        if float(ln["end"]) <= de or float(ln["start"]) >= de + dur:
            continue
        if alvo and normalizar(ln["text"]) != alvo:
            continue
        prox = float(sync[k + 1]["start"]) if k + 1 < len(sync) else None
        words = [{"text": w["text"], "start": float(w["start"]) - de, "end": float(w["end"]) - de}
                 for w in ln.get("words") or []]
        ini, fim = float(ln["start"]) - de, fim_da_linha(ln, prox) - de
        if alvo:
            # a frase e do TAKE: ele tem de estar na tela durante a janela inteira.
            # A janela pode comecar antes da linha (take antecipa) ou terminar depois
            # dela, e sem isto sobra um vao em branco numa das pontas.
            ini = min(ini, 0.0)
            fim = min(max(fim, dur - FADE_LINHA_DEPOIS - FADE_LINHA_DUR), dur)
        out.append({"text": ln["text"], "start": ini, "end": fim,
                    "keyword": ln.get("keyword"), "words": words})
    return out


def palavra_dominante(linha: dict, nomes: list[str] | None = None) -> str:
    """keyword da linha > nome do personagem/anime > palavra mais longa fora das stopwords."""
    if linha.get("keyword"):
        return str(linha["keyword"]).upper()
    palavras = [w.strip(",.!?;:\"'()") for w in str(linha.get("text", "")).split()]
    alvo = {normalizar(n) for n in (nomes or []) if n}
    for p in palavras:
        if normalizar(p) in alvo:
            return p.upper()
    candidatas = [p for p in palavras if normalizar(p) and normalizar(p) not in STOP]
    return (max(candidatas, key=len) if candidatas else (palavras[0] if palavras else "")).upper()


def nomes_do_manifesto(m: dict) -> list[str]:
    """Nomes proprios que devem vencer como palavra dominante (personagem, anime, vocabulario)."""
    nomes = str(m.get("personagem", "")).split() + str(m.get("anime", "")).split()
    voc = m.get("vocabulario") or {}
    if isinstance(voc, dict):
        for termo in voc.get("termos") or []:
            nomes += str(termo).split()
    return [n for n in nomes if len(n) > 2]


def linha_ativa(linhas: list[dict], t: float, segurar: float = 0.65) -> dict | None:
    """Linha sendo cantada em t; segura por `segurar` s depois do fim real (= tempo do fade
    dos estilos de linha, para a frase nao sumir de uma vez)."""
    atual = None
    for ln in linhas:
        if ln["start"] - 0.05 <= t < ln["end"] + segurar:
            atual = ln
    return atual


def cor_da_letra(texto: str, cores: dict) -> str | None:
    """Cor do conceito cantado (ex.: 'Azul atraindo' -> azul). Chaves compostas casam
    como trecho; simples casam a palavra inteira ou o comeco (>= 4 letras: vermelh-a).
    Havendo mais de uma, vence a que aparece PRIMEIRO na linha."""
    n = normalizar(texto)
    palavras = n.split()
    melhor = None                      # (posicao, -tamanho_chave, cor)
    for chave, cor in (cores or {}).items():
        k = normalizar(chave)
        if not k:
            continue
        if " " in k:
            pos = f" {n} ".find(f" {k} ")
            if pos >= 0:
                pos = len(f" {n} "[:pos].split())
        else:
            pos = next((j for j, p in enumerate(palavras)
                        if p == k or (len(k) >= 4 and p.startswith(k))), -1)
        if pos >= 0:
            cand = (pos, -len(k), cor)
            melhor = cand if melhor is None or cand < melhor else melhor
    return melhor[2] if melhor else None


def kanji_para(palavra: str, mapa: dict, padrao: str) -> str:
    n = normalizar(palavra)
    for chave, kanji in sorted(mapa.items(), key=lambda kv: -len(kv[0])):
        if normalizar(chave) and normalizar(chave) in n:
            return kanji
    return padrao


def acumular_tracking(deltas: list[tuple[float, float]], cortes: set[int], fator: float,
                      suavizacao: float, max_px: float) -> list[tuple[float, float]]:
    """Deslocamento do texto por quadro: segue a camera, suavizado, zera em cada corte."""
    out, acc, lis = [], [0.0, 0.0], [0.0, 0.0]
    for i, (dx, dy) in enumerate(deltas):
        if i in cortes:
            acc, lis = [0.0, 0.0], [0.0, 0.0]
        else:
            acc = [max(-max_px, min(max_px, acc[0] + dx * fator)),
                   max(-max_px, min(max_px, acc[1] + dy * fator))]
            # volta devagar ao centro para o texto nunca fugir do quadro
            acc = [acc[0] * 0.985, acc[1] * 0.985]
        lis = [lis[0] * suavizacao + acc[0] * (1 - suavizacao),
               lis[1] * suavizacao + acc[1] * (1 - suavizacao)]
        out.append((lis[0], lis[1]))
    return out


def compor_camadas(plate: Image.Image, sujeito: Image.Image, mascara: Image.Image,
                   atras: Image.Image | None, frente: Image.Image | None) -> Image.Image:
    """plate -> texto de tras -> personagem (mascara) -> texto da frente."""
    base = plate.convert("RGBA")
    if atras is not None:
        base = Image.alpha_composite(base, atras)
    base = Image.composite(sujeito.convert("RGBA"), base, mascara)
    if frente is not None:
        base = Image.alpha_composite(base, frente)
    return base.convert("RGB")


def transformar(img: Image.Image, zoom: float, dx: float, dy: float) -> Image.Image:
    """Zoom central + deslocamento (px do quadro final), sem sair da imagem."""
    if zoom <= 1.0005 and abs(dx) < 0.5 and abs(dy) < 0.5:
        return img
    zoom = max(1.0, zoom)
    W, H = img.size
    w2, h2 = W / zoom, H / zoom
    folga_x, folga_y = (W - w2) / 2, (H - h2) / 2
    ox = max(-folga_x, min(folga_x, -dx / zoom))
    oy = max(-folga_y, min(folga_y, -dy / zoom))
    caixa = (folga_x + ox, folga_y + oy, folga_x + ox + w2, folga_y + oy + h2)
    return img.resize((W, H), Image.Resampling.BILINEAR, box=caixa)


def cobertura_recorte(mascaras: list[Image.Image]) -> dict:
    """Fracao do quadro ocupada pelo personagem recortado (0..1). ~0 = texto 'atras'
    nao tem efeito; ~1 = recorte engoliu o quadro e esconde o texto."""
    fr = [float(np.asarray(m.resize((96, 54)), dtype=np.float32).mean() / 255) for m in mascaras]
    if not fr:
        return {"media": 0.0, "min": 0.0, "max": 0.0, "aviso": "sem quadros"}
    media = sum(fr) / len(fr)
    aviso = ("recorte quase vazio: texto atras do personagem nao aparece como profundidade"
             if media < 0.04 else
             "recorte cobre quase o quadro todo: texto atras fica escondido" if media > 0.7 else "")
    return {"media": round(media, 3), "min": round(min(fr), 3), "max": round(max(fr), 3), "aviso": aviso}


def folha_img(miniaturas: list[Image.Image]) -> Image.Image:
    """Folha de contato 2x2 para revisao rapida sem abrir o video."""
    if not miniaturas:
        return Image.new("RGB", (8, 8))
    w, h = miniaturas[0].size
    folha = Image.new("RGB", (w * 2, h * 2))
    for k, m in enumerate(miniaturas[:4]):
        folha.paste(m, ((k % 2) * w, (k // 2) * h))
    return folha


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ease_out_back(x: float, k: float = 1.7) -> float:
    x = max(0.0, min(1.0, x))
    return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2


def escolher_inicio(timeline: dict, sync: list[dict]) -> float:
    """Sem --de: primeira linha de refrao; senao uma linha a 1/3 da musica."""
    for s in sorted(timeline.get("segments") or [], key=lambda s: float(s["start"])):
        if (s.get("scene_match") or {}).get("section") == "chorus" and s.get("type") == "lyric":
            return max(0.0, round(float(s["start"]) - 0.3, 2))
    if sync:
        return max(0.0, round(float(sync[len(sync) // 3]["start"]) - 0.3, 2))
    return 0.0


# ---------------------------------------------------------------------------
# Texto (Pillow)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=64)
def _fonte(caminho: str, tamanho: int) -> ImageFont.FreeTypeFont:
    p = Path(caminho)
    if not p.is_absolute():
        p = RAIZ / p
    return ImageFont.truetype(str(p), max(8, int(tamanho)))


def _ajustar(texto: str, caminho: str, max_w: int, max_h: int, inicio: int = 420) -> ImageFont.FreeTypeFont:
    d = ImageDraw.Draw(Image.new("L", (8, 8)))
    tam = inicio
    while tam > 20:
        f = _fonte(caminho, tam)
        bb = d.textbbox((0, 0), texto, font=f)
        if bb[2] - bb[0] <= max_w and bb[3] - bb[1] <= max_h:
            return f
        tam = int(tam * 0.92)
    return _fonte(caminho, 20)


def _rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else (255, 255, 255)


def _texto(texto: str, fonte, cor=(255, 255, 255), stroke=0, stroke_cor=(0, 0, 0),
           glow=None, glow_r=0, alpha=255, pad=None) -> Image.Image:
    """Camada RGBA justa ao texto, com contorno e brilho opcionais."""
    d = ImageDraw.Draw(Image.new("L", (8, 8)))
    bb = d.textbbox((0, 0), texto, font=fonte, stroke_width=stroke)
    pad = pad if pad is not None else max(8, glow_r * 3)
    w, h = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    org = (pad - bb[0], pad - bb[1])
    layer = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    if glow and glow_r:
        g = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).text(org, texto, font=fonte, fill=(*glow, 255),
                               stroke_width=stroke + 2, stroke_fill=(*glow, 255))
        layer = Image.alpha_composite(layer, g.filter(ImageFilter.GaussianBlur(glow_r)))
    ImageDraw.Draw(layer).text(org, texto, font=fonte, fill=(*cor, 255),
                               stroke_width=stroke, stroke_fill=(*stroke_cor, 255))
    if alpha < 255:
        layer.putalpha(layer.getchannel("A").point(lambda p: p * alpha // 255))
    return layer


def _colar(canvas: Image.Image, layer: Image.Image, cx: float, cy: float) -> None:
    canvas.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def _blur_mov(layer: Image.Image, forca: float) -> Image.Image:
    """Motion blur horizontal barato para entradas rapidas."""
    n = int(forca)
    if n < 2:
        return layer
    acc = np.zeros((layer.height, layer.width + n, 4), dtype=np.float32)
    arr = np.asarray(layer, dtype=np.float32)
    for i in range(n):
        acc[:, i:i + layer.width] += arr
    return Image.fromarray(np.clip(acc / n, 0, 255).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------------------
# Estilos: cada um devolve (camada_atras, camada_frente) para o tempo t
# ---------------------------------------------------------------------------

class Contexto:
    def __init__(self, cfg: dict, linhas: list[dict], dur: float, acento: tuple, nomes: list[str],
                 picos: list[dict], palavra: str | None = None, t_palavra: float | None = None):
        self.cfg, self.linhas, self.dur, self.acento = cfg, linhas, dur, acento
        self.nomes, self.picos = nomes, picos
        self.palavra, self.t_palavra = palavra, t_palavra
        self.cor_cena = tuple(acento)                # fallback: cor dominante da cena
        self.cor_take: str | None = None             # cor da linha do take (graficos-auto)
        self._cor_atual: tuple | None = None
        self.mascara: Image.Image | None = None      # recorte do quadro atual (renderizar)
        self.efeito_plate: dict | None = None        # camera pedida pelo estilo neste quadro
        # Cards de fundo (lote 3): o estilo pode TROCAR o plate inteiro neste quadro.
        # (plate RGB, sujeito RGB ou None). None no sujeito = sem personagem por cima.
        self.plate_custom: tuple | None = None
        self.quadro: np.ndarray | None = None        # quadro atual da cena real (RGB)
        self.quadros: list[np.ndarray] = []          # todos os quadros da janela
        self.projeto: Path | None = None
        self.cache: dict = {}                        # por estilo (paineis de manga, fundo IA...)
        self.mascaras: list = []                     # recortes de todos os quadros da janela
        self.mascara_custom: Image.Image | None = None  # recorte que acompanha um plate_custom
        self.W, self.H = cfg["largura"], cfg["altura"]
        self.f = cfg["fontes"]

    def cor_alvo(self, t: float) -> tuple[int, int, int]:
        """Cor pela LETRA: palavra do take > linha cantada em t > linha do take > cor da cena."""
        cores = self.cfg.get("cores") or {}
        hexc = cor_da_letra(self.palavra, cores) if self.palavra else None
        ln = linha_ativa(self.linhas, t)
        if not hexc and ln:
            hexc = cor_da_letra(ln["text"], cores)
        hexc = hexc or self.cor_take
        return _rgb(hexc) if hexc else self.cor_cena

    def atualizar_cor(self, t: float) -> None:
        """Troca de cor entre linhas com transicao curta (~0.2 s), sem piscar."""
        alvo = self.cor_alvo(t)
        if self._cor_atual is None:
            self._cor_atual = tuple(float(x) for x in alvo)
        else:
            self._cor_atual = tuple(a + (b - a) * 0.35 for a, b in zip(self._cor_atual, alvo))
        self.acento = tuple(int(round(x)) for x in self._cor_atual)

    def janela_palavra(self, t: float) -> tuple[str, float, float] | None:
        """(palavra, inicio, fim) para os estilos de palavra unica.

        Take do graficos-auto: a palavra ja foi escolhida e dura o take inteiro.
        Lab livre: palavra dominante da linha cantada em t.
        """
        if self.palavra:
            ini = max(0.0, (self.t_palavra or 0.0) - 0.08)
            return self.palavra, ini, max(ini + 0.3, self.dur - 0.6)
        ln = linha_ativa(self.linhas, t) or (self.linhas[0] if self.linhas else None)
        if not ln:
            return None
        return palavra_dominante(ln, self.nomes), max(0.0, ln["start"]), ln["end"]

    def vazio(self) -> Image.Image:
        return Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))

    def pulso(self, t: float) -> float:
        from audio_reactive_fx import pulso_no_tempo
        return pulso_no_tempo(self.picos, t)


def estilo_atras_personagem(c: Contexto, t: float, i: int, off):
    """Palavra gigante ATRAS do personagem, escrita da esquerda para a direita."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.92), int(c.H * 0.62))
    layer = _texto(palavra, f, cor=(245, 245, 250), glow=c.acento, glow_r=22)
    prog = ease_out((t - ini) / 0.55)
    if prog <= 0:
        return None, None
    # write-on: revela por largura com cabeca de luz
    corte = int(layer.width * prog)
    rev = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    rev.paste(layer.crop((0, 0, corte, layer.height)), (0, 0))
    escala = 1.0 + 0.06 * (t / max(0.1, c.dur))
    rev = rev.resize((int(rev.width * escala), int(rev.height * escala)), Image.Resampling.BILINEAR)
    fade = 1.0 - ease_out((t - (fim + 0.25)) / 0.35)
    if fade < 1:
        rev.putalpha(rev.getchannel("A").point(lambda p: int(p * max(0.0, fade))))
    atras = c.vazio()
    _colar(atras, rev, c.W / 2 + off[0], c.H * 0.44 + off[1])
    if prog < 1:
        cab = Image.new("RGBA", (90, 90), (0, 0, 0, 0))
        ImageDraw.Draw(cab).ellipse((25, 25, 65, 65), fill=(*c.acento, 255))
        cab = cab.filter(ImageFilter.GaussianBlur(12))
        x0 = c.W / 2 - rev.width / 2 + corte * escala
        _colar(atras, cab, x0 + off[0], c.H * 0.44 + off[1])
    return atras, None


# Estilos de linha: a frase inteira fica na tela ate FADE_LINHA_DEPOIS apos o fim real da
# linha e some em FADE_LINHA_DUR. O take do graficos-auto precisa cobrir isso (TAKE_LINHA_SOBRA).
FADE_LINHA_DEPOIS = 0.35
FADE_LINHA_DUR = 0.3
TAKE_LINHA_SOBRA = FADE_LINHA_DEPOIS + FADE_LINHA_DUR


def estilo_palavra_por_palavra(c: Contexto, t: float, i: int, off):
    """Cada palavra entra no tempo em que e cantada (pop + blur); a atual brilha."""
    ln = linha_ativa(c.linhas, t)
    if not ln or not ln["words"]:
        return None, None
    f = _fonte(c.f["apoio"], 118)
    d = ImageDraw.Draw(Image.new("L", (8, 8)))
    palavras = [w for w in ln["words"]]
    larg = [d.textlength(w["text"].upper() + " ", font=f) for w in palavras]
    # quebra em ate 2 linhas equilibradas
    total, linhas_px, atual, acc = sum(larg), [[]], 0, 0.0
    for k, w in enumerate(larg):
        if acc + w > max(total / 2 + 60, c.W * 0.45) and atual == 0 and linhas_px[0]:
            linhas_px.append([])
            atual, acc = 1, 0.0
        linhas_px[atual].append(k)
        acc += w
    frente = c.vazio()
    fade_fim = 1.0 - ease_out((t - (ln["end"] + FADE_LINHA_DEPOIS)) / FADE_LINHA_DUR)
    for r, idxs in enumerate(linhas_px):
        largura = sum(larg[k] for k in idxs)
        x = c.W / 2 - largura / 2 + off[0] * 0.5
        y = c.H * (0.62 + 0.13 * r) + off[1] * 0.5
        for k in idxs:
            w = palavras[k]
            prog = (t - w["start"] + 0.04) / 0.14
            if prog <= 0:
                x += larg[k]
                continue
            ultima = k == len(palavras) - 1
            # a ultima palavra fica acesa ate o fim da linha (sustentada no canto)
            cantando = w["start"] - 0.04 <= t < (ln["end"] + 0.2 if ultima else w["end"] + 0.05)
            cor = c.acento if cantando else (240, 240, 244)
            alpha = int(255 * ease_out(prog) * max(0.0, fade_fim) * (1.0 if cantando else 0.86))
            lay = _texto(w["text"].upper(), f, cor=cor, stroke=3, stroke_cor=(8, 8, 12),
                         glow=c.acento if cantando else None, glow_r=14 if cantando else 0, alpha=alpha)
            esc = ease_out_back(prog) if prog < 1 else 1.0
            esc = 0.6 + 0.4 * esc
            lay = lay.resize((max(1, int(lay.width * esc)), max(1, int(lay.height * esc))),
                             Image.Resampling.BILINEAR)
            if prog < 1:
                lay = _blur_mov(lay, (1 - prog) * 18)
            wl = d.textlength(w["text"].upper(), font=f)
            _colar(frente, lay, x + wl / 2, y - (1 - min(1, prog)) * 22)
            x += larg[k]
    return None, frente


def estilo_glitch_slice(c: Contexto, t: float, i: int, off):
    """Palavra entra fatiada com RGB split; nos picos de 808 treme e refatia."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    f = _ajustar(palavra, c.f["glitch"], int(c.W * 0.78), int(c.H * 0.36))
    base = _texto(palavra, f, cor=(250, 250, 250), stroke=4, stroke_cor=(10, 10, 14),
                  glow=c.acento, glow_r=10)
    prog = (t - ini) / 0.35
    if prog <= 0:
        return None, None
    pulso = c.pulso(t)
    forca = max(0.0, 1 - prog) * 1.0 + pulso * 0.55
    rnd = random.Random(i // 2)
    out = Image.new("RGBA", (base.width + 200, base.height), (0, 0, 0, 0))
    faixas = 9
    hf = max(1, base.height // faixas)
    for k in range(faixas):
        y0 = k * hf
        faixa = base.crop((0, y0, base.width, min(base.height, y0 + hf + 1)))
        dx = int(rnd.uniform(-1, 1) * 160 * forca)
        out.alpha_composite(faixa, (100 + dx, y0))
    if forca > 0.05:
        a = out.getchannel("A")
        split = int(6 + 22 * forca)
        r = Image.new("RGBA", out.size, (255, 30, 70, 0)); r.putalpha(a.point(lambda p: p * 150 // 255))
        cy = Image.new("RGBA", out.size, (0, 230, 255, 0)); cy.putalpha(a.point(lambda p: p * 150 // 255))
        comp = Image.new("RGBA", (out.width + 2 * split, out.height), (0, 0, 0, 0))
        comp.alpha_composite(r, (0, 0)); comp.alpha_composite(cy, (2 * split, 0))
        comp.alpha_composite(out, (split, 0))
        out = comp
    fade = 1.0 - ease_out((t - (fim + 0.25)) / 0.3)
    if fade < 1:
        out.putalpha(out.getchannel("A").point(lambda p: int(p * max(0.0, fade))))
    tremor = (rnd.uniform(-1, 1) * 18 * pulso, rnd.uniform(-1, 1) * 12 * pulso)
    frente = c.vazio()
    _colar(frente, out, c.W / 2 + off[0] + tremor[0], c.H * 0.5 + off[1] + tremor[1])
    if pulso > 0.3:
        frente = Image.alpha_composite(frente, Image.new("RGBA", frente.size, (255, 255, 255, int(40 * pulso))))
    return None, frente


def estilo_kanji_fundo(c: Contexto, t: float, i: int, off):
    """Kanji enorme translucido atras do personagem + palavra em portugues na frente."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    kanji = kanji_para(palavra, c.cfg.get("kanji") or {}, c.cfg.get("kanji_padrao", "力"))
    fk = _ajustar(kanji, c.f["kanji"], int(c.W * 0.8), int(c.H * 0.9), inicio=900)
    prog = ease_out((t - ini + 0.1) / 0.6)
    fade = 1.0 - ease_out((t - (fim + 0.3)) / 0.4)
    alpha = int(120 * prog * max(0.0, fade))
    if alpha <= 0:
        return None, None
    kl = _texto(kanji, fk, cor=c.acento, glow=c.acento, glow_r=30, alpha=alpha)
    atras = c.vazio()
    deriva = (t / max(0.1, c.dur)) * 40
    _colar(atras, kl, c.W * 0.5 + off[0] * 0.4 - deriva, c.H * 0.47 + off[1] * 0.4)
    # palavra da frente com espacamento que fecha (tracking in)
    fp = _fonte(c.f["apoio"], 96)
    esp = int(40 * (1 - prog))
    letras = [_texto(ch, fp, cor=(245, 245, 248), stroke=2, stroke_cor=(6, 6, 10),
                     alpha=int(255 * prog * max(0.0, fade))) for ch in palavra]
    total = sum(l.width - 16 for l in letras) + esp * max(0, len(letras) - 1)
    frente = c.vazio()
    x = c.W / 2 - total / 2 + off[0]
    for l in letras:
        _colar(frente, l, x + (l.width - 16) / 2, c.H * 0.8 + off[1])
        x += l.width - 16 + esp
    return atras, frente


def estilo_maquina_escrever(c: Contexto, t: float, i: int, off):
    """Linha digitada letra a letra no ritmo das palavras, com cursor piscando."""
    ln = linha_ativa(c.linhas, t)
    if not ln:
        return None, None
    texto = ""
    for w in ln["words"] or [{"text": ln["text"], "start": ln["start"], "end": ln["end"]}]:
        if t < w["start"]:
            break
        frac = min(1.0, (t - w["start"]) / max(0.06, (w["end"] - w["start"]) * 0.8))
        texto += w["text"][:max(1, int(round(len(w["text"]) * frac)))] + " "
    texto = texto.rstrip()
    cursor = "▌" if (i // 8) % 2 == 0 or t < ln["end"] else " "
    fade = 1.0 - ease_out((t - (ln["end"] + FADE_LINHA_DEPOIS)) / FADE_LINHA_DUR)
    f = _fonte(c.f["maquina"], 64)
    lay = _texto(texto + cursor, f, cor=(236, 236, 240), stroke=2, stroke_cor=(4, 4, 8),
                 glow=c.acento, glow_r=6, alpha=int(255 * max(0.0, fade)))
    frente = c.vazio()
    jit = (random.Random(i).uniform(-1.2, 1.2), random.Random(i + 7).uniform(-1.2, 1.2))
    frente.alpha_composite(lay, (int(c.W * 0.08 + off[0] * 0.5 + jit[0]),
                                 int(c.H * 0.76 + off[1] * 0.5 + jit[1])))
    return None, frente


# ---------------------------------------------------------------------------
# Estilos em teste (lote 2). Entram no graficos-auto so depois de aprovados.
# Um estilo pode pedir efeito de camera no quadro via c.efeito_plate
# {"zoom", "dx", "dy"}; o mesmo transform e aplicado a cena e ao recorte.
# ---------------------------------------------------------------------------

def _fade_saida(t: float, fim: float, depois: float = 0.25, dur: float = 0.35) -> float:
    return max(0.0, 1.0 - ease_out((t - (fim + depois)) / dur))


def _contorno(texto: str, fonte, cor: tuple, largura: int, alpha: int = 255) -> Image.Image:
    """So o contorno das letras (miolo vazado): texto com stroke menos texto sem stroke."""
    from PIL import ImageChops
    cheio = _texto(texto, fonte, cor=cor, stroke=largura, stroke_cor=cor, pad=largura * 3 + 8)
    # pad maior compensa o bbox sem stroke: as duas camadas ficam com a mesma origem
    miolo = _texto(texto, fonte, cor=cor, stroke=0, pad=largura * 4 + 8)
    if miolo.size != cheio.size:
        miolo = miolo.crop((0, 0, cheio.width, cheio.height))
    a = ImageChops.subtract(cheio.getchannel("A"), miolo.getchannel("A"))
    if alpha < 255:
        a = a.point(lambda p: p * alpha // 255)
    out = Image.new("RGBA", cheio.size, (*cor, 0))
    out.putalpha(a)
    return out


def _escalar(layer: Image.Image, esc: float) -> Image.Image:
    if abs(esc - 1.0) < 0.003:
        return layer
    return layer.resize((max(1, int(layer.width * esc)), max(1, int(layer.height * esc))),
                        Image.Resampling.BILINEAR)


def _com_alpha(layer: Image.Image, fator: float) -> Image.Image:
    if fator >= 0.999:
        return layer
    layer = layer.copy()
    layer.putalpha(layer.getchannel("A").point(lambda p: int(p * max(0.0, fator))))
    return layer


def estilo_impacto_zoom(c: Contexto, t: float, i: int, off):
    """Palavra cai de 3x para 1x no tempo cantado; camera da um soco (zoom + tremor) e flash."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    dt = t - ini
    if dt < 0:
        return None, None
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.84), int(c.H * 0.46))
    queda = ease_out(dt / 0.16)
    esc = min(2.4, 3.0 - 2.0 * queda) if dt < 0.16 else 1.0 + 0.03 * (dt - 0.16)
    lay = _texto(palavra, f, cor=(255, 255, 255), stroke=6, stroke_cor=(4, 4, 8), glow=c.acento, glow_r=20)
    lay = _escalar(lay, esc)
    if dt < 0.16:
        lay = lay.filter(ImageFilter.GaussianBlur((1 - queda) * 7))
    lay = _com_alpha(lay, min(1.0, dt / 0.06) * _fade_saida(t, fim))
    pulso = c.pulso(t)
    batida = max(0.0, 1 - ease_out((dt - 0.14) / 0.4)) if dt >= 0.14 else 0.0
    rnd = random.Random(i)
    amp = 24 * batida + 12 * pulso
    tremor = (rnd.uniform(-1, 1) * amp, rnd.uniform(-1, 1) * amp)
    c.efeito_plate = {"zoom": 1.0 + 0.07 * batida + 0.02 * pulso, "dx": tremor[0] * 0.7, "dy": tremor[1] * 0.7}
    frente = c.vazio()
    _colar(frente, lay, c.W / 2 + off[0] + tremor[0], c.H * 0.47 + off[1] + tremor[1])
    if 0.14 <= dt < 0.26:
        frente = Image.alpha_composite(
            frente, Image.new("RGBA", frente.size, (255, 255, 255, int(120 * (1 - (dt - 0.14) / 0.12)))))
    return None, frente


def estilo_eco_repeticao(c: Contexto, t: float, i: int, off):
    """Palavra atras do personagem com ecos em contorno que se expandem e pulsam no 808."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    prog = ease_out((t - ini) / 0.4)
    if prog <= 0:
        return None, None
    fade = _fade_saida(t, fim)
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.62), int(c.H * 0.34))
    pulso = c.pulso(t)
    atras = c.vazio()
    cx, cy = c.W / 2 + off[0] * 0.8, c.H * 0.45 + off[1] * 0.8
    ecos = 6
    for k in range(ecos, 0, -1):
        onda = (t * 0.9 + k / ecos) % 1.0           # ecos nascem no centro e se afastam
        esc = 1.0 + onda * 1.3 * prog + 0.12 * pulso * k / ecos
        alpha = int(170 * (1 - onda) * prog * fade)
        if alpha < 6:
            continue
        cont = _escalar(_contorno(palavra, f, c.acento, 3, alpha), esc)
        _colar(atras, cont, cx, cy)
    solida = _texto(palavra, f, cor=(248, 248, 252), stroke=3, stroke_cor=(6, 6, 10),
                    glow=c.acento, glow_r=14, alpha=int(255 * prog * fade))
    _colar(atras, _escalar(solida, 0.85 + 0.15 * prog), cx, cy)
    return atras, None


def estilo_fragmentos(c: Contexto, t: float, i: int, off):
    """Letras voam de posicoes aleatorias, girando, e montam a palavra no tempo cantado."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.8), int(c.H * 0.4))
    d = ImageDraw.Draw(Image.new("L", (8, 8)))
    larg = [d.textlength(ch, font=f) for ch in palavra]
    total = sum(larg)
    fade = _fade_saida(t, fim)
    frente = c.vazio()
    x = c.W / 2 - total / 2 + off[0]
    y = c.H * 0.47 + off[1]
    for k, ch in enumerate(palavra):
        if not ch.strip():
            x += larg[k]
            continue
        rnd = random.Random(k * 97 + len(palavra))
        p = ease_out((t - ini - 0.035 * k) / 0.45)
        if p <= 0:
            x += larg[k]
            continue
        ox, oy = rnd.uniform(-760, 760), rnd.uniform(-460, 460)
        rot = rnd.uniform(-140, 140) * (1 - p)
        letra = _texto(ch, f, cor=(250, 250, 252), stroke=4, stroke_cor=(6, 6, 10),
                       glow=c.acento, glow_r=10, alpha=int(255 * min(1.0, p * 1.6) * fade))
        letra = _escalar(letra, 0.45 + 0.55 * p)
        if abs(rot) > 0.5:
            letra = letra.rotate(rot, resample=Image.Resampling.BILINEAR, expand=True)
        if p < 0.85:
            letra = _blur_mov(letra, (1 - p) * 22)
        _colar(frente, letra, x + larg[k] / 2 + ox * (1 - p), y + oy * (1 - p))
        x += larg[k]
    return None, frente


def estilo_contorno_energia(c: Contexto, t: float, i: int, off):
    """Aura de energia no contorno do personagem (pulsa no 808) + palavra atras dele."""
    from PIL import ImageChops
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    prog = ease_out((t - ini + 0.15) / 0.5)
    fade = _fade_saida(t, fim)
    atras = c.vazio()
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.8), int(c.H * 0.46))
    lay = _texto(palavra, f, cor=(240, 240, 246), glow=c.acento, glow_r=16, alpha=int(215 * prog * fade))
    _colar(atras, lay, c.W / 2 + off[0], c.H * 0.45 + off[1])
    m = getattr(c, "mascara", None)
    if m is not None and prog > 0:
        pequeno = m.resize((c.W // 4, c.H // 4), Image.Resampling.BILINEAR).point(lambda p: 255 if p > 110 else 0)
        borda = ImageChops.subtract(pequeno.filter(ImageFilter.MaxFilter(7)), pequeno)
        borda = borda.resize((c.W, c.H), Image.Resampling.BILINEAR)
        pulso = c.pulso(t)
        forca = (0.55 + 0.5 * pulso + 0.12 * math.sin(t * 38)) * prog * fade
        for raio, ganho in ((5, 1.8), (18, 1.2)):
            a = borda.filter(ImageFilter.GaussianBlur(raio)).point(lambda p, g=ganho: min(255, int(p * g * forca)))
            aura = Image.new("RGBA", (c.W, c.H), (*c.acento, 0))
            aura.putalpha(a)
            atras = Image.alpha_composite(atras, aura)
    return atras, None


def estilo_letterbox_cinema(c: Contexto, t: float, i: int, off):
    """Barras de cinema fecham; titulo espacado atras do personagem; credito na barra."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    entra = ease_out((t - max(0.0, ini - 0.25)) / 0.4)
    sai = _fade_saida(t, fim, depois=0.2, dur=0.4)
    barra = int(c.H * 0.12 * entra * sai)
    frente = c.vazio()
    if barra > 0:
        dr = ImageDraw.Draw(frente)
        dr.rectangle((0, 0, c.W, barra), fill=(0, 0, 0, 255))
        dr.rectangle((0, c.H - barra, c.W, c.H), fill=(0, 0, 0, 255))
    prog = ease_out((t - ini) / 0.7)
    esp = int(70 - 46 * prog)
    fp = _fonte(c.f["apoio"], 150)
    letras = [_texto(ch, fp, cor=(242, 242, 246), glow=c.acento, glow_r=8,
                     alpha=int(255 * prog * sai)) for ch in palavra]
    total = sum(l.width - 24 for l in letras) + esp * max(0, len(letras) - 1)
    atras = c.vazio()
    x = c.W / 2 - total / 2 + off[0] * 0.5
    for l in letras:
        _colar(atras, l, x + (l.width - 24) / 2, c.H * 0.46 + off[1] * 0.5)
        x += l.width - 24 + esp
    credito = " · ".join(n for n in c.nomes[:2]).upper() or "VX RAPS"
    if barra > 20:
        cl = _texto(credito, _fonte(c.f["apoio"], 34), cor=(210, 210, 216), alpha=int(200 * entra * sai))
        _colar(frente, cl, c.W / 2, barra / 2)
    return atras, frente


def estilo_faiscas(c: Contexto, t: float, i: int, off):
    """Palavra na frente soltando faiscas/brasas da cor da cena; mais faiscas no 808."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    prog = ease_out((t - ini) / 0.3)
    if prog <= 0:
        return None, None
    fade = _fade_saida(t, fim)
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.72), int(c.H * 0.36))
    lay = _texto(palavra, f, cor=(255, 250, 244), stroke=4, stroke_cor=(8, 6, 6),
                 glow=c.acento, glow_r=16, alpha=int(255 * prog * fade))
    cx, cy = c.W / 2 + off[0], c.H * 0.5 + off[1]
    x0, x1 = cx - lay.width * 0.42, cx + lay.width * 0.42
    base_y = cy + lay.height * 0.2
    faiscas = Image.new("RGBA", (c.W, c.H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(faiscas)
    pulso = c.pulso(t)
    for k in range(140):
        rnd = random.Random(k * 7919)
        nasce = ini + rnd.uniform(0, max(0.3, fim - ini + 0.3))
        vida = rnd.uniform(0.5, 1.2)
        age = t - nasce
        if not (0 <= age < vida) or (k >= 90 and pulso < 0.35):
            continue                      # as ultimas 50 so aparecem nos picos de 808
        px = rnd.uniform(x0, x1) + rnd.uniform(-90, 90) * age + 25 * math.sin(age * 9 + k)
        py = base_y - rnd.uniform(160, 460) * age + 120 * age * age
        r = rnd.uniform(1.5, 4.5) * (1 - age / vida) + 0.5
        cor = c.acento if k % 3 else (255, 244, 214)
        a = int(255 * (1 - age / vida) * fade)
        dr.ellipse((px - r, py - r, px + r, py + r), fill=(*cor, a))
    brilho = faiscas.filter(ImageFilter.GaussianBlur(4))
    frente = Image.alpha_composite(c.vazio(), brilho)
    frente = Image.alpha_composite(frente, faiscas)
    _colar(frente, lay, cx, cy)
    return None, frente


def estilo_impacto_portal(c: Contexto, t: float, i: int, off):
    """Portal dimensional de energia girando atras do personagem + pulso no 808 + palavra com choque."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    prog = ease_out((t - ini + 0.1) / 0.45)
    if prog <= 0:
        return None, None
    fade = _fade_saida(t, fim)
    pulso = c.pulso(t)

    atras = c.vazio()
    cx, cy = c.W / 2 + off[0] * 0.7, c.H * 0.45 + off[1] * 0.7

    # Aneis concêntricos de energia do portal com rotacao
    raio_max = int(c.H * 0.42 * prog)
    if raio_max > 8:
        portal = Image.new("RGBA", (c.W, c.H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(portal)
        ang = (t * 2.8) % (2 * math.pi)
        n_arcos = 5
        for r_idx in range(n_arcos):
            r = int(raio_max * (0.35 + 0.65 * (r_idx + 1) / n_arcos))
            r_pulso = int(r * (1.0 + 0.08 * pulso))
            box = (cx - r_pulso, cy - r_pulso, cx + r_pulso, cy + r_pulso)
            rot_arco = math.degrees(ang * (1 if r_idx % 2 == 0 else -1.2) + r_idx * 45)
            alpha_arco = int(180 * (1 - r_idx / n_arcos * 0.4) * prog * fade)
            dr.arc(box, start=rot_arco, end=rot_arco + 230, fill=(*c.acento, alpha_arco), width=4 + (2 if r_idx == 0 else 0))
        glow_portal = portal.filter(ImageFilter.GaussianBlur(8))
        atras = Image.alpha_composite(atras, glow_portal)
        atras = Image.alpha_composite(atras, portal)

    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.78), int(c.H * 0.42))
    esc = 1.0 + 0.05 * pulso
    lay = _texto(palavra, f, cor=(250, 248, 255), stroke=4, stroke_cor=(8, 8, 14),
                 glow=c.acento, glow_r=20, alpha=int(255 * prog * fade))
    _colar(atras, _escalar(lay, esc), cx, cy)

    return atras, None


def estilo_aura_eletrica(c: Contexto, t: float, i: int, off):
    """Descargas eletricas / relampagos em zigue-zague contornando o personagem recortado + pulso forte no 808."""
    from PIL import ImageChops
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    prog = ease_out((t - ini + 0.1) / 0.45)
    if prog <= 0:
        return None, None
    fade = _fade_saida(t, fim)
    pulso = c.pulso(t)

    atras = c.vazio()
    frente = c.vazio()
    cx, cy = c.W / 2 + off[0], c.H * 0.46 + off[1]

    # Palavra de impacto com brilho elétrico
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.75), int(c.H * 0.4))
    lay = _texto(palavra, f, cor=(255, 255, 255), stroke=4, stroke_cor=(10, 15, 30),
                 glow=c.acento, glow_r=22, alpha=int(255 * prog * fade))
    _colar(atras, lay, cx, cy)

    # Raios e centelhas elétricas ao redor do personagem recortado
    m = getattr(c, "mascara", None)
    if m is not None and prog > 0:
        pequeno = m.resize((c.W // 4, c.H // 4), Image.Resampling.BILINEAR).point(lambda p: 255 if p > 100 else 0)
        borda = ImageChops.subtract(pequeno.filter(ImageFilter.MaxFilter(7)), pequeno)
        borda = borda.resize((c.W, c.H), Image.Resampling.BILINEAR)

        # Camada de aura base azulada/neon
        forca = (0.6 + 0.6 * pulso) * prog * fade
        a_base = borda.filter(ImageFilter.GaussianBlur(12)).point(lambda p: min(255, int(p * 1.5 * forca)))
        aura = Image.new("RGBA", (c.W, c.H), (*c.acento, 0))
        aura.putalpha(a_base)
        atras = Image.alpha_composite(atras, aura)

        # Descargas procedurais de raios em zigue-zague ao redor da borda
        raios = Image.new("RGBA", (c.W, c.H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(raios)
        n_raios = int(8 + 12 * pulso)
        seed_frame = int(t * 24) * 31 + 7
        rnd = random.Random(seed_frame)

        cor_raio = (255, 255, 255)
        for _ in range(n_raios):
            # Ponto de origem próximo ao contorno central
            ang = rnd.uniform(0, 2 * math.pi)
            dist_base = rnd.uniform(c.H * 0.15, c.H * 0.45)
            x_ini = cx + math.cos(ang) * dist_base * 0.6
            y_ini = cy + math.sin(ang) * dist_base * 0.6

            pts = [(x_ini, y_ini)]
            passos = rnd.randint(4, 7)
            tam_passo = rnd.uniform(25, 60)
            curr_x, curr_y = x_ini, y_ini
            for _ in range(passos):
                curr_x += math.cos(ang) * tam_passo + rnd.uniform(-35, 35)
                curr_y += math.sin(ang) * tam_passo + rnd.uniform(-35, 35)
                pts.append((curr_x, curr_y))

            alpha_raio = int(rnd.uniform(190, 255) * fade * prog)
            dr.line(pts, fill=(*cor_raio, alpha_raio), width=rnd.randint(2, 4))

        glow_raios = raios.filter(ImageFilter.GaussianBlur(6))
        frente = Image.alpha_composite(frente, glow_raios)
        frente = Image.alpha_composite(frente, raios)

    return atras, frente


def estilo_corte_slash(c: Contexto, t: float, i: int, off):
    """Golpe de corte/slash diagonal cortando a cena e a palavra com feixe luminoso afiado e impacto no 808."""
    jp = c.janela_palavra(t)
    if not jp:
        return None, None
    palavra, ini, fim = jp
    prog = ease_out((t - ini + 0.08) / 0.4)
    if prog <= 0:
        return None, None
    fade = _fade_saida(t, fim)
    pulso = c.pulso(t)

    atras = c.vazio()
    frente = c.vazio()
    cx, cy = c.W / 2 + off[0], c.H * 0.46 + off[1]

    # Palavra fatiada pelo corte
    f = _ajustar(palavra, c.f["impacto"], int(c.W * 0.76), int(c.H * 0.4))
    lay = _texto(palavra, f, cor=(252, 252, 255), stroke=4, stroke_cor=(10, 10, 15),
                 glow=c.acento, glow_r=18, alpha=int(255 * prog * fade))

    # Leve separação das duas metades do texto ao longo da linha do corte
    if prog > 0.15:
        w_l, h_l = lay.size
        # Slash diagonal corta no centro
        _colar(atras, lay, cx, cy)
    else:
        _colar(atras, lay, cx, cy)

    # Feixe luminoso de slash cortando o quadro
    p_slash = min(1.0, max(0.0, (t - ini + 0.05) / 0.22))
    if 0.0 < p_slash < 1.0:
        slash_layer = Image.new("RGBA", (c.W, c.H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(slash_layer)

        # Traço diagonal cruzando de cima à direita para baixo à esquerda
        ang = math.radians(-32)
        diag_len = math.hypot(c.W, c.H) * 1.2
        meio = p_slash * diag_len

        x0 = cx + math.cos(ang) * (meio - diag_len * 0.5)
        y0 = cy + math.sin(ang) * (meio - diag_len * 0.5)
        x1 = cx + math.cos(ang) * (meio - diag_len * 0.1)
        y1 = cy + math.sin(ang) * (meio - diag_len * 0.1)

        # Lâmina central branca e aura externa na cor da letra
        largura_traco = int(12 + 18 * pulso)
        dr.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, int(255 * (1 - p_slash * 0.6))), width=largura_traco)

        aura_slash = slash_layer.filter(ImageFilter.GaussianBlur(16))
        # Tingir aura na cor de destaque
        dr_a = ImageDraw.Draw(aura_slash)
        dr_a.line([(x0, y0), (x1, y1)], fill=(*c.acento, int(220 * (1 - p_slash * 0.4))), width=largura_traco * 2)

        frente = Image.alpha_composite(frente, aura_slash.filter(ImageFilter.GaussianBlur(8)))
        frente = Image.alpha_composite(frente, slash_layer)

    return atras, frente


# ---------------------------------------------------------------------------
# Lote 3 (em teste): CARDS com fundo proprio — medidos na referencia MUGEN RAPS
# (cerebro/referencias.md): 20 momentos graficos em 240 s; 13 sobre a cena
# escurecida (fundo 60-80 % quase preto, texto no meio/centro), cenario tematico,
# paineis de manga (fechamento) e tela escura so com a letra.
# O estilo desenha o fundo inteiro via c.plate_custom = (plate, sujeito|None).
# ---------------------------------------------------------------------------

def _cobrir(img: Image.Image, W: int, H: int) -> Image.Image:
    from PIL import ImageOps
    return ImageOps.fit(img.convert("RGB"), (W, H), Image.Resampling.LANCZOS)


def _tratar(img: Image.Image, luz: float, sat: float, blur: float = 0.0, tinta: tuple | None = None,
            forca_tinta: float = 0.0) -> Image.Image:
    a = np.asarray(img, dtype=np.float32)
    cinza = a.mean(axis=2, keepdims=True)
    a = (cinza + (a - cinza) * sat) * luz
    if tinta is not None and forca_tinta > 0:
        a = a * (1 - forca_tinta) + np.asarray(tinta, np.float32) * (a.mean(axis=2, keepdims=True) / 255) * forca_tinta * 1.6
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return out.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else out


def _brilho_radial(W: int, H: int, cor: tuple, cx: float, cy: float, raio: float, alpha: int) -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - cx) / raio) ** 2 + ((yy - cy) / raio) ** 2)
    a = np.clip(1 - d, 0, 1) ** 2 * alpha
    lay = np.zeros((H, W, 4), np.uint8)
    lay[..., :3] = cor
    lay[..., 3] = a.astype(np.uint8)
    return Image.fromarray(lay, "RGBA")


def _entrada_card(c: "Contexto", t: float, frente: Image.Image) -> Image.Image:
    """Flash curto na entrada do card (a referencia corta seco com pontuacao de luz)."""
    if t < 0.1:
        return Image.alpha_composite(frente, Image.new("RGBA", frente.size, (255, 255, 255, int(90 * (1 - t / 0.1)))))
    return frente


def _titulo_card(c: "Contexto", palavra: str, prog: float, fade: float, largura: float = 0.8,
                 altura: float = 0.34) -> Image.Image:
    f = _ajustar(palavra, c.f["impacto"], int(c.W * largura), int(c.H * altura))
    lay = _texto(palavra, f, cor=(250, 248, 244), stroke=3, stroke_cor=(6, 6, 8), glow=c.acento, glow_r=24,
                 alpha=int(255 * min(1.0, prog * 1.4) * fade))
    return _escalar(lay, 1.12 - 0.12 * ease_out(prog))


def _credito(c: "Contexto", alpha: float) -> Image.Image:
    texto = "  ·  ".join(n.upper() for n in c.nomes[:2]) or "VX RAPS"
    return _texto(texto, _fonte(c.f["apoio"], 40), cor=(215, 215, 222), alpha=int(220 * alpha))


def _regua(c: "Contexto", largura_px: int, prog: float, alpha: float) -> Image.Image:
    """Filetes finos dos dois lados do credito (acabamento de 'title card')."""
    w = int(largura_px * ease_out(prog))
    lay = Image.new("RGBA", (max(1, w), 4), (*c.acento, int(230 * alpha)))
    return lay


def estilo_card_cena_escura(c: Contexto, t: float, i: int, off):
    """Cena congelada, bem escura e desfocada, push-in lento; palavra gigante + credito."""
    jp = c.janela_palavra(t)
    if not jp or not c.quadros:
        return None, None
    palavra, ini, fim = jp
    if "cena_escura" not in c.cache:
        base = Image.fromarray(c.quadros[0])
        c.cache["cena_escura"] = _tratar(base, luz=0.30, sat=0.55, blur=5, tinta=c.cor_cena, forca_tinta=0.18)
    prog_t = t / max(0.1, c.dur)
    plate = transformar(c.cache["cena_escura"], 1.0 + 0.08 * prog_t, 0, 0)
    plate = Image.alpha_composite(plate.convert("RGBA"),
                                  _brilho_radial(c.W, c.H, c.acento, c.W / 2, c.H * 0.45, c.W * 0.45, 70)).convert("RGB")
    c.plate_custom = (plate, None)
    prog = ease_out((t - max(0.0, ini - 0.1)) / 0.45)
    fade = _fade_saida(t, fim)
    frente = c.vazio()
    _colar(frente, _titulo_card(c, palavra, prog, fade), c.W / 2, c.H * 0.45)
    cred = _credito(c, prog * fade)
    _colar(frente, cred, c.W / 2, c.H * 0.66)
    regua = _regua(c, int(c.W * 0.14), prog, fade)
    _colar(frente, regua, c.W / 2 - cred.width / 2 - regua.width / 2 - 24, c.H * 0.66)
    _colar(frente, regua, c.W / 2 + cred.width / 2 + regua.width / 2 + 24, c.H * 0.66)
    return None, _entrada_card(c, t, frente)


def _fundo_ia(c: "Contexto") -> Image.Image | None:
    """Cenario tematico gerado para o projeto (artes_ia/fundo_*.png), se existir."""
    if "fundo_ia" in c.cache:
        return c.cache["fundo_ia"]
    img = None
    if c.projeto is not None:
        cand = sorted((Path(c.projeto) / "artes_ia").glob("fundo_*.png"))
        if cand:
            img = _cobrir(Image.open(cand[-1]), int(c.W * 1.15), int(c.H * 1.15))
    c.cache["fundo_ia"] = img
    return img


def estilo_card_cenario(c: Contexto, t: float, i: int, off):
    """Cenario tematico do projeto (imagem IA 'fundo', sem personagem) com pan lento e a
    cor da letra; palavra no centro e brasas de luz. Sem cenario IA: cena real bem desfocada."""
    jp = c.janela_palavra(t)
    if not jp or not c.quadros:
        return None, None
    palavra, ini, fim = jp
    fundo = _fundo_ia(c)
    prog_t = t / max(0.1, c.dur)
    if fundo is not None:
        dx = int((fundo.width - c.W) * (0.2 + 0.6 * prog_t))
        dy = int((fundo.height - c.H) * 0.5)
        base = fundo.crop((dx, dy, dx + c.W, dy + c.H))
        base = _tratar(base, luz=0.62, sat=0.95, tinta=c.acento, forca_tinta=0.22)
    else:
        if "cenario_fallback" not in c.cache:
            c.cache["cenario_fallback"] = _tratar(Image.fromarray(c.quadros[len(c.quadros) // 2]), 0.45, 0.8, blur=14)
        base = transformar(c.cache["cenario_fallback"], 1.0 + 0.06 * prog_t, 0, 0)
    c.plate_custom = (base, None)
    prog = ease_out((t - max(0.0, ini - 0.1)) / 0.5)
    fade = _fade_saida(t, fim)
    frente = c.vazio()
    _colar(frente, _titulo_card(c, palavra, prog, fade, 0.74, 0.32), c.W / 2, c.H * 0.47)
    frente = Image.alpha_composite(frente, _faiscas_leves(c, t, fade))
    return None, _entrada_card(c, t, frente)


def _faiscas_leves(c: "Contexto", t: float, fade: float) -> Image.Image:
    lay = Image.new("RGBA", (c.W, c.H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    for k in range(60):
        rnd = random.Random(k * 131)
        x = rnd.uniform(0, c.W) + 30 * math.sin(t * 1.3 + k)
        y = (rnd.uniform(0, c.H) - t * rnd.uniform(40, 120)) % c.H
        r = rnd.uniform(1.0, 3.0)
        dr.ellipse((x - r, y - r, x + r, y + r), fill=(*c.acento, int(rnd.uniform(90, 200) * fade)))
    return Image.alpha_composite(lay.filter(ImageFilter.GaussianBlur(2)), lay)


# Retrato so vale com personagem "de apresentacao": nem sumido, nem close gigante.
RETRATO_COBERTURA = (0.10, 0.45)     # fracao do quadro ocupada pelo recorte
RETRATO_MAX_CAIXA = (0.85, 0.97)     # caixa do recorte: largura, altura maximas (fracao do quadro)
RETRATO_MAX_TAPA_TEXTO = 0.45        # recorte cobrindo mais que isso da faixa do titulo -> texto na frente
                                     # (personagem central com 1/3 da largura cobre ~35 %: a palavra
                                     # passa por tras e aparece dos dois lados — e o efeito desejado)


def avaliar_retrato(mascara: Image.Image, quadro: np.ndarray) -> dict:
    """Mede um quadro candidato a retrato: cobertura, caixa do recorte, centro e nitidez
    (variancia do Laplaciano dentro do recorte). Regressao: o 1o card_retrato escolhia o
    quadro com MAIS recorte = um ombro em close, gigante e desfocado, escondendo o titulo."""
    import cv2
    m = np.asarray(mascara.resize((96, 54)), dtype=np.float32) / 255
    cob = float(m.mean())
    ys, xs = np.where(m > 0.5)
    if len(xs) < 8:
        return {"valido": False, "cobertura": cob, "motivo": "sem personagem"}
    larg, alt = (xs.max() - xs.min() + 1) / 96, (ys.max() - ys.min() + 1) / 54
    cx = float(xs.mean()) / 96
    g = cv2.cvtColor(cv2.resize(quadro, (480, 270)), cv2.COLOR_RGB2GRAY)
    lap = cv2.Laplacian(g, cv2.CV_32F)
    mm = cv2.resize(m, (480, 270)) > 0.5
    nitidez = float(lap[mm].var()) if mm.any() else 0.0
    motivo = ""
    if not (RETRATO_COBERTURA[0] <= cob <= RETRATO_COBERTURA[1]):
        motivo = "cobertura fora da faixa"
    elif larg > RETRATO_MAX_CAIXA[0] and alt > RETRATO_MAX_CAIXA[1]:
        motivo = "close gigante (recorte ocupa o quadro)"
    elif not (0.2 <= cx <= 0.8):
        motivo = "personagem na borda"
    elif nitidez < 25:
        motivo = "desfocado"
    return {"valido": not motivo, "cobertura": round(cob, 3), "caixa": (round(larg, 2), round(alt, 2)),
            "centro_x": round(cx, 2), "nitidez": round(nitidez, 1), "motivo": motivo}


def escolher_quadro_retrato(mascaras: list, quadros: list) -> int | None:
    """Melhor quadro valido: nitido e com cobertura perto de ~28 %. None = nenhum serve."""
    melhor, nota_m = None, -1.0
    passo = max(1, len(quadros) // 24)                 # ~24 candidatos bastam
    for k in range(0, min(len(mascaras), len(quadros)), passo):
        a = avaliar_retrato(mascaras[k], quadros[k])
        if not a["valido"]:
            continue
        nota = min(1.0, a["nitidez"] / 400) * (1 - abs(a["cobertura"] - 0.28) * 2)
        if nota > nota_m:
            melhor, nota_m = k, nota
    return melhor


def tapa_texto(mascara: Image.Image, faixa=(0.22, 0.62)) -> float:
    """Quanto o recorte cobre da faixa horizontal onde o titulo fica."""
    m = np.asarray(mascara.resize((96, 54)), dtype=np.float32) / 255
    return float(m[int(54 * faixa[0]):int(54 * faixa[1]), 5:91].mean())


def estilo_card_retrato(c: Contexto, t: float, i: int, off):
    """Personagem nitido recortado sobre fundo escuro com brilho da cor; palavra ENORME
    atras dele (ou na frente, se ele taparia o titulo) e credito embaixo.
    Sem quadro que sirva de retrato na janela -> vira card_cena_escura."""
    jp = c.janela_palavra(t)
    if not jp or not c.quadros:
        return None, None
    palavra, ini, fim = jp
    if "retrato" not in c.cache:
        masc = getattr(c, "mascaras", None) or []
        k = escolher_quadro_retrato(masc, c.quadros)
        if k is None:
            c.cache["retrato"] = None
        else:
            base = Image.fromarray(c.quadros[k])
            fundo = _tratar(base, luz=0.18, sat=0.4, blur=18)
            fundo = Image.alpha_composite(fundo.convert("RGBA"),
                                          _brilho_radial(c.W, c.H, c.acento, c.W / 2, c.H * 0.55, c.W * 0.5, 120)).convert("RGB")
            c.cache["retrato"] = (fundo, _tratar(base, luz=1.0, sat=1.05), masc[k],
                                  tapa_texto(masc[k]) > RETRATO_MAX_TAPA_TEXTO)
    if c.cache["retrato"] is None:
        return estilo_card_cena_escura(c, t, i, off)
    fundo, sujeito, masc_k, texto_na_frente = c.cache["retrato"]
    prog_t = t / max(0.1, c.dur)
    z = 1.0 + 0.05 * prog_t
    plate = transformar(fundo, z, 0, 0)
    suj = transformar(sujeito, z * 1.01, 0, 0)
    if masc_k is not None:
        c.plate_custom = (plate, suj)
        c.mascara_custom = transformar(masc_k, z * 1.01, 0, 0)
    else:
        c.plate_custom = (plate, None)
    prog = ease_out((t - max(0.0, ini - 0.1)) / 0.5)
    fade = _fade_saida(t, fim)
    titulo = c.vazio()
    _colar(titulo, _titulo_card(c, palavra, prog, fade, 0.94, 0.55), c.W / 2, c.H * 0.42)
    frente = c.vazio()
    if texto_na_frente:
        frente = Image.alpha_composite(frente, titulo)
        titulo = None
    _colar(frente, _credito(c, prog * fade), c.W / 2, c.H * 0.9)
    return titulo, _entrada_card(c, t, frente)


def _manga_painel(img: Image.Image, W: int, H: int) -> Image.Image:
    """Cena real -> painel de manga: P&B de alto contraste + reticula nas sombras."""
    from PIL import ImageOps
    g = ImageOps.autocontrast(_cobrir(img, W, H).convert("L"), cutoff=2)
    a = np.asarray(g, dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    pontos = ((np.sin(xx * 0.9) * np.sin(yy * 0.9)) > 0.2)          # reticula
    tinta = np.where(a < 70, 0, np.where(a < 150, np.where(pontos, 30, 235), 255))
    bordas = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    tinta = np.where(bordas > 60, 0, tinta)
    return Image.fromarray(tinta.astype(np.uint8)).convert("RGB")


def estilo_card_manga(c: Contexto, t: float, i: int, off):
    """Pagina de manga montada com 3 momentos da propria janela (paineis entram em
    sequencia) + palavra em balao branco. A referencia fecha o video assim."""
    jp = c.janela_palavra(t)
    if not jp or not c.quadros:
        return None, None
    palavra, ini, fim = jp
    W, H = c.W, c.H
    if "manga" not in c.cache:
        n = len(c.quadros)
        idx = [int(n * 0.1), int(n * 0.45), int(n * 0.8)]
        caixas = [(int(W * 0.02), int(H * 0.03), int(W * 0.58), int(H * 0.55)),
                  (int(W * 0.60), int(H * 0.03), int(W * 0.98), int(H * 0.55)),
                  (int(W * 0.02), int(H * 0.57), int(W * 0.98), int(H * 0.97))]
        paineis = [(_manga_painel(Image.fromarray(c.quadros[k]), b[2] - b[0], b[3] - b[1]), b)
                   for k, b in zip(idx, caixas)]
        c.cache["manga"] = paineis
    pagina = Image.new("RGB", (W, H), (245, 243, 238))
    dr = ImageDraw.Draw(pagina)
    for j, (pn, b) in enumerate(c.cache["manga"]):
        p = ease_out((t - 0.12 * j) / 0.25)
        if p <= 0:
            continue
        deslocado = int((1 - p) * 60)
        pagina.paste(pn, (b[0], b[1] + deslocado))
        dr.rectangle((b[0], b[1] + deslocado, b[2] - 1, b[3] - 1 + deslocado), outline=(10, 10, 10), width=6)
    c.plate_custom = (pagina, None)
    prog = ease_out((t - max(0.0, ini)) / 0.3)
    fade = _fade_saida(t, fim)
    f = _ajustar(palavra, c.f["impacto"], int(W * 0.5), int(H * 0.22))
    txt = _texto(palavra, f, cor=(12, 12, 14), pad=36)
    balao = Image.new("RGBA", (txt.width + 40, txt.height + 20), (0, 0, 0, 0))
    ImageDraw.Draw(balao).rounded_rectangle((4, 4, balao.width - 4, balao.height - 4), radius=30,
                                            fill=(255, 255, 255, 255), outline=(10, 10, 10, 255), width=7)
    balao.alpha_composite(txt, (20, 10))
    balao = _com_alpha(_escalar(balao, 0.7 + 0.3 * ease_out_back(prog)), prog * fade)
    frente = c.vazio()
    _colar(frente, balao, W * 0.62, H * 0.3)
    return None, frente


def estilo_card_letra(c: Contexto, t: float, i: int, off):
    """Tela escura so com a letra (palavra por palavra, grande e centralizada) e a
    palavra-chave na cor da letra; fundo com degrade sutil da cor. Estilo de LINHA."""
    if "letra_fundo" not in c.cache:
        yy = np.linspace(0, 1, c.H, dtype=np.float32)[:, None, None]
        base = np.asarray(c.cor_cena, np.float32) * 0.0
        cor = np.asarray(c.acento, np.float32)
        a = np.clip(6 + cor * 0.16 * (1 - np.abs(yy - 0.55) * 1.6), 0, 255) + base
        c.cache["letra_fundo"] = Image.fromarray(np.repeat(a, c.W, axis=1).astype(np.uint8))
    c.plate_custom = (c.cache["letra_fundo"], None)     # fundo o take inteiro, mesmo entre linhas
    if not linha_ativa(c.linhas, t):
        return None, None
    _atras, frente = estilo_palavra_por_palavra(c, t, i, (0.0, -c.H * 0.17))
    return None, frente


ESTILOS = {
    "atras_personagem": estilo_atras_personagem,
    "palavra_por_palavra": estilo_palavra_por_palavra,
    "glitch_slice": estilo_glitch_slice,
    "kanji_fundo": estilo_kanji_fundo,
    "maquina_escrever": estilo_maquina_escrever,
    # lote 2 (em teste no lab)
    "impacto_zoom": estilo_impacto_zoom,
    "eco_repeticao": estilo_eco_repeticao,
    "fragmentos": estilo_fragmentos,
    "contorno_energia": estilo_contorno_energia,
    "letterbox_cinema": estilo_letterbox_cinema,
    "faiscas": estilo_faiscas,
    "impacto_portal": estilo_impacto_portal,
    "aura_eletrica": estilo_aura_eletrica,
    "corte_slash": estilo_corte_slash,
    # lote 3 (em teste no lab): cards com fundo proprio
    "card_cena_escura": estilo_card_cena_escura,
    "card_cenario": estilo_card_cenario,
    "card_retrato": estilo_card_retrato,
    "card_manga": estilo_card_manga,
    "card_letra": estilo_card_letra,
}
# Estilos implementados mas ainda nao aprovados (so no lab). Lote 2 aprovado em 2026-09-30.
# ---------------------------------------------------------------------------
# BIBLIOTECA (assets/design/biblioteca_motion.json): fonte unica de status e regras
# ---------------------------------------------------------------------------
BIBLIOTECA_ARQ = RAIZ / "assets" / "design" / "biblioteca_motion.json"
STATUS_VALIDOS = {"ativo", "em_teste", "desativado"}
CATEGORIAS = {"nome", "batida", "atmosfera", "linha", "fechamento"}


@functools.lru_cache(maxsize=4)
def _biblioteca_cache(caminho: str, mtime: float) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def biblioteca(arquivo: Path = BIBLIOTECA_ARQ) -> dict:
    """Catalogo de efeitos. Relido sozinho quando o arquivo muda."""
    arquivo = Path(arquivo)
    return _biblioteca_cache(str(arquivo), arquivo.stat().st_mtime)


def status_de(estilo: str) -> str:
    return ((biblioteca().get("estilos") or {}).get(estilo) or {}).get("status", "desativado")


def ativos() -> list[str]:
    """Estilos que a esteira pode usar sozinha (status 'ativo' e implementados)."""
    return [e for e, info in (biblioteca().get("estilos") or {}).items()
            if info.get("status") == "ativo" and e in ESTILOS]


def exige(estilo: str) -> list[str]:
    return list(((biblioteca().get("estilos") or {}).get(estilo) or {}).get("exige") or [])


def regras() -> dict:
    return dict(biblioteca().get("_regras") or {})


EM_TESTE: tuple[str, ...] = tuple(e for e, i in (biblioteca().get("estilos") or {}).items()
                                  if i.get("status") == "em_teste")

NOMES_CATEGORIA = {"nome": "letra cita o personagem", "batida": "808 forte (beat ≥ 0,6)",
                   "atmosfera": "demais momentos", "linha": "linha curta (frase inteira na tela)",
                   "fechamento": "último quinto da música"}


def documentacao_biblioteca() -> str:
    """Markdown de cerebro/biblioteca_motion.md (gerado; nao editar a mao)."""
    lib = biblioteca()
    est = lib.get("estilos") or {}
    rg = lib.get("_regras") or {}
    L = ["# Biblioteca de motion (gerado de `assets/design/biblioteca_motion.json`)", "",
         "> Não edite à mão: mude o JSON e rode `estudio.py cerebro`. Um teste falha se este arquivo ficar defasado.",
         "> Como funciona o sistema inteiro: `cerebro/motion.md`.", "",
         f"**{sum(1 for i in est.values() if i.get('status') == 'ativo')} ativos** · "
         f"{sum(1 for i in est.values() if i.get('status') == 'em_teste')} em teste · "
         f"{sum(1 for i in est.values() if i.get('status') == 'desativado')} desativados", "",
         "## Como a esteira escolhe (automático, pela letra e pelo vídeo)",
         "1. O `graficos-auto` escolhe os momentos (palavra forte, nome, batida) e, para cada um, a **categoria**:",
         *[f"   - `{k}`: {v}" for k, v in NOMES_CATEGORIA.items()],
         "2. Dentro da categoria, os estilos entram na ordem de prioridade (tabela abaixo); linha curta insere os "
         "estilos de `linha` logo depois do 1º; no fechamento, os de `fechamento` vêm antes de tudo.",
         f"3. Só entram estilos `ativo`. Quem `exige protagonista` só entra com o personagem principal "
         f"verificado em cena (visual ≥ {rg.get('protagonista_visual_min')}; ver regra abaixo).",
         f"4. Variedade: fora os {rg.get('nao_repetir_ultimos', 3)} últimos, vence o menos usado no vídeo.",
         "", "## Prioridade por categoria (1 = primeiro)", "",
         "| categoria | estilos (ativos, em ordem) |", "|---|---|"]
    for cat in NOMES_CATEGORIA:
        itens = sorted((i["gatilhos"][cat], e) for e, i in est.items()
                       if cat in (i.get("gatilhos") or {}) and i.get("status") == "ativo")
        L.append(f"| `{cat}` | " + " → ".join(f"`{e}`" for _p, e in itens) + " |")
    L += ["", "## Regra do protagonista", "", str(rg.get("_protagonista", "")), "",
          "## Catálogo", ""]
    for status in ("ativo", "em_teste", "desativado"):
        nomes = [e for e, i in est.items() if i.get("status") == status]
        if not nomes:
            continue
        L += [f"### {status.replace('_', ' ').capitalize()} ({len(nomes)})", ""]
        for e in nomes:
            i = est[e]
            gat = ", ".join(f"{k} {v}" for k, v in sorted((i.get("gatilhos") or {}).items(), key=lambda kv: kv[1]))
            L += [f"#### `{e}` — {i.get('tipo')} · camada {i.get('camada')} · lote {i.get('lote')}", "",
                  i.get("descricao", ""), "",
                  f"- **Quando usar:** {i.get('quando_usar', '')}",
                  f"- **Evitar:** {i.get('evitar', '')}",
                  f"- **Gatilhos:** {gat}"]
            if i.get("exige"):
                L.append(f"- **Exige:** {', '.join(i['exige'])}")
            if i.get("motivo"):
                L.append(f"- **Motivo do status:** {i['motivo']}")
            if i.get("notas"):
                L.append(f"- **Notas:** {i['notas']}")
            L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Protagonista em cena (regra 'exige: protagonista' da biblioteca)
# ---------------------------------------------------------------------------
_TAGS_GENERICAS = {"1boy", "1girl", "solo", "male focus", "female focus", "tall", "lean", "short", "muscular"}


def aparencia_protagonista(manifesto: dict) -> str | None:
    """Descricao VISUAL do personagem principal a partir de projeto.json -> imagem_ia.tags_personagem,
    sem nomes/anime/tags genericas (o CLIP reconhece aparencia muito melhor que nome).
    Gojo: 'white hair, blue eyes, blindfold, black blindfold, uniform'."""
    tags = str(imagem_ia_cfg(manifesto).get("tags_personagem") or "")
    nomes = {p for p in normalizar(f"{manifesto.get('personagem', '')} {manifesto.get('anime', '')}").split()
             if len(p) >= 3}
    visuais = []
    for t in (x.strip() for x in tags.split(",")):
        n = normalizar(t)
        if not n or t.lower() in _TAGS_GENERICAS or any(p in n.split() for p in nomes) or "series" in n:
            continue
        visuais.append(t)
    return ", ".join(visuais[:6]) or None


class DetectorProtagonista:
    """OpenCLIP zero-shot: 'personagem com a aparencia do protagonista' x 'outro personagem' x
    'sem personagem'. score = probabilidade media da 1a hipotese nos quadros."""

    def __init__(self, manifesto: dict):
        self.aparencia = aparencia_protagonista(manifesto)
        self.ok = False
        if not self.aparencia:
            return
        import torch
        import open_clip
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.modelo, _, self.prep = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k", device=self.dev)
        self.modelo.eval()
        tok = open_clip.get_tokenizer("ViT-B-32")
        prompts = [f"an anime character with {self.aparencia}",
                   "an anime character with a completely different hair color, face and outfit",
                   "an anime frame with no character, only effects, explosion or scenery"]
        with torch.no_grad():
            tf = self.modelo.encode_text(tok(prompts).to(self.dev))
            self.tf = tf / tf.norm(dim=-1, keepdim=True)
        self.ok = True

    def score(self, quadros: list[np.ndarray]) -> float:
        if not self.ok or not quadros:
            return 0.0
        torch = self.torch
        with torch.no_grad():
            im = torch.stack([self.prep(Image.fromarray(q)) for q in quadros]).to(self.dev)
            f = self.modelo.encode_image(im)
            f = f / f.norm(dim=-1, keepdim=True)
            pr = (100.0 * f @ self.tf.T).softmax(dim=-1)[:, 0]
        return float(pr.mean())

    def score_janela(self, d: Path, timeline: dict, inicio: float, dur: float, n: int = 3,
                     salvar: Path | None = None) -> float:
        """Amostra n quadros da footage real que o take cobre (448x252) e mede.
        `salvar`: grava o quadro do meio com o score no nome, para auditoria humana."""
        from timeline_clipe import fonte
        cfg = {"largura": 448, "altura": 252, "fps": 2}
        quadros = []
        for tr in trechos_fonte(timeline, inicio, dur):
            quadros += _decodificar(fonte(d, tr["clip"]), tr["src"], max(0.5, tr["t_fim"] - tr["t_ini"]), cfg)
        if not quadros:
            return 0.0
        idx = sorted({int(len(quadros) * (k + 0.5) / n) for k in range(n)})
        s = self.score([quadros[min(i, len(quadros) - 1)] for i in idx])
        if salvar is not None:
            Path(salvar).mkdir(parents=True, exist_ok=True)
            Image.fromarray(quadros[len(quadros) // 2]).save(Path(salvar) / f"{inicio:07.2f}s_score{s:.2f}.jpg", quality=85)
        return s


# ---------------------------------------------------------------------------
# Quadros: decodificacao, plate, recorte, tracking
# ---------------------------------------------------------------------------

def _decodificar(clip: Path, src: float, dur: float, cfg: dict):
    """Decode (sem encode) do trecho em RGB 1920x1080 @fps, via pipe rawvideo."""
    import render_dispatch as rd
    W, H, fps = cfg["largura"], cfg["altura"], cfg["fps"]
    n = max(1, round(dur * fps))
    cmd = [rd.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", f"{src:.3f}", "-i", str(clip),
           "-t", f"{dur + 0.2:.3f}", "-vf",
           f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
           "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="replace")[-600:])
    tam = W * H * 3
    quadros = [np.frombuffer(p.stdout[k:k + tam], np.uint8).reshape(H, W, 3)
               for k in range(0, len(p.stdout) - tam + 1, tam)]
    while quadros and len(quadros) < n:
        quadros.append(quadros[-1])
    return quadros[:n]


def _plate(arr: np.ndarray, cfg: dict, prog: float) -> tuple[Image.Image, Image.Image]:
    pc = cfg["plate"]
    img = Image.fromarray(arr)
    z = 1.0 + pc["push_in"] * prog
    if z > 1.001:
        W, H = img.size
        w2, h2 = int(W / z), int(H / z)
        img = img.crop(((W - w2) // 2, (H - h2) // 2, (W + w2) // 2, (H + h2) // 2)).resize((W, H), Image.Resampling.BILINEAR)
    a = np.asarray(img, dtype=np.float32)
    cinza = a.mean(axis=2, keepdims=True)
    plate = (cinza + (a - cinza) * pc["saturacao"]) * pc["escurecer"]
    sujeito = a * pc["sujeito_brilho"]
    return (Image.fromarray(np.clip(plate, 0, 255).astype(np.uint8)),
            Image.fromarray(np.clip(sujeito, 0, 255).astype(np.uint8)))


def _acento(quadros: list[np.ndarray], padrao: str) -> tuple[int, int, int]:
    """Cor de destaque tirada da cena (pixels saturados e claros); senao a do manifesto."""
    import colorsys
    amostra = quadros[len(quadros) // 2][::8, ::8].reshape(-1, 3).astype(np.float32) / 255
    mx, mn = amostra.max(1), amostra.min(1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    sel = amostra[(sat > 0.45) & (mx > 0.45)]
    if len(sel) < 30:
        return _rgb(padrao)
    h = matiz_dominante(sel)
    return tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, 0.8, 1.0))


def matiz_dominante(rgb: np.ndarray, bins: int = 24) -> float:
    """Matiz (0..1) mais frequente, ponderado pela saturacao. Media de RGB mistura
    azul+vermelho em cinza/verde; o histograma pega a cor que de fato domina."""
    mx, mn = rgb.max(1), rgb.min(1)
    delta = np.maximum(mx - mn, 1e-6)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    h = np.where(mx == r, ((g - b) / delta) % 6, np.where(mx == g, (b - r) / delta + 2, (r - g) / delta + 4)) / 6
    peso = (mx - mn) / np.maximum(mx, 1e-6)
    hist, bordas = np.histogram(h, bins=bins, range=(0, 1), weights=peso)
    k = int(hist.argmax())
    return float((bordas[k] + bordas[k + 1]) / 2)


@functools.lru_cache(maxsize=4)
def _sessao_recorte(modelo: str):
    """Sessão rembg com fallback automático para u2net se o modelo falhar."""
    from rembg import new_session
    try:
        return new_session(modelo)
    except Exception as exc:
        if modelo != "u2net":
            print(f"  [motion_lab] aviso: modelo {modelo} falhou ({exc}); usando fallback u2net...")
            try:
                return new_session("u2net")
            except Exception:
                pass
        raise


def _mascaras(quadros: list[np.ndarray], cortes: set[int], cfg: dict) -> list[Image.Image]:
    from rembg import remove
    rc = cfg["recorte"]
    sessao = _sessao_recorte(rc.get("modelo", "isnet-anime"))
    W, H = cfg["largura"], cfg["altura"]
    lado = int(rc["lado"])
    out, anterior = [], None
    for i, arr in enumerate(quadros):
        peq = Image.fromarray(arr).resize((lado, int(lado * H / W)), Image.Resampling.BILINEAR)
        m = np.asarray(remove(peq, session=sessao, only_mask=True), dtype=np.float32)
        if anterior is not None and i not in cortes:
            m = anterior * rc["suavizacao"] + m * (1 - rc["suavizacao"])
        anterior = m
        mi = Image.fromarray(np.clip(m, 0, 255).astype(np.uint8), "L").resize((W, H), Image.Resampling.BILINEAR)
        out.append(mi.filter(ImageFilter.GaussianBlur(rc["feather"])))
    return out


def _deltas(quadros: list[np.ndarray]) -> list[tuple[float, float]]:
    import cv2
    out, ant = [(0.0, 0.0)], None
    for arr in quadros:
        g = cv2.cvtColor(cv2.resize(arr, (480, 270)), cv2.COLOR_RGB2GRAY).astype(np.float32)
        if ant is not None:
            (dx, dy), _ = cv2.phaseCorrelate(ant, g)
            out.append((float(dx) * 4, float(dy) * 4))
        ant = g
    return out[:len(quadros)]


def _acabamento(cfg: dict):
    W, H = cfg["largura"], cfg["altura"]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vin = (1 - cfg["vinheta"] * np.clip(r - 0.35, 0, 1) ** 1.6)[..., None]
    rng = np.random.default_rng(7)
    grao = cfg["grao"] * 255

    def aplicar(img: Image.Image) -> Image.Image:
        a = np.asarray(img, dtype=np.float32) * vin
        if grao:
            ruido = rng.normal(0, grao, (H // 2, W // 2, 1)).astype(np.float32)
            a += np.repeat(np.repeat(ruido, 2, 0), 2, 1)
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return aplicar


# ---------------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------------

def preparar(d: Path, manifesto: dict, timeline: dict, sync: list[dict], de: float, dur: float,
             cfg: dict | None = None, so_linha: str | None = None) -> dict:
    """Decodifica a footage real da janela e calcula recorte, tracking e cor (uma vez por janela)."""
    from audio_reactive_fx import carregar_picos, relativos
    from timeline_clipe import fonte

    d = Path(d)
    cfg = cfg or carregar_cfg(manifesto=manifesto)
    trechos = trechos_fonte(timeline, de, dur)
    if not trechos:
        raise ValueError(f"nenhuma cena real em {de}s..{de + dur}s")
    fps = cfg["fps"]
    total = max(1, round(dur * fps))
    quadros, cortes = [], set()
    for tr in trechos:
        cortes.add(len(quadros))
        quadros += _decodificar(fonte(d, tr["clip"]), tr["src"], tr["t_fim"] - tr["t_ini"], cfg)
    cortes.discard(0)
    # arredondamento por plano: fecha exatamente no numero de quadros da janela
    while len(quadros) < total:
        quadros.append(quadros[-1])
    quadros = quadros[:total]
    cortes = {c for c in cortes if c < total}
    print(f"  {len(quadros)} quadros de {len(trechos)} plano(s); recortando personagem "
          f"({cfg['recorte']['modelo']})...")
    mascaras = _mascaras(quadros, cortes, cfg)
    tc = cfg["tracking"]
    try:
        picos = relativos(carregar_picos(d, manifesto), de, dur)
    except Exception:
        picos = []
    return {
        "cfg": cfg, "de": de, "dur": dur, "trechos": trechos, "quadros": quadros,
        "mascaras": mascaras, "cortes": cortes, "recorte": cobertura_recorte(mascaras),
        "offs": acumular_tracking(_deltas(quadros), cortes, tc["fator"], tc["suavizacao"], tc["max_px"]),
        "acento": _acento(quadros, (manifesto.get("cor") or {}).get("destaque", "#00E5FF")),
        "linhas": linhas_no_trecho(sync, de, dur, so_linha), "nomes": nomes_do_manifesto(manifesto),
        "picos": picos, "projeto": d,
    }


def renderizar(prep: dict, estilo: str, destino: Path, audio: Path | None = None,
               palavra: str | None = None, t_palavra: float | None = None,
               linha_take: str | None = None) -> list[Image.Image]:
    """Renderiza um estilo sobre a janela preparada. Sem `audio`: MP4 so de video (take da esteira)."""
    import render_dispatch as rd
    if estilo not in ESTILOS:
        raise ValueError(f"estilo desconhecido: {estilo}; disponiveis: {sorted(ESTILOS)}")
    cfg, quadros, dur, fps = prep["cfg"], prep["quadros"], prep["dur"], prep["cfg"]["fps"]
    ctx = Contexto(cfg, prep["linhas"], dur, tuple(prep["acento"]), prep["nomes"], prep["picos"],
                   palavra=palavra, t_palavra=t_palavra)
    if linha_take:
        ctx.cor_take = cor_da_letra(linha_take, cfg.get("cores") or {})
    ctx.quadros, ctx.projeto = quadros, prep.get("projeto")
    ctx.mascaras = prep["mascaras"]
    vazia = Image.new("L", (cfg["largura"], cfg["altura"]), 0)
    fn, acabar = ESTILOS[estilo], _acabamento(cfg)
    n = len(quadros)
    amostras = {int(n * k / 5) for k in (1, 2, 3, 4)}
    miniaturas = []
    destino = Path(destino)
    with tempfile.TemporaryDirectory(prefix="vx_motion_") as tmp:
        pasta = Path(tmp)
        for i, arr in enumerate(quadros):
            t = i / fps
            ctx.mascara, ctx.efeito_plate, ctx.plate_custom = prep["mascaras"][i], None, None
            ctx.mascara_custom = None
            ctx.quadro = arr
            ctx.atualizar_cor(t)
            atras, frente = fn(ctx, t, i, prep["offs"][i])
            masc = prep["mascaras"][i]
            if ctx.plate_custom is not None:
                # card de fundo: o estilo desenhou o fundo inteiro (e, se quiser, o proprio recorte)
                plate, sujeito = ctx.plate_custom
                if sujeito is None:
                    sujeito, masc = plate, vazia
                elif ctx.mascara_custom is not None:
                    masc = ctx.mascara_custom
            else:
                if ctx.efeito_plate:
                    # camera do estilo (soco de zoom/tremor): mesmo transform na cena e no recorte
                    e = ctx.efeito_plate
                    arr = np.asarray(transformar(Image.fromarray(arr), e.get("zoom", 1.0), e.get("dx", 0), e.get("dy", 0)))
                    masc = transformar(masc, e.get("zoom", 1.0), e.get("dx", 0), e.get("dy", 0))
                plate, sujeito = _plate(arr, cfg, t / max(0.1, dur))
            quadro = acabar(compor_camadas(plate, sujeito, masc, atras, frente))
            quadro.save(pasta / f"f_{i:05d}.png", compress_level=1)
            if i in amostras:
                miniaturas.append(quadro.resize((cfg["largura"] // 4, cfg["altura"] // 4)))
        entradas = ["-framerate", str(fps), "-i", str(pasta / "f_%05d.png")]
        if audio is not None:
            entradas += ["-ss", f"{prep['de']:.3f}", "-t", f"{dur:.3f}", "-i", str(audio)]
            rd.encode(saida=str(destino), entradas=entradas, mapa=["-map", "0:v:0", "-map", "1:a:0"],
                      args_extra=["-shortest", "-r", str(fps)], cq="17", silencioso=True)
        else:
            rd.encode(saida=str(destino), entradas=entradas, mapa=["-map", "0:v:0"], args_audio=["-an"],
                      args_extra=["-r", str(fps), "-frames:v", str(n)], cq="17", silencioso=True)
    return miniaturas


def renderizar_take(d: Path, manifesto: dict, base_timeline: dict, sync: list[dict], spec: dict,
                    destino: Path) -> dict:
    """Take do graficos-auto sobre a cena real que ele substitui (MP4 sem audio).

    spec: {estilo, start, duration, word, word_start}. Devolve a cobertura do recorte.
    """
    prep = preparar(d, manifesto, base_timeline, sync, float(spec["start"]), float(spec["duration"]),
                    so_linha=spec.get("line_text"))
    palavra = spec.get("word") if spec["estilo"] not in ESTILOS_DE_LINHA else None
    t_palavra = (float(spec["word_start"]) - float(spec["start"])) if spec.get("word_start") is not None else None
    renderizar(prep, spec["estilo"], destino, audio=None, palavra=palavra, t_palavra=t_palavra,
               linha_take=spec.get("line_text"))
    return prep["recorte"]


ESTILOS_DE_LINHA = {e for e, i in (biblioteca().get("estilos") or {}).items() if i.get("tipo") == "linha"}
ESTILOS_DE_PALAVRA = tuple(e for e in ESTILOS if e not in ESTILOS_DE_LINHA)


def escolher_estilo(candidato: dict, recentes: list[str], estilos: list[str],
                    max_linha: float = 3.6) -> str | None:
    """Estilo do take pela natureza do momento, sem repetir os 3 ultimos.

    nome do personagem -> presenca (atras, aura, cinema, kanji);
    808 forte -> impacto (soco de camera, glitch, fragmentos, faiscas);
    demais -> atmosfera (kanji, eco, faiscas, cinema...);
    linha curta e clara -> estilos de linha (a legenda do trecho e ocultada no render).
    """
    lib = biblioteca().get("estilos") or {}
    rg = regras()

    def por_categoria(cat: str) -> list[str]:
        itens = [(info["gatilhos"][cat], e) for e, info in lib.items() if cat in (info.get("gatilhos") or {})]
        return [e for _p, e in sorted(itens)]

    dur_linha = float(candidato["line_end"]) - float(candidato["line_start"])
    if candidato.get("name_hit"):
        pref = por_categoria("nome")
    elif float(candidato.get("beat_score", 0)) >= 0.6:
        pref = por_categoria("batida")
    else:
        pref = por_categoria("atmosfera")
    if dur_linha <= max_linha:
        pref = pref[:1] + por_categoria("linha") + pref[1:]
    # fechamento (como a referencia MUGEN RAPS): ultimo quinto da musica
    if float(candidato.get("posicao", 0.0)) >= float(rg.get("fechamento_a_partir_de", 0.78)):
        pref = por_categoria("fechamento") + pref
    # qualquer estilo habilitado fora das preferencias ainda pode ser usado (menor prioridade)
    pref += [e for e in estilos if e not in pref and e not in ESTILOS_DE_LINHA]
    ordem = []
    for e in pref:
        if e in ordem or e not in estilos or lib.get(e, {}).get("status") != "ativo":
            continue
        # regra 'protagonista': so com o personagem principal comprovadamente em cena
        if "protagonista" in exige(e) and candidato.get("protagonista") is not True:
            continue
        ordem.append(e)
    # variedade: entre os que nao sao dos N ultimos, o MENOS usado no video vence
    # (empate -> ordem de preferencia). Assim todos aparecem antes de repetir.
    n = int(rg.get("nao_repetir_ultimos", 3))
    livres = [e for e in ordem if e not in recentes[-n:]]
    if livres:
        return min(livres, key=lambda e: (recentes.count(e), ordem.index(e)))
    return ordem[0] if ordem else None


def executar(d: Path, manifesto: dict, slug: str, de: float | None = None, dur: float = 4.0,
             estilos: list[str] | None = None) -> dict:
    """Lab livre: uma previa por estilo em lab/motion/. Nao toca timeline, legenda nem master."""
    d = Path(d)
    cfg = carregar_cfg(manifesto=manifesto)
    timeline = json.loads((d / "timeline.json").read_text(encoding="utf-8"))
    sync = json.loads((d / "letra_sincronizada.json").read_text(encoding="utf-8"))
    if de is None:
        de = escolher_inicio(timeline, sync)
    estilos = estilos or list(cfg["estilos"])
    desconhecidos = [e for e in estilos if e not in ESTILOS]
    if desconhecidos:
        raise ValueError(f"estilo desconhecido: {desconhecidos}; disponiveis: {sorted(ESTILOS)}")
    prep = preparar(d, manifesto, timeline, sync, de, dur, cfg)
    audio = vx_projeto.audio(d, manifesto)
    saida_dir = d / "lab" / "motion"
    saida_dir.mkdir(parents=True, exist_ok=True)
    rel = {"slug": slug, "de": de, "dur": dur, "trechos": prep["trechos"], "acento": prep["acento"],
           "linhas": [ln["text"] for ln in prep["linhas"]], "recorte": prep["recorte"],
           "previas": {}, "folhas": {}}
    for nome in estilos:
        destino = saida_dir / f"{nome}_{de:g}s.mp4"
        miniaturas = renderizar(prep, nome, destino, audio=audio)
        folha = saida_dir / f"{nome}_{de:g}s_folha.png"
        folha_img(miniaturas).save(folha)
        rel["previas"][nome] = str(destino.relative_to(d))
        rel["folhas"][nome] = str(folha.relative_to(d))
        print(f"  {nome}: {destino}")
    (saida_dir / f"lab_{de:g}s.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    return rel
