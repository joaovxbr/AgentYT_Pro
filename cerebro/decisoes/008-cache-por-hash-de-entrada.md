# 008 — Cache por hash de entrada (reaproveitar entre execuções)

**Data:** 2026-10-09 · **Status:** aceita
**Relaciona-se a:** 002 (porteiros sem override), 005 (métricas), 006 (checkpoint), 007
(etapas in-process) — é a Fase 4 do plano de robustez.

**Contexto:** as Fases 2 e 3 atacaram *quando* uma etapa roda (retomada) e *quanto custa*
chamá-la (in-process), mas nenhuma das duas respondeu "esta entrada já foi processada antes,
por qualquer execução?". O caso concreto: trocar um único clipe de fundo muda o hash de
`timeline`, o que reescreve a timeline — mas `stems`, `transcrever` e `sincronizar` não
dependem disso. Sem cache, o rebuild separava o áudio com Demucs na GPU e rodava o Whisper
inteiro de novo, por nada.

**Decisão:** `vx/cache.py` guarda, por etapa e por projeto, o resultado de cada combinação de
entradas já vista. Antes de chamar a etapa, o pipeline pergunta se alguma execução ANTERIOR já
produziu aquele resultado e se as saídas continuam no lugar.

**A confusão que este módulo existe para não permitir:** cache ≠ checkpoint.

| | `vx/checkpoint.py` (006) | `vx/cache.py` (008) |
|---|---|---|
| Pergunta | "posso retomar esta execução?" | "esta entrada já foi processada?" |
| Escopo | um `run_id` | o projeto inteiro |
| Onde mora | `qa/esteira/<run_id>/_checkpoint.json` | `qa/cache/<etapa>.json` |
| Morre quando | a execução termina | o operador invalida |

Os dois usam a **mesma primitiva** (`checkpoint.hash_entradas`) para calcular o hash, então
nunca discordam sobre o que "mesma entrada" significa. Quem manda no que é uma entrada
continua sendo o `le` de `vx/etapas.py` — nem o cache nem o checkpoint inventam isso.

**As três provas** (as mesmas do checkpoint, escopo diferente): o hash das entradas atuais
casa com uma entrada guardada + todas as saídas DECLARADAS existem e não estão vazias + todas
as saídas REGISTRADAS continuam no lugar. A terceira importa porque o `escreve` de algumas
etapas é glob: um glob que não casa não é falha (por design), então o registro do que a
execução realmente produziu é a prova mais forte. Apagar um render na mão derruba o cache.

**Guarda variações, não só a última.** O cache guarda até `LIMITE_POR_ETAPA` (8) combinações
por etapa. Alternar entre duas versões de um clipe (A → B → A) volta a reaproveitar na volta,
em vez de recomeçar. `usos` conta os reaproveitamentos — é o dado que mostra se o cache paga
o próprio custo.

**O que NÃO é cacheável, e por quê** (`cacheavel=False` em `vx/etapas.py`, fonte única):

- **as 6 etapas de composição** (`cenas-auto`, `chroma-auto`, `cenas-ia`, `titulos`,
  `manga-auto`, `graficos-auto`): elas **editam `timeline.json` sobre a base limpa** a cada
  esteira por design (`vx/composicao.py`, decisão 001). Já têm idempotência interna via
  `qa/<etapa>/state.json`. Cachear por fora brigaria com esse desenho — a etapa não é "pular",
  é "reaplicar sobre uma base que muda".
- **as 3 de master** (`render-clipe`, `intro`, `qa-master`): escrevem em
  `saidas/esteira/<run_id>/`, que é da execução atual. Reaproveitar de outra execução daria um
  master de outro run.

O gerador de `cerebro/etapas.md` passou a marcar `cacheável` / `sempre refeita` em cada etapa,
então a política fica visível no doc que o operador já lê.

**Falha fechada e robustez:** reaproveitar errado produz vídeo errado em silêncio (o erro
caro); refazer custa tempo (o erro barato). Faltando qualquer prova — hash diferente, saída
sumiu, registro ilegível, estrutura errada — a resposta é `rodar`. Ler e gravar o cache
**nunca** derrubam a esteira (mesmo padrão de `metrics`/`checkpoint`). O nome da etapa é
sanitizado antes de virar nome de arquivo, para que um nome inesperado não escreva fora do
projeto.

**Controle do operador:** `estudio.py cache <slug>` mostra o que está guardado, quantas
variações e quantos usos; `--limpar` apaga. `esteira --sem-cache` ignora o cache e refaz toda
etapa cacheável. `--rebuild-clean` **implica** `--sem-cache`: o pedido explícito é refazer tudo
do zero, e reaproveitar por baixo dos panos contradiria a intenção.

**Consequência medida:** numa segunda execução do mesmo projeto, 5 das 6 etapas cacheáveis não
são chamadas. A invalidação é precisa, não um flush geral — mudar a letra derruba o cache de
`auditar-letra` e deixa `fonte-limpa`, `planejar` e `sincronia` intactos.

**Testes:** `tests/test_cache.py` (28), incluindo reaproveitamento entre execuções distintas,
volta a uma entrada antiga, saída registrada apagada derrubando o cache mesmo quando o glob
declarado ainda casa, registro corrompido/com estrutura errada, gravar que nunca levanta, poda
dentro do limite, e o contrato com `vx/etapas.py` (composição e master não-cacheáveis; toda
etapa cacheável declara `le`).
