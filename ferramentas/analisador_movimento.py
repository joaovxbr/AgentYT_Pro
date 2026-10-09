#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analisador_movimento.py — Detecção de optical flow e picos de impacto (hit-frames).
Mede a energia de movimento em cada frame de um clipe para garantir que socos, cortes
e explosões caiam exatamente na batida (kick/snare/drop).
"""
import sys
import json
from pathlib import Path
import cv2
import numpy as np

def analisar_fluxo_movimento(video_path: str, max_frames: int = 900, downscale: int = 4) -> dict:
    """
    Analisa o vetor de optical flow (Farneback) ao longo do clipe.
    Retorna uma lista de magnitudes médias por segundo e identifica os picos de impacto (hit frames).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir o vídeo: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    ret, prev_frame = cap.read()
    if not ret:
        cap.release()
        return {"fps": fps, "picos": [], "curva_energia": []}

    h, w = prev_frame.shape[:2]
    small_size = (w // downscale, h // downscale)
    prev_gray = cv2.cvtColor(cv2.resize(prev_frame, small_size), cv2.COLOR_BGR2GRAY)

    energias = []
    frame_idx = 1
    
    while cap.isOpened() and frame_idx < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        curr_gray = cv2.cvtColor(cv2.resize(frame, small_size), cv2.COLOR_BGR2GRAY)
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None,
            pyr_scale=0.5, levels=2, winsize=11, iterations=2, poly_n=5, poly_sigma=1.1, flags=0
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        energia_frame = float(np.mean(mag))
        energias.append((frame_idx / fps, energia_frame))

        prev_gray = curr_gray
        frame_idx += 1

    cap.release()

    if not energias:
        return {"fps": fps, "picos": [], "curva_energia": []}

    # Detectar picos (frames com impacto acima de média + 1.2 * std)
    vals = [e[1] for e in energias]
    media = np.mean(vals)
    desvio = np.std(vals)
    limiar = media + 1.2 * desvio

    picos = []
    for t, val in energias:
        if val >= limiar:
            picos.append({"tempo": round(t, 3), "intensidade": round(val, 2)})

    # Filtrar picos muito próximos (mínimo de 0.3s entre impactos)
    picos_filtrados = []
    ultimo_t = -1.0
    for p in sorted(picos, key=lambda x: x["intensidade"], reverse=True):
        if all(abs(p["tempo"] - pf["tempo"]) >= 0.35 for pf in picos_filtrados):
            picos_filtrados.append(p)

    picos_filtrados.sort(key=lambda x: x["tempo"])

    return {
        "video": Path(video_path).name,
        "fps": round(fps, 2),
        "total_analisado_segundos": round(frame_idx / fps, 2),
        "picos_impacto": picos_filtrados
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python analisador_movimento.py <video.mp4>")
        sys.exit(1)
    res = analisar_fluxo_movimento(sys.argv[1])
    print(json.dumps(res, indent=2))
