#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analisar_referencia.py — raio-x de um video de referencia (concorrente/inspiracao).

Mede o que da para medir sem "assistir": cortes e ritmo, sincronia dos cortes com a
batida, flashes, telas pretas, zoom/tremor de camera, letterbox, cor por trecho,
loudness/BPM do audio e, com OpenCLIP (GPU), o TIPO de quadro (texto grande na tela,
legenda, manga, glitch, close, luta...). Gera folhas de contato para o humano ver.

Uso: estudio.py referencia <url|arquivo.mp4> [--comparar outro.mp4]
Saida: referencias/<id>/analise.json, analise.md, folha_XX.png (quadro a cada 2 s).
O video baixado fica so local, para estudo; nao e publicado nem reaproveitado como footage.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

import _vx  # noqa: F401
RAIZ = Path(__file__).resolve().parents[1]
REFS = RAIZ / "referencias"

FPS_CORTE = 24           # amostragem para cortes/flash/movimento
FPS_CLIP = 2             # amostragem para classificacao e folhas
LIMIAR_CORTE = 0.42      # distancia de histograma HSV (Bhattacharyya) para contar corte
JANELA_TRECHO = 10.0     # tabela por trecho de N s

# Tipos de quadro (zero-shot). O texto do prompt e o que o CLIP compara.
ROTULOS = [
    ("texto_grande", "large bold stylized typography text over an anime scene, motion graphics title"),
    ("legenda", "an anime screenshot with subtitles text at the bottom of the screen"),
    ("anime_limpo", "a clean anime screenshot with no text"),
    ("close_rosto", "extreme close-up of an anime character face and eyes"),
    ("luta", "anime fight scene with explosion, energy blast and impact"),
    ("manga", "black and white manga panel page"),
    ("glitch", "glitch effect with rgb split and digital distortion"),
    ("tela_preta", "a black screen"),
    ("flash_branco", "a white flash overexposed frame"),
    ("kanji", "large japanese kanji characters on screen"),
    ("letterbox", "cinematic frame with black bars at top and bottom"),
    ("speedlines", "manga speed lines radial motion effect"),
    ("brilho_glow", "neon glow light effect with lens flare"),
    ("logo_card", "title card with logo and channel name"),
]


# ---------------------------------------------------------------------------
# Download e decodificacao
# ---------------------------------------------------------------------------

def id_de(fonte: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", fonte)
    return m.group(1) if m else Path(fonte).stem


def baixar(url: str, destino: Path) -> Path:
    import yt_dlp
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / "video.mp4"
    if alvo.is_file() and alvo.stat().st_size:
        return alvo
    opts = {"quiet": True, "outtmpl": str(destino / "video.%(ext)s"),
            "format": "bv*[height<=1080]+ba/b[height<=1080]", "merge_output_format": "mp4",
            "ffmpeg_location": str(RAIZ / "ferramentas" / "bin"), "writeinfojson": True}
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    return alvo


def _quadros(video: Path, fps: int, w: int, h: int):
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


def duracao(video: Path) -> float:
    import render_dispatch as rd
    r = subprocess.run([rd.ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(video)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


# ---------------------------------------------------------------------------
# Medidas puras (testadas)
# ---------------------------------------------------------------------------

def detectar_cortes(distancias: list[float], fps: float, limiar: float = LIMIAR_CORTE,
                    min_intervalo: float = 0.12) -> list[float]:
    """Tempos de corte: pico de distancia acima do limiar e maior que os vizinhos."""
    cortes, ultimo = [], -9.0
    for i in range(1, len(distancias) - 1):
        d = distancias[i]
        if d >= limiar and d >= distancias[i - 1] and d >= distancias[i + 1]:
            t = i / fps
            if t - ultimo >= min_intervalo:
                cortes.append(round(t, 3))
                ultimo = t
    return cortes


def detectar_flashes(luma: list[float], fps: float, salto: float = 55.0, max_dur: float = 0.25) -> list[float]:
    """Flash: luma sobe `salto` de uma vez e volta em ate `max_dur` s."""
    out, n, i = [], len(luma), 1
    janela = max(1, int(round(max_dur * fps)))
    while i < n:
        if luma[i] - luma[i - 1] >= salto:
            base = luma[i - 1]
            volta = next((j for j in range(i + 1, min(n, i + janela + 1)) if luma[j] - base < salto * 0.5), None)
            if volta is not None:
                out.append(round(i / fps, 3))
                i = volta
        i += 1
    return out


def sincronia_com_batida(cortes: list[float], batidas: list[float]) -> dict:
    """% de cortes a <= 50/100 ms da batida mais proxima."""
    if not cortes or not batidas:
        return {"cortes": len(cortes), "ate_50ms": 0.0, "ate_100ms": 0.0, "mediana_ms": None}
    b = np.asarray(sorted(batidas))
    dist = []
    for c in cortes:
        k = int(np.searchsorted(b, c))
        cand = [abs(c - b[j]) for j in (k - 1, k) if 0 <= j < len(b)]
        dist.append(min(cand))
    dist = np.asarray(dist)
    return {"cortes": len(cortes), "ate_50ms": round(float((dist <= 0.05).mean()), 3),
            "ate_100ms": round(float((dist <= 0.10).mean()), 3),
            "mediana_ms": round(float(np.median(dist) * 1000), 1)}


def estatisticas_planos(cortes: list[float], dur: float) -> dict:
    marcos = [0.0] + list(cortes) + [dur]
    planos = np.diff(marcos)
    planos = planos[planos > 0]
    if not len(planos):
        return {}
    return {"planos": int(len(planos)), "cortes_por_minuto": round(len(cortes) / max(1e-6, dur) * 60, 1),
            "plano_medio_s": round(float(planos.mean()), 2), "plano_mediano_s": round(float(np.median(planos)), 2),
            "plano_min_s": round(float(planos.min()), 2), "plano_max_s": round(float(planos.max()), 2),
            "planos_menores_0_5s": round(float((planos < 0.5).mean()), 3)}


def nome_cor(h: float, s: float, v: float) -> str:
    if v < 0.18:
        return "escuro"
    if s < 0.18:
        return "cinza/branco" if v > 0.6 else "cinza"
    nomes = [(15, "vermelho"), (40, "laranja"), (65, "amarelo"), (160, "verde"), (200, "ciano"),
             (255, "azul"), (290, "roxo"), (330, "magenta"), (360, "vermelho")]
    graus = h * 360
    return next(n for lim, n in nomes if graus < lim)


# ---------------------------------------------------------------------------
# Passadas
# ---------------------------------------------------------------------------

def passada_movimento(video: Path) -> dict:
    """24 fps @160x90: cortes, flashes, preto, letterbox, zoom e tremor."""
    import cv2
    dist, luma, letter, preto, desloc, zoom = [], [], [], [], [], []
    ant_hist = ant_g = None
    for arr in _quadros(video, FPS_CORTE, 160, 90):
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY).astype(np.float32)
        luma.append(float(g.mean()))
        preto.append(g.mean() < 14)
        topo, baixo, meio = g[:11].mean(), g[-11:].mean(), g[20:70].mean()
        letter.append(topo < 10 and baixo < 10 and meio > 28)
        if ant_hist is not None:
            dist.append(float(cv2.compareHist(ant_hist, hist, cv2.HISTCMP_BHATTACHARYYA)))
            (dx, dy), _r = cv2.phaseCorrelate(ant_g, g)
            desloc.append(math.hypot(dx, dy))
            flow = cv2.calcOpticalFlowFarneback(ant_g.astype(np.uint8), g.astype(np.uint8), None,
                                                0.5, 2, 9, 2, 5, 1.1, 0)
            yy, xx = np.mgrid[0:90, 0:160].astype(np.float32)
            rx, ry = xx - 80, yy - 45
            nrm = np.sqrt(rx * rx + ry * ry) + 1e-3
            zoom.append(float(((flow[..., 0] * rx + flow[..., 1] * ry) / nrm).mean()))
        else:
            dist.append(0.0)
            desloc.append(0.0)
            zoom.append(0.0)
        ant_hist, ant_g = hist, g
    return {"dist": dist, "luma": luma, "letter": letter, "preto": preto, "desloc": desloc, "zoom": zoom}


def passada_clip(video: Path, pasta: Path) -> dict:
    """2 fps @448x252: tipo de quadro (OpenCLIP), cor, e folhas de contato (1 quadro/2 s)."""
    import colorsys
    from PIL import Image, ImageDraw
    import torch
    import open_clip
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, _, prep = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k", device=dev)
    modelo.eval()
    tok = open_clip.get_tokenizer("ViT-B-32")
    with torch.no_grad():
        tf = modelo.encode_text(tok([p for _, p in ROTULOS]).to(dev))
        tf = tf / tf.norm(dim=-1, keepdim=True)
    tipos, cores, minis = [], [], []
    lote, idx = [], 0

    def flush():
        if not lote:
            return
        with torch.no_grad():
            im = torch.stack([prep(Image.fromarray(a)) for a in lote]).to(dev)
            f = modelo.encode_image(im)
            f = f / f.norm(dim=-1, keepdim=True)
            pr = (100.0 * f @ tf.T).softmax(dim=-1).cpu().numpy()
        for linha in pr:
            tipos.append({ROTULOS[k][0]: round(float(v), 4) for k, v in enumerate(linha)})
        lote.clear()

    for arr in _quadros(video, FPS_CLIP, 448, 252):
        lote.append(arr)
        a = arr[::6, ::6].reshape(-1, 3).astype(np.float32) / 255
        mx, mn = a.max(1), a.min(1)
        sat = (mx - mn) / np.maximum(mx, 1e-6)
        sel = a[(sat > 0.35) & (mx > 0.3)]
        if len(sel) > 20:
            import motion_lab as ml
            hue = ml.matiz_dominante(sel)
            cores.append(nome_cor(hue, 0.8, 0.8))
        else:
            v = float(a.mean())
            cores.append(nome_cor(0, 0.0, v))
        if idx % (2 * FPS_CLIP) == 0:
            mini = Image.fromarray(arr).resize((240, 135))
            ImageDraw.Draw(mini).text((4, 2), f"{idx // FPS_CLIP // 60}:{idx // FPS_CLIP % 60:02d}", fill=(255, 255, 0))
            minis.append(mini)
        idx += 1
        if len(lote) >= 32:
            flush()
    flush()
    folhas = []
    for k in range(0, len(minis), 40):
        grupo = minis[k:k + 40]
        folha = Image.new("RGB", (240 * 8, 135 * math.ceil(len(grupo) / 8)))
        for j, m in enumerate(grupo):
            folha.paste(m, ((j % 8) * 240, (j // 8) * 135))
        destino = pasta / f"folha_{k // 40 + 1:02d}.png"
        folha.save(destino)
        folhas.append(destino.name)
    return {"tipos": tipos, "cores": cores, "folhas": folhas, "dispositivo": dev}


def passada_audio(video: Path) -> dict:
    import librosa
    import render_dispatch as rd
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        subprocess.run([rd.ffmpeg_bin(), "-v", "error", "-y", "-i", str(video), "-ac", "1", "-ar", "22050",
                        str(wav)], check=True)
        y, sr = librosa.load(str(wav), sr=22050)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    batidas = librosa.frames_to_time(beats, sr=sr).tolist()
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time").tolist()
    rms = librosa.feature.rms(y=y)[0]
    t_rms = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
    r = subprocess.run([rd.ffmpeg_bin(), "-hide_banner", "-i", str(video), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    pico = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return {"bpm": round(float(np.atleast_1d(tempo)[0]), 1), "batidas": batidas, "onsets": onsets,
            "lufs": float(lufs[-1]) if lufs else None, "true_peak": float(pico[-1]) if pico else None,
            "rms": rms.tolist()[::10], "t_rms": t_rms.tolist()[::10]}


# ---------------------------------------------------------------------------
# Fundos e cards graficos (o que aparece atras/ao redor do texto)
# ---------------------------------------------------------------------------

TIPOS_GRAFICOS = ("texto_grande", "logo_card", "kanji", "manga")
ESTILOS_FUNDO = [
    ("cena_anime_escurecida", "a darkened blurred anime scene used as background behind big text"),
    ("cena_anime_nitida", "a sharp colorful anime scene with a character"),
    ("cor_solida", "a flat solid color background"),
    ("degrade", "a smooth color gradient background"),
    ("raios_de_luz", "radial light rays sunburst background"),
    ("fumaca_neblina", "smoke and fog atmospheric background"),
    ("fogo_brasas", "fire flames and embers background"),
    ("particulas", "floating glowing particles and dust background"),
    ("textura_grunge", "grunge distressed texture background with scratches"),
    ("papel_retícula", "paper texture with halftone dots screentone"),
    ("formas_geometricas", "abstract geometric shapes lines and stripes background"),
    ("painel_manga", "black and white manga panels comic page layout"),
    ("glitch_digital", "digital glitch scanlines background"),
    ("tribunal_cenario", "a courtroom interior background illustration"),
    ("ceu_nuvens", "dramatic sky with clouds background"),
    ("energia_aura", "swirling energy aura and lightning background"),
]


def paleta(arr: np.ndarray, k: int = 4) -> list[dict]:
    """k cores dominantes (k-means em amostra) com a fracao de cada uma."""
    import cv2
    px = arr[::4, ::4].reshape(-1, 3).astype(np.float32)
    k = max(1, min(k, len(px)))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _c, rot, centros = cv2.kmeans(px, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    cont = np.bincount(rot.flatten(), minlength=k) / len(rot)
    ordem = np.argsort(-cont)
    return [{"hex": "#%02X%02X%02X" % tuple(int(v) for v in centros[j]), "fracao": round(float(cont[j]), 3)}
            for j in ordem]


def layout_texto(arr: np.ndarray) -> dict:
    """Onde estao as bordas fortes (texto costuma ser a regiao de maior contraste fino)."""
    import cv2
    g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    bordas = cv2.Canny(g, 120, 240).astype(np.float32) / 255
    h, w = bordas.shape
    faixas = {"topo": bordas[: h // 3].mean(), "meio": bordas[h // 3: 2 * h // 3].mean(), "base": bordas[2 * h // 3:].mean()}
    colunas = {"esq": bordas[:, : w // 3].mean(), "centro": bordas[:, w // 3: 2 * w // 3].mean(), "dir": bordas[:, 2 * w // 3:].mean()}
    return {"vertical": max(faixas, key=faixas.get), "horizontal": max(colunas, key=colunas.get),
            "densidade_bordas": round(float(bordas.mean()), 4),
            "area_lisa": round(float((cv2.blur(bordas, (15, 15)) < 0.01).mean()), 3)}


def momentos_graficos(tipos: list[dict], fps: int = FPS_CLIP, limiar: float = 0.35,
                      min_dur: float = 1.0, juntar: float = 0.6) -> list[dict]:
    """Trechos em que um tipo grafico (texto grande/card/kanji/manga) domina o quadro."""
    marcados = []
    for i, t in enumerate(tipos):
        tipo = max(TIPOS_GRAFICOS, key=lambda k: t.get(k, 0))
        if t.get(tipo, 0) >= limiar:
            marcados.append((i / fps, tipo))
    out: list[dict] = []
    for tempo, tipo in marcados:
        if out and tempo - out[-1]["ate"] <= juntar:
            out[-1]["ate"] = tempo + 1 / fps
            out[-1]["tipos"].append(tipo)
        else:
            out.append({"de": tempo, "ate": tempo + 1 / fps, "tipos": [tipo]})
    res = []
    for m in out:
        if m["ate"] - m["de"] >= min_dur:
            res.append({"de": round(m["de"], 2), "ate": round(m["ate"], 2),
                        "tipo": max(set(m["tipos"]), key=m["tipos"].count)})
    return res


def passada_graficos(video: Path, pasta: Path, tipos: list[dict]) -> list[dict]:
    """Para cada momento grafico: quadros-chave, paleta, layout e estilo do fundo (CLIP)."""
    import render_dispatch as rd
    from PIL import Image, ImageDraw
    import torch
    import open_clip
    momentos = momentos_graficos(tipos)
    if not momentos:
        return []
    destino = pasta / "graficos"
    destino.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, _, prep = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k", device=dev)
    modelo.eval()
    tok = open_clip.get_tokenizer("ViT-B-32")
    with torch.no_grad():
        tf = modelo.encode_text(tok([p for _, p in ESTILOS_FUNDO]).to(dev))
        tf = tf / tf.norm(dim=-1, keepdim=True)
    minis = []
    for n, m in enumerate(momentos, 1):
        tempos = [m["de"] + (m["ate"] - m["de"]) * f for f in (0.2, 0.5, 0.85)]
        quadros = []
        for k, t in enumerate(tempos):
            arq = destino / f"g{n:02d}_{k}.png"
            subprocess.run([rd.ffmpeg_bin(), "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=960:540", str(arq)])
            if arq.is_file():
                quadros.append(np.asarray(Image.open(arq).convert("RGB")))
        if not quadros:
            continue
        meio = quadros[len(quadros) // 2]
        with torch.no_grad():
            im = torch.stack([prep(Image.fromarray(q)) for q in quadros]).to(dev)
            f = modelo.encode_image(im)
            f = f / f.norm(dim=-1, keepdim=True)
            pr = (100.0 * f @ tf.T).softmax(dim=-1).mean(0).cpu().numpy()
        top = sorted(((ESTILOS_FUNDO[j][0], float(v)) for j, v in enumerate(pr)), key=lambda kv: -kv[1])[:3]
        movimento = float(np.mean([np.abs(quadros[j + 1].astype(np.float32) - quadros[j]).mean()
                                   for j in range(len(quadros) - 1)])) if len(quadros) > 1 else 0.0
        m.update({"n": n, "duracao": round(m["ate"] - m["de"], 2), "paleta": paleta(meio),
                  "layout": layout_texto(meio), "fundo": [{"estilo": e, "score": round(s, 3)} for e, s in top],
                  "mudanca_visual": round(movimento, 1),
                  "quadros": [f"graficos/g{n:02d}_{k}.png" for k in range(len(quadros))]})
        mini = Image.fromarray(meio).resize((320, 180))
        ImageDraw.Draw(mini).text((4, 2), f"#{n} {int(m['de']) // 60}:{int(m['de']) % 60:02d} {m['tipo']}",
                                  fill=(255, 255, 0))
        minis.append(mini)
    if minis:
        cols = 6
        folha = Image.new("RGB", (320 * cols, 180 * math.ceil(len(minis) / cols)))
        for j, mi in enumerate(minis):
            folha.paste(mi, ((j % cols) * 320, (j // cols) * 180))
        folha.save(destino / "folha_graficos.png")
    return [m for m in momentos if "n" in m]


def markdown_graficos(graf: list[dict]) -> str:
    if not graf:
        return "## Fundos e cards gráficos\n\nNenhum momento gráfico detectado."
    from collections import Counter
    estilos = Counter(g["fundo"][0]["estilo"] for g in graf)
    tot = sum(g["duracao"] for g in graf)
    L = ["## Fundos e cards gráficos", "",
         f"{len(graf)} momentos gráficos, {tot:.0f} s no total. Folha: `graficos/folha_graficos.png`; "
         "3 quadros de cada em `graficos/gNN_k.png`.", "",
         "Fundo mais comum (1º lugar do CLIP): " + ", ".join(f"{e} ({c})" for e, c in estilos.most_common(6)), "",
         "| # | tempo | dur | tipo | fundo (CLIP top-3) | paleta | texto em | área lisa | mudança |",
         "|---|---|---|---|---|---|---|---|---|"]
    for g in graf:
        fundo = ", ".join(f"{x['estilo']} {x['score']:.0%}" for x in g["fundo"])
        pal = " ".join(f"{p['hex']}({p['fracao']:.0%})" for p in g["paleta"][:3])
        lay = g["layout"]
        L.append(f"| {g['n']} | {int(g['de']) // 60}:{g['de'] % 60:04.1f} | {g['duracao']:.1f} s | {g['tipo']} | {fundo} | "
                 f"{pal} | {lay['vertical']}/{lay['horizontal']} | {lay['area_lisa']:.0%} | {g['mudanca_visual']} |")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Relatorio
# ---------------------------------------------------------------------------

def _frac(vals, t0, t1, fps):
    a, b = int(t0 * fps), int(t1 * fps)
    seg = vals[a:b]
    return float(np.mean(seg)) if len(seg) else 0.0


def resumir(mov: dict, clip: dict, aud: dict, dur: float) -> dict:
    cortes = detectar_cortes(mov["dist"], FPS_CORTE)
    flashes = detectar_flashes(mov["luma"], FPS_CORTE)
    desloc, zoom = np.asarray(mov["desloc"]), np.asarray(mov["zoom"])
    tipos = clip["tipos"]
    media_tipos = {k: round(float(np.mean([t[k] for t in tipos])), 3) for k, _ in ROTULOS} if tipos else {}
    dominante = [max(t, key=t.get) for t in tipos]
    contagem = {k: round(dominante.count(k) / max(1, len(dominante)), 3) for k, _ in ROTULOS}
    trechos = []
    t = 0.0
    while t < dur:
        t1 = min(dur, t + JANELA_TRECHO)
        c = [x for x in cortes if t <= x < t1]
        f = [x for x in flashes if t <= x < t1]
        ks = dominante[int(t * FPS_CLIP):int(t1 * FPS_CLIP)]
        cs = clip["cores"][int(t * FPS_CLIP):int(t1 * FPS_CLIP)]
        top = sorted({k: ks.count(k) for k in set(ks)}.items(), key=lambda kv: -kv[1])[:3]
        cor = max(set(cs), key=cs.count) if cs else ""
        z = zoom[int(t * FPS_CORTE):int(t1 * FPS_CORTE)]
        trechos.append({
            "de": round(t, 1), "ate": round(t1, 1), "cortes": len(c), "flashes": len(f),
            "movimento_px": round(_frac(desloc, t, t1, FPS_CORTE), 2),
            "zoom_in": round(float((z > 0.15).mean()) if len(z) else 0, 2),
            "letterbox": round(_frac(mov["letter"], t, t1, FPS_CORTE), 2),
            "tipos": [f"{k} {v / max(1, len(ks)):.0%}" for k, v in top], "cor": cor,
            "energia_audio": round(float(np.mean([r for tr, r in zip(aud["t_rms"], aud["rms"]) if t <= tr < t1] or [0])), 4),
        })
        t = t1
    return {
        "duracao": round(dur, 2),
        "planos": estatisticas_planos(cortes, dur),
        "cortes": cortes, "flashes": flashes,
        "flashes_por_minuto": round(len(flashes) / max(1e-6, dur) * 60, 1),
        "tela_preta": round(float(np.mean(mov["preto"])), 3),
        "letterbox": round(float(np.mean(mov["letter"])), 3),
        "movimento_medio_px": round(float(desloc.mean()), 2),
        "tremor_quadros": round(float((desloc > 6).mean()), 3),
        "zoom_in_quadros": round(float((zoom > 0.15).mean()), 3),
        "zoom_out_quadros": round(float((zoom < -0.15).mean()), 3),
        "audio": {k: aud[k] for k in ("bpm", "lufs", "true_peak")},
        "sincronia_batida": sincronia_com_batida(cortes, aud["batidas"]),
        "sincronia_onset": sincronia_com_batida(cortes, aud["onsets"]),
        "tipos_media": media_tipos, "tipos_dominante": contagem,
        "cores": {c: round(clip["cores"].count(c) / max(1, len(clip["cores"])), 3) for c in set(clip["cores"])},
        "trechos": trechos, "folhas": clip["folhas"],
    }


def analisar(video: Path, pasta: Path) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    dur = duracao(video)
    print("  [1/3] cortes, flashes e camera...")
    mov = passada_movimento(video)
    print("  [2/3] tipo de quadro (OpenCLIP), cor e folhas...")
    clip = passada_clip(video, pasta)
    print("  [3/4] audio (BPM, batidas, LUFS)...")
    aud = passada_audio(video)
    r = resumir(mov, clip, aud, dur)
    print("  [4/4] fundos e cards graficos...")
    r["graficos"] = passada_graficos(video, pasta, clip["tipos"])
    return r


def _pct(x):
    return f"{x * 100:.0f}%" if isinstance(x, (int, float)) else "—"


def markdown(r: dict, titulo: str, meta: dict | None = None, comp: dict | None = None) -> str:
    p, sb, so = r["planos"], r["sincronia_batida"], r["sincronia_onset"]
    L = [f"# Raio-x: {titulo}", ""]
    if meta:
        L += [f"- Canal: {meta.get('channel')} · publicado {meta.get('upload_date')} · {meta.get('view_count')} views",
              f"- {meta.get('width')}x{meta.get('height')} @ {meta.get('fps')} fps · {r['duracao']:.0f} s", ""]
    L += ["## Ritmo de edição",
          f"- {p.get('planos')} planos · **{p.get('cortes_por_minuto')} cortes/min** · plano médio {p.get('plano_medio_s')} s "
          f"(mediana {p.get('plano_mediano_s')} s, mín {p.get('plano_min_s')} s, máx {p.get('plano_max_s')} s)",
          f"- Planos < 0,5 s: {_pct(p.get('planos_menores_0_5s'))}",
          f"- Cortes na batida: {_pct(sb['ate_50ms'])} a ≤50 ms, {_pct(sb['ate_100ms'])} a ≤100 ms (mediana {sb['mediana_ms']} ms); "
          f"em onset: {_pct(so['ate_100ms'])} a ≤100 ms",
          f"- Flashes: {len(r['flashes'])} ({r['flashes_por_minuto']}/min) · tela preta {_pct(r['tela_preta'])} · letterbox {_pct(r['letterbox'])}",
          "", "## Câmera",
          f"- Movimento médio {r['movimento_medio_px']} px/quadro (160x90) · tremor {_pct(r['tremor_quadros'])} dos quadros",
          f"- Zoom-in {_pct(r['zoom_in_quadros'])} · zoom-out {_pct(r['zoom_out_quadros'])}",
          "", "## Áudio",
          f"- BPM ≈ {r['audio']['bpm']} · LUFS {r['audio']['lufs']} · pico {r['audio']['true_peak']} dBFS",
          "", "## Tipo de quadro (OpenCLIP, % dos quadros em que é o tipo dominante)"]
    for k, v in sorted(r["tipos_dominante"].items(), key=lambda kv: -kv[1]):
        if v >= 0.01:
            L.append(f"- {k}: {_pct(v)}")
    L += ["", "## Cores dominantes"]
    for k, v in sorted(r["cores"].items(), key=lambda kv: -kv[1])[:6]:
        L.append(f"- {k}: {_pct(v)}")
    L += ["", f"## Trecho a trecho ({JANELA_TRECHO:.0f} s)", "",
          "| trecho | cortes | flashes | mov | zoom-in | letterbox | tipos | cor | energia |", "|---|---|---|---|---|---|---|---|---|"]
    for t in r["trechos"]:
        L.append(f"| {t['de']:.0f}–{t['ate']:.0f} s | {t['cortes']} | {t['flashes']} | {t['movimento_px']} | {_pct(t['zoom_in'])} | "
                 f"{_pct(t['letterbox'])} | {', '.join(t['tipos'])} | {t['cor']} | {t['energia_audio']} |")
    if comp:
        cp, cs = comp["planos"], comp["sincronia_batida"]
        L += ["", "## Comparação com o nosso vídeo", "", "| métrica | referência | nosso |", "|---|---|---|",
              f"| cortes/min | {p.get('cortes_por_minuto')} | {cp.get('cortes_por_minuto')} |",
              f"| plano mediano | {p.get('plano_mediano_s')} s | {cp.get('plano_mediano_s')} s |",
              f"| cortes na batida ≤100 ms | {_pct(sb['ate_100ms'])} | {_pct(cs['ate_100ms'])} |",
              f"| flashes/min | {r['flashes_por_minuto']} | {comp['flashes_por_minuto']} |",
              f"| tremor | {_pct(r['tremor_quadros'])} | {_pct(comp['tremor_quadros'])} |",
              f"| zoom-in | {_pct(r['zoom_in_quadros'])} | {_pct(comp['zoom_in_quadros'])} |",
              f"| letterbox | {_pct(r['letterbox'])} | {_pct(comp['letterbox'])} |",
              f"| texto grande (dominante) | {_pct(r['tipos_dominante'].get('texto_grande'))} | {_pct(comp['tipos_dominante'].get('texto_grande'))} |",
              f"| LUFS | {r['audio']['lufs']} | {comp['audio']['lufs']} |"]
    L += ["", markdown_graficos(r.get("graficos") or [])]
    L += ["", "Folhas de contato (1 quadro a cada 2 s): " + ", ".join(f"`{f}`" for f in r["folhas"]),
          "", "> Medido por software (histograma, fluxo óptico, OpenCLIP, librosa). Tipos de quadro são estimativas"
          " zero-shot; confirme nas folhas."]
    return "\n".join(L)


def executar(fonte: str, comparar: str | None = None) -> dict:
    ident = id_de(fonte)
    pasta = REFS / ident
    video = baixar(fonte, pasta) if fonte.startswith("http") else Path(fonte)
    meta = None
    info = next(pasta.glob("*.info.json"), None)
    if info:
        m = json.loads(info.read_text(encoding="utf-8"))
        meta = {k: m.get(k) for k in ("title", "channel", "upload_date", "view_count", "width", "height", "fps",
                                      "description", "tags")}
    print(f"== referencia {ident} ==")
    r = analisar(video, pasta)
    comp = None
    if comparar:
        print(f"== comparando com {comparar} ==")
        comp = analisar(Path(comparar), pasta / "nosso")
        r["comparacao"] = {"video": str(comparar), **{k: comp[k] for k in comp if k not in ("trechos", "graficos")}}
    (pasta / "analise.json").write_text(json.dumps({"meta": meta, **r}, ensure_ascii=False, indent=2), encoding="utf-8")
    (pasta / "analise.md").write_text(markdown(r, (meta or {}).get("title") or ident, meta, comp), encoding="utf-8")
    print(f"  relatorio: {pasta / 'analise.md'}")
    return r
