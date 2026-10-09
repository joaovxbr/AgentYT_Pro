"""Contrato da montagem longa: um relógio, uma fonte por trecho e validação antes do render."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path


def duracao(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True)
    if r.returncode:
        raise ValueError(f"ffprobe falhou: {path}: {r.stderr.strip()}")
    return float(r.stdout.strip())


def carregar(projeto: Path) -> dict:
    return json.loads((projeto / "timeline.json").read_text(encoding="utf-8"))


def fonte(projeto: Path, clip: str) -> Path:
    origem = Path(clip)
    if origem.is_absolute() or ".." in origem.parts:
        raise ValueError(f"fonte fora do projeto: {clip}")
    return projeto / (origem if len(origem.parts) > 1 else Path("clips_raw") / origem)


def validar(projeto: Path, timeline: dict, audio: Path, *, verificar_fontes: bool = True) -> list[str]:
    erros = []
    segmentos = timeline.get("segments", [])
    if not segmentos:
        return ["timeline sem segments"]
    try:
        fim_audio = duracao(audio)
    except (ValueError, OSError) as exc:
        return [str(exc)]
    anterior = 0.0
    cache = {}
    for i, s in enumerate(segmentos):
        try:
            inicio, fim, src = (float(s[k]) for k in ("start", "end", "src"))
            if not all(math.isfinite(v) for v in (inicio, fim, src)):
                raise ValueError("número não finito")
            if abs(inicio - anterior) > 0.045:
                erros.append(f"segmento {i}: lacuna/sobreposição em {anterior:.3f} → {inicio:.3f}s")
            if fim <= inicio or src < 0:
                erros.append(f"segmento {i}: intervalo inválido")
            path = fonte(projeto, s["clip"])
            if not path.is_file():
                erros.append(f"segmento {i}: fonte ausente: {path}")
            elif verificar_fontes:
                if path not in cache:
                    cache[path] = duracao(path)
                if src + fim - inicio > cache[path] + 0.04:
                    erros.append(f"segmento {i}: trecho excede a fonte ({cache[path]:.2f}s)")
            anterior = fim
        except (KeyError, TypeError, ValueError, OSError) as exc:
            erros.append(f"segmento {i}: {exc}")
    if abs(anterior - fim_audio) > 0.05:
        erros.append(f"timeline termina em {anterior:.3f}s; áudio em {fim_audio:.3f}s")
    return erros
