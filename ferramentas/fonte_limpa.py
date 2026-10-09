#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fonte_limpa.py — porteiro de FONTE: marca d'agua / logo e legenda queimada nos clipes.

Incidente Douma (30/09/2026): clipes oficiais (Crunchyroll/Aniplex no YouTube) vem com
LEGENDA EM INGLES queimada e packs de twixtor vem com MARCA D'AGUA do canal. O QA antigo
so via tela morta/congelada, entao o video saiu com cenas "poluidas".

O que este modulo faz (sem OCR; medidas de imagem):
1. Marca d'agua / logo (`detectar_marca`): borda que fica PARADA enquanto a imagem muda.
   Amostra ~48 quadros do clipe; pixel e "persistente" se e borda em >= 55 % deles e o resto
   do quadro varia. Componentes conexos dessas bordas = caixas da marca.
2. Legenda queimada (`legenda_no_quadro`): faixa de baixo com texto claro de contorno escuro,
   linhas de glifos alinhadas na horizontal e centralizadas; compara com a faixa de cima para
   nao confundir cenario.
3. Limpeza (`limpar_clipe`): marca perto da borda -> zoom-in minimo que a empurra para fora
   (<= 1,18x); marca no meio -> `delogo` do ffmpeg na caixa. Original vai para
   clips_raw/_originais/. Segmentos com legenda queimada viram "cena poluida" no catalogo e o
   Scene Matcher nunca os escolhe (como dead_scene).

Porta: estudio.py fonte-limpa <slug> [--corrigir]   (roda sozinho em estudio.py clipes)
Relatorio: qa/fonte_limpa.json + qa/fonte_limpa.md. Limiares em config/porteiros.json[fonte].
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

import _vx  # noqa: F401
from _vx import config as vx_config

W, H = 480, 270
PADRAO = {
    "amostras_marca": 48,
    "persistencia_min": 0.55,        # fracao dos quadros em que o pixel e borda
    "area_min_px": 60,               # caixa minima (em 480x270)
    "variacao_min_cena": 8.0,        # o resto do quadro precisa mudar (clipe nao estatico)
    "margem_borda": 0.14,            # caixa dentro desta margem = "marca de canto" (zoom resolve)
    "zoom_max": 1.18,
    "legenda_fps": 2.0,
    "legenda_score_min": 0.55,
    "legenda_fracao_cena": 0.30,     # cena poluida se >= 30 % dos quadros tem legenda
    "max_poluido_clipe": 0.60,       # clipe reprovado se > 60 % tem legenda (nao sobra material)
    "contraste_max": 0.45,           # marca por trecho: std dentro / std no entorno
    "chroma_min": 0.25,              # quadro de tela verde: >= 25 % de verde chroma uniforme
    "chroma_fracao_cena": 0.5,       # cena de tela verde se >= 50 % dos quadros
    # OCR (RapidOCR local) — regressao Douma 01/10/2026 (logo Crunchyroll, "DESTROY", cartela)
    "ocr_fps": 2.0,                  # amostragem do OCR no original (cache em qa/fonte_ocr/)
    "ocr_fps_verificacao": 0.5,      # OCR de novo no clipe limpo: o que sobrar reprova
    "ocr_conf_min": 0.6,
    "ocr_marca_min_s": 6.0,          # mesmo texto no mesmo lugar por >= 6 s = marca, nao legenda
    "ocr_marca_todo": 0.5,           # marca em >= 50 % do clipe: limpeza do clipe todo (recorte)
}


def cfg() -> dict:
    return vx_config.porteiro("fonte", PADRAO)


# ---------------------------------------------------------------------------
# Decodificacao
# ---------------------------------------------------------------------------

def _duracao(video: Path) -> float:
    import render_dispatch as rd
    r = subprocess.run([rd.ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(video)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _quadros(video: Path, fps: float, w: int = W, h: int = H):
    import render_dispatch as rd
    cmd = [rd.ffmpeg_bin(), "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    tam = w * h * 3
    try:
        while True:
            buf = p.stdout.read(tam)
            if len(buf) < tam:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.wait()


# ---------------------------------------------------------------------------
# Marca d'agua (funcoes puras testadas)
# ---------------------------------------------------------------------------

def sem_linhas_de_borda(mascara: np.ndarray, fracao: float = 0.5) -> np.ndarray:
    """Tira da mascara de bordas paradas as LINHAS longas (limite de letterbox/pillarbox,
    moldura do player). Regressao Douma/Crunchyroll (01/10/2026): o logo no canto encostava
    na linha da moldura, a dilatacao fundia os dois num componente com > 70 % da largura e o
    filtro de letterbox jogava o logo fora junto."""
    import cv2
    m = mascara.copy()
    h, w = m.shape
    horiz = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((1, max(3, int(w * fracao))), np.uint8))
    vert = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((max(3, int(h * fracao)), 1), np.uint8))
    linhas = cv2.dilate(((horiz | vert) > 0).astype(np.uint8), np.ones((3, 3), np.uint8))
    m[linhas > 0] = 0
    return m


def caixas_persistentes(quadros: list[np.ndarray], c: dict | None = None) -> list[dict]:
    """Caixas de bordas que ficam paradas enquanto a cena muda (logo/marca d'agua)."""
    import cv2
    c = c or cfg()
    if len(quadros) < 8:
        return []
    cinzas = [cv2.cvtColor(q, cv2.COLOR_RGB2GRAY) for q in quadros]
    bordas = np.stack([cv2.Canny(g, 80, 180) > 0 for g in cinzas]).astype(np.float32)
    persist = bordas.mean(axis=0)
    variacao = float(np.stack(cinzas).astype(np.float32).std(axis=0).mean())
    if variacao < float(c["variacao_min_cena"]):
        return []                                   # clipe estatico: tudo "persiste"
    mascara = (persist >= float(c["persistencia_min"])).astype(np.uint8)
    mascara = sem_linhas_de_borda(mascara)
    mascara = cv2.dilate(mascara, np.ones((5, 9), np.uint8))
    n, rot, stats, _ = cv2.connectedComponentsWithStats(mascara, 8)
    out = []
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[k])
        if area < int(c["area_min_px"]) or w * h > 0.35 * W * H:
            continue
        if w > 0.7 * W or h > 0.7 * H:
            continue                                # limite de letterbox/pillarbox, nao e logo
        if (w <= 0.03 * W and (x <= 0.02 * W or x + w >= 0.98 * W)) or \
           (h <= 0.03 * H and (y <= 0.02 * H or y + h >= 0.98 * H)):
            continue                                # emenda do pad borrado (normalizacao 16:9)
        m = float(c["margem_borda"])
        canto = (x < W * m or x + w > W * (1 - m)) and (y < H * m or y + h > H * (1 - m))
        borda = x < W * m or x + w > W * (1 - m) or y < H * m or y + h > H * (1 - m)
        out.append({"x": x / W, "y": y / H, "w": w / W, "h": h / H, "area": area,
                    "persistencia": round(float(persist[rot == k].mean()), 3),
                    "posicao": "canto" if canto else ("borda" if borda else "centro")})
    return sorted(out, key=lambda b: -b["area"])


def enquadramento_limpo(caixas: list[dict], zoom_max: float, folga: float = 0.01) -> dict | None:
    """Menor recorte (mesma proporcao) que deixa TODAS as caixas fora do quadro.

    Cada caixa sai pelo lado que ela toca (esquerda, direita, cima, baixo); o recorte nao
    precisa ser central (marca no rodape -> recorte ancorado em cima). Retorna
    {"s": lado relativo do recorte, "x": ..., "y": ..., "zoom": 1/s} ou None se precisar de
    zoom acima de `zoom_max` (ai a limpeza cai no delogo)."""
    from itertools import product
    if not caixas:
        return None
    melhor = None
    for lados in product(("esq", "dir", "cima", "baixo"), repeat=len(caixas)):
        L, R, T, B = 0.0, 1.0, 0.0, 1.0
        for b, lado in zip(caixas, lados):
            if lado == "esq":
                L = max(L, b["x"] + b["w"] + folga)
            elif lado == "dir":
                R = min(R, b["x"] - folga)
            elif lado == "cima":
                T = max(T, b["y"] + b["h"] + folga)
            else:
                B = min(B, b["y"] - folga)
        s = min(R - L, B - T)
        if s <= 0:
            continue
        z = 1 / s
        if z > zoom_max or (melhor and z >= melhor["zoom"]):
            continue
        # centraliza o recorte dentro da faixa permitida
        x = L + ((R - L) - s) / 2
        y = T + ((B - T) - s) / 2
        melhor = {"s": round(s, 4), "x": round(x, 4), "y": round(y, 4), "zoom": round(z, 3)}
    return melhor


def zoom_para_esconder(caixas: list[dict], zoom_max: float) -> float | None:
    """So o fator de zoom do `enquadramento_limpo`."""
    e = enquadramento_limpo(caixas, zoom_max)
    return e["zoom"] if e else None


def contraste_temporal(quadros: list[np.ndarray], caixa: dict) -> float:
    """std temporal DENTRO da caixa / std no anel ao redor. Logo de verdade fica parado
    enquanto o entorno muda (razao << 1); detalhe de cenario muda junto com o entorno."""
    import cv2
    cinzas = [cv2.cvtColor(q, cv2.COLOR_RGB2GRAY) for q in quadros]
    g = np.stack(cinzas).astype(np.float32)
    std = g.std(axis=0)
    x0, y0 = int(caixa["x"] * W), int(caixa["y"] * H)
    x1, y1 = max(x0 + 1, int((caixa["x"] + caixa["w"]) * W)), max(y0 + 1, int((caixa["y"] + caixa["h"]) * H))
    # so os TRACOS da marca (bordas persistentes): o fundo entre as letras muda de verdade
    persist = np.stack([cv2.Canny(c, 80, 180) > 0 for c in cinzas]).mean(axis=0)
    tracos = cv2.dilate((persist >= 0.6).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    sub = std[y0:y1, x0:x1][tracos[y0:y1, x0:x1]]
    dentro = float(sub.mean()) if sub.size else float(std[y0:y1, x0:x1].mean())
    m = 12
    ax0, ay0, ax1, ay1 = max(0, x0 - m), max(0, y0 - m), min(W, x1 + m), min(H, y1 + m)
    anel = std[ay0:ay1, ax0:ax1].copy()
    anel[y0 - ay0:y1 - ay0, x0 - ax0:x1 - ax0] = np.nan
    fora = float(np.nanmean(anel)) if np.isfinite(anel).any() else 0.0
    return round(dentro / max(1e-3, fora), 3)


def marcas_por_trecho(quadros: list[np.ndarray], fps: float, c: dict | None = None,
                      janela_s: float = 6.0) -> list[dict]:
    """Marca d'agua que aparece so em PARTE do clipe (packs de twixtor: cada sub-clipe tem a
    sua). Caixas persistentes por janela deslizante, confirmadas por contraste temporal
    (dentro parado, entorno mexendo) e juntadas no tempo. Regressao Douma (30/09/2026):
    'watermark ta cheio' — a deteccao do clipe inteiro so via marca que ficava o video todo."""
    c = c or cfg()
    n = max(8, int(round(janela_s * fps)))
    passo = max(1, n // 2)
    achadas: list[dict] = []
    for ini in range(0, max(1, len(quadros) - n + 1), passo):
        bloco = quadros[ini:ini + n]
        for b in caixas_persistentes(bloco, {**c, "persistencia_min": max(0.7, float(c["persistencia_min"]))}):
            if b["w"] * b["h"] > 0.06 or contraste_temporal(bloco, b) > float(c.get("contraste_max", 0.45)):
                continue
            t0, t1 = ini / fps, (ini + len(bloco)) / fps
            for a in achadas:                       # mesma caixa na janela seguinte: estende
                ix = max(0.0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
                iy = max(0.0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
                if ix * iy > 0.4 * min(a["w"] * a["h"], b["w"] * b["h"]) and t0 <= a["t1"] + 0.1:
                    a["t1"] = max(a["t1"], t1)
                    break
            else:
                achadas.append({**b, "t0": round(t0, 2), "t1": round(t1, 2)})
    return achadas


FAIXA_LEGENDA = (0.70, 0.96)       # mesma faixa de `legenda_no_quadro`


def separar_legenda(marcas: list[dict], linha_legenda: list[tuple[float, float]],
                    c: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Separa marca de trecho de LEGENDA PARADA. Caixa na faixa da legenda, num trecho em que
    a legenda queimada aparece, e frase de legenda que ficou alguns segundos na tela — nao e
    logo. Ela nao leva delogo (borraria o rosto/cenario) nem reprova: a cena ja vira `poluida`
    e o matcher pula. Regressao Douma/Crunchyroll (30/09/2026)."""
    c = c or cfg()
    marcas_reais, legenda = [], []
    for m in marcas:
        cy = m["y"] + m["h"] / 2
        na_faixa = FAIXA_LEGENDA[0] <= cy <= FAIXA_LEGENDA[1]
        com_legenda = fracao_legenda(linha_legenda, m["t0"], m["t1"], float(c["legenda_score_min"])) \
            >= float(c["legenda_fracao_cena"])
        (legenda if na_faixa and com_legenda else marcas_reais).append(m)
    return marcas_reais, legenda


def separar_trechos(v: dict, c: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Marcas por trecho que merecem delogo. Fica de fora: legenda parada (`separar_legenda`)
    e trecho de TELA VERDE — la o contorno parado e o personagem sobre fundo liso, nao logo, e
    o `chroma-auto` troca o fundo inteiro (delogo ali borraria o recorte)."""
    c = c or cfg()
    reais, legenda = separar_legenda(v["marcas_trecho"], v["legenda"], c)
    chroma_min, fracao = float(c["chroma_min"]), float(c["chroma_fracao_cena"])
    reais = [m for m in reais if fracao_legenda(v["chroma"], m["t0"], m["t1"], chroma_min) < fracao]
    return reais, legenda


# ---------------------------------------------------------------------------
# OCR (RapidOCR/ONNX, local): texto de verdade na imagem
# Regressao Douma (01/10/2026): logo Crunchyroll, legenda de 1 palavra ("DESTROY") e cartela
# do filme passaram pela heuristica de bordas. O OCR le o texto; a POSICAO repetida no tempo
# separa marca (logo/copyright, sempre no mesmo lugar) de texto passageiro (legenda/cartela).
# ---------------------------------------------------------------------------

OCR_W, OCR_H = 960, 540
_OCR = None


def _motor_ocr():
    global _OCR
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:   # porteiro nao roda pela metade: sem OCR, reprova alto
            raise RuntimeError("fonte-limpa precisa do OCR: pip install -r requerimentos.txt "
                               "(rapidocr_onnxruntime)") from e
        _OCR = RapidOCR()
    return _OCR


def caixas_ocr(resultado, c: dict | None = None) -> list[dict]:
    """Saida crua do RapidOCR -> caixas normalizadas (0..1) com texto confiavel.
    Ignora confianca baixa e texto sem 3 caracteres latinos/digitos (kanji de cenario,
    simbolo solto): o canal so quer limpar texto em ingles/marca de canal."""
    c = c or cfg()
    out = []
    for box, txt, conf in resultado or []:
        alnum = sum(ch.isascii() and ch.isalnum() for ch in str(txt))
        if float(conf) < float(c["ocr_conf_min"]) or alnum < 3:
            continue
        xs = [float(p[0]) / OCR_W for p in box]
        ys = [float(p[1]) / OCR_H for p in box]
        out.append({"x": max(0.0, min(xs)), "y": max(0.0, min(ys)),
                    "w": min(1.0, max(xs)) - max(0.0, min(xs)), "h": min(1.0, max(ys)) - max(0.0, min(ys)),
                    "texto": str(txt), "conf": round(float(conf), 3)})
    return out


def _iou(a: dict, b: dict) -> float:
    ix = max(0.0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0.0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    uniao = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / uniao if uniao > 0 else 0.0


def _mesmo_texto(a: str, b: str) -> bool:
    """OCR oscila letra a letra ('Gotege'/'Gotoge'); compara so letras/digitos."""
    from difflib import SequenceMatcher
    na = "".join(ch for ch in a.lower() if ch.isalnum())
    nb = "".join(ch for ch in b.lower() if ch.isalnum())
    return bool(na and nb) and SequenceMatcher(None, na, nb).ratio() >= 0.7


def no_recorte(b: dict, e: dict | None) -> dict | None:
    """Caixa do quadro original -> coordenadas depois do recorte `e` (None = saiu do quadro)."""
    if not e:
        return dict(b)
    s = float(e["s"])
    x0, y0 = (b["x"] - e["x"]) / s, (b["y"] - e["y"]) / s
    x1, y1 = x0 + b["w"] / s, y0 + b["h"] / s
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
    if x1 - x0 <= 0.002 or y1 - y0 <= 0.002:
        return None
    return {**b, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def agrupar_ocr(amostras: list[tuple[float, list[dict]]], dur: float, c: dict | None = None) -> dict:
    """amostras = [(t, caixas_ocr)] -> {"marcas": [...], "texto_linha": [(t, 0|1)]}.

    Marca = MESMO texto no MESMO lugar (IoU >= 0.5) em >= `ocr_marca_min_s` segundos de amostras
    (logo do streaming, copyright, @ do canal). Marca que cobre >= `ocr_marca_todo` do clipe vai
    para a limpeza do clipe todo (`todo=True`); senao e marca de trecho (t0..t1, delogo so ali).
    Todo o resto (legenda, cartela, titulo) e TEXTO: o instante fica com 1 na linha."""
    c = c or cfg()
    passo = (amostras[1][0] - amostras[0][0]) if len(amostras) > 1 else 1.0
    grupos: list[dict] = []
    for t, caixas in amostras:
        for b in caixas:
            for g in grupos:
                # mesmo lugar E mesmo texto: linhas de legenda diferentes no mesmo ponto nao viram "marca"
                if _iou(g["caixa"], b) >= 0.5 and _mesmo_texto(g["caixa"]["texto"], b["texto"]):
                    g["ts"].append(t)
                    break
            else:
                grupos.append({"caixa": dict(b), "ts": [t]})
    marcas, chaves_marca = [], []
    longos = [g for g in grupos if len(g["ts"]) * passo >= float(c["ocr_marca_min_s"])]
    for g in longos:
        cobre_g = len(g["ts"]) * passo / max(passo, dur)
        if cobre_g < float(c["ocr_marca_todo"]):
            # TELA DE TEXTO (cartela final "Watch Full Episodes / Continue Watching", creditos):
            # varios textos parados ao mesmo tempo = cartela, nao logo -> vira texto (cena poluida)
            ts = set(g["ts"])
            juntos = sum(1 for o in longos if o is not g and len(ts & set(o["ts"])) >= 0.5 * len(ts)
                         and len(o["ts"]) * passo / max(passo, dur) < float(c["ocr_marca_todo"]))
            if juntos >= 2:
                continue
        t0, t1 = min(g["ts"]), max(g["ts"]) + passo
        cobre = len(g["ts"]) * passo / max(passo, dur)
        b = g["caixa"]
        marcas.append({"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "texto": b["texto"],
                       "t0": round(t0, 2), "t1": round(min(dur, t1), 2),
                       "todo": cobre >= float(c["ocr_marca_todo"]),
                       "posicao": "ocr", "persistencia": round(cobre, 3)})
        chaves_marca.append(b)
    linha = []
    for t, caixas in amostras:
        resto = [b for b in caixas if not any(_iou(m, b) >= 0.5 for m in chaves_marca)]
        linha.append((round(t, 2), 1.0 if resto else 0.0))
    return {"marcas": marcas, "texto_linha": linha}


def ocr_do_clipe(video: Path, fps: float, cache: Path | None = None, c: dict | None = None) -> list:
    """[(t, caixas_ocr)] a `fps`. Cache por nome+tamanho+mtime (o original nao muda)."""
    c = c or cfg()
    video = Path(video)
    st = video.stat()
    chave = {"nome": video.name, "tam": st.st_size, "mtime": int(st.st_mtime), "fps": fps,
             "conf": c["ocr_conf_min"]}
    if cache is not None and cache.is_file():
        dados = json.loads(cache.read_text(encoding="utf-8"))
        if dados.get("chave") == chave:
            return [(t, cx) for t, cx in dados["amostras"]]
    motor = _motor_ocr()
    amostras = []
    for i, q in enumerate(_quadros(video, fps, OCR_W, OCR_H)):
        res, _ = motor(q[:, :, ::-1].copy())          # RapidOCR espera BGR
        amostras.append((round(i / fps, 2), caixas_ocr(res, c)))
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"chave": chave, "amostras": amostras}, ensure_ascii=False), encoding="utf-8")
    return amostras


def juntar_caixas(*listas: list[dict]) -> list[dict]:
    """Une caixas de detectores diferentes sem duplicar (IoU >= 0.3 = mesma marca; fica a maior)."""
    out: list[dict] = []
    for b in sorted((b for l in listas for b in l), key=lambda b: -(b["w"] * b["h"])):
        if not any(_iou(a, b) >= 0.3 for a in out):
            out.append(b)
    return out


def mesclar_linha(base: list[tuple[float, float]], ocr: list[tuple[float, float]],
                  raio: float) -> list[tuple[float, float]]:
    """Score de legenda = max(heuristica, OCR mais proximo a <= raio s). Sem amostras de OCR,
    devolve a base; sem base, devolve o OCR."""
    if not ocr:
        return list(base)
    if not base:
        return list(ocr)
    ts = np.array([t for t, _s in ocr])
    vs = np.array([s for _t, s in ocr])
    out = []
    for t, s in base:
        k = int(np.argmin(np.abs(ts - t)))
        out.append((t, max(float(s), float(vs[k])) if abs(ts[k] - t) <= raio else float(s)))
    return out


def marcar_trechos(linha: list[tuple[float, float]], trechos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Score 1.0 em todo instante dentro de algum trecho (texto residual = cena poluida)."""
    if not trechos:
        return list(linha)
    return [(t, 1.0 if any(a <= t <= b for a, b in trechos) else s) for t, s in linha]


def plano_limpeza(caixas: list[dict], zoom_max: float) -> dict:
    """Recorte que esconde o MAXIMO de area de marca dentro do zoom_max; o que sobrar leva
    delogo. Douma/Crunchyroll: logo grande no canto de cima + copyright embaixo nao cabiam
    juntos em 1,18x; recortar o logo (1,12x) e delogo so na linha fina do copyright."""
    from itertools import combinations
    melhor = {"recorte": None, "escondidas": [], "delogo": list(caixas), "area": 0.0}
    for k in range(len(caixas), 0, -1):
        for sub in combinations(caixas, k):
            e = enquadramento_limpo(list(sub), zoom_max)
            if e is None:
                continue
            area = sum(b["w"] * b["h"] for b in sub)
            if area > melhor["area"] + 1e-9 or (abs(area - melhor["area"]) <= 1e-9 and melhor["recorte"]
                                                 and e["zoom"] < melhor["recorte"]["zoom"]):
                melhor = {"recorte": e, "escondidas": list(sub),
                          "delogo": [b for b in caixas if not any(b is s for s in sub)], "area": area}
    return melhor


def chroma_no_quadro(q: np.ndarray) -> float:
    """Fracao do quadro que e fundo de CHROMA KEY (verde puro saturado e uniforme)."""
    import cv2
    hsv = cv2.cvtColor(q, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1], hsv[..., 2]
    verde = (h >= 45) & (h <= 80) & (s >= 140) & (v >= 80)          # OpenCV: H 0..180
    frac = float(verde.mean())
    if frac < 0.2:
        return 0.0
    uniforme = float(np.std(h[verde])) < 6.0                        # tela verde e lisa
    return round(frac if uniforme else 0.0, 3)


def detectar_marca(video: Path, c: dict | None = None) -> list[dict]:
    c = c or cfg()
    dur = _duracao(video)
    if dur <= 0:
        return []
    fps = max(0.2, min(4.0, float(c["amostras_marca"]) / dur))
    quadros = list(_quadros(video, fps))
    return caixas_persistentes(quadros, c)


# ---------------------------------------------------------------------------
# Legenda queimada
# ---------------------------------------------------------------------------

def _score_texto(faixa: np.ndarray) -> float:
    """Quanto a faixa parece TEXTO de legenda: glifos claros com contorno escuro, alinhados."""
    import cv2
    g = cv2.cvtColor(faixa, cv2.COLOR_RGB2GRAY)
    claro = g > 200
    escuro = g < 60
    # contorno: pixel claro com vizinho escuro a 2 px (texto branco com borda preta)
    vizinho_escuro = cv2.dilate(escuro.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    contorno = (claro & vizinho_escuro).astype(np.uint8)
    if contorno.sum() < 25:
        return 0.0
    # glifos: componentes pequenos (letras), muitos, em poucas linhas horizontais
    n, _rot, stats, cent = cv2.connectedComponentsWithStats(contorno, 8)
    letras = [(stats[k], cent[k]) for k in range(1, n)
              if 3 <= stats[k][3] <= faixa.shape[0] * 0.7 and stats[k][2] <= faixa.shape[1] * 0.12
              and stats[k][4] >= 4]
    if len(letras) < 6:
        return 0.0
    ys = np.array([c[1] for _s, c in letras])
    xs = np.array([c[0] for _s, c in letras])
    alinhado = float((np.abs(ys - np.median(ys)) < faixa.shape[0] * 0.18).mean())
    centralizado = 1.0 - min(1.0, abs(float(xs.mean()) - faixa.shape[1] / 2) / (faixa.shape[1] / 2))
    densidade = min(1.0, len(letras) / 18.0)
    return round(0.45 * alinhado + 0.25 * centralizado + 0.30 * densidade, 3)


def legenda_no_quadro(q: np.ndarray) -> float:
    """Score 0..1 de legenda queimada: faixa de baixo com texto e faixa de cima sem."""
    baixo = q[int(H * 0.70):int(H * 0.96)]
    cima = q[int(H * 0.04):int(H * 0.30)]
    s_baixo, s_cima = _score_texto(baixo), _score_texto(cima)
    return round(max(0.0, s_baixo - 0.5 * s_cima), 3)


def linha_do_tempo_legenda(video: Path, c: dict | None = None) -> list[tuple[float, float]]:
    return varrer(video, c)["legenda"]


def varrer(video: Path, c: dict | None = None) -> dict:
    """Uma passada a legenda_fps: legenda queimada, chroma verde e marcas por trecho."""
    c = c or cfg()
    fps = float(c["legenda_fps"]) * 2          # 4 fps: marca por trecho precisa de mais quadros
    leg, chroma, quadros = [], [], []
    for i, q in enumerate(_quadros(video, fps)):
        t = round(i / fps, 2)
        quadros.append(q)
        if i % 2 == 0:
            leg.append((t, legenda_no_quadro(q)))
            chroma.append((t, chroma_no_quadro(q)))
    return {"legenda": leg, "chroma": chroma, "marcas_trecho": marcas_por_trecho(quadros, fps, c)}


def fracao_legenda(linha: list[tuple[float, float]], inicio: float, fim: float, score_min: float) -> float:
    dentro = [s for t, s in linha if inicio <= t < fim]
    return float(np.mean([s >= score_min for s in dentro])) if dentro else 0.0


# ---------------------------------------------------------------------------
# Limpeza e relatorio
# ---------------------------------------------------------------------------

def _delogo(b: dict, margem: int = 8, enable: str | None = None) -> str:
    x, y = max(1, int(b["x"] * 1920) - margem), max(1, int(b["y"] * 1080) - margem)
    w = max(4, min(1918 - x, int(b["w"] * 1920) + 2 * margem))
    h = max(4, min(1078 - y, int(b["h"] * 1080) + 2 * margem))
    f = f"delogo=x={x}:y={y}:w={w}:h={h}"
    return f + (f":enable='{enable}'" if enable else "")


def limpar_clipe(video: Path, caixas: list[dict], c: dict | None = None) -> dict:
    """Esconde a marca: zoom-in se couber, senao delogo. Original em _originais/."""
    import render_dispatch as rd
    c = c or cfg()
    video = Path(video)
    orig_dir = video.parent / "_originais"
    orig_dir.mkdir(exist_ok=True)
    original = orig_dir / video.name
    if not original.exists():
        shutil.copy2(video, original)
    plano = plano_limpeza(caixas, float(c["zoom_max"]))
    # delogo primeiro (coordenadas do quadro 1920x1080 original), recorte depois
    partes = ["scale=1920:1080:flags=lanczos,setsar=1"] + [_delogo(b) for b in plano["delogo"]]
    acoes = []
    e = plano["recorte"]
    if e is not None:
        partes.append(f"crop=iw*{e['s']}:ih*{e['s']}:iw*{e['x']}:ih*{e['y']},"
                      f"scale=1920:1080:flags=lanczos,setsar=1")
        acoes.append(f"recorte {e['zoom']}x em ({e['x']:.2f},{e['y']:.2f})")
    if plano["delogo"]:
        acoes.append(f"delogo em {len(plano['delogo'])} caixa(s)")
    vf = ",".join(partes)
    acao = " + ".join(acoes)
    tmp = video.with_name(video.stem + ".limpo.mp4")
    rd.encode(str(tmp), ["-i", str(original)], filtro_v=vf + ",format=yuv420p", mapa=["-map", "0:v:0"],
              args_audio=["-an"], silencioso=True)
    tmp.replace(video)
    return {"acao": acao, "original": str(original), "recorte": e,
            "delogo": [{k: b[k] for k in ("x", "y", "w", "h")} for b in plano["delogo"]]}


def limpar_trechos(video: Path, marcas: list[dict]) -> dict:
    """delogo so nos intervalos em que cada marca aparece (enable='between(t,a,b)')."""
    import render_dispatch as rd
    video = Path(video)
    orig_dir = video.parent / "_originais"
    orig_dir.mkdir(exist_ok=True)
    original = orig_dir / video.name
    if not original.exists():
        shutil.copy2(video, original)
    fonte = video          # estado atual (ja recortado se havia marca no clipe todo)
    partes = ["scale=1920:1080:flags=lanczos,setsar=1"]
    for b in marcas:
        partes.append(_delogo(b, enable=f"between(t,{max(0.0, b['t0'] - 0.5):.2f},{b['t1'] + 0.5:.2f})"))
    tmp = video.with_name(video.stem + ".trechos.mp4")
    rd.encode(str(tmp), ["-i", str(fonte)], filtro_v=",".join(partes) + ",format=yuv420p",
              mapa=["-map", "0:v:0"], args_audio=["-an"], silencioso=True)
    tmp.replace(video)
    return {"acao": f"delogo em {len(marcas)} trecho(s)", "trechos": [[m["t0"], m["t1"]] for m in marcas]}


def _aplicar_excecao(d: Path, clipe: str, pendente: list[dict]) -> tuple[list[dict], list[dict]]:
    """Remove de `pendente` SO as caixas listadas em qa/excecao_fonte_limpa.json para este
    clipe (mesmo tempo e posicao, com tolerancia). Nao muda limiar nem o porteiro; a decisao
    de exceção é humana e fica registrada no arquivo (ver decisoes/002)."""
    arq = Path(d) / "qa" / "excecao_fonte_limpa.json"
    if not arq.is_file() or not pendente:
        return pendente, []
    reg = json.loads(arq.read_text(encoding="utf-8"))
    if reg.get("clipe") != clipe:
        return pendente, []
    permitidas = reg.get("caixas_falso_positivo") or []
    tol_t, tol_p = 0.6, 0.02
    sobra, usadas = [], []
    for m in pendente:
        ok = None
        for e in permitidas:
            if (abs(float(m["t0"]) - e["t0"]) <= tol_t and abs(float(m["t1"]) - e["t1"]) <= tol_t
                    and abs(float(m["x"]) - e["x"]) <= tol_p and abs(float(m["y"]) - e["y"]) <= tol_p):
                ok = e
                break
        if ok is None:
            sobra.append(m)
        else:
            usadas.append({"t0": m["t0"], "t1": m["t1"], "x": m["x"], "y": m["y"],
                           "motivo": reg.get("tipo", "excecao"), "registro": str(arq.name)})
    return sobra, usadas


def auditar_projeto(d: Path, corrigir: bool = False) -> dict:
    """Varre clips_raw/*.mp4: marca d'agua (e corrige) + linha do tempo de legenda queimada."""
    d = Path(d)
    c = cfg()
    clips = sorted(p for p in (d / "clips_raw").glob("*.mp4") if not p.name.startswith("vx_"))
    rel = {"clipes": {}, "aprovado": True, "motivos": []}
    for clip in clips:
        item: dict = {}
        original = clip.parent / "_originais" / clip.name
        if corrigir and original.is_file():
            # idempotente: toda correcao parte do original (sem delogo em cima de delogo e
            # limpeza antiga com regra velha e desfeita sozinha)
            shutil.copy2(original, clip)
            item["restaurado_do_original"] = True
        dur = _duracao(clip)
        # OCR no estado original do clipe: marca de texto (logo/copyright) e texto passageiro
        ocr = agrupar_ocr(ocr_do_clipe(clip, float(c["ocr_fps"]), d / "qa" / "fonte_ocr" / f"{clip.stem}.json", c),
                          dur, c)
        item["marca_ocr"] = ocr["marcas"]
        caixas = juntar_caixas(detectar_marca(clip, c), [m for m in ocr["marcas"] if m["todo"]])
        item["marca"] = caixas
        recorte = None
        if caixas and corrigir:
            item["limpeza"] = limpar_clipe(clip, caixas, c)
            recorte = item["limpeza"]["recorte"]
            item["marca_depois"] = detectar_marca(clip, c)
        v = varrer(clip, c)
        v["marcas_trecho"], item["legenda_parada"] = separar_trechos(v, c)
        # marca de texto so num trecho (OCR), levada para as coordenadas do clipe ja recortado
        trecho_ocr = [no_recorte(m, recorte) for m in ocr["marcas"] if not m["todo"]]
        v["marcas_trecho"] = juntar_caixas(v["marcas_trecho"], [m for m in trecho_ocr if m])
        # marca d'agua de TRECHO (so parte do clipe): delogo so naquele intervalo
        if v["marcas_trecho"] and corrigir:
            item["limpeza_trechos"] = limpar_trechos(clip, v["marcas_trecho"])
            v = varrer(clip, c)
            v["marcas_trecho"], _ = separar_trechos(v, c)
        if corrigir and (caixas or item.get("limpeza_trechos")):
            # prova real: OCR de novo no clipe limpo; marca que o OCR ainda le reprova
            depois = agrupar_ocr(ocr_do_clipe(clip, float(c["ocr_fps_verificacao"]), None, c), dur, c)
            item["marca_ocr_depois"] = depois["marcas"]
            item["marca_depois"] = juntar_caixas(item.get("marca_depois") or [],
                                                 [m for m in depois["marcas"] if m["todo"]])
            # texto de TRECHO que o OCR ainda le depois da limpeza (cartela final cortada pelo
            # recorte, marca que mudou de lugar): o trecho vira poluido e sai da escolha
            item["texto_residual"] = [[m["t0"], m["t1"], m["texto"]] for m in depois["marcas"] if not m["todo"]]
        item["marcas_trecho"] = v["marcas_trecho"]
        # legenda/cartela/titulo lidos pelo OCR entram na linha do tempo de legenda (cena poluida)
        linha = mesclar_linha(v["legenda"], ocr["texto_linha"], 0.5 / float(c["ocr_fps"]) + 0.01)
        linha = marcar_trechos(linha, [(a, b) for a, b, _t in item.get("texto_residual") or []])
        # linha so do OCR (texto LIDO de verdade): 1 amostra dentro da cena ja a torna poluida
        item["texto_ocr_linha"] = marcar_trechos(ocr["texto_linha"],
                                                 [(a, b) for a, b, _t in item.get("texto_residual") or []])
        item["texto_ocr_fracao"] = round(float(np.mean([s for _t, s in ocr["texto_linha"]])) if ocr["texto_linha"] else 0.0, 3)
        frac = fracao_legenda(linha, 0.0, 1e9, float(c["legenda_score_min"]))
        item["legenda_fracao"] = round(frac, 3)
        item["legenda_linha"] = linha
        item["chroma_linha"] = v["chroma"]
        item["chroma_fracao"] = round(fracao_legenda(v["chroma"], 0.0, 1e9, float(c.get("chroma_min", 0.25))), 3)
        pendente = (item.get("marca_depois", caixas) if corrigir else caixas) + \
            [m for m in v["marcas_trecho"] if m["t1"] - m["t0"] >= 1.5]
        # excecao humana registrada para ESTE clipe (qa/excecao_fonte_limpa.json): so as
        # caixas listadas, com a mesma posicao e tempo. Qualquer outra caixa continua reprovando.
        pendente, excecoes = _aplicar_excecao(d, clip.name, pendente)
        if excecoes:
            item["excecoes_aplicadas"] = excecoes
        if pendente:
            rel["aprovado"] = False
            rel["motivos"].append(f"{clip.name}: marca d'agua/logo em {len(pendente)} caixa(s)")
        if frac > float(c["max_poluido_clipe"]):
            # aviso (nao reprova): as cenas com texto ja saem da escolha; so sobra pouco material
            rel.setdefault("avisos", []).append(f"{clip.name}: {frac:.0%} com texto queimado (sobra pouco material)")
        rel["clipes"][clip.name] = item
    qa = d / "qa"
    qa.mkdir(exist_ok=True)
    (qa / "fonte_limpa.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    (qa / "fonte_limpa.md").write_text(markdown(rel, d.name), encoding="utf-8")
    return rel


def cenas_poluidas(d: Path) -> dict[str, list[tuple[float, float]]]:
    """clip -> linha do tempo de legenda (para o catalogo marcar cenas poluidas)."""
    p = Path(d) / "qa" / "fonte_limpa.json"
    if not p.is_file():
        return {}
    dados = json.loads(p.read_text(encoding="utf-8"))
    return {nome: [tuple(x) for x in item.get("legenda_linha") or []] for nome, item in dados["clipes"].items()}


def linhas_texto_ocr(d: Path) -> dict[str, list[tuple[float, float]]]:
    """clip -> linha do tempo de texto lido pelo OCR (legenda/cartela/titulo; marcas fora)."""
    p = Path(d) / "qa" / "fonte_limpa.json"
    if not p.is_file():
        return {}
    dados = json.loads(p.read_text(encoding="utf-8"))
    return {nome: [tuple(x) for x in item.get("texto_ocr_linha") or []] for nome, item in dados["clipes"].items()}


def texto_na_janela(linha: list[tuple[float, float]], inicio: float, fim: float, folga: float = 0.25) -> int:
    """Quantas amostras do OCR leram texto dentro de [inicio-folga, fim+folga]."""
    return sum(1 for t, s in linha if s > 0 and inicio - folga <= t <= fim + folga)


# ---------------------------------------------------------------------------
# Prova final no RENDER: texto que nao e nosso (letra/titulos/marca do canal) reprova
# ---------------------------------------------------------------------------

MARCAS_TERCEIROS = ("crunchyroll", "netflix", "aniplex", "funimation", "shueisha", "ufotable",
                    "watchon", "watchfull", "episodes", "continuewatching", "subscribe", "description")


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if ch.isascii() and ch.isalnum())


def corpus_permitido(d: Path) -> str:
    """Todo texto que o NOSSO video escreve: letra, titulo, nome, marca, handle, CTA."""
    d = Path(d)
    partes = []
    for nome in ("LETRA.txt", "LETRA_LINHAS.txt"):
        p = d / nome
        if p.is_file():
            partes.append(p.read_text(encoding="utf-8-sig"))
    try:
        man = json.loads((d / "projeto.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        man = {}

    def coletar(v):
        if isinstance(v, str):
            partes.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                coletar(x)
        elif isinstance(v, list):
            for x in v:
                coletar(x)
    coletar(man)
    # textos fixos que os nossos cards escrevem (titulos_pipeline: abertura e end card)
    partes += ["VX RAPS APRESENTA", "@VXRaps", "INSCREVA-SE NO CANAL"]
    return "|".join(_norm(p) for p in partes)


def texto_e_nosso(texto: str, corpus: str) -> bool:
    from difflib import SequenceMatcher
    n = _norm(texto)
    if len(n) < 5:
        return True                                  # fragmento de efeito (eco/glitch)
    if n in corpus:
        return True
    m = SequenceMatcher(None, n, corpus, autojunk=False).find_longest_match(0, len(n), 0, len(corpus))
    if m.size < 3:
        return False
    # alinha pelo maior trecho comum e compara a janela do mesmo tamanho (OCR troca letra:
    # 'GLICINIA' -> 'CLICINIA', junta palavras, perde acento)
    ini = max(0, m.b - m.a)
    janela = corpus[ini:ini + len(n) + 2]
    return SequenceMatcher(None, n, janela, autojunk=False).ratio() >= 0.75


def intrusos_render(amostras: list, corpus: str) -> list[dict]:
    """Texto de terceiros no render. Marca conhecida reprova na hora; texto estranho precisa
    aparecer em 2 amostras em ate 1,5 s (1 leitura solta = ruido do OCR)."""
    estranhos = []
    for t, caixas in amostras:
        for b in caixas:
            if any(m in _norm(b["texto"]) for m in MARCAS_TERCEIROS):
                estranhos.append({"t": t, "texto": b["texto"], "marca": True})
            elif not texto_e_nosso(b["texto"], corpus):
                estranhos.append({"t": t, "texto": b["texto"], "marca": False})
    out = []
    for e in estranhos:
        if e["marca"] or any(o is not e and abs(o["t"] - e["t"]) <= 1.5 for o in estranhos):
            out.append(e)
    return out


def auditar_texto_render(video: Path, d: Path, fps: float = 2.0) -> dict:
    """OCR no corpo renderizado. Porteiro final do qa-master (prints do usuario 01/10/2026)."""
    amostras = ocr_do_clipe(Path(video), fps, None)
    intrusos = intrusos_render(amostras, corpus_permitido(d))
    return {"video": str(video), "fps": fps, "amostras": len(amostras), "intrusos": intrusos,
            "aprovado": not intrusos}


def linhas_chroma(d: Path) -> dict[str, list[tuple[float, float]]]:
    """clip -> linha do tempo de chroma verde (para o catalogo marcar cenas de tela verde)."""
    p = Path(d) / "qa" / "fonte_limpa.json"
    if not p.is_file():
        return {}
    dados = json.loads(p.read_text(encoding="utf-8"))
    return {nome: [tuple(x) for x in item.get("chroma_linha") or []] for nome, item in dados["clipes"].items()}


def markdown(rel: dict, slug: str) -> str:
    L = [f"# Fonte limpa — {slug}", "", "Marca d'água/logo e legenda queimada nos clipes de `clips_raw/`.", "",
         "| clipe | marca d'água (clipe todo) | limpeza | marca por trecho | legenda queimada | legenda parada | tela verde |",
         "|---|---|---|---|---|---|---|"]
    for nome, it in rel["clipes"].items():
        marca = ", ".join(f"{b['posicao']} ({b['x']:.2f},{b['y']:.2f} {b['w']:.2f}x{b['h']:.2f})"
                          + (f" “{b['texto'][:24]}”" if b.get("texto") else "") for b in it["marca"]) or "—"
        limp = (it.get("limpeza") or {}).get("acao", "—")
        depois = it.get("marca_depois")
        if depois is not None:
            limp += " ✅" if not depois else f" ⚠️ restou {len(depois)}"
        lt = it.get("limpeza_trechos")
        trecho = lt["acao"] if lt else "—"
        if it.get("marcas_trecho"):
            trecho += f" ⚠️ restou {len(it['marcas_trecho'])}"
        parada = len(it.get("legenda_parada") or [])
        if it.get("limpeza_trechos") and it.get("marca_ocr"):
            textos = sorted({m["texto"][:20] for m in it["marca_ocr"] if not m.get("todo")})
            if textos:
                trecho += " (" + ", ".join(textos) + ")"
        L.append(f"| {nome} | {marca} | {limp} | {trecho} | {it['legenda_fracao']:.0%} | "
                 f"{parada or '—'} | {it.get('chroma_fracao', 0):.0%} |")
    L += ["", "Legenda parada = caixa estática na faixa da legenda num trecho com legenda queimada: não leva "
          "delogo nem reprova (a cena já é `poluida`). Tela verde vira take `vx_chroma` na etapa `chroma-auto`."]
    L += [f"- aviso: {a}" for a in rel.get("avisos") or []]
    L += ["", "**APROVADO**" if rel["aprovado"] else "**REPROVADO**: " + "; ".join(rel["motivos"])]
    return "\n".join(L)
