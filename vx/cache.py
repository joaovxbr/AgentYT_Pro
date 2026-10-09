"""Cache de etapa por hash de entrada — reaproveitar ENTRE execucoes.

Diferenca em relacao ao checkpoint (`vx/checkpoint.py`), que e a confusao mais
facil de cometer aqui:

- **checkpoint** responde "posso retomar esta execucao?". O escopo e UM `run_id`:
  o registro mora em `qa/esteira/<run_id>/_checkpoint.json` e morre com a execucao.
- **cache** responde "esta entrada ja foi processada alguma vez, por qualquer
  execucao?". O escopo e o PROJETO: o registro mora em `qa/cache/` e sobrevive
  entre execucoes.

Sem isso, cada `--resume` (Fase 2) so ajuda dentro da propria execucao, e a Fase 3
so tornou a etapa mais barata de *chamar*. Aqui a etapa nem e chamada.

Caso concreto: trocar um unico clipe de fundo muda o hash de `timeline`, o que
reescreve a timeline -- mas `stems`, `transcrever` e `sincronizar` nao dependem
disso. Antes, o rebuild re-separava o audio com Demucs na GPU e rodava o Whisper
de novo, por nada.

**O cache nunca inventa o que e uma entrada.** Quem manda e o `le` declarado em
`vx/etapas.py`, exatamente como no checkpoint -- a mesma primitiva
(`checkpoint.hash_entradas`) calcula o hash nos dois casos, entao cache e retomada
nunca discordam sobre o que "mesma entrada" significa.

**Falha fechada.** Reaproveitar errado produz video errado em silencio; refazer
custa tempo. Faltando qualquer prova (hash diferente, saida sumiu, saida vazia,
registro ilegivel, etapa declarada `nao_cacheavel`), a resposta e `rodar`.

**Garantias:**
1. Consultar o cache NUNCA derruba a esteira: qualquer erro de I/O vira `rodar`.
2. Gravar NUNCA derruba a esteira (mesmo padrao de `metrics`/`checkpoint`).
3. Nao guarda conteudo de producao -- so hashes, caminhos e tamanhos.

Formato (`qa/cache/<etapa>.json`):

    {
      "etapa": "stems",
      "atualizado_em": "...",
      "entradas": {
        "ab12...": {"saidas": [{"caminho": "...", "bytes": 1234}, ...],
                    "criado_em": "...", "usos": 3}
      }
    }

`usos` conta quantas vezes o resultado foi reaproveitado -- e o dado que mostra
se o cache esta pagando o proprio custo.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import checkpoint as _checkpoint

#: Subpasta do projeto onde o cache vive (fora de `qa/esteira/<run_id>`, de proposito).
DIR = ("qa", "cache")

#: Decisao de cache.
REAPROVEITAR = "reaproveitar"
RODAR = "rodar"

#: Numero de entradas distintas guardadas por etapa. Etapas reais oscilam entre
#: poucas entradas (a letra muda raramente) e muitas (cada clipe novo muda a
#: timeline); 8 cobre o vai-e-vem de producao sem crescer para sempre.
LIMITE_POR_ETAPA = 8


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_dir(projeto: Path) -> Path:
    return Path(projeto).joinpath(*DIR)


def hash_obj(dados) -> str:
    """Hash canonico de uma estrutura JSON-serializavel.

    Existe porque seis modulos (`manga_auto_pipeline`, `semantic_scene_matcher`,
    `graphic_auto_pipeline`, `cenas_ia_pipeline`, `titulos_pipeline`,
    `chroma_auto`) mantinham copias quase iguais deste calculo, com divergencias
    reais: uns passavam `default=str` (senao `Path`/`datetime` no payload
    explodem) e outros nao. Uma copia que explode num caso legitimo derruba a
    etapa; uma copia sem `sort_keys` produz hash diferente para o mesmo dado.

    Ordena chaves e usa separadores compactos para que o MESMO dado produza
    SEMPRE o MESMO hash -- do contrario o cache nunca acerta.
    """
    raw = json.dumps(dados, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Decisao:
    """Resultado da consulta. `motivo` sempre explica, para o log e o relatorio."""

    acao: str
    motivo: str = ""
    saidas: list[str] = field(default_factory=list)
    bytes: int = 0

    @property
    def reaproveitar(self) -> bool:
        return self.acao == REAPROVEITAR


def _caminho_etapa(projeto: Path, etapa: str) -> Path:
    # Nome de etapa vem de `vx/etapas.py` (slug-safe), mas nunca confie: um path
    # traverse aqui escreveria fora do projeto.
    seguro = "".join(c for c in str(etapa) if c.isalnum() or c in "-_")
    if not seguro:
        seguro = "etapa"
    return cache_dir(projeto) / f"{seguro}.json"


def carregar(projeto: Path, etapa: str) -> dict:
    """Le o registro da etapa. Ausente/ilegivel -> vazio (tudo roda)."""
    caminho = _caminho_etapa(projeto, etapa)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"etapa": etapa, "entradas": {}}
    if not isinstance(dados, dict):
        return {"etapa": etapa, "entradas": {}}
    entradas = dados.get("entradas")
    if not isinstance(entradas, dict):
        return {"etapa": etapa, "entradas": {}}
    return dados


def gravar(projeto: Path, etapa: str, dados: dict) -> Path | None:
    """Escreve o registro. Nunca levanta -- cache nao pode derrubar a esteira."""
    caminho = _caminho_etapa(projeto, etapa)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_suffix(caminho.suffix + ".tmp")
        tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(caminho)
        return caminho
    except OSError:
        return None


def _podar(entradas: dict, limite: int = LIMITE_POR_ETAPA) -> dict:
    """Mantem as `limite` entradas mais recentes (mais usadas primeiro no empate)."""
    if len(entradas) <= limite:
        return entradas
    ordenadas = sorted(
        entradas.items(),
        key=lambda kv: (kv[1].get("criado_em", ""), kv[1].get("usos", 0)),
        reverse=True,
    )
    return dict(ordenadas[:limite])


def pode_reaproveitar(etapa: str, padroes_le, padroes_escreve, projeto: Path,
                      slug: str, *, registro: dict | None = None) -> Decisao:
    """Decide se a etapa pode ser pulada com base em execucoes ANTERIORES.

    Mesmas tres provas do checkpoint, com um escopo diferente: o hash das
    entradas atuais tem que casar com alguma entrada JA PROCESSADA, e todas as
    saidas daquele registro tem que continuar no lugar.
    """
    if registro is None:
        registro = carregar(projeto, etapa)
    entradas = registro.get("entradas") or {}
    if not entradas:
        return Decisao(RODAR, "cache vazio para a etapa")

    try:
        atual = _checkpoint.hash_entradas(padroes_le, projeto, slug)
    except Exception:  # noqa: BLE001 - falha fechada: nao saber o hash e nao cachear
        return Decisao(RODAR, "nao foi possivel calcular o hash das entradas")

    reg = entradas.get(atual)
    if not isinstance(reg, dict):
        return Decisao(RODAR, "entradas mudaram desde o ultimo resultado")

    # Saidas nominais declaradas tem que existir E nao estar vazias.
    try:
        ok_declaradas, faltando = _checkpoint.saidas_existem(padroes_escreve, projeto, slug)
    except Exception:  # noqa: BLE001
        return Decisao(RODAR, "nao foi possivel validar as saidas")
    if not ok_declaradas:
        return Decisao(RODAR, f"saida ausente/vazia: {', '.join(faltando[:4])}")

    # Saidas REGISTRADAS: o que a execucao realmente produziu. Uma saida que foi
    # apagada depois (ex.: render apagado na mao) tem que derrubar o cache, mesmo
    # que as declaradas continuem (o `escreve` de algumas etapas e glob).
    caminhos: list[str] = []
    total = 0
    for item in reg.get("saidas") or ():
        p = str(item.get("caminho", ""))
        if not p:
            continue
        caminho = Path(projeto) / p
        if not caminho.is_file() or caminho.stat().st_size == 0:
            return Decisao(RODAR, f"saida apagada desde o cache: {p}")
        caminhos.append(p)
        total += caminho.stat().st_size

    return Decisao(REAPROVEITAR, "mesmas entradas e saidas no lugar",
                   saidas=caminhos, bytes=total)


def registrar(etapa: str, padroes_le, padroes_escreve, projeto: Path, slug: str) -> bool:
    """Guarda o resultado da etapa executada agora. False se nao deu para gravar."""
    try:
        chave = _checkpoint.hash_entradas(padroes_le, projeto, slug)
    except Exception:  # noqa: BLE001
        return False

    saidas: list[dict] = []
    total_bytes = 0
    for caminho in _checkpoint._expandir(padroes_escreve, projeto, slug):  # noqa: SLF001
        try:
            if caminho.is_file():
                bytes_ = caminho.stat().st_size
                saidas.append({"caminho": caminho.relative_to(projeto).as_posix(),
                               "bytes": bytes_})
                total_bytes += bytes_
        except (OSError, ValueError):
            continue

    registro = carregar(projeto, etapa)
    entradas = dict(registro.get("entradas") or {})
    anterior = entradas.get(chave) or {}
    usos = int(anterior.get("usos", 0))
    entradas[chave] = {"saidas": saidas, "bytes": total_bytes,
                       "criado_em": _agora(), "usos": usos}
    registro.update({"etapa": etapa, "atualizado_em": _agora(),
                     "entradas": _podar(entradas)})
    return gravar(projeto, etapa, registro) is not None


def confirmar_uso(etapa: str, padroes_le, projeto: Path, slug: str) -> None:
    """Incrementa `usos` da entrada correspondente ao estado atual. Nunca levanta.

    E o dado que mostra se o cache paga o proprio custo: uma entrada com `usos`
    alto e uma etapa que vale manter; uma que nunca repete nao compensa.
    """
    try:
        chave = _checkpoint.hash_entradas(padroes_le, projeto, slug)
    except Exception:  # noqa: BLE001
        return
    registro = carregar(projeto, etapa)
    entradas = registro.get("entradas") or {}
    if chave not in entradas:
        return
    entradas[chave]["usos"] = int(entradas[chave].get("usos", 0)) + 1
    registro["entradas"] = entradas
    gravar(projeto, etapa, registro)


def invalidar(projeto: Path, etapa: str | None = None) -> int:
    """Apaga o cache (da etapa ou do projeto). Devolve quantos arquivos removeu."""
    alvo = cache_dir(projeto)
    if not alvo.is_dir():
        return 0
    arquivos = ([_caminho_etapa(projeto, etapa)] if etapa
                else sorted(alvo.glob("*.json")))
    removidos = 0
    for caminho in arquivos:
        try:
            if caminho.is_file():
                caminho.unlink()
                removidos += 1
        except OSError:
            continue
    return removidos


def resumo(projeto: Path) -> dict:
    """O que esta cacheado e quanto espaco ocupa -- para `estudio.py cache`."""
    alvo = cache_dir(projeto)
    etapas: dict[str, dict] = {}
    if alvo.is_dir():
        for caminho in sorted(alvo.glob("*.json")):
            dados = carregar(projeto, caminho.stem)
            entradas = dados.get("entradas") or {}
            etapas[caminho.stem] = {
                "variacoes": len(entradas),
                "usos": sum(int(v.get("usos", 0)) for v in entradas.values()
                            if isinstance(v, dict)),
                "bytes": sum(int(v.get("bytes", 0)) for v in entradas.values()
                             if isinstance(v, dict)),
                "atualizado_em": dados.get("atualizado_em"),
            }
    return {"diretorio": str(alvo), "etapas": etapas,
            "total_variacoes": sum(e["variacoes"] for e in etapas.values()),
            "total_bytes": sum(e["bytes"] for e in etapas.values())}
