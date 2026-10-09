"""Grafo de dependencias das etapas — o que pode rodar JUNTO, nao so em que ordem.

O `pipeline_autonomo_pro` sempre rodou as 18 etapas em fila indiana. Isso era
seguro, mas desperdica: duas etapas que so LEEM as mesmas entradas nao precisam
esperar uma pela outra.

A ARMADILHA que este modulo existe para desarmar: o `le`/`escreve` de
`vx/etapas.py` parece declarar um grafo limpo, mas as etapas de composicao
(`cenas-auto`, `chroma-auto`, `cenas-ia`, `titulos`, `manga-auto`,
`graficos-auto`) declaram TODAS `le=("timeline.json", ...)` E
`escreve=("timeline.json", ...)`. Lida ao pe da letra, a declaracao diria que
cada uma depende das outras cinco -- o que e falso. Elas nao dependem uma da
outra: cada uma EDITA `timeline.json` no lugar, sobre a base limpa, numa ordem
fixa (`vx/composicao.py`). Sao mutuamente exclusivas por causa da ESCRITA
COMPARTILHADA, nao por causa de dados que trocam entre si.

Confundir as duas coisas daria um grafo cheio de arestas falsas e nenhum
paralelismo; pior, poderia sugerir que duas delas rodam juntas (corrida de
escrita no mesmo arquivo -> timeline corrompida em silencio).

Modelo correto, entao:

1. **Corrente.** As etapas que escrevem um artefato compartilhado sao ordenadas
   pela posicao no registro (`vx/etapas.py` manda) e rodam SEMPRE em serie,
   cada uma na sua propria onda. A leitura que elas fazem do proprio artefato
   que editam NAO gera aresta -- seria um ciclo falso.
2. **Consumidor do compartilhado.** Quem LE o compartilhado sem edita-lo
   (`render-clipe`, `auditar-ritmo`, `planejar`, ...) depende de TODOS os que o
   escrevem, e em particular da ULTIMA da corrente. Sem essa aresta o
   `render-clipe` aparecia antes de `graficos-auto` e renderizava uma timeline
   pela metade.
3. **Ondas.** O que sobra pode rodar junto, desde que as entradas ja existam. A
   escala privilegia o paralelo: etapas fora da corrente se agrupam primeiro, e
   so quando nao ha mais o que paralelizar uma etapa da corrente e emitida.

**Falha fechada:** qualquer ambiguidade (leitura que casa com escrita de outra
etapa de forma nao obvia, ciclo, dependencia nao resolvida) faz a etapa cair na
onda serial. Perder paralelismo e barato; ganhar uma corrida de escrita nao e.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import etapas as _etapas

#: Artefatos que, se escritos por duas etapas, as tornam mutuamente exclusivas.
#: `timeline.json` e o caso real: as seis etapas de composicao o editam no lugar.
COMPARTILHADOS = ("timeline.json",)


def _norm(rel: str) -> str:
    """Normaliza um caminho declarado, para comparar `le` com `escreve`.

    `{slug}` e `<run_id>` viram `*` (sao da execucao/projeto, nao identificam o
    artefato). Directivas `<projeto.json:campo>` viram `*` tambem: o valor real
    so se conhece em runtime, e supor seria pior que serializar.
    """
    n = str(rel).replace("{slug}", "*").replace("<run_id>", "*")
    if n.startswith("<") and ">" in n:
        return "*"
    return n


def _dir(rel: str) -> str:
    n = _norm(rel)
    return n.rsplit("/", 1)[0] if "/" in n else ""


def _glob(rel: str) -> bool:
    return "*" in _norm(rel)


def _casa_trecho(padrao: str, valor: str) -> bool:
    """Glob de UM segmento (sem `/` dos dois lados)."""
    if padrao == "*":
        return True
    if "*" not in padrao:
        return padrao == valor
    reg = "".join(".*" if ch == "*" else re.escape(ch) for ch in padrao)
    return re.fullmatch(reg, valor) is not None


def _casa_segmento(padrao: str, valor: str) -> bool:
    """`fnmatch` **por segmento**, para o `*` nao atravessar `/`.

    `fnmatch` cru deixaria `clips_raw/*.mp4` casar com
    `clips_raw/vx_cenas_ia/*.mp4` -- o `*` engole a barra. Era exatamente essa
    a aresta falsa `cenas-auto <- cenas-ia` (cenas-auto le `clips_raw/*.mp4` e
    cenas-ia escreve `clips_raw/vx_cenas_ia/*.mp4`), que fechava um ciclo no
    grafo e invertia a ordem da composicao. Aqui um `*` so vale dentro do
    proprio segmento.
    """
    ps, vs = padrao.split("/"), valor.split("/")
    if len(ps) != len(vs):
        return False
    return all(_casa_trecho(p, v) for p, v in zip(ps, vs))


def _casa(a: str, b: str) -> bool:
    """Dois caminhos declarados se referem ao mesmo artefato?

    **Deliberadamente conservador.** A versao antiga tambem casava dois caminhos
    so por estarem no mesmo diretorio, o que gerava aresta FALSA: o `stems`
    escreve `entradas/stems/*_vocals.wav` e o `transcrever` LE esse mesmo
    arquivo -- mas casar por diretorio tambem fazia a saida *diferente* do
    `stems` casar com a leitura, invertendo a aresta (`stems <- transcrever`, um
    ciclo logico). Perder uma aresta aqui e barato (cai em serial, falha
    fechada); ganhar uma errada nao e.

    Casam:
      * caminhos identicos;
      * um glob que o outro satisfaz, **segmento a segmento** (`clips_raw/*.mp4`
        casa com `clips_raw/a.mp4`, mas NAO com `clips_raw/sub/a.mp4`);
      * uma pasta declarada terminando em `/` cobre tudo dentro dela.
    """
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if not na or not nb or na == "*" or nb == "*":
        # coringa puro ou vazio: nao da para provar nada -> nao casa.
        # Falha fechada: sem aresta, a etapa cai na onda serial.
        return False
    # pasta explicita: `x/` cobre `x/y` e `x/y/z`
    for x, o in ((na, nb), (nb, na)):
        if x.endswith("/") and o.startswith(x):
            return True
    if not (_glob(na) or _glob(nb)):
        return False  # dois arquivos concretos e diferentes: nunca casam
    return _casa_segmento(na, nb) or _casa_segmento(nb, na)


@dataclass(frozen=True)
class Aresta:
    origem: str
    destino: str
    motivo: str


@dataclass
class Grafo:
    """Dependencias entre etapas + agrupamento em ondas executaveis."""

    etapa_para_deps: dict[str, set[str]] = field(default_factory=dict)
    arestas: list[Aresta] = field(default_factory=list)
    #: Etapas que escrevem um artefato compartilhado: corrente serial obrigatoria.
    corrente: list[str] = field(default_factory=list)

    # -- consultas -----------------------------------------------------------
    def deps(self, nome: str) -> set[str]:
        return set(self.etapa_para_deps.get(nome, ()))

    def pode_rodar_junto(self, a: str, b: str) -> bool:
        """Duas etapas podem ser despachadas ao mesmo tempo?

        Regra **conservadora**, na ordem do mais barato ao mais caro:

        1. Duas etapas da corrente NUNCA (elas editam o mesmo arquivo).
        2. Qualquer uma que toque o artefato compartilhado nao roda junto de
           ninguem: quem edita `timeline.json` nao pode executar enquanto outra
           etapa o le ou escreve.
        3. Uma dependencia declarada entre as duas bloqueia.
        4. Caso contrario, pode.

        O ponto 2 e a rede de seguranca "falha fechada": prefere perder
        paralelismo a arriscar uma leitura de `timeline.json` no meio de uma
        edicao. Duas etapas que nao tocam o compartilhado (ex.: `sincronizar` e
        `auditar-letra`) passam direto pela regra.
        """
        if a == b:
            return False
        if a in self.corrente and b in self.corrente:
            return False  # (1) dois editores do mesmo arquivo
        if self.toca_compartilhado(a) or self.toca_compartilhado(b):
            return False  # (2) falha fechada em volta do artefato compartilhado
        if a in self.deps(b) or b in self.deps(a):
            return False  # (3) dependencia declarada
        return True

    def toca_compartilhado(self, nome: str) -> bool:
        """A etapa escreve algum artefato compartilhado (editado no lugar)?"""
        return nome in self.corrente

    def ondas(self, nomes: list[str]) -> list[list[str]]:
        """Agrupa `nomes` em ondas: tudo numa onda pode rodar junto.

        Duas regras de agendamento, nesta ordem de prioridade:

        * **Preferencia pelo paralelo.** Enquanto houver etapa fora da corrente
          com as entradas prontas, ela entra na onda. So quando nao sobra nada
          paralelizavel e que uma etapa da corrente e emitida — **sozinha**, ja
          que ela edita o arquivo compartilhado.
        * **Preserva a ordem do registro** dentro de cada onda (o despacho segue
          `vx/etapas.py`, entao o log fica na mesma sequencia de sempre).

        Sem essa preferencia, cada etapa da corrente criava uma onda vazia em
        volta e `sincronia`/`auditar-ritmo` (que so olham a saida) ficavam
        garroteados atras da composicao sem nenhum motivo real.
        """
        restantes = list(nomes)
        concluidas: set[str] = set()
        ondas: list[list[str]] = []
        while restantes:
            prontas = [n for n in restantes if not (self.deps(n) - concluidas)]
            if not prontas:
                # ciclo: serializa o resto (falha fechada, nunca trava)
                ondas.append([restantes[0]])
                concluidas.add(restantes[0])
                restantes.pop(0)
                continue
            paralelas = [n for n in prontas if n not in self.corrente]
            if paralelas:
                onda: list[str] = []
                for nome in paralelas:
                    if all(self.pode_rodar_junto(nome, x) for x in onda):
                        onda.append(nome)
            else:
                onda = [prontas[0]]  # corrente: sempre sozinha na onda
            ondas.append(onda)
            for n in onda:
                concluidas.add(n)
                restantes.remove(n)
        return ondas


def construir(etapas=None, compartilhados=COMPARTILHADOS) -> Grafo:
    """Monta o grafo a partir do registro unico (`vx/etapas.py`)."""
    etapas = tuple(etapas if etapas is not None else _etapas.TODAS)
    nomes = [e.nome for e in etapas]
    por_nome = {e.nome: e for e in etapas}
    g = Grafo()

    # 1) corrente: quem escreve artefato compartilhado, na ordem do registro
    for e in etapas:
        if any(_casa(w, c) for w in e.escreve for c in compartilhados):
            g.corrente.append(e.nome)

    # 2) arestas de dependencia real (quem produz o que esta etapa le).
    #    Leitura de artefato COMPARTILHADO fica de fora: quem edita `timeline.json`
    #    tambem o declara em `le` (le a versao que herdou, edita, devolve). Tratar
    #    isso como dado daria `cenas-auto <- titulos` e `titulos <- cenas-auto` ao
    #    mesmo tempo -- ciclo falso. A ordem entre elas vem da regra 4.
    e_corrente = set(g.corrente)
    for e in etapas:
        deps: set[str] = set()
        editando_compartilhado = e.nome in e_corrente
        for le in e.le:
            for outra in etapas:
                if outra.nome == e.nome:
                    continue
                for w in outra.escreve:
                    if not _casa(le, w):
                        continue
                    if editando_compartilhado and any(_casa(w, c) for c in compartilhados):
                        continue  # mesmo arquivo editado no lugar: ver regra 3/4
                    deps.add(outra.nome)
                    g.arestas.append(Aresta(outra.nome, e.nome, f"{w} -> {le}"))
        g.etapa_para_deps[e.nome] = deps

    # 3) artefato compartilhado. Duas situacoes bem diferentes:
    #
    #    (a) a etapa EDITA o compartilhado (esta na corrente): ela nao le a
    #        versao final, ela e uma das que a constroem. Depende apenas da
    #        anterior da corrente (regra 4). Nao pode receber aresta das
    #        outras seis, senao vira ciclo e perde-se a ordem real.
    #    (b) a etapa LE o compartilhado sem escreve-lo (`render-clipe`,
    #        `auditar-ritmo`, `planejar`, `cenas-ia`...): consome o resultado
    #        FINAL, entao depende de TODOS os que escrevem -- em particular da
    #        ultima da corrente. Sem isso o `render-clipe` aparecia antes de
    #        `graficos-auto` e renderizava uma timeline pela metade.
    escritores: list[str] = []
    for nome in g.corrente:
        for w in por_nome[nome].escreve:
            if any(_casa(w, c) for c in compartilhados):
                escritores.append(nome)
                break
    for e in etapas:
        if e.nome in g.corrente:
            continue  # caso (a): ordem vem da regra 4
        for le in e.le:
            for autor in escritores:
                if autor == e.nome:
                    continue
                if any(_casa(le, w) for w in por_nome[autor].escreve):
                    g.etapa_para_deps[e.nome].add(autor)

    # 4) a corrente impoe ordem entre suas proprias etapas (na ordem do registro)
    for i, nome in enumerate(g.corrente):
        g.etapa_para_deps[nome] |= set(g.corrente[:i])

    # 5) sanitizacao: descarta dependencia que aponta para fora do conjunto
    for nome in nomes:
        g.etapa_para_deps[nome] = {d for d in g.etapa_para_deps[nome] if d in por_nome}
    return g


def validar(g: Grafo, nomes: list[str] | None = None) -> list[str]:
    """Confere invariantes do grafo. Devolve a lista de problemas (vazia = ok).

    Verifica, na ordem:

    * nenhuma dependencia aponta para etapa inexistente;
    * nenhum ciclo (a esteira nunca pode travar esperando a si mesma);
    * **nenhuma onda agrupa duas etapas que nao podem rodar juntas** -- esta e a
      invariante que protege o `timeline.json`, e o motivo de o modulo existir;
    * toda etapa aparece em exatamente uma onda.

    Pensado para rodar num teste (`tests/test_dag.py`) e, opcionalmente, no
    inicio da esteira com `--jobs`: se falhar, o orquestrador cai para serial.
    """
    nomes = list(nomes if nomes is not None else [e.nome for e in _etapas.TODAS])
    problemas: list[str] = []

    conhecidos = set(nomes)
    for nome in nomes:
        for d in g.deps(nome):
            if d not in conhecidos:
                problemas.append(f"{nome}: depende de '{d}', que nao existe")

    # ciclo: caminho de volta ate o proprio no
    visitando: set[str] = set()
    feito: set[str] = set()

    def _dfs(n: str, trilha: list[str]) -> bool:
        if n in feito:
            return False
        if n in visitando:
            problemas.append("ciclo: " + " -> ".join(trilha + [n]))
            return True
        visitando.add(n)
        for d in sorted(g.deps(n)):
            if _dfs(d, trilha + [n]):
                return True
        visitando.discard(n)
        feito.add(n)
        return False

    for nome in nomes:
        if _dfs(nome, []):
            break  # um ciclo ja basta para reprovar

    ondas = g.ondas(nomes)
    vistas: list[str] = []
    for i, onda in enumerate(ondas, 1):
        for a in range(len(onda)):
            for b in range(a + 1, len(onda)):
                if not g.pode_rodar_junto(onda[a], onda[b]):
                    problemas.append(
                        f"onda {i}: '{onda[a]}' e '{onda[b]}' nao podem rodar juntas")
        vistas += onda
    faltando = [n for n in nomes if n not in vistas]
    if faltando:
        problemas.append("etapas fora das ondas: " + ", ".join(faltando))
    repetidas = sorted({n for n in vistas if vistas.count(n) > 1})
    if repetidas:
        problemas.append("etapas em mais de uma onda: " + ", ".join(repetidas))
    return problemas


def ordem_topologica(g: Grafo, nomes: list[str] | None = None) -> list[str]:
    """Ordem serial (uma etapa por vez) que respeita todas as dependencias.

    E a esteira de sempre. Usada por `--serial` e como resposta a qualquer
    duvida: se `validar` reprovar ou o paralelismo estiver desligado, este e o
    caminho seguro. Empate e desfeito pela ordem do registro, para o log nao
    mudar de formato entre execucoes.
    """
    nomes = list(nomes if nomes is not None else [e.nome for e in _etapas.TODAS])
    ordem: list[str] = []
    concluidas: set[str] = set()
    restantes = list(nomes)
    while restantes:
        prontas = [n for n in restantes if not (g.deps(n) - concluidas)]
        if not prontas:
            ordem += restantes  # ciclo: devolve o resto na ordem do registro
            break
        escolhida = prontas[0]
        ordem.append(escolhida)
        concluidas.add(escolhida)
        restantes.remove(escolhida)
    return ordem


def _so_nomes(coisa) -> list[str]:
    """Aceita um iteravel de `Etapa` ou de `str` e devolve so os nomes.

    As funcoes publicas (`diagnosticar`, `ganho_estimado`) sao chamadas tanto com
    `etapas.TODAS` quanto com `etapas.nomes()`; normalizar aqui evita que o
    chamador precise saber qual dos dois a funcao espera.
    """
    if coisa is None:
        return [e.nome for e in _etapas.TODAS]
    return [x if isinstance(x, str) else x.nome for x in coisa]


def diagnosticar(g: Grafo, etapas=None) -> str:
    """Texto legivel: ondas e por que cada etapa esta onde esta (log/console)."""
    nomes = _so_nomes(etapas)
    linhas = ["Paralelismo por etapa (vx/dag.py):"]
    if g.corrente:
        linhas.append(f"  corrente serial (escrevem {'/'.join(COMPARTILHADOS)}): "
                      + " -> ".join(g.corrente))
    for i, onda in enumerate(g.ondas(nomes), 1):
        marca = "serie" if len(onda) == 1 else f"{len(onda)} em paralelo"
        linhas.append(f"  onda {i} ({marca}): {', '.join(onda)}")
    return "\n".join(linhas)


def ganho_estimado(g: Grafo, etapas=None) -> dict:
    """Numeros para o console: quantas ondas em vez de quantas etapas."""
    nomes = _so_nomes(etapas)
    ondas = g.ondas(nomes)
    paralelas = [o for o in ondas if len(o) > 1]
    return {
        "n_etapas": len(nomes),
        "n_ondas": len(ondas),
        "n_ondas_paralelas": len(paralelas),
        "etapas_em_paralelo": sum(len(o) for o in paralelas),
    }
