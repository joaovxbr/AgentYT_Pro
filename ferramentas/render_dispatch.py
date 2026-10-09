#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_dispatch.py — encode acelerado por GPU (NVENC), sem fallback para CPU.

A regra do canal: **usamos GPU, porque CPU nao da certo** (lento e engasga).
Este modulo centraliza TODA chamada de encode do estudio. Nenhuma ferramenta
deve chamar `ffmpeg` de encode direto — todas passam por aqui, para que a
politica de GPU seja unica e as ferramentas nao se dupliquem (a regra da porta
unica vale tambem para o render).

Uso como biblioteca:

    from render_dispatch import encode, tem_nvenc, ffmpeg_bin

    encode(
        entradas=["-i", "in.mp4"],
        filtro_v="scale=1920:1080",
        saida="out.mp4",
        args_audio=["-c:a", "aac", "-b:a", "256k"],
    )

Uso como CLI (diagnostico):

    python render_dispatch.py doutor
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import sys
from typing import List, Optional, Sequence

# ffmpeg/ffprobe de ferramentas/bin no PATH do processo (e dos subprocessos),
# sem depender do PATH configurado pelo usuario. Ver vx/ambiente.py.
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from vx import ambiente as _ambiente  # noqa: E402
_ambiente.garantir_path()


# ---------------------------------------------------------------------------
# Deteccao de ambiente
# ---------------------------------------------------------------------------

def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


@functools.lru_cache(maxsize=1)
def _encoders() -> str:
    try:
        out = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30,
        )
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


@functools.lru_cache(maxsize=1)
def tem_nvenc() -> bool:
    """True se o ffmpeg desta maquina tem o encoder h264_nvenc disponivel."""
    return "h264_nvenc" in _encoders()


@functools.lru_cache(maxsize=1)
def tem_gpu_nvidia() -> bool:
    """True se `nvidia-smi` responde — a GPU esta realmente presente e viva."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False
    try:
        r = subprocess.run(
            [exe, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def nome_gpu() -> str:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return "(sem nvidia-smi)"
    try:
        r = subprocess.run(
            [exe, "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip() or "(desconhecida)"
    except Exception:
        return "(erro ao consultar)"


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------

# Qualidade-alvo do canal: master 1080p limpo. NVENC usa -cq (constant quality),
# equivalente aproximado do CRF do x264. cq=19 ~ crf=18 do x264 em p7/slow.
NVENC_CQ_MASTER = "19"
X264_CRF_MASTER = "18"


def video_args(preferir_gpu: bool = True, cq: str = NVENC_CQ_MASTER,
               crf: str = X264_CRF_MASTER) -> List[str]:
    """Argumentos de codec de video. NVENC obrigatorio; indisponibilidade interrompe o encode."""
    if preferir_gpu and tem_nvenc() and tem_gpu_nvidia():
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p7",         # p7 = maxima qualidade do NVENC
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", cq,
            "-b:v", "0",             # deixa o -cq mandar
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
        ]
    raise RuntimeError('NVENC required by studio policy; CPU fallback forbidden.')


def encode(
    saida: str,
    entradas: Sequence[str],
    filtro_v: Optional[str] = None,
    filtro_complexo: Optional[str] = None,
    mapa: Optional[Sequence[str]] = None,
    args_audio: Optional[Sequence[str]] = None,
    args_extra: Optional[Sequence[str]] = None,
    preferir_gpu: bool = True,
    cq: str = NVENC_CQ_MASTER,
    faststart: bool = True,
    silencioso: bool = False,
) -> str:
    """Roda um encode via ffmpeg, preferindo a GPU (NVENC).

    NVENC obrigatorio. Falhas preservam o arquivo anterior.

    Retorna o caminho de saida.
    """
    from pathlib import Path
    from uuid import uuid4
    destino = Path(saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.stem + "." + uuid4().hex + ".partial" + destino.suffix)
    def montar(preferir_gpu_: bool) -> List[str]:
        cmd: List[str] = [ffmpeg_bin(), "-y", "-hide_banner"]
        cmd += list(entradas)
        if filtro_complexo:
            cmd += ["-filter_complex", filtro_complexo]
        elif filtro_v:
            cmd += ["-vf", filtro_v]
        if mapa:
            cmd += list(mapa)
        cmd += video_args(preferir_gpu=preferir_gpu_, cq=cq)
        if args_audio:
            cmd += list(args_audio)
        else:
            cmd += ["-c:a", "aac", "-b:a", "256k", "-ar", "48000"]
        if faststart:
            cmd += ["-movflags", "+faststart"]
        if args_extra:
            cmd += list(args_extra)
        cmd += [str(temporario)]
        return cmd

    usar_gpu = preferir_gpu and tem_nvenc() and tem_gpu_nvidia()
    cmd = montar(usar_gpu)
    if not silencioso:
        print("  [render] encode via GPU (NVENC)")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL)
        log = Path(str(saida) + '.encode.log')
        if r.returncode != 0:
            # log so em falha: sucesso nao deixa lixo ao lado de cada render
            log.write_text(r.stderr or '', encoding='utf-8')
            raise RuntimeError("ffmpeg/NVENC falhou no encode.\n" + _tail(r.stderr, retornar=True))
        log.unlink(missing_ok=True)
        if not temporario.is_file() or temporario.stat().st_size == 0:
            raise RuntimeError("ffmpeg terminou sem produzir um arquivo valido")
        temporario.replace(destino)
        return saida
    finally:
        temporario.unlink(missing_ok=True)


def _tail(texto: str, n: int = 12, retornar: bool = False):
    linhas = [l for l in (texto or "").splitlines() if l.strip()]
    trecho = "\n".join(linhas[-n:])
    if retornar:
        return trecho
    print("    " + trecho.replace("\n", "\n    "))
    return None


# ---------------------------------------------------------------------------
# CLI de diagnostico
# ---------------------------------------------------------------------------

def doutor() -> int:
    print("== render_dispatch: ambiente de encode ==")
    print(f"  ffmpeg:        {ffmpeg_bin()}")
    print(f"  GPU NVIDIA:    {'sim' if tem_gpu_nvidia() else 'NAO'}  ({nome_gpu()})")
    print(f"  encoder NVENC: {'sim (h264_nvenc)' if tem_nvenc() else 'NAO'}")
    if tem_nvenc() and tem_gpu_nvidia():
        print("  -> render acelerado por GPU ATIVO. Encodes usam h264_nvenc p7.")
        return 0
    print("  -> GPU indisponivel; encode bloqueado pela politica NVENC.")
    return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "doutor":
        sys.exit(doutor())
    print(__doc__)
