"""Configuracao em camadas: padrao do codigo < config/estudio.json < projeto.json.

- `secao(nome, padrao, manifesto)`: parametros editoriais (quantos cards, espacamento,
  guardas...). O padrao do codigo define as CHAVES validas; o config do estudio e o
  manifesto so podem mudar valores dessas chaves (chave desconhecida e ignorada e
  pega por teste, para nao virar erro silencioso de digitacao).
- `porteiro(nome, padrao)`: limiares de QA. Vem do codigo < config/porteiros.json e
  NUNCA do projeto: um projeto nao pode afrouxar um porteiro (decisao 002).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DIR = RAIZ / "config"
ESTUDIO = CONFIG_DIR / "estudio.json"
PORTEIROS = CONFIG_DIR / "porteiros.json"


def _ler(path: Path) -> dict:
    try:
        dados = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _mesclar(base: dict, extra, chaves) -> dict:
    if isinstance(extra, dict):
        for k in chaves:
            if k in extra:
                base[k] = copy.deepcopy(extra[k])
    return base


def secao(nome: str, padrao: dict, manifesto: dict | None = None, *,
          chave_manifesto: str | None = None, arquivo: Path = ESTUDIO) -> dict:
    """Padrao do codigo < config/estudio.json[nome] < manifesto[chave_manifesto or nome]."""
    cfg = copy.deepcopy(padrao)
    _mesclar(cfg, _ler(arquivo).get(nome), padrao)
    _mesclar(cfg, (manifesto or {}).get(chave_manifesto or nome), padrao)
    return cfg


def porteiro(nome: str, padrao: dict, *, arquivo: Path = PORTEIROS) -> dict:
    """Limiares de QA: padrao do codigo < config/porteiros.json[nome]. Sem override de projeto."""
    return _mesclar(copy.deepcopy(padrao), _ler(arquivo).get(nome), padrao)
