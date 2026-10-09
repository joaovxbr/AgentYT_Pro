# 005 — Métricas por etapa e caixa preta da execução

**Data:** 2026-10-09 · **Status:** aceita
**Relaciona-se a:** 001 (reconstrução incremental) — é a Fase 1 do plano de robustez.

**Contexto:** quando a esteira do `asta` levou 23 minutos até morrer no `sincronia`, o
diagnóstico foi arqueologia manual. O `execucao.json` só registrava
`{"nome": ..., "status": ...}` — sem tempo, sem tamanho de saída, sem motivo estruturado
de falha. Não havia como responder "qual etapa é o gargalo?", "esta etapa pulou por cache
ou rodou de novo?" nem "por que falhou?" sem ler o log inteiro.

**Decisão:** `vx/metrics.py` é a camada de MEDIÇÃO, separada da ORQUESTRAÇÃO. Ele não
decide nada: o `pipeline_autonomo_pro` continua mandando a esteira. Três garantias:

1. **Medir nunca derruba a esteira.** Qualquer erro em `metrics` é engolido e vira
   ausência de dado, nunca exceção (`gravar()` protege o `OSError`).
2. **O formato antigo de `execucao.json` continua válido.** As etapas seguem sendo
   `{"nome", "status"}`; os campos de métrica são ADICIONADOS em `report["metricas"]` e
   num arquivo irmão `qa/esteira/<run_id>/_metricas.json`.
3. **Etapa interrompida não desaparece.** No `finally` do pipeline, toda etapa que ficou
   `"executando"` vira `STATUS_FALHOU` — processo morto no meio aparece no relatório.

O que é medido por etapa: duração (perf_counter), status, `cache_hit`, bytes de saída
(resolvidos de `vx/etapas.py -> escreve`, então a medição não duplica a declaração do
registro), motivo da falha e a origem (`subprocess.CalledProcessError` vs tipo da exceção).

**Além do arquivo:** o `finally` imprime a tabela no console (gargalo + falhas) — o
operador vê o resumo sem abrir log nenhum. `metrics.comparar(antes, depois)` responde
"o que ficou mais lento" entre duas execuções.

**Consequência:** habilita a Fase 2 (resume), que precisa saber o que cada etapa produziu
e quanto custou. Também dá base para decidir cache por hash de entrada (Fase 4) com dado
real em vez de palpite.

**Testes:** `tests/test_metrics.py` (13), incluindo os dois de integração que provam que
o `execucao.json` mantém o formato antigo e ganha `metricas`, e que uma queda simulada
deixa a etapa registrada como falha.
