"""Metricas de execucao da esteira: quanto cada etapa custou e por que falhou.

Problema que resolve: a esteira `asta` levou 23 minutos ate morrer no `sincronia`, e
o diagnostico foi arqueologia manual -- o `execucao.json` so dizia
`{"nome": ..., "status": ...}`, sem tempo, sem tamanho de saida, sem motivo
estruturado. Nao havia como responder "qual etapa e o gargalo?", "aquela etapa
pulou por cache ou rodou de novo?" nem "por que falhou?" sem ler o log inteiro.

Este modulo e a camada de MEDICAO, separada da ORQUESTRACAO. Ele nao decide nada:
o `pipeline_autonomo_pro` continua mandando a esteira. Aqui so medimos.

Garantias (o que NAO pode quebrar):
- medir nunca derruba a esteira: qualquer erro aqui e engolido e vira ausencia de
  dado, nunca excecao;
- o formato antigo de `execucao.json` continua valido: as etapas seguem sendo
  `{"nome", "status"}` e os campos de metrica sao ADICIONADOS, nao substituem nada;
- nada de tempo de parede que dependa de relogio de parede para orquestrar: aqui o
  tempo serve para diagnostico, nao para controle.

Uso:

    from vx import metrics

    relogio = metrics.Cronometro()
    with relogio.medir() as m:
        ...
        m.registrar_saidas([caminho1, caminho2])
    # m.duracao_s, m.saidas, m.bytes_saida, m.cache_hit

    relatorio = metrics.Relatorio(run_id)
    relatorio.etapa_inicio("stems")
    relatorio.etapa_fim("stems", status="concluido", duracao_s=..., saidas=[...])
    relatorio.resumo()          # -> dict
    relatorio.gravar(destino)   # -> escreve _metricas.json ao lado do execucao.json
    print(relatorio.tabela())   # -> tabela legivel para o console
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Vocabulario (alinhado com vx/etapas.py e pipeline_autonomo_pro)
# ---------------------------------------------------------------------------
STATUS_CONCLUIDO = "concluido"
STATUS_FALHOU = "falhou"
STATUS_AVISO = "aviso"          # etapa nao-bloqueante que falhou mas nao reprova
STATUS_PULADA = "pulada"        # nao rodou (cache / saida ja existia / pre-requisito)

#: Status que exigem cuidados na leitura do relatorio.
STATUS_RUINS = (STATUS_FALHOU, STATUS_AVISO)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tamanho_bytes(caminhos) -> int:
    """Soma o tamanho dos arquivos que existirem. Caminho ausente conta 0."""
    total = 0
    for c in caminhos:
        try:
            p = Path(c)
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


# ---------------------------------------------------------------------------
# Cronometro: mede um bloco (uso inline dentro de uma etapa)
# ---------------------------------------------------------------------------
@dataclass
class Medida:
    """Uma medicao pontual de trabalho."""
    duracao_s: float = 0.0
    saidas: list[str] = field(default_factory=list)
    cache_hit: bool = False
    detalhe: dict = field(default_factory=dict)

    @property
    def bytes_saida(self) -> int:
        return _tamanho_bytes(self.saidas)

    def registrar_saidas(self, caminhos) -> None:
        for c in caminhos:
            self.saidas.append(str(c))

    def registrar_cache_hit(self, detalhe: str | None = None) -> None:
        self.cache_hit = True
        if detalhe:
            self.detalhe["cache"] = detalhe

    def como_dict(self) -> dict:
        d = {"duracao_s": round(self.duracao_s, 3),
             "bytes_saida": self.bytes_saida,
             "cache_hit": self.cache_hit}
        if self.saidas:
            d["saidas"] = self.saidas
        if self.detalhe:
            d["detalhe"] = self.detalhe
        return d


@dataclass
class Cronometro:
    """Mede blocos de codigo com `with relogio.medir() as m:`."""

    from contextlib import contextmanager

    def medir(self):
        import contextlib as _ctx

        @_ctx.contextmanager
        def _bloco():
            m = Medida()
            t0 = time.perf_counter()
            try:
                yield m
            finally:
                m.duracao_s = time.perf_counter() - t0
        return _bloco()


# ---------------------------------------------------------------------------
# Relatorio: acumula as etapas de uma execucao
# ---------------------------------------------------------------------------
@dataclass
class EtapaMedida:
    nome: str
    status: str = "pendente"
    duracao_s: float = 0.0
    bytes_saida: int = 0
    cache_hit: bool = False
    erro: str | None = None
    saidas: list[str] = field(default_factory=list)
    inicio: str | None = None
    fim: str | None = None
    #: Rota de falha (qual funcao levantou) -- util quando o erro nao diz onde nasceu.
    origem_erro: str | None = None

    def como_dict(self) -> dict:
        d = {
            "nome": self.nome,
            "status": self.status,
            "duracao_s": round(self.duracao_s, 3),
            "bytes_saida": int(self.bytes_saida),
            "cache_hit": bool(self.cache_hit),
        }
        if self.inicio:
            d["inicio"] = self.inicio
        if self.fim:
            d["fim"] = self.fim
        if self.erro:
            d["erro"] = self.erro
        if self.origem_erro:
            d["origem_erro"] = self.origem_erro
        if self.saidas:
            d["saidas"] = list(self.saidas)
        return d


class Relatorio:
    """Metricas de uma execucao (run_id), por etapa.

    Substitui o relogio de parede espalhado pelo pipeline: um objeto so, com
    inicio/fim por etapa, status, cache e motivo de falha.
    """

    def __init__(self, run_id: str, projeto: str | Path | None = None):
        self.run_id = run_id
        self.projeto = str(projeto) if projeto is not None else None
        self.criado_em = _agora()
        self.etapas: dict[str, EtapaMedida] = {}
        self._inicio_parede = time.perf_counter()

    # -- ciclo de vida de uma etapa -----------------------------------------
    def etapa_inicio(self, nome: str) -> EtapaMedida:
        e = self.etapas.get(nome)
        if e is None:
            e = EtapaMedida(nome=nome)
            self.etapas[nome] = e
        e.status = "executando"
        e.inicio = _agora()
        return e

    def etapa_fim(self, nome: str, *, status: str, duracao_s: float = 0.0,
                  saidas=None, cache_hit: bool = False, erro=None,
                  origem_erro=None) -> EtapaMedida:
        e = self.etapas.get(nome) or EtapaMedida(nome=nome)
        self.etapas[nome] = e
        e.status = status
        e.duracao_s = float(duracao_s)
        e.cache_hit = bool(cache_hit)
        e.fim = _agora()
        if erro is not None:
            e.erro = str(erro)[:2000]
        if origem_erro is not None:
            e.origem_erro = str(origem_erro)
        if saidas:
            e.saidas = [str(x) for x in saidas]
            e.bytes_saida = _tamanho_bytes(e.saidas)
        return e

    def etapa_pulada(self, nome: str, motivo: str = "cache") -> EtapaMedida:
        return self.etapa_fim(nome, status=STATUS_PULADA, duracao_s=0.0,
                              cache_hit=True, erro=None, origem_erro=None)

    # -- leitura -------------------------------------------------------------
    @property
    def duracao_total_s(self) -> float:
        return time.perf_counter() - self._inicio_parede

    @property
    def falhas(self) -> list[EtapaMedida]:
        return [e for e in self.etapas.values() if e.status in STATUS_RUINS]

    def gargalo(self) -> EtapaMedida | None:
        executadas = [e for e in self.etapas.values() if e.duracao_s > 0]
        return max(executadas, key=lambda e: e.duracao_s, default=None)

    def resumo(self) -> dict:
        return {
            "run_id": self.run_id,
            "projeto": self.projeto,
            "gerado_em": _agora(),
            "duracao_total_s": round(self.duracao_total_s, 3),
            "etapas": [e.como_dict() for e in self.etapas.values()],
            "n_etapas": len(self.etapas),
            "n_falhas": len(self.falhas),
            "n_cache_hit": sum(1 for e in self.etapas.values() if e.cache_hit),
        }

    def gravar(self, destino: str | Path) -> Path:
        """Escreve o JSON de metricas. Nunca levanta: metrica nao derruba esteira."""
        destino = Path(destino)
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            tmp = destino.with_suffix(destino.suffix + ".tmp")
            tmp.write_text(json.dumps(self.resumo(), indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(destino)
        except OSError:
            pass
        return destino

    def tabela(self) -> str:
        """Tabela legivel para o console (nome | status | tempo | cache)."""
        linhas = [f"  {'ETAPA':<18} {'STATUS':<10} {'TEMPO':>9} {'CACHE':>6}  SAIDA"]
        linhas.append("  " + "-" * 62)
        for e in self.etapas.values():
            tmp = f"{e.duracao_s:8.1f}s" if e.duracao_s else "       -"
            cache = "sim" if e.cache_hit else "-"
            saida = _human_bytes(e.bytes_saida) if e.bytes_saida else ""
            if e.status == STATUS_FALHOU:
                saida = (e.erro or "")[:40]
            linhas.append(f"  {e.nome:<18} {e.status:<10} {tmp:>9} {cache:>6}  {saida}")
        g = self.gargalo()
        if g is not None:
            linhas.append("  " + "-" * 62)
            linhas.append(f"  gargalo: {g.nome} ({g.duracao_s:.1f}s)")
        return "\n".join(linhas)


def _human_bytes(n: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f}{unidade}" if unidade == "B" else f"{n:.1f}{unidade}"
        n /= 1024.0
    return f"{n:.1f}GB"


def ler_metricas(caminho: str | Path) -> dict:
    """Le um `_metricas.json` gravado. Devolve {} se ausente/ilegivel."""
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def comparar(anterior: dict, atual: dict) -> list[dict]:
    """Compara duas execucoes por etapa. Util para ver o que ficou mais lento.

    Devolve uma lista de `{"etapa", "antes_s", "depois_s", "delta_s"}` ordenada
    pelo maior aumento absoluto de tempo.
    """
    def _mapa(doc: dict) -> dict[str, float]:
        return {e.get("nome"): float(e.get("duracao_s") or 0.0)
                for e in (doc or {}).get("etapas", []) if e.get("nome")}

    a, b = _mapa(anterior), _mapa(atual)
    linhas = []
    for nome in sorted(set(a) | set(b)):
        antes, depois = a.get(nome, 0.0), b.get(nome, 0.0)
        if abs(depois - antes) < 0.05:
            continue
        linhas.append({"etapa": nome, "antes_s": round(antes, 3),
                       "depois_s": round(depois, 3),
                       "delta_s": round(depois - antes, 3)})
    linhas.sort(key=lambda x: abs(x["delta_s"]), reverse=True)
    return linhas
