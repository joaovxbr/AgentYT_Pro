# 007 — Etapas in-process (fim do subprocess por etapa)

**Data:** 2026-10-09 · **Status:** aceita
**Relaciona-se a:** 001 (reconstrução incremental), 005 (métricas), 006 (resume) — é a Fase 3
do plano de robustez.

**Contexto:** a esteira chamava `estudio.py` por `subprocess` — 71 pontos em `ferramentas/*.py`.
Isso custava caro em duas frentes:

1. **tempo**: cada etapa era um processo Python novo, pagando de novo o import de numpy, torch e
   cv2. O `vx/lazy.py` já tinha resolvido o import *dentro* de um processo, mas não entre
   processos — cada uma das 18 etapas recomeçava do zero.
2. **diagnóstico**: o erro voltava como `CalledProcessError` com um `exit code`. O
   `vx/metrics.py` registrava literalmente `"exit 1"` e `origem_erro =
   "subprocess.CalledProcessError"` — o operador precisava abrir o log para descobrir *o que*
   morreu. A decisão 005 existia justamente para dar contexto ao erro, e o subprocess o
   descartava.

**Decisão:** `vx/runner.py` executa a etapa DENTRO do processo da esteira, chamando
`estudio.main(argv)`. O que isso muda:

- **erro tem contexto**: a exceção original sobe com traceback e `metrics` registra o tipo real;
- **o processo não é recriado** entre etapas;
- **o log continua existindo**, no mesmo `qa/esteira/<run_id>/NN_<etapa>.log` de antes — e a
  saída passa a ser *espelhada* (console **e** arquivo), então a esteira não fica mais muda
  enquanto uma etapa longa roda.

**A pegadinha que isso cria — e que define o módulo:** `estudio.py` levanta `SystemExit` em
**28 pontos** para sinalizar erro de entrada (letra ausente, ASS faltando, timeline inválida…).
Em subprocess isso era só o exit code. In-process, um `SystemExit` cru **mataria o processo da
esteira** — o `finally` do pipeline nunca rodaria, e nem métricas nem checkpoint seriam
fechados. Por isso `runner.executar()` captura `SystemExit` e o converte em `ErroDeEtapa`
(subclasse de `RuntimeError`, para continuar caindo no `except (ValueError, RuntimeError,
OSError)` da porta `estudio.py`). `sys.exit()` sem argumento continua sendo sucesso.

**Três garantias:**

1. **O cwd não vaza.** `estudio.py` usa caminhos relativos à raiz; o runner fixa o cwd em
   `RAIZ` durante a etapa e restaura depois — mesmo que a etapa levante. (Sem
   `contextlib.chdir`, que só existe no 3.11+; a esteira roda em 3.10.)
2. **O log nunca derruba a etapa.** Se não puder abrir o arquivo de log, a etapa roda igual —
   log é conveniência, não ponto de falha.
3. **Falha fechada na saída.** Só `0` aprova. Contrato de `estudio.main`: `None` é sucesso
   (caminho não tratado no dispatcher); para reprovar é preciso devolver != 0 ou levantar.

**Escape:** `--isolado` (e `executar_isolado()`) roda por subprocess com a mesma interface e o
mesmo contrato de erro — para etapa que precise de processo limpo. O custo é voltar a pagar o
import.

**Consequência:** é a base para a Fase 4 (cache por hash) e a Fase 5 (DAG + paralelismo). As
duas exigem etapas como unidades chamáveis *no mesmo processo* — um DAG não pode ser montado
sobre `subprocess` sem pagar processo por nó. Esta fase é o pré-requisito estrutural.

**O que NÃO mudou:** o `ffmpeg -f null -` de verificação de decode continua em subprocess
(é uma ferramenta externa, não uma etapa), e o contrato de `vx/etapas.py` segue intocado.

**Testes:** `tests/test_runner.py` (25), incluindo `SystemExit` virando `ErroDeEtapa`, `sys.exit()`
vazio sendo sucesso, `None` sendo sucesso, cwd/`stdout`/`stderr` restaurados mesmo em falha, log
impossível não derrubando a etapa, e in-process vs `--isolado` entregando o mesmo log.
Ajustados os 5 testes que injetavam falha pelo seam antigo (`pipeline.executar_passo`) passaram a
usar o seam novo (`pipeline.vx_runner.executar`) — o comportamento testado é o mesmo.
