"""Fixtures hermeticas dos testes.

Problema que resolve: alguns testes liam `projetos/<slug>/...` do repositorio
(`projetos/sasuke/projeto.json`, `projetos/sasuke/transcricao_canonica.json`,
`projetos/sasuke/motion_manga_ato2_rinnegan.json`). Como `projetos/` e material de
producao (grande, pessoal, nao versionado), a suite ficava VERMELHA num clone limpo
-- e "suite verde" e a regra sagrada 6 do AGENTS.md.

Regra: teste que precisa de um projeto monta o seu, com estes helpers. Nunca le
`projetos/` real. O conteudo minimo reproduz exatamente o que o contrato sob teste
precisa; nao e uma copia do projeto de producao.

Uso:

    from _fixtures import projeto_sasuke_canonico

    with projeto_sasuke_canonico() as (raiz, projeto):
        ...  # raiz/sasuke/transcricao_canonica.json existe
"""
from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

# ---------------------------------------------------------------------------
# Transcricao canonica do Sasuke (Ato 3: linhas 17..21 em 62..78 s).
# `tests/test_motion_manga_ato3_*.py` indexa por POSICAO e por tempo, entao as
# linhas 0..21 precisam existir na ordem. As demais linhas sao preenchidas com
# versos neutros: o contrato sob teste so olha os indices/tempos citados.
# ---------------------------------------------------------------------------
LIMITE = 0.6
_DUR = 0.9
_VERSAO = "fixture-tests-v1"


def _palavras(texto: str, inicio: float, fim: float) -> list[dict]:
    """Distribui os tokens de `texto` uniformemente entre `inicio` e `fim`."""
    tokens = texto.split()
    if not tokens:
        return []
    passo = (fim - inicio) / len(tokens)
    return [
        {"word": t, "start": round(inicio + i * passo, 3),
         "end": round(inicio + (i + 1) * passo, 3), "probability": 0.9}
        for i, t in enumerate(tokens)
    ]


def _linha(indice: int, texto: str, inicio: float, fim: float) -> dict:
    return {
        "index": indice,
        "text": texto,
        "start": round(inicio, 3),
        "end": round(fim, 3),
        "words": _palavras(texto, inicio, fim),
        "origem": "fixture",
    }


# Ato 3 -- os 5 versos que os testes realmente verificam (indices 17..21).
_ATO3 = [
    (17, "CHAMAS DO Amaterasu NÃO VÃO SE APAGAR", 62.00, 64.80),
    (18, "Susanoo perfeito protege o meu olhar", 65.00, 67.60),
    (19, "O Hokage me teme, o mundo vai lembrar", 68.00, 70.60),
    (20, "Kirin desce do céu pra te apagar", 71.00, 73.60),
    (21, "O último Uchiha que o mundo já viu", 74.00, 76.60),
]

# Versos neutros para as linhas 0..16 (nao sao verificados por nenhum teste).
_VERSO_NEUTRO = "VERSO NEUTRO PARA FIXTURE DO CONTRATO"


def transcricao_canonica() -> dict:
    """`transcricao_canonica.json` minimo com indices 0..21 e o Ato 3 correto."""
    linhas: list[dict] = []
    for i in range(17):
        inicio = i * 3.0
        linhas.append(_linha(i, _VERSO_NEUTRO, inicio, inicio + 2.0))
    linhas.append(_linha(17, _ATO3[0][1], _ATO3[0][2], _ATO3[0][3]))
    for indice, texto, inicio, fim in _ATO3[1:]:
        linhas.append(_linha(indice, texto, inicio, fim))
    return {"versao": _VERSAO, "limite": LIMITE, "lines": linhas}


def manifesto_sasuke() -> dict:
    """`projeto.json` minimo: so o vocabulario canonico sob teste."""
    return {
        "faixa": "FIXTURE",
        "personagem": "Uchiha Sasuke",
        "anime": "Naruto Shippuden",
        "titulo_linhas": ["O ÚLTIMO UCHIHA"],
        "cor": {"destaque": "#7c3aed", "destaque_claro": "#a78bfa"},
        "vocabulario": {
            "termos": [
                "Mangekyō", "Amaterasu", "Susanoo", "Hokage", "Kirin", "Uchiha",
                "Rinnegan", "Danzō", "Chidori", "Kusanagi", "Itachi", "Naruto",
            ],
            "variantes": {"tomoes": "tomoe", "manjeco": "Mangekyō",
                          "manjekyo": "Mangekyō", "jitori": "Chidori"},
        },
    }


def motion_manga_ato2() -> dict:
    """`motion_manga_ato2_rinnegan.json`: 19,6 s / 588 quadros, 8 linhas, 8 planos."""
    frames = 588
    duracao = frames / 30.0  # 19.6
    planos = [
        {"start": 0.0, "end": 2.0, "rinnegan_fx": True, "panels_3": True},
        {"start": 2.0, "end": 4.0, "amenotejikara": True},
        {"start": 4.0, "end": 6.0, "panels_3": True},
        {"start": 6.0, "end": 8.0, "susanoo_arrow": True},
        {"start": 8.0, "end": 11.0, "rinnegan_fx": True},
        {"start": 11.0, "end": 14.0, "amenotejikara": True, "panels_3": True},
        {"start": 14.0, "end": 17.0, "susanoo_arrow": True},
        {"start": 17.0, "end": round(duracao, 3), "rinnegan_fx": True},
    ]
    return {"start": 78.8, "frames": frames, "lines": [22, 23, 24, 25, 26, 27, 28, 29],
            "shots": planos, "versao": _VERSAO}


@contextmanager
def projeto_sasuke_canonico(*, com_ato2: bool = True):
    """Cria um `projetos/` temporario com o projeto `sasuke` minimo.

    Entrega `(raiz, projeto)` onde `raiz/sasuke/...` existe; ao sair, apaga tudo.
    """
    with tempfile.TemporaryDirectory(prefix="vx_fixture_") as tmp:
        raiz = Path(tmp) / "projetos"
        projeto = raiz / "sasuke"
        projeto.mkdir(parents=True)
        (projeto / "projeto.json").write_text(
            json.dumps(manifesto_sasuke(), ensure_ascii=False, indent=2), encoding="utf-8")
        (projeto / "transcricao_canonica.json").write_text(
            json.dumps(transcricao_canonica(), ensure_ascii=False, indent=2), encoding="utf-8")
        if com_ato2:
            (projeto / "motion_manga_ato2_rinnegan.json").write_text(
                json.dumps(motion_manga_ato2(), ensure_ascii=False, indent=2), encoding="utf-8")
        yield raiz, projeto
