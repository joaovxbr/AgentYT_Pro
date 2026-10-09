"""Ambiente do estudio: binarios externos resolvidos sem depender do PATH do usuario.

Problema que resolve: ffmpeg/ffprobe/yt-dlp vivem em `ferramentas/bin`, mas o
codigo inteiro chama `shutil.which("ffmpeg")` ou o nome solto "ffprobe". Num
shell/agente sem esse PATH a esteira reprovava ("ffmpeg nao encontrado").

`garantir_path()` coloca `ferramentas/bin` na frente do PATH do processo. Como
subprocessos herdam o ambiente, basta chamar uma vez na entrada (estudio.py).
Idempotente.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BIN = RAIZ / "ferramentas" / "bin"
BINARIOS = ("ffmpeg", "ffprobe")


def garantir_path(bin_dir: Path = BIN) -> bool:
    """Prependa `bin_dir` ao PATH se existir e ainda nao estiver la. True se alterou."""
    bin_dir = Path(bin_dir)
    if not bin_dir.is_dir():
        return False
    atual = os.environ.get("PATH", "")
    partes = [p for p in atual.split(os.pathsep) if p]
    alvo = os.path.normcase(str(bin_dir.resolve()))
    if any(os.path.normcase(os.path.abspath(p)) == alvo for p in partes):
        return False
    os.environ["PATH"] = str(bin_dir) + os.pathsep + atual
    return True


def binario(nome: str) -> str:
    """Caminho absoluto do binario (prioriza ferramentas/bin) ou o nome solto."""
    garantir_path()
    return shutil.which(nome) or nome


def diagnostico() -> dict:
    """Estado dos binarios externos, para `estudio.py doutor` e o preflight."""
    garantir_path()
    return {nome: shutil.which(nome) for nome in BINARIOS}
