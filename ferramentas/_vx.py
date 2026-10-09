"""Ponte ferramentas/ -> nucleo vx/ (raiz do repo).

Os modulos de ferramentas/ sao importados com ferramentas/ no sys.path; o pacote
`vx` mora na raiz. `from _vx import config, projeto` garante a raiz no path e
reexporta os modulos do nucleo sem cada arquivo repetir o ajuste.
"""
import sys
from pathlib import Path

_RAIZ = str(Path(__file__).resolve().parents[1])
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from vx import ambiente, config, projeto  # noqa: E402,F401

ambiente.garantir_path()
