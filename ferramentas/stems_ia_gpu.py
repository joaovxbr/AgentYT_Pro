#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stems_ia_gpu.py — Separação de Stems em 4 Canais via Demucs (Meta AI) acelerado na RTX 3090.
Separa qualquer música do Suno em:
- vocals.wav (Voz limpa para Whisper e sincronia cirúrgica de karaoke)
- drums.wav (Bateria/Caixa/Hi-hats para triggers de flash e transição)
- bass.wav (808 / Sub-grave puro para distorção e camera shake)
- other.wav (Melodia / Instrumentos)
"""
from pathlib import Path
import sys
import subprocess
import shutil

def separar_stems_gpu(audio_path: str, pasta_saida: Path, modelo: str = "htdemucs") -> dict:
    """
    Roda Demucs com aceleração CUDA nativa na RTX 3090.
    Retorna o dicionário de caminhos dos stems gerados.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m", "demucs.separate",
        "-n", modelo,
        "-d", "cuda",
        "-o", str(pasta_saida),
        str(audio_path)
    ]

    print(f"[DEMUCS GPU] Separando stems de {audio_path.name} na RTX 3090...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("[AVISO] Demucs GPU retornou erro, tentando CPU...", proc.stderr)
        cmd[cmd.index("cuda")] = "cpu"
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)

    # O Demucs salva em pasta_saida / modelo / nome_do_audio /
    pasta_resultado = pasta_saida / modelo / audio_path.stem

    stems = {
        "vocals": pasta_resultado / "vocals.wav",
        "drums": pasta_resultado / "drums.wav",
        "bass": pasta_resultado / "bass.wav",
        "other": pasta_resultado / "other.wav"
    }

    # Copia para raiz de pasta_saida para acesso direto
    # Move para a raiz de pasta_saida (acesso direto) e apaga a arvore do Demucs:
    # manter as duas copias dobrava ~120 MB por projeto sem uso.
    stems_finais = {}
    for nome, p in stems.items():
        if p.exists():
            destino = pasta_saida / f"{audio_path.stem}_{nome}.wav"
            shutil.move(str(p), str(destino))
            stems_finais[nome] = str(destino)
    shutil.rmtree(pasta_saida / modelo, ignore_errors=True)

    return stems_finais

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python stems_ia_gpu.py <musica.mp3|wav> [pasta_saida]")
        sys.exit(1)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("stems_saida")
    res = separar_stems_gpu(sys.argv[1], out)
    print("Stems separados com sucesso:", res)
