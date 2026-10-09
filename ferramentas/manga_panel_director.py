#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Manga Panel Director — take curto de clímax com painéis animados.

Versão de laboratório reutilizável:
- escolhe cenas semanticamente relacionadas via Scene Intelligence;
- evita assets gerados e repetições muito próximas;
- estiliza em ink/duotone;
- compõe 3 painéis diagonais com entrada curta;
- renderiza por NVENC via render_dispatch.

Ainda não injeta automaticamente na timeline. Primeiro precisa de aprovação visual.
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import cv2
import numpy as np

import render_dispatch as rd
import semantic_scene_matcher as sm
from paineis_manga import mascaras_3_paineis
from style_preset_engine import normalizar

FPS = 30
WIDTH = 1920
HEIGHT = 1080


def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _hex_rgb(value: str, fallback=(142, 72, 255)):
    text = str(value or "").lstrip("#")
    if len(text) == 6:
        try:
            return tuple(int(text[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return fallback


def _ease_out(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return 1.0 - (1.0 - p) ** 3


def _fit_cover(rgb: np.ndarray, w=WIDTH, h=HEIGHT) -> np.ndarray:
    ih, iw = rgb.shape[:2]
    if iw <= 0 or ih <= 0:
        return np.zeros((h, w, 3), np.uint8)
    scale = max(w / float(iw), h / float(ih))
    nw, nh = max(w, int(round(iw * scale))), max(h, int(round(ih * scale)))
    resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_CUBIC)
    x = max(0, (nw - w) // 2)
    y = max(0, (nh - h) // 2)
    return resized[y:y+h, x:x+w]


def _translate(rgb: np.ndarray, dx: float, dy: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    mat = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        rgb, mat, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )


def _manga_ink(rgb: np.ndarray, accent=(142, 72, 255), intensity=0.20) -> np.ndarray:
    """Ink limpo: processa em meia resolução e retorna 1080p."""
    orig_h, orig_w = rgb.shape[:2]
    work = rgb
    if orig_w > 960:
        scale = 960.0 / orig_w
        work = cv2.resize(
            rgb, (960, max(2, int(orig_h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    gray = cv2.cvtColor(work, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=1.7, tileGridSize=(8, 8))
    g = clahe.apply(gray)
    g = np.clip((g.astype(np.float32) - 24.0) * 1.18 + 24.0, 8, 248).astype(np.uint8)

    # Linhas de tinta preservam formas do anime sem virar edge-map feio.
    smooth = cv2.bilateralFilter(g, 5, 30, 30)
    edges = cv2.Canny(smooth, 62, 132)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

    base = np.repeat(g[:, :, None], 3, axis=2).astype(np.float32)
    accent_arr = np.array(accent, dtype=np.float32)[None, None, :]
    shadow = ((1.0 - g.astype(np.float32) / 255.0) ** 1.65)[:, :, None]
    weight = shadow * float(max(0.0, min(0.32, intensity)))
    base = base * (1.0 - weight) + accent_arr * weight

    # Linhas pretas com alpha variável para evitar visual "xerox".
    line_alpha = (edges.astype(np.float32) / 255.0 * 0.72)[:, :, None]
    base = base * (1.0 - line_alpha) + 10.0 * line_alpha

    # Halftone extremamente leve apenas nas sombras.
    yy, xx = np.indices(g.shape)
    dots = ((xx % 9 == 0) & (yy % 9 == 0) & (g < 92)).astype(np.float32)[:, :, None]
    base = base * (1.0 - dots * 0.10)

    out = np.clip(base, 0, 255).astype(np.uint8)
    if out.shape[:2] != (orig_h, orig_w):
        out = cv2.resize(out, (orig_w, orig_h), interpolation=cv2.INTER_CUBIC)
    return out


def _border_from_mask(mask: np.ndarray, width=3) -> np.ndarray:
    kernel = np.ones((max(3, width * 2 + 1),) * 2, np.uint8)
    dil = cv2.dilate(mask, kernel, iterations=1)
    ero = cv2.erode(mask, kernel, iterations=1)
    return cv2.subtract(dil, ero)


def _rank_scenes(project: Path, text: str, duration: float, count=3):
    """Escolhe painel esquerdo, hero center e painel direito com diversidade real."""
    catalog = _json(project / "scene_intelligence.json", {}) or {}
    if not catalog:
        raise FileNotFoundError("scene_intelligence.json ausente; rode catalogar-cenas")
    manifest = _json(project / "projeto.json", {}) or {}
    inventory = sm._scene_inventory(catalog)
    intent = sm.interpretar_texto(text, manifest, tipo="lyric")
    ranked = []
    for scene in inventory:
        breakdown = sm.score_scene(intent, scene, duration)
        if sm._duration_score(scene, duration) < 0.55:
            continue
        ranked.append((breakdown["score"], scene, breakdown))
    ranked.sort(key=lambda x: (-x[0], -x[1].get("quality", 0.0)))
    if len(ranked) < 2:
        raise RuntimeError("cenas insuficientes para manga panels")

    def feat(scene, key, default=0.0):
        return float((scene.get("features") or {}).get(key, default))

    # HERO CENTER: relevância + qualidade + assunto bem centralizado.
    hero_rank = sorted(
        ranked,
        key=lambda row: -(
            row[0]
            + 0.070 * feat(row[1], "center_saliency")
            + 0.025 * float(row[1].get("quality", 0.0))
        ),
    )
    center = hero_rank[0]
    center_score, center_scene, _ = center

    # ACTION LEFT: prefere enquadramento mais aberto, motion forte e outro scene pack.
    left_rank = []
    for row in ranked:
        score, scene, _ = row
        if scene["id"] == center_scene["id"]:
            continue
        openness = 1.0 - feat(scene, "center_saliency", 0.5)
        motion = feat(scene, "motion_peak")
        diff_clip = 0.07 if scene["clip"] != center_scene["clip"] else 0.0
        far = 0.035 if (
            scene["clip"] != center_scene["clip"]
            or abs(float(scene["start"]) - float(center_scene["start"])) >= 10.0
        ) else -0.05
        role_score = score + 0.24 * openness + 0.045 * motion + diff_clip + far
        left_rank.append((role_score, row))
    left_rank.sort(key=lambda x: -x[0])
    left = left_rank[0][1]

    chosen_ids = {center_scene["id"], left[1]["id"]}
    used_dirs = {
        str(center_scene.get("motion_direction", "static")),
        str(left[1].get("motion_direction", "static")),
    }

    # DETAIL/IMPACT RIGHT: borda/detalhe + direção distinta + distância temporal.
    right_rank = []
    for row in ranked:
        score, scene, _ = row
        if scene["id"] in chosen_ids:
            continue
        edge = feat(scene, "edge_density")
        contrast = float((scene.get("tag_scores") or {}).get("high_contrast", 0.0))
        impact = float((scene.get("tag_scores") or {}).get("impact", 0.0))
        direction_bonus = (
            0.055 if str(scene.get("motion_direction", "static")) not in used_dirs else 0.0
        )
        too_close = any(
            scene["clip"] == x[1]["clip"]
            and abs(float(scene["start"]) - float(x[1]["start"])) < 7.0
            for x in (center, left)
        )
        diversity_bonus = 0.045 if not too_close else -0.055
        role_score = (
            score + min(0.075, edge * 0.55)
            + 0.035 * contrast + 0.035 * impact
            + direction_bonus + diversity_bonus
        )
        right_rank.append((role_score, row))
    right_rank.sort(key=lambda x: -x[0])
    right = right_rank[0][1]

    ordered = [left, center, right]
    return intent, [
        {"scene": row[1], "score": row[0], "breakdown": row[2]}
        for row in ordered[:count]
    ]


def _open_source(project: Path, scene: dict, duration: float):
    path = project / "clips_raw" / scene["clip"]
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"nao abriu fonte: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    start = sm._source_start(scene, duration)
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
    return {
        "cap": cap, "fps": fps, "start": start, "path": path,
        "decoded_index": -1, "last_frame": None,
    }


def _read_at_stream(source: dict, target_index: int) -> np.ndarray:
    """Leitura sequencial: 30fps usa 1:1; 60fps descarta frames intermediários."""
    target_source_index = int(round(target_index * source["fps"] / FPS))
    while source["decoded_index"] < target_source_index:
        ok, bgr = source["cap"].read()
        if not ok or bgr is None:
            if source["last_frame"] is None:
                raise RuntimeError(
                    f"falha lendo {source['path']} frame {target_source_index}"
                )
            break
        source["decoded_index"] += 1
        source["last_frame"] = bgr
    if source["last_frame"] is None:
        ok, bgr = source["cap"].read()
        if not ok or bgr is None:
            raise RuntimeError(f"falha lendo {source['path']}")
        source["decoded_index"] = 0
        source["last_frame"] = bgr
    return cv2.cvtColor(source["last_frame"], cv2.COLOR_BGR2RGB)


def render_take(
    project: Path,
    text: str,
    output: Path,
    duration: float = 1.55,
    layout: str = "3_shonen",
) -> dict:
    project = Path(project)
    output = Path(output)
    frames_total = max(30, int(round(duration * FPS)))
    duration = frames_total / FPS

    manifest = _json(project / "projeto.json", {}) or {}
    accent = _hex_rgb(manifest.get("cor", {}).get("destaque", "#8E48FF"))
    intent, picks = _rank_scenes(project, text, duration, count=3)
    sources = [_open_source(project, x["scene"], duration) for x in picks]

    try:
        with tempfile.TemporaryDirectory(prefix="vx_manga_panels_") as tmp:
            tmpdir = Path(tmp)
            for n in range(frames_total):
                p = n / max(1, frames_total - 1)
                entry = _ease_out(min(1.0, p / 0.26))
                hold_p = min(1.0, max(0.0, (p - 0.18) / 0.82))

                frames = []
                # Reframing: leva o assunto central de cada fonte para dentro
                # do painel que ele realmente ocupa, em vez de cortar o personagem.
                base_offsets = [
                    (-WIDTH * 0.29, 0),
                    (0, 0),
                    (WIDTH * 0.29, 0),
                ]
                entry_offsets = [
                    (-90 * (1 - entry), 18 * (1 - entry)),
                    (0, 72 * (1 - entry)),
                    (90 * (1 - entry), -18 * (1 - entry)),
                ]
                offsets = [
                    (base_offsets[i][0] + entry_offsets[i][0],
                     base_offsets[i][1] + entry_offsets[i][1])
                    for i in range(3)
                ]
                for i, src in enumerate(sources):
                    rgb = _read_at_stream(src, n)
                    rgb = _fit_cover(rgb)
                    # Micro zoom por painel; evita congelado mesmo em plano calmo.
                    z = 1.0 + (0.018 + i * 0.005) * hold_p
                    zw, zh = int(WIDTH * z), int(HEIGHT * z)
                    zoomed = cv2.resize(rgb, (zw, zh), interpolation=cv2.INTER_CUBIC)
                    x0, y0 = (zw - WIDTH) // 2, (zh - HEIGHT) // 2
                    rgb = zoomed[y0:y0+HEIGHT, x0:x0+WIDTH]
                    rgb = _translate(rgb, *offsets[i])
                    frames.append(_manga_ink(rgb, accent=accent, intensity=0.18 + i * 0.025))

                if layout != "3_shonen":
                    raise ValueError(f"layout manga nao suportado: {layout}")

                masks = mascaras_3_paineis(
                    WIDTH, HEIGHT,
                    progresso=0.12 + 0.88 * entry,
                    borda=22,
                )
                canvas = np.full((HEIGHT, WIDTH, 3), 8, dtype=np.uint8)

                # Entrada staggered: painel 1, centro, painel 3.
                staggers = [
                    smooth_alpha(p, 0.00, 0.16),
                    smooth_alpha(p, 0.055, 0.20),
                    smooth_alpha(p, 0.105, 0.23),
                ]
                for frame, mask, alpha in zip(frames, masks, staggers):
                    a = (mask.astype(np.float32) / 255.0 * alpha)[:, :, None]
                    canvas = np.clip(
                        canvas.astype(np.float32) * (1.0 - a) + frame.astype(np.float32) * a,
                        0, 255
                    ).astype(np.uint8)

                # Gutters claros finos + borda escura grossa dão leitura de mangá.
                for mask in masks:
                    edge = _border_from_mask(mask, width=2)
                    strong = edge > 0
                    canvas[strong] = np.clip(
                        canvas[strong].astype(np.float32) * 0.52
                        + np.array(accent, np.float32) * 0.18
                        + 84.0,
                        0, 255
                    ).astype(np.uint8)

                # Vinheta leve, sem texto.
                yy, xx = np.indices((HEIGHT, WIDTH))
                dx = (xx - WIDTH / 2) / (WIDTH / 2)
                dy = (yy - HEIGHT / 2) / (HEIGHT / 2)
                rad = np.sqrt(dx * dx + dy * dy)
                vign = np.clip(1.0 - np.maximum(0.0, rad - 0.48) * 0.18, 0.84, 1.0)
                canvas = np.clip(canvas.astype(np.float32) * vign[:, :, None], 0, 255).astype(np.uint8)

                cv2.imwrite(
                    str(tmpdir / f"frame_{n:05d}.jpg"),
                    cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 95],
                )

            rd.encode(
                saida=str(output),
                entradas=[
                    "-framerate", str(FPS),
                    "-i", str(tmpdir / "frame_%05d.jpg"),
                ],
                args_audio=["-an"],
                args_extra=["-r", str(FPS), "-frames:v", str(frames_total)],
                cq="17",
                silencioso=False,
            )
    finally:
        for src in sources:
            src["cap"].release()

    design = {
        "engine": "vx_manga_panel_director",
        "status": "lab",
        "text_reference": text,
        "normalized_text": normalizar(text),
        "duration": duration,
        "layout": layout,
        "accent": "#%02X%02X%02X" % accent,
        "intent": intent,
        "sources": [
            {
                "clip": x["scene"]["clip"],
                "scene_id": x["scene"]["id"],
                "scene_start": x["scene"]["start"],
                "scene_end": x["scene"]["end"],
                "score": x["score"],
                "tags": x["scene"].get("tags", []),
                "motion_direction": x["scene"].get("motion_direction", "static"),
            }
            for x in picks
        ],
    }
    output.with_suffix(".design.json").write_text(
        json.dumps(design, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return design


def smooth_alpha(p: float, start: float, end: float) -> float:
    if p <= start:
        return 0.0
    if p >= end:
        return 1.0
    x = (p - start) / max(1e-6, end - start)
    return x * x * (3.0 - 2.0 * x)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("text")
    parser.add_argument("output")
    parser.add_argument("--dur", type=float, default=1.55)
    args = parser.parse_args()
    result = render_take(
        Path(args.project), args.text, Path(args.output), duration=args.dur
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
