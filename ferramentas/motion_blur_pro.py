#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motion_blur_pro.py — Motion Blur Cinemático Natural (Simulação de RSMB via Vetores de Movimento).
Calcula o vetor de velocidade entre frames adjacentes e desfoca na direção do vetor.
Suaviza animações a 12/24fps, dando aspecto fluido e orgânico de anime de cinema em 60fps.
"""
from pathlib import Path
import sys
import cv2
import numpy as np

def aplicar_motion_blur_video(
    video_entrada: str,
    video_saida: str,
    intensidade: float = 1.2,
    max_frames: int = 150
) -> str:
    """
    Aplica desfoque direcional baseado em Optical Flow (Farneback).
    """
    cap = cv2.VideoCapture(video_entrada)
    if not cap.isOpened():
        raise RuntimeError(f"Erro ao abrir: {video_entrada}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    ret, prev_frame = cap.read()
    if not ret:
        cap.release()
        return video_entrada

    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(video_saida, fourcc, fps, (w, h))

    # Escreve o primeiro frame normal
    out.write(prev_frame)

    frame_count = 1
    print(f"[MOTION BLUR] Processando blur cinemático (intensidade {intensidade})...")

    while cap.isOpened() and frame_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Optical flow para achar a velocidade de cada região
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None,
            pyr_scale=0.5, levels=2, winsize=13, iterations=2, poly_n=5, poly_sigma=1.1, flags=0
        )

        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mag_media = np.mean(mag)

        # Se houver movimento relevante, aplica blur direcional
        if mag_media > 1.5:
            # Kernel direcional baseado na média do ângulo do movimento
            ang_medio = np.mean(ang)
            ksize = int(min(25, max(3, mag_media * intensidade)))
            if ksize % 2 == 0:
                ksize += 1

            # Cria matriz de kernel rotacionada
            kernel = np.zeros((ksize, ksize))
            kernel[int((ksize - 1) / 2), :] = np.ones(ksize)
            M = cv2.getRotationMatrix2D((ksize / 2, ksize / 2), np.degrees(ang_medio), 1.0)
            kernel = cv2.warpAffine(kernel, M, (ksize, ksize))
            kernel = kernel / np.sum(kernel)

            frame_borrado = cv2.filter2D(frame, -1, kernel)
            # Mescla leve com o original para não perder nitidez de detalhes faciais
            frame_final = cv2.addWeighted(frame, 0.4, frame_borrado, 0.6, 0)
        else:
            frame_final = frame

        out.write(frame_final)
        prev_gray = curr_gray
        frame_count += 1

    cap.release()
    out.release()
    print(f"[MOTION BLUR] Concluído: {video_saida}")
    return video_saida

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python motion_blur_pro.py <in.mp4> <out.mp4> [intensidade]")
        sys.exit(1)
    intens = float(sys.argv[3]) if len(sys.argv) > 3 else 1.2
    aplicar_motion_blur_video(sys.argv[1], sys.argv[2], intens)
