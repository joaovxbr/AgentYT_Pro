# 006 — Retomada por checkpoint (`--resume`)

**Data:** 2026-10-09 · **Status:** aceita
**Relaciona-se a:** 001 (reconstrução incremental), 005 (métricas) — é a Fase 2 do plano de
robustez.

**Contexto:** a esteira do `asta` levou 23 minutos e morreu no `sincronia`. O trabalho até ali
(`separar`, `stems`, `demo`, `transcrição`, `sync`, `motion`…) estava todo no disco — e foi
jogado fora. O registro de etapas (`vx/etapas.py`) só declarava `quando="se_ausente"`, que
resolve *bootstrap* (pula se a saída nem existe), não o caso real: "a etapa já rodou com
ESTA entrada e a saída continua no lugar". Sem isso, toda falha tardia custa a esteira
inteira de novo — e uma falha no minuto 23 de um render custa minutos de GPU por nada.

**Decisão:** `vx/checkpoint.py` é a camada de RETOMADA, separada da medição (005) e da
orquestração. A esteira passa a poder ser retomada de onde parou:

```
python ferramentas/estudio.py esteira <slug> --resume          # checkpoint mais recente
python ferramentas/estudio.py esteira <slug> --resume <run_id> # checkpoint específico
```

**Prova tripla — só pula com as três, juntas:**

1. o registro anterior da etapa tem status `concluido`;
2. o hash das entradas (`le` de `vx/etapas.py`) não mudou;
3. todas as saídas nominais (`escreve`) existem e não estão vazias.

Faltando qualquer uma, a etapa RODA. Isso é **falha fechada**: pular errado gera vídeo errado
em silêncio — o erro caro; rodar de novo custa tempo — o erro barato. Na dúvida, gasta tempo.

**Três garantias (mesmo padrão da decisão 005):**

1. **Escrever checkpoint nunca derruba a esteira.** `gravar()` engole `OSError` (disco cheio,
   path impossível) — retomada é conveniência, não pode ser ponto de falha novo.
2. **O hash não guarda conteúdo.** Só `relpath:size:mtime` das entradas, agregado em 64 hex.
   Áudio de 200 MB não vira 200 MB de JSON.
3. **`--resume` sem checkpoint não mente.** `auto` procura o `run_id` mais recente; se não
   existe ou está ilegível, começa execução limpa com aviso — nunca finge retomada.

**Como o hash lida com o registro real:** `_expandir()` aceita glob (`clips_raw/*.mp4`) e
placeholder (`<run_id>`, que é ignorado, porque a pasta ainda não existe), e trata glob sem
resultado como conjunto vazio legítimo (projeto sem clipes ainda ⇒ hash estável, sem exceção).

**Consequência:** falha no meio da esteira deixa de custar o trabalho anterior. É pré-requisito
para a Fase 4 (cache por hash de entrada): as duas usam exatamente o mesmo `hash_entradas` e a
mesma pergunta "esta saída corresponde a esta entrada?" — a Fase 4 só estende a decisão de
"pular" para "reaproveitar entre execuções diferentes".

**Testes:** `tests/test_checkpoint.py` (18), incluindo falha fechada em dúvida, ausência de
projeto, status anterior de falha, saída vazia contando como ausente, round-trip, arquivo
corrompido, `gravar()` que nunca levanta, hash só de metadados, e o contrato com `vx/etapas.py`
(toda etapa do registro é avaliável sem explodir).
