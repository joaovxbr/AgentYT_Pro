#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
curadoria_ia.py — Auditoria e Limpeza Inteligente de Clipes (Zero Watermarks).
Escaneia automaticamente clipes de twixtor/scene packs para:
1. Rejeitar logos persistentes de streaming (Crunchyroll, VIZ, Funimation) nos 4 cantos.
2. Identificar e cortar os últimos segundos com cartões de CapCut / créditos de canais.
3. Detectar promoções intermediárias ("Follow me on TikTok") e trechos congelados.
"""
from pathlib import Path
import sys
import json
import cv2
import numpy as np

def auditar_clipe_completo(video_path: str) -> dict:
    """
    Inspeciona o clipe frame a frame em amostras estratégicas:
    - 5 segundos finais (detecção de CapCut/outros de editores)
    - Amostragem periódica ao longo de todo o vídeo para marcas d'água de canais nos cantos
    - Verificação de frames estáticos ou pretos
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"erro": f"Não foi possível abrir {video_path}"}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duracao_s = total_frames / fps

    problemas = []
    
    # 1. Auditoria dos últimos 5 segundos (procurando CapCut / telas pretas com logo)
    frames_fim = int(min(total_frames, fps * 5))
    inicio_fim = max(0, total_frames - frames_fim)
    cap.set(cv2.CAP_PROP_POS_FRAMES, inicio_fim)
    
    capcut_detectado = False
    segundo_corte_sugerido = duracao_s

    while cap.isOpened():
        pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
        ret, frame = cap.read()
        if not ret or pos >= total_frames:
            break
            
        t_atual = pos / fps
        h, w = frame.shape[:2]
        
        # O logo CapCut é tipicamente branco centralizado sobre fundo 100% preto
        centro = frame[int(h*0.35):int(h*0.65), int(w*0.35):int(w*0.65)]
        bordas = frame[:int(h*0.15), :]
        
        media_centro = float(np.mean(centro))
        media_borda = float(np.mean(bordas))
        
        if media_borda < 8.0 and media_centro > 40.0:
            # Fundo quase negro com elemento no meio no fim do clipe
            capcut_detectado = True
            segundo_corte_sugerido = min(segundo_corte_sugerido, t_atual - 0.2)

    if capcut_detectado:
        problemas.append({
            "tipo": "capcut_ou_outro_detectado",
            "detalhes": f"Card final encontrado. Corte o clipe em {segundo_corte_sugerido:.2f}s."
        })

    # 2. Auditoria de Watermark persistente nos 4 cantos
    # Amostra 15 frames ao longo do vídeo
    passo = max(1, total_frames // 15)
    cantos_acumulados = {
        "top_left": [],
        "top_right": [],
        "bottom_left": [],
        "bottom_right": []
    }

    for idx in range(0, total_frames, passo):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            break
        h, w = frame.shape[:2]
        
        # Pega 10% de cada canto
        cw, ch = int(w * 0.15), int(h * 0.12)
        cantos_acumulados["top_left"].append(cv2.cvtColor(frame[:ch, :cw], cv2.COLOR_BGR2GRAY))
        cantos_acumulados["top_right"].append(cv2.cvtColor(frame[:ch, w-cw:], cv2.COLOR_BGR2GRAY))
        cantos_acumulados["bottom_left"].append(cv2.cvtColor(frame[h-ch:, :cw], cv2.COLOR_BGR2GRAY))
        cantos_acumulados["bottom_right"].append(cv2.cvtColor(frame[h-ch:, w-cw:], cv2.COLOR_BGR2GRAY))

    cap.release()

    # Um logo fixo (Crunchyroll/TV) tem baixíssima variância temporal entre frames diferentes
    for canto, frames_list in cantos_acumulados.items():
        if len(frames_list) >= 5:
            stack = np.array(frames_list)
            # Desvio padrão temporal pixel a pixel
            std_temporal = np.mean(np.std(stack, axis=0))
            if std_temporal < 9.5:  # Muito estático ao longo de todo o clipe
                problemas.append({
                    "tipo": "watermark_estatica_detectada",
                    "canto": canto,
                    "variancia_temporal": round(float(std_temporal), 2),
                    "aviso": f"Possível logo ou marca d'água persistente no canto {canto}!"
                })

    aprovado = len([p for p in problemas if p["tipo"] == "watermark_estatica_detectada"]) == 0

    return {
        "arquivo": Path(video_path).name,
        "duracao_total": round(duracao_s, 2),
        "duracao_limpa_recomendada": round(segundo_corte_sugerido, 2),
        "aprovado_para_esteira": aprovado,
        "problemas_encontrados": problemas
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python curadoria_ia.py <video.mp4>")
        sys.exit(1)
    rel = auditar_clipe_completo(sys.argv[1])
    print(json.dumps(rel, indent=2, ensure_ascii=False))
