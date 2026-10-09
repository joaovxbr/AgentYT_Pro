"""Lock de execucao por projeto com verificacao de PID.

Problema que resolve: `.esteira.lock` era criado com O_EXCL e, se o processo
morresse (kill, terminal fechado), ficava orfao e bloqueava a proxima esteira
ate alguem apagar na mao. Agora:

- lock com JSON {"pid", "run_id", "inicio"}; se o PID nao existe mais, o lock
  e considerado orfao e e retomado (registrado em `lock_orfao_removido`);
- lock ilegivel (formato desconhecido) e tratado como VIVO: nunca apagamos o que
  nao entendemos (falha fechada).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class LockOcupado(RuntimeError):
    pass


def pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            # acesso negado = processo existe mas e de outro usuario
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ler(lock: Path):
    try:
        dados = json.loads(lock.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) and isinstance(dados.get("pid"), int) else None
    except (OSError, ValueError):
        return None


def adquirir(lock: Path, run_id: str) -> dict:
    """Cria o lock. Retoma lock orfao (PID morto). Levanta LockOcupado se vivo."""
    lock = Path(lock)
    info = {"pid": os.getpid(), "run_id": run_id,
            "inicio": datetime.now(timezone.utc).isoformat()}
    for tentativa in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            dono = _ler(lock)
            if tentativa == 0 and dono is not None and not pid_vivo(dono["pid"]):
                lock.unlink(missing_ok=True)
                info["lock_orfao_removido"] = dono
                continue
            raise LockOcupado(
                f"Esteira ja bloqueada: {lock} (dono: {dono or 'formato desconhecido'}). "
                "Verifique o processo antes de remover o lock.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(info, f)
        return info
    raise LockOcupado(f"Esteira ja bloqueada: {lock}")


def liberar(lock: Path, run_id: str) -> None:
    """Remove o lock so se ainda for nosso (mesmo run_id)."""
    lock = Path(lock)
    dono = _ler(lock)
    if dono is not None and dono.get("run_id") == run_id:
        lock.unlink(missing_ok=True)
