#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Scene Intelligence — catálogo visual genérico dos clipes.

Analisa o conteúdo real dos vídeos em clips_raw/ em vez de depender do nome
do arquivo. Produz scene_intelligence.json com cenas, tags, intensidade,
qualidade e métricas visuais. A análise usa OpenCV offline e cache por
fingerprint. Um encoder semântico mais forte pode ser acoplado depois sem
mudar o contrato do catálogo.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from semantic_vision import (
    SemanticVisionEncoder, pick_sample_indices, profile_from_manifest, profile_hash,
)

SCHEMA_VERSION = 2
DEFAULT_SAMPLE_INTERVAL = 0.72
MAX_SCENE_SECONDS = 5.4
MIN_SCENE_SECONDS = 0.72
SCENE_CHANGE_THRESHOLD = 0.46


def _clamp(value: float, lo=0.0, hi=1.0) -> float:
    return float(max(lo, min(hi, value)))


def _fingerprint(path: Path) -> dict:
    st = path.stat()
    return {
        "size": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
    }


def is_generated_asset(path: Path) -> bool:
    """True para assets derivados/laboratório que nunca devem virar fonte narrativa."""
    name = path.stem.lower()
    prefixes = (
        "impact_", "take_chroma_", "take_saber_", "demo_",
        "vx_graphics_", "card_", "intro_", "overlay_",
    )
    return (
        name.startswith(prefixes)
        or "graphics_auto" in name
        or "manga_auto" in name
        or "cena_ia" in name
        or "title_card" in name
        or "end_card" in name
    )


# Compatibilidade com testes/código anterior.
_is_generated_asset = is_generated_asset


def _probe(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"nao foi possivel abrir video: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    duration = frames / fps if fps > 0 else 0.0
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"duracao invalida: {path}")
    return {
        "fps": round(fps, 4),
        "frames": frames,
        "width": width,
        "height": height,
        "duration": round(duration, 4),
    }


def _log(msg: str) -> None:
    """Progresso em stderr: a esteira grava no log da etapa (stdout fica para o JSON)."""
    print(f"[scene-intel] {msg}", file=sys.stderr, flush=True)


def _hwdec_enabled() -> bool:
    return os.environ.get("VX_SCENE_HWDEC", "1").strip().lower() not in {"0", "false", "off", "no"}


def _open_capture(path: Path, hw: bool):
    """Abre o video pedindo decode por hardware (D3D11/NVDEC) com fallback software.

    Material de anime baixado costuma vir em AV1 1080p: software decodifica ~100 fps,
    hardware ~1000 fps. Retorna (cap, "hw"|"sw").
    """
    prop = getattr(cv2, "CAP_PROP_HW_ACCELERATION", None)
    accel = getattr(cv2, "VIDEO_ACCELERATION_ANY", None)
    if hw and prop is not None and accel is not None:
        try:
            cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [prop, accel])
            if cap.isOpened():
                return cap, ("hw" if float(cap.get(prop) or 0.0) > 0.0 else "sw")
            cap.release()
        except Exception:
            pass
    return cv2.VideoCapture(str(path)), "sw"


def _face_detector():
    try:
        xml = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(str(xml))
        return None if detector.empty() else detector
    except Exception:
        return None


def _sample_times(duration: float, interval: float) -> list[float]:
    interval = max(0.35, float(interval))
    if duration <= interval:
        return [max(0.0, duration * 0.5)]
    start = min(0.18, duration * 0.1)
    out = []
    t = start
    while t < duration - 0.06:
        out.append(round(t, 4))
        t += interval
    if out and duration - out[-1] > interval * 0.65:
        out.append(round(max(0.0, duration - 0.08), 4))
    return out


def _resize_for_analysis(frame: np.ndarray, max_width=384) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / float(w)
    return cv2.resize(frame, (max_width, max(2, int(h * scale))),
                      interpolation=cv2.INTER_AREA)


def _color_ratios(hsv: np.ndarray) -> dict:
    h = hsv[..., 0]
    s = hsv[..., 1]
    v = hsv[..., 2]
    active = (s >= 72) & (v >= 45)
    total = max(1, int(active.size))

    def ratio(mask):
        return float(np.count_nonzero(mask & active) / total)

    return {
        "red": ratio((h <= 8) | (h >= 172)),
        "orange": ratio((h >= 9) & (h <= 25)),
        "yellow": ratio((h >= 24) & (h <= 38)),
        "green": ratio((h >= 39) & (h <= 82)),
        "cyan_blue": ratio((h >= 83) & (h <= 128)),
        "purple": ratio((h >= 129) & (h <= 171)),
    }


def _hsv_hist(hsv: np.ndarray) -> np.ndarray:
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def _frame_features(frame: np.ndarray, prev_gray, prev_hist, detector):
    small = _resize_for_analysis(frame)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    brightness = float(np.mean(gray) / 255.0)
    contrast = _clamp(float(np.std(gray) / 92.0))
    saturation = float(np.mean(hsv[..., 1]) / 255.0)
    sharp_raw = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness = _clamp(sharp_raw / 520.0)
    edges = cv2.Canny(gray, 70, 150)
    edge_density = float(np.count_nonzero(edges) / edges.size)
    dark_ratio = float(np.count_nonzero(gray < 34) / gray.size)
    highlight_ratio = float(np.count_nonzero(gray > 222) / gray.size)

    colors = _color_ratios(hsv)
    hist = _hsv_hist(hsv)
    hist_diff = 0.0
    if prev_hist is not None:
        corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
        hist_diff = _clamp((1.0 - corr) / 1.35)

    motion = 0.0
    motion_x = motion_y = 0.0
    if prev_gray is not None and prev_gray.shape == gray.shape:
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, gray, None,
            pyr_scale=0.5, levels=2, winsize=11,
            iterations=2, poly_n=5, poly_sigma=1.1, flags=0,
        )
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        motion_raw = float(np.percentile(mag, 72))
        motion = _clamp(motion_raw / 5.0)
        valid = mag > max(0.35, np.percentile(mag, 58))
        if np.any(valid):
            motion_x = float(np.mean(flow[..., 0][valid]))
            motion_y = float(np.mean(flow[..., 1][valid]))

    face_count = 0
    face_area = 0.0
    if detector is not None and gray.shape[1] >= 120:
        try:
            faces = detector.detectMultiScale(
                gray, scaleFactor=1.12, minNeighbors=4,
                minSize=(max(24, gray.shape[1] // 12),) * 2,
            )
            face_count = len(faces)
            area = float(gray.shape[0] * gray.shape[1])
            if face_count:
                face_area = max(float(w * h) / area for x, y, w, h in faces)
        except Exception:
            pass

    center = gray[
        int(gray.shape[0] * 0.23):int(gray.shape[0] * 0.80),
        int(gray.shape[1] * 0.22):int(gray.shape[1] * 0.78)
    ]
    center_edges = cv2.Canny(center, 70, 150) if center.size else edges
    center_saliency = _clamp(
        (np.count_nonzero(center_edges) / max(1, center_edges.size))
        / max(0.025, edge_density)
        / 1.65
    )

    features = {
        "brightness": round(brightness, 4),
        "contrast": round(contrast, 4),
        "saturation": round(saturation, 4),
        "sharpness": round(sharpness, 4),
        "edge_density": round(edge_density, 4),
        "dark_ratio": round(dark_ratio, 4),
        "highlight_ratio": round(highlight_ratio, 4),
        "motion": round(motion, 4),
        "motion_x": round(motion_x, 4),
        "motion_y": round(motion_y, 4),
        "hist_diff": round(hist_diff, 4),
        "face_count": int(face_count),
        "face_area": round(face_area, 4),
        "center_saliency": round(center_saliency, 4),
        **{k: round(v, 4) for k, v in colors.items()},
    }
    return features, gray, hist


def _aggregate(samples: list[dict]) -> dict:
    if not samples:
        return {}
    keys = [
        "brightness", "contrast", "saturation", "sharpness",
        "edge_density", "dark_ratio", "highlight_ratio",
        "motion", "motion_x", "motion_y", "face_area",
        "center_saliency", "red", "orange", "yellow", "green",
        "cyan_blue", "purple",
    ]
    result = {}
    for key in keys:
        vals = [float(s["features"].get(key, 0.0)) for s in samples]
        result[key] = round(float(np.mean(vals)), 4)
    result["motion_peak"] = round(max(
        float(s["features"].get("motion", 0.0)) for s in samples
    ), 4)
    result["face_count_max"] = int(max(
        s["features"].get("face_count", 0) for s in samples
    ))
    return result


def _tag_scores(f: dict) -> dict:
    motion = f.get("motion", 0.0)
    peak = f.get("motion_peak", motion)
    contrast = f.get("contrast", 0.0)
    sat = f.get("saturation", 0.0)
    edge = f.get("edge_density", 0.0)
    face = f.get("face_area", 0.0)
    bright = f.get("brightness", 0.0)
    dark = f.get("dark_ratio", 0.0)
    red = f.get("red", 0.0)
    orange = f.get("orange", 0.0)
    blue = f.get("cyan_blue", 0.0)
    purple = f.get("purple", 0.0)

    scores = {
        "action": _clamp((motion - 0.12) / 0.48),
        "impact": _clamp(0.62 * peak + 0.22 * contrast + 0.16 * edge),
        "speed": _clamp((peak - 0.34) / 0.48),
        "calm": _clamp((0.28 - motion) / 0.28),
        "portrait": _clamp(face / 0.055),
        "closeup": _clamp(face / 0.12),
        "emotional": _clamp((face / 0.08) * (1.0 - min(1.0, motion))),
        "dark": _clamp(max((0.43 - bright) / 0.32, dark / 0.72)),
        "bright": _clamp((bright - 0.48) / 0.38),
        "fire": _clamp((orange + 0.55 * red) / 0.15 * sat),
        "blood": _clamp((red - orange * 0.35) / 0.13 * sat),
        "electric": _clamp(blue / 0.16 * (0.55 + sat * 0.7)),
        "purple_energy": _clamp(purple / 0.12 * (0.55 + sat * 0.7)),
        "power": _clamp(0.42 * sat + 0.34 * contrast + 0.24 * peak),
        "monochrome": _clamp((0.24 - sat) / 0.24),
        "high_contrast": _clamp((contrast - 0.38) / 0.50),
        "center_subject": _clamp(f.get("center_saliency", 0.0)),
    }
    scores["fight"] = _clamp(
        0.62 * scores["action"] + 0.38 * scores["impact"]
    )
    scores["destruction"] = _clamp(
        0.45 * scores["impact"] + 0.35 * scores["fire"]
        + 0.20 * scores["high_contrast"]
    )
    scores["energy"] = max(
        scores["electric"], scores["purple_energy"],
        _clamp(scores["power"] * 0.84),
    )
    return {k: round(v, 4) for k, v in scores.items()}


def _quality(f: dict, width: int, height: int) -> float:
    resolution = _clamp(min(width / 1920.0, height / 1080.0))
    exposure = 1.0 - _clamp(abs(f.get("brightness", 0.5) - 0.48) / 0.52)
    if f.get("dark_ratio", 0.0) > 0.88:
        exposure *= 0.45
    score = (
        0.34 * f.get("sharpness", 0.0)
        + 0.21 * exposure
        + 0.18 * f.get("contrast", 0.0)
        + 0.15 * resolution
        + 0.12 * f.get("center_saliency", 0.0)
    )
    return round(_clamp(score), 4)


def _scene_from_samples(
    clip_name: str, samples: list[dict], start: float, end: float,
    width: int, height: int, index: int,
) -> dict:
    agg = _aggregate(samples)
    tags = _tag_scores(agg)
    selected_tags = [
        name for name, score in sorted(tags.items(), key=lambda kv: -kv[1])
        if score >= 0.52
    ][:8]
    intensity = _clamp(
        0.46 * agg.get("motion_peak", 0.0)
        + 0.22 * agg.get("contrast", 0.0)
        + 0.18 * agg.get("saturation", 0.0)
        + 0.14 * agg.get("edge_density", 0.0) * 3.2
    )
    direction = "static"
    mx, my = agg.get("motion_x", 0.0), agg.get("motion_y", 0.0)
    if abs(mx) + abs(my) > 0.12:
        if abs(mx) >= abs(my):
            direction = "right" if mx > 0 else "left"
        else:
            direction = "down" if my > 0 else "up"

    # Cena "morta": quase preta e sem detalhe (ex.: tail preto de clipe,
    # splash de servico de streaming tipo "prime"/"netflix" sobre fundo preto).
    # Nunca e material narrativo bom e reprovaria o porteiro de imagem, entao
    # marcamos para o Scene Matcher e o Title Card nunca escolherem essa janela.
    # Criterio alinhado ao porteiro imagem.py (luz baixa + detalhe baixo),
    # medido em 0..1: brightness<~0.11 e edge_density baixo.
    brightness = float(agg.get("brightness", 0.5))
    edge_density = float(agg.get("edge_density", 0.0))
    saturation = float(agg.get("saturation", 0.0))
    dark_ratio = float(agg.get("dark_ratio", 0.0))
    dead = (
        brightness < 0.11
        and edge_density < 0.05
        and saturation < 0.18
    ) or dark_ratio > 0.96

    return {
        "id": f"{Path(clip_name).stem}_scene_{index:03d}",
        "start": round(max(0.0, start), 4),
        "end": round(max(start, end), 4),
        "duration": round(max(0.0, end - start), 4),
        "tags": selected_tags,
        "tag_scores": tags,
        "intensity": round(intensity, 4),
        "quality": _quality(agg, width, height),
        "motion_direction": direction,
        "features": agg,
        "sample_count": len(samples),
        "dead_scene": bool(dead),
    }


def _sample_pass(
    path: Path, meta: dict, sample_interval: float,
    semantic_encoder: SemanticVisionEncoder | None, hw: bool,
) -> tuple[list[dict], int, str]:
    """Uma passada sequencial: features CV + scores semanticos no mesmo frame.

    Nao faz seek: o CLIP pontua os frames ja amostrados, e cada cena usa um
    subconjunto deles (pick_sample_indices).
    """
    duration = float(meta["duration"])
    detector = _face_detector()
    cap, decoder = _open_capture(path, hw)
    if not cap.isOpened():
        raise RuntimeError(f"nao foi possivel abrir {path}")
    samples = []
    prev_gray = prev_hist = None
    fps = float(meta["fps"] or 30.0)
    stride = max(1, int(round(fps * sample_interval)))
    frame_index = 0
    next_sample = max(0, int(round(min(0.18, duration * 0.1) * fps)))
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            if frame_index >= next_sample:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    t = min(duration, frame_index / fps)
                    features, prev_gray, prev_hist = _frame_features(
                        frame, prev_gray, prev_hist, detector
                    )
                    sample = {"time": round(t, 4), "features": features}
                    if semantic_encoder is not None:
                        sample["semantic"] = semantic_encoder.frame_scores(frame)
                    samples.append(sample)
                next_sample += stride
            frame_index += 1
    finally:
        cap.release()
    return samples, frame_index, decoder


def analisar_clipe(
    path: Path, sample_interval: float = DEFAULT_SAMPLE_INTERVAL,
    semantic_encoder: SemanticVisionEncoder | None = None,
) -> dict:
    path = Path(path)
    meta = _probe(path)
    duration = float(meta["duration"])
    generated = is_generated_asset(path)
    use_semantic = bool(
        semantic_encoder is not None and semantic_encoder.enabled and not generated
    )
    encoder = semantic_encoder if use_semantic else None

    samples, decoded, decoder = _sample_pass(
        path, meta, sample_interval, encoder, hw=_hwdec_enabled()
    )
    expected = int(meta.get("frames") or 0)
    if decoder == "hw" and expected > 0 and decoded < expected * 0.9:
        # decode por hardware parou antes do fim: refaz em software em vez de
        # catalogar so metade do clipe.
        _log(f"{path.name}: decode HW entregou {decoded}/{expected} frames; refazendo em software")
        samples, decoded, decoder = _sample_pass(
            path, meta, sample_interval, encoder, hw=False
        )

    if not samples:
        raise RuntimeError(f"nenhum frame amostrado: {path}")

    groups = []
    current = []
    scene_start = 0.0
    for sample in samples:
        t = float(sample["time"])
        elapsed = t - scene_start
        change = float(sample["features"].get("hist_diff", 0.0))
        boundary = (
            current
            and elapsed >= MIN_SCENE_SECONDS
            and (
                change >= SCENE_CHANGE_THRESHOLD
                or elapsed >= MAX_SCENE_SECONDS
            )
        )
        if boundary:
            groups.append((scene_start, t, current))
            current = []
            scene_start = t
        current.append(sample)
    if current:
        groups.append((scene_start, duration, current))

    nframes = int((semantic_encoder.profile if use_semantic else {}).get("frames_per_scene", 3))
    scenes = []
    for idx, (start, end, group) in enumerate(groups, 1):
        if end - start < 0.20:
            continue
        scene = _scene_from_samples(
            path.name, group, start, min(duration, end),
            meta["width"], meta["height"], idx,
        )
        if use_semantic:
            scored = [s["semantic"] for s in group if s.get("semantic")]
            picks = pick_sample_indices(len(scored), nframes)
            semantic_encoder.attach_scene_scores(scene, [scored[i] for i in picks])
        scenes.append(scene)

    semantic_meta = semantic_encoder.info() if semantic_encoder is not None else {"enabled": False}

    clip_tags = {}
    for scene in scenes:
        for tag, score in scene["tag_scores"].items():
            clip_tags[tag] = max(clip_tags.get(tag, 0.0), score)
    summary_tags = [
        name for name, score in sorted(
            clip_tags.items(), key=lambda kv: -kv[1]
        ) if score >= 0.56
    ][:10]

    return {
        "file": path.name,
        "fingerprint": _fingerprint(path),
        **meta,
        "generated_asset": generated,
        "eligible_for_semantic_selection": (
            not generated and duration >= 2.0
        ),
        "analysis": {
            "engine": "vx_scene_intelligence_cv_clip",
            "sample_interval": sample_interval,
            "sample_count": len(samples),
            "decoder": decoder,
            "frames_decoded": decoded,
            "semantic_sampling": "sequential_samples" if use_semantic else None,
            "semantic_encoder": ("openclip_zero_shot" if semantic_meta.get("enabled") else "cv_heuristics"),
            "semantic_profile_hash": semantic_meta.get("profile_hash"),
            "semantic": semantic_meta,
        },
        "tags": summary_tags,
        "tag_scores": {
            k: round(v, 4) for k, v in sorted(clip_tags.items())
        },
        "scene_count": len(scenes),
        "scenes": scenes,
    }


def catalogar_projeto(
    projeto_dir: Path, force: bool = False,
    sample_interval: float = DEFAULT_SAMPLE_INTERVAL,
) -> dict:
    projeto_dir = Path(projeto_dir)
    clips_dir = projeto_dir / "clips_raw"
    if not clips_dir.is_dir():
        raise FileNotFoundError(f"clips_raw ausente: {clips_dir}")

    try:
        manifesto = json.loads((projeto_dir / "projeto.json").read_text(encoding="utf-8-sig"))
    except Exception:
        manifesto = {}
    semantic_profile = profile_from_manifest(manifesto)
    semantic_profile_hash = profile_hash(semantic_profile)
    semantic_encoder = None

    out_path = projeto_dir / "scene_intelligence.json"
    old = {}
    if out_path.exists() and not force:
        try:
            old = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    old_clips = old.get("clips", {}) if old.get("schema_version") == SCHEMA_VERSION else {}

    results = {}
    reused = analyzed = failed = 0
    errors = []
    files = sorted(clips_dir.glob("*.mp4"))

    def snapshot(complete: bool) -> dict:
        clips = dict(results)
        if not complete:
            # parcial: clipes ainda nao revisitados mantem a entrada antiga como
            # cache (revalidada por fingerprint na proxima execucao).
            for clip in files:
                if clip.name not in clips and clip.name in old_clips:
                    clips[clip.name] = old_clips[clip.name]
        return {
            "schema_version": SCHEMA_VERSION,
            "project": projeto_dir.name,
            "engine": "vx_scene_intelligence",
            "complete": complete,
            "sample_interval": sample_interval,
            "semantic_profile": {
                "enabled": bool(semantic_profile.get("enabled")),
                "hash": semantic_profile_hash,
                "model": semantic_profile.get("model"),
                "pretrained": semantic_profile.get("pretrained"),
                "labels": len(semantic_profile.get("labels") or []),
                "runtime": (semantic_encoder.info() if semantic_encoder is not None else None),
            },
            "clips_total": len(files),
            "eligible_clips": sum(
                1 for x in clips.values()
                if x.get("eligible_for_semantic_selection")
            ),
            "scenes_total": sum(len(x.get("scenes", [])) for x in clips.values()),
            "cache": {
                "reused": reused, "analyzed": analyzed, "failed": failed,
            },
            "errors": errors,
            "clips": clips,
        }

    for pos, clip in enumerate(files, 1):
        tag = f"({pos}/{len(files)}) {clip.name}"
        fp = _fingerprint(clip)
        cached = old_clips.get(clip.name)
        if (
            not force and cached
            and cached.get("fingerprint") == fp
            and cached.get("analysis", {}).get("sample_interval") == sample_interval
            and cached.get("analysis", {}).get("semantic_profile_hash") == semantic_profile_hash
        ):
            results[clip.name] = cached
            reused += 1
            _log(f"{tag}: cache")
            continue
        started = time.monotonic()
        try:
            if semantic_encoder is None:
                semantic_encoder = SemanticVisionEncoder(semantic_profile)
                info = semantic_encoder.info()
                _log(
                    "encoder semantico: "
                    + (f"{info['model']} em {info['device']}" if info["enabled"]
                       else f"desligado ({info.get('error') or 'sem rotulos'})")
                )
            _log(f"{tag}: analisando...")
            results[clip.name] = analisar_clipe(
                clip, sample_interval=sample_interval, semantic_encoder=semantic_encoder
            )
            analyzed += 1
            entry = results[clip.name]
            _log(
                f"{tag}: {entry['scene_count']} cenas, {entry['duration']:.0f}s de video, "
                f"decoder={entry['analysis'].get('decoder')}, {time.monotonic() - started:.1f}s"
            )
        except Exception as exc:
            failed += 1
            errors.append({"clip": clip.name, "error": str(exc)})
            _log(f"{tag}: FALHOU ({exc})")
        # grava a cada clipe: interrupcao (timeout/kill) nao perde o que ja foi analisado
        _write_catalog(out_path, snapshot(complete=False))

    catalog = snapshot(complete=True)
    marcar_cenas_poluidas(projeto_dir, catalog)
    marcar_cenas_pagina(projeto_dir, catalog)
    _write_catalog(out_path, catalog)
    return catalog


def marcar_cenas_poluidas(projeto_dir: Path, catalog: dict) -> int:
    """Cena com LEGENDA QUEIMADA (qa/fonte_limpa.json) vira `poluida` e sai do inventario,
    como dead_scene. Incidente Douma 30/09/2026: clipes oficiais com legenda em ingles
    entraram no video. Refeito a cada catalogo (barato; nao depende do cache)."""
    try:
        import fonte_limpa as fl
    except Exception:
        return 0
    linhas = fl.cenas_poluidas(projeto_dir)
    if not linhas:
        return 0
    textos = fl.linhas_texto_ocr(projeto_dir)
    c = fl.cfg()
    n = 0
    for nome, clip in (catalog.get("clips") or {}).items():
        linha = linhas.get(nome) or []
        texto = textos.get(nome) or []
        for cena in clip.get("scenes") or []:
            a, b = float(cena["start"]), float(cena["end"])
            frac = fl.fracao_legenda(linha, a, b, float(c["legenda_score_min"]))
            cena["legenda_queimada"] = round(frac, 3)
            # texto LIDO pelo OCR em qualquer instante da cena = poluida (prints do usuario,
            # 01/10/2026: legenda curta/no topo passava pela regra de fracao)
            cena["texto_ocr"] = fl.texto_na_janela(texto, a, b)
            cena["poluida"] = frac >= float(c["legenda_fracao_cena"]) or cena["texto_ocr"] > 0
            n += int(cena["poluida"])
    catalog["cenas_poluidas"] = n
    return n


def runs_pagina(mascara, dt: float, min_dur: float = 0.33) -> list:
    """Agrupa a mascara 'pagina' em janelas (inicio, fim) com duracao >= min_dur.

    0.33s = 2 amostras a 6 fps: abaixo disso e um quadro isolado (0.17s), que o
    gate de imagem so reprovaria se se acumulasse.
    """
    out, i, n = [], 0, len(mascara)
    while i < n:
        if mascara[i]:
            j = i
            while j < n and mascara[j]:
                j += 1
            if (j - i) * dt >= min_dur:
                out.append((i * dt, j * dt))
            i = j
        else:
            i += 1
    return out


def cenas_alcancadas(cenas: list, janelas: list) -> list:
    """Cenas ainda vivas que sobrepoe alguma janela de pagina."""
    return [
        cena for cena in cenas
        if not cena.get("dead_scene")
        and any(ini < float(cena["end"]) and fim > float(cena["start"])
                for ini, fim in janelas)
    ]


def marcar_cenas_pagina(projeto_dir: Path, catalog: dict) -> int:
    """Cena que cai numa janela 'pagina clara sem cor / line-art' vira `dead_scene`.

    E o outro lado do `dead_scene` que ja existia: o catalogo so conhecia a metade
    ESCURA do gate (tela preta / tail de clipe). Incidente Asta 05/10/2026: o master
    reprovou com 3,0s de pagina — fades brancos de clipe oficial e um close de pele
    clara tinham sido escolhidos pelo Scene Matcher, porque ninguam olhava o lado
    CLARO. O criterio e o do proprio `imagem.mascara_pagina`, entao o catalogo e o
    gate nunca divergem.
    """
    try:
        import imagem as im
    except Exception:
        return 0
    dt = 1.0 / float(getattr(im, "FPS_AMOSTRA", 6))
    for nome, clip in (catalog.get("clips") or {}).items():
        arquivo = projeto_dir / "clips_raw" / nome
        if not arquivo.exists():
            arquivo = projeto_dir / nome
        if not arquivo.exists():
            continue
        try:
            mascara = im.mascara_pagina(im._amostrar(arquivo))
        except Exception:
            continue
        for cena in cenas_alcancadas(clip.get("scenes") or [], runs_pagina(mascara, dt)):
            cena["dead_scene"] = True
            cena["pagina"] = True
    _marcar_cenas_claras_chapadas(catalog)
    # total, nao "da execucao": as marcas vivem no catalogo em cache e sobrevivem
    # a rebuild sem --force (sem isso o numero caia de 15 para 1 na rodada seguinte).
    marcadas = sum(
        1 for clip in (catalog.get("clips") or {}).values()
        for cena in clip.get("scenes") or [] if cena.get("pagina")
    )
    catalog["cenas_pagina"] = marcadas
    return marcadas


def _marcar_cenas_claras_chapadas(catalog: dict) -> int:
    """Chão de segurança: cena CLARA e CHAPADA também sai.

    O grade do render empurra pele clara por cima do limiar do gate mesmo com a
    fonte normal (Asta 05/10/2026: close de olho, fracao branca 0,03 na fonte e
    0,76 no master -> 0,66s de pagina que nenhuma medicao na fonte pegava).
    `contrast < 0.28` e o proprio limiar de DETALHE do gate (std < 26/255, pois
    contrast = std/92); brightness > 0,60 e o que o grade precisa pra virar branco.
    No catalogo do Asta: 4 cenas de 447 — 3 ja marcadas pelo video, sobrava so o
    close de olho.
    """
    n = 0
    for clip in (catalog.get("clips") or {}).values():
        for cena in clip.get("scenes") or []:
            if cena.get("dead_scene"):
                continue
            f = cena.get("features") or {}
            if float(f.get("brightness", 0.0)) > 0.60 and float(f.get("contrast", 1.0)) < 0.28:
                cena["dead_scene"] = True
                cena["pagina"] = True
                n += 1
    return n


def _write_catalog(out_path: Path, catalog: dict) -> None:
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.replace(tmp, out_path)
    except PermissionError:
        backup = out_path.with_suffix(out_path.suffix + ".vxscene.bak")
        if out_path.exists():
            shutil.copy2(out_path, backup)
        out_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--interval", type=float, default=DEFAULT_SAMPLE_INTERVAL)
    args = parser.parse_args()
    result = catalogar_projeto(
        Path(args.project), force=args.force, sample_interval=args.interval
    )
    print(json.dumps({
        "project": result["project"],
        "clips_total": result["clips_total"],
        "eligible_clips": result["eligible_clips"],
        "scenes_total": result["scenes_total"],
        "cache": result["cache"],
        "errors": result["errors"],
    }, ensure_ascii=False, indent=2))
