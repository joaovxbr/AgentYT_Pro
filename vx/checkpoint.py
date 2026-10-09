"""Checkpoint de execucao: retomar a esteira da etapa que falhou, nao do zero.

Problema que resolve: `quando="se_ausente"` em `vx/etapas.py` cobre BOOTSTRAP (se a
saida existe, pula). Mas em PRODUCAO/MASTER nao havia retomada: se a esteira caia na
etapa 14, rodar de novo re-executava as 13 anteriores. No caso real do `asta`, morrer
no `sincronia` custou 23 minutos -- e a proxima tentativa custaria os mesmos 23.

Este modulo guarda, por execucao, o que JA foi concluido e se aquilo ainda e VALIDO.
A pergunta que ele responde e uma so:

    "posso pular esta etapa?"

E a resposta e sempre conservadora: `pular` SO quando ha prova de que a etapa ja
rodou com as MESMAS entradas e de que todas as saidas ainda existem. Qualquer
duvida -> `rodar`. Uma etapa re-executada a toa custa tempo; uma etapa pulada a toa
produz um video errado em silencio. O erro caro e o segundo.

Garantias (o que NAO pode quebrar):
- falha fechada: duvida, arquivo ilegivel, hash que nao bate -> RODAR;
- o checkpoint NUNCA decide sozinho o que e uma entrada valida: quem manda e o `le`
  declarado em `vx/etapas.py` (fonte unica). Aqui so comparamos hashes;
- escrever checkpoint nunca derruba a esteira (erro engolido, como em metrics);
- nao guarda conteudo, so hash -- nenhum dado de producao vaza para o checkpoint.

Formato (qa/esteira/<run_id>/_checkpoint.json):

    {
      "run_id": "...", "iniciado_em": "...", "atualizado_em": "...",
      "etapas": {
        "stems": {"status": "concluido", "entradas_hash": "ab12...",
                  "saidas": ["entradas/stems/x_vocals.wav", ...],
                  "saidas_bytes": 12345, "concluido_em": "..."},
        ...
      }
    }
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ARQ = "_checkpoint.json"

#: Decisao de retomada.
RODAR = "rodar"
PULAR = "pular"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_arquivo(caminho: Path) -> str | None:
    """Hash do conteudo. None se nao existir ou nao der para ler (falha fechada)."""
    try:
        caminho = Path(caminho)
        if not caminho.is_file():
            return None
        h = hashlib.sha256()
        with caminho.open("rb") as f:
            for bloco in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloco)
        return h.hexdigest()
    except OSError:
        return None


def _expandir(padroes, projeto: Path, slug: str) -> list[Path]:
    """Resolve os caminhos de `le`/`escreve` de uma etapa.

    Lida com o que existe no registro: `{slug}`, globs (`clips_raw/*.mp4`) e
    placeholders de execucao (`<run_id>`, `<projeto.json:chave>`).

    Um glob sem nenhum resultado devolve lista vazia -- e isso e uma entrada
    legitima (projeto sem `clips_raw` ainda), tratado como "conjunto vazio".
    """
    projeto = Path(projeto)
    saida: list[Path] = []
    for padrao in padroes or ():
        p = str(padrao).replace("{slug}", slug)
        if "<" in p:
            # placeholder resolvido em tempo de execucao (<run_id>, <projeto.json:...>):
            # nao da para prever o caminho agora, entao nao entra na conta.
            continue
        if "*" in p or "?" in p:
            saida.extend(sorted(projeto.glob(p)))
        else:
            saida.append(projeto / p)
    return saida


def hash_entradas(padroes, projeto: Path, slug: str) -> str:
    """Hash do conjunto de entradas declaradas.

    Combina (nome relativo, tamanho, mtime, hash do conteudo quando e arquivo unico).
    Nao usa apenas mtime porque copia/checkout mexeria no tempo sem mudar o dado; e
    nao usa hash de conteudo em glob grande porque custaria caro a cada etapa.
    """
    projeto = Path(projeto)
    itens: list[str] = []
    for caminho in _expandir(padroes, projeto, slug):
        try:
            rel = caminho.relative_to(projeto).as_posix()
        except ValueError:
            rel = str(caminho)
        if caminho.is_file():
            st = caminho.stat()
            itens.append(f"{rel}:{st.st_size}:{int(st.st_mtime)}")
        elif caminho.is_dir():
            itens.append(f"{rel}:dir")
        else:
            itens.append(f"{rel}:ausente")
    return hashlib.sha256("\n".join(sorted(itens)).encode("utf-8")).hexdigest()


def saidas_existem(padroes, projeto: Path, slug: str) -> tuple[bool, list[str]]:
    """(existe_tudo, caminhos_que_faltam_ou_estao_vazios).

    Saida declarada que e glob nao exige resultado (pode nao casar por design);
    saida declarada nominal precisa existir e nao estar vazia.
    """
    projeto = Path(projeto)
    faltando: list[str] = []
    for padrao in padroes or ():
        p = str(padrao).replace("{slug}", slug)
        if "<" in p:
            continue
        if "*" in p or "?" in p:
            continue  # glob de saida: ausencia nao e falha
        caminho = projeto / p
        if not caminho.is_file() or caminho.stat().st_size == 0:
            faltando.append(p)
    return (not faltando), faltando


def _saidas_bytes(padroes, projeto: Path, slug: str) -> int:
    total = 0
    for caminho in _expandir(padroes, projeto, slug):
        try:
            if caminho.is_file():
                total += caminho.stat().st_size
        except OSError:
            continue
    return total


@dataclass
class Decisao:
    """Resultado de "posso pular?" -- com o motivo, para o log dizer por que."""
    acao: str
    motivo: str

    @property
    def pular(self) -> bool:
        return self.acao == PULAR


@dataclass
class Checkpoint:
    """Estado de retomada de uma execucao. `projeto`/`slug` habilitam a validacao."""

    run_id: str
    projeto: Path | None = None
    slug: str = ""
    iniciado_em: str = field(default_factory=_agora)
    atualizado_em: str = field(default_factory=_agora)
    etapas: dict[str, dict] = field(default_factory=dict)

    # -- leitura/escrita -----------------------------------------------------
    @classmethod
    def ler(cls, caminho: str | Path, *, projeto=None, slug: str = "") -> "Checkpoint":
        """Le um checkpoint. Arquivo ausente/ilegivel -> checkpoint vazio (tudo roda)."""
        caminho = Path(caminho)
        doc = {}
        try:
            lido = json.loads(caminho.read_text(encoding="utf-8"))
            if isinstance(lido, dict):
                doc = lido
        except (OSError, ValueError):
            doc = {}
        cp = cls(run_id=doc.get("run_id") or caminho.parent.name,
                 projeto=Path(projeto) if projeto is not None else None, slug=slug)
        cp.iniciado_em = doc.get("iniciado_em") or cp.iniciado_em
        cp.atualizado_em = doc.get("atualizado_em") or cp.atualizado_em
        etapas = doc.get("etapas")
        cp.etapas = etapas if isinstance(etapas, dict) else {}
        return cp

    def gravar(self, caminho: str | Path) -> Path:
        """Escreve o checkpoint. Nunca levanta (nao pode derrubar a esteira)."""
        caminho = Path(caminho)
        self.atualizado_em = _agora()
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            tmp = caminho.with_suffix(caminho.suffix + ".tmp")
            tmp.write_text(json.dumps(self.como_dict(), indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(caminho)
        except OSError:
            pass
        return caminho

    def como_dict(self) -> dict:
        return {"run_id": self.run_id, "iniciado_em": self.iniciado_em,
                "atualizado_em": self.atualizado_em, "etapas": self.etapas}

    # -- decisao -------------------------------------------------------------
    def pode_pular(self, nome: str, padroes_le, padroes_escreve) -> Decisao:
        """`PULAR` so com prova: etapa concluida + entradas iguais + saidas presentes."""
        reg = self.etapas.get(nome)
        if not isinstance(reg, dict):
            return Decisao(RODAR, "sem registro anterior")
        if reg.get("status") != "concluido":
            return Decisao(RODAR, f"status anterior: {reg.get('status')}")
        if self.projeto is None:
            return Decisao(RODAR, "sem projeto para validar entradas")

        atual = hash_entradas(padroes_le, self.projeto, self.slug)
        anterior = reg.get("entradas_hash")
        if anterior != atual:
            return Decisao(RODAR, "entradas mudaram")

        ok, faltando = saidas_existem(padroes_escreve, self.projeto, self.slug)
        if not ok:
            return Decisao(RODAR, "saida ausente/vazia: " + ", ".join(faltando[:3]))

        return Decisao(PULAR, "concluida com as mesmas entradas e saidas no lugar")

    # -- registro ------------------------------------------------------------
    def registrar(self, nome: str, *, padroes_le=(), padroes_escreve=(), status: str = "concluido") -> None:
        """Marca uma etapa como concluida (com hash das entradas e saidas do momento)."""
        self.etapas[nome] = {
            "status": status,
            "entradas_hash": (hash_entradas(padroes_le, self.projeto, self.slug)
                              if self.projeto is not None else None),
            "saidas": [str((self.projeto / str(p).replace("{slug}", self.slug)).relative_to(self.projeto)).replace("\\", "/")
                       if self.projeto is not None else str(p) for p in padroes_escreve],
            "saidas_bytes": (_saidas_bytes(padroes_escreve, self.projeto, self.slug)
                             if self.projeto is not None else 0),
            "concluido_em": _agora(),
        }

    def registrar_pulado(self, nome: str, motivo: str) -> None:
        reg = self.etapas.setdefault(nome, {})
        reg["ultimo_pulo"] = {"em": _agora(), "motivo": motivo}

    def resumo(self) -> dict:
        return {"run_id": self.run_id, "n_registradas": len(self.etapas),
                "concluidas": sum(1 for e in self.etapas.values()
                                  if isinstance(e, dict) and e.get("status") == "concluido")}


def run_ids_disponiveis(projeto: Path) -> list[str]:
    """Execucoes com checkpoint, da mais recente para a mais antiga."""
    base = Path(projeto) / "qa" / "esteira"
    if not base.is_dir():
        return []
    achados = [d.name for d in base.iterdir() if (d / ARQ).is_file()]
    return sorted(achados, reverse=True)


def mais_recente(projeto: Path) -> str | None:
    ids = run_ids_disponiveis(projeto)
    return ids[0] if ids else None
