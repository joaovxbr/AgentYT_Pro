#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_crop_916.py — Auto-Reframing Inteligente 9:16 para Shorts / TikTok com Rastreamento de Movimento.
Resolve o problema do crop estático central:
1. Analisa o centróide de movimento ou posição do personagem em cada frame via OpenCV (Optical Flow / Threshold)
2. Aplica interpolação suave (Low-pass filter / moving average) para a câmera deslizar sem solavancos
3. Gera o vídeo 1080x1920 mantendo a ação principal sempre visível no centro da tela vertical.
"""
from pathlib import Path
import sys
import cv2
import numpy as np

def calcular_trajetoria_camera(video_entrada: str, janela_suavizacao: int = 15) -> list[int]:
    """
    Rastreia o centro de interesse horizontal x_center ao longo do vídeo.
    Retorna uma lista com a coordenada X de corte para cada frame.
    """
    cap = cv2.VideoCapture(video_entrada)
    if not cap.isOpened():
        raise RuntimeError(f"Erro ao abrir vídeo: {video_entrada}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Largura de corte vertical correspondente à proporção 9:16 (crop_w = h * 9 / 16)
    crop_w = int(h * 9.0 / 16.0)
    if crop_w > w:
        crop_w = w

    max_x = w - crop_w
    centros_x = []

    ret, prev_frame = cap.read()
    if not ret:
        cap.release()
        return [max_x // 2] * max(1, total_frames)

    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    centros_x.append(w // 2)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(prev_gray, curr_gray)
        _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)

        # Encontra o centro de massa do movimento
        m = cv2.moments(thresh)
        if m["m00"] > 400:
            cx = int(m["m10"] / m["m00"])
        else:
            # Em cenas com movimento sutil, detecta o centro de bordas/detalhes (personagem/rosto)
            sobel_x = cv2.Sobel(curr_gray, cv2.CV_32F, 1, 0, ksize=3)
            bordas = np.abs(sobel_x)
            # Pondera a regiao central e terço superior (onde rostos costumam estar)
            col_weights = bordas[int(h * 0.15):int(h * 0.70), :].sum(axis=0)
            if col_weights.sum() > 1000:
                cx = int(np.average(np.arange(w), weights=col_weights))
            else:
                cx = w // 2

        # Limita o centro X
        x_desejado = cx - crop_w // 2
        x_clamped = max(0, min(max_x, x_desejado))
        centros_x.append(x_clamped)

        prev_gray = curr_gray

    cap.release()

    # Suavização da trajetória da câmera (Moving Average) para evitar tremedeira
    suavizados = []
    meia_janela = janela_suavizacao // 2
    for i in range(len(centros_x)):
        inicio = max(0, i - meia_janela)
        fim = min(len(centros_x), i + meia_janela + 1)
        media = int(np.mean(centros_x[inicio:fim]))
        suavizados.append(media)

    return suavizados

def renderizar_smart_crop_916(video_entrada: str, video_saida: str, fps: int = 30) -> str:
    """
    Executa o crop dinâmico 9:16 e redimensiona para 1080x1920.
    """
    cap = cv2.VideoCapture(video_entrada)
    if not cap.isOpened():
        raise RuntimeError(f"Erro ao abrir vídeo: {video_entrada}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_in = cap.get(cv2.CAP_PROP_FPS) or fps
    crop_w = int(h * 9.0 / 16.0)
    if crop_w > w:
        crop_w = w

    print("[SMART CROP 9:16] Calculando rastreamento de ação...")
    trajetoria = calcular_trajetoria_camera(video_entrada)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(video_saida, fourcc, fps_in, (1080, 1920))

    frame_idx = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    print(f"[SMART CROP 9:16] Renderizando {len(trajetoria)} frames verticais...")

    while cap.isOpened() and frame_idx < len(trajetoria):
        ret, frame = cap.read()
        if not ret:
            break

        x_crop = trajetoria[frame_idx]
        crop_frame = frame[0:h, x_crop:x_crop + crop_w]
        resized = cv2.resize(crop_frame, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)

        out.write(resized)
        frame_idx += 1

    cap.release()
    out.release()
    print(f"[SMART CROP 9:16] Vídeo vertical gerado com sucesso em: {video_saida}")
    return video_saida

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python smart_crop_916.py <in.mp4> <out_916.mp4>")
        sys.exit(1)
    renderizar_smart_crop_916(sys.argv[1], sys.argv[2])
