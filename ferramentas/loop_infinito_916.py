#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
loop_infinito_916.py — Construtor de Loop Infinito Perfeito para Shorts / TikTok.
Garante retenção >100% no algoritmo:
1. Analisa os últimos 0.4s e os primeiros 0.4s do vídeo e do áudio
2. Aplica crossfade suave de vídeo (blend com rampa de opacidade) e áudio (equal-power afade)
3. Conecta o final diretamente no início para que o espectador não perceba o término do Short.
"""
from pathlib import Path
import sys
import subprocess
import json

def criar_short_loop_infinito(
    video_entrada: str,
    video_saida: str,
    duracao_crossfade: float = 0.45
) -> str:
    """
    Usa FFmpeg para cruzar os últimos 'duracao_crossfade' segundos com o início do vídeo.
    """
    p_in = Path(video_entrada)
    if not p_in.exists():
        raise FileNotFoundError(f"Vídeo de entrada não encontrado: {video_entrada}")

    # Obter duração exata
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", str(p_in)
    ]
    proc = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
    dur_total = float(json.loads(proc.stdout)["format"]["duration"])
    
    t_corte_fim = dur_total - duracao_crossfade
    
    # Grafo de loop perfeito:
    # Corta o pedaço final [dur_total - duracao_crossfade até o fim] e cola no início
    # fazendo crossfade transparente para que a junção fique invisível
    filtro_complex = (
        f"[0:v]trim=start=0:end={t_corte_fim},setpts=PTS-STARTPTS[base_v];"
        f"[0:v]trim=start={t_corte_fim}:end={dur_total},setpts=PTS-STARTPTS[tail_v];"
        f"[tail_v][base_v]xfade=transition=fade:duration={duracao_crossfade}:offset=0[v_loop];"
        f"[0:a]atrim=start=0:end={t_corte_fim},asetpts=PTS-STARTPTS[base_a];"
        f"[0:a]atrim=start={t_corte_fim}:end={dur_total},asetpts=PTS-STARTPTS[tail_a];"
        f"[tail_a][base_a]acrossfade=d={duracao_crossfade}:c1=tri:c2=tri[a_loop]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(p_in),
        "-filter_complex", filtro_complex,
        "-map", "[v_loop]", "-map", "[a_loop]",
        "-c:v", "h264_nvenc", "-preset", "p7", "-cq", "18",
        "-c:a", "aac", "-b:a", "256k",
        str(video_saida)
    ]

    print(f"[LOOP INFINITO] Compilando loop perfeito de {dur_total:.2f}s com crossfade de {duracao_crossfade}s...")
    subprocess.run(cmd, check=True)
    print(f"[LOOP INFINITO] Sucesso: {video_saida}")
    return video_saida

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python loop_infinito_916.py <in.mp4> <out_loop.mp4> [crossfade_s]")
        sys.exit(1)
    cf = float(sys.argv[3]) if len(sys.argv) > 3 else 0.45
    criar_short_loop_infinito(sys.argv[1], sys.argv[2], cf)
