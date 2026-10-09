# 009 — Ondas paralelas por grafo de dependências (`vx/dag.py`)

Data: 2026-10-09
Status: aprovado e integrado

## Contexto

A esteira sempre rodou as 18 etapas em fila indiana. Depois das fases 1–4 (métricas,
resume, execução in-process, cache), a etapa virou uma chamada Python no mesmo processo
— o que faltava para rodar duas etapas ao mesmo tempo sem o custo de dois interpretadores.

O grafo já estava *declarado* desde sempre: cada `Etapa` em `vx/etapas.py` diz o que
`le` e o que `escreve`. O problema é que essa declaração não pode ser lida ao pé da letra.

## O problema real

As sete etapas de composição (`timeline`, `cenas-auto`, `chroma-auto`, `cenas-ia`,
`titulos`, `manga-auto`, `graficos-auto`) declaram **todas** `le=("timeline.json", …)` e
**todas** `escreve=("timeline.json", …)`.

Lida ingenuamente, a declaração diz duas coisas falsas:

1. **"cada uma depende das outras seis"** — falso. Elas não trocam dados entre si. Cada
   uma **edita o arquivo no lugar**, sobre a base limpa, numa ordem fixa
   (`vx/composicao.py`). São mutuamente exclusivas por *escrita compartilhada*, não por
   dependência de dado. Tratar isso como dado daria um ciclo de sete nós e zero
   paralelismo.
2. **"quem lê `timeline.json` só depende de uma delas"** — pior. `render-clipe` lê
   `timeline.json`, mas precisa da versão **final**, depois de `graficos-auto`. Sem uma
   aresta explícita o grafo colocava `render-clipe` antes de `graficos-auto`: o render
   sairia com uma timeline pela metade, silenciosamente.

## Decisão

`vx/dag.py` deriva o grafo do registro único e trata escrita compartilhada como
**exclusão mútua**, não como dependência de dado.

1. **Corrente.** As escritoras do artefato compartilhado são ordenadas pela posição no
   registro e rodam **cada uma na sua própria onda, sempre**.
2. **Consumidor do compartilhado.** Quem lê o compartilhado **sem editá-lo**
   (`render-clipe`, `auditar-ritmo`, `planejar`) depende de *todos* os que o escrevem —
   em particular da última da corrente.
3. **Ondas.** O que sobra roda junto. O escalonador **prefere o paralelo**: agrupa as
   etapas fora da corrente primeiro e só emite uma etapa da corrente quando não há mais
   o que paralelizar.
4. **Falha fechada.** Qualquer ambiguidade — ciclo, dependência não resolvida, caminho
   que casa de forma não óbvia — joga a etapa na onda serial. Perder paralelismo é
   barato; ganhar uma corrida de escrita no `timeline.json` não é.

## Integração no orquestrador

`estudio.py esteira <slug> --jobs N` (ou `--jobs` no `pipeline_autonomo_pro`).

- **Padrão é `--jobs 1`**, e nesse caso o grafo **não é consultado**: a ordem é a do
  registro, byte a byte a esteira de sempre. `--serial` é o mesmo, explícito.
- **`--jobs N` agrupa bootstrap + produção numa escala única.** Paralelizar só a produção
  não renderia nada: 7 das 11 etapas escrevem `timeline.json`, então a produção é
  praticamente uma cadeia. As ondas úteis **cruzam as fases**:
  `stems` ∥ `fonte-limpa`, `sincronizar` ∥ `auditar-letra`,
  `auditar-ritmo` ∥ `planejar`.
- O estado compartilhado escrito por `step` (relatório, métricas, checkpoint) é guardado
  por um `threading.Lock`. O lock **não** cobre a execução da etapa, só a contabilidade.
- O log de cada etapa usa o índice do **registro**, não o da lista de execução: duas
  etapas em paralelo não escrevem no mesmo arquivo.
- Grafo inválido → aviso e escalonamento serial (falha fechada).

## Bugs reais que os testes encontraram

Os testes deste módulo acharam três erros de modelagem antes de qualquer execução real:

1. **`_casa` casava dois caminhos só por dividirem o diretório.** Isso invertia a aresta
   `stems → transcrever` (o `stems` produz o vocal; o `transcrever` o consome) num ciclo
   lógico.
2. **`fnmatch` deixa `*` atravessar `/`.** `clips_raw/*.mp4` engolia
   `clips_raw/vx_cenas_ia/*.mp4`, fechando uma aresta falsa `cenas-auto ← cenas-ia`.
   Substituído por casamento **segmento a segmento**.
3. **`cenas-ia` declarava `escreve=("artes_ia/*", …)`**, o que cobria as `fundo_*.png` —
   que são *assets do projeto* lidos por `chroma-auto`/`titulos`, não saída da IA.
   Declaração estreitada para `artes_ia/cena_*.png` + `artes_ia/escolhas.json`,
   espelhando o código real (`gerador_imagem_local.py` grava `<tipo>_<seed>_<digest>.png`).

O terceiro é o mais instrutivo: **a declaração estava errada, não o matcher.** A correção
certa foi alinhar `vx/etapas.py` à realidade.

## Grafo resultante

```
corrente (escrevem timeline.json): timeline → cenas-auto → chroma-auto → cenas-ia
                                   → titulos → manga-auto → graficos-auto
onda  1 (2 paralelas): stems, fonte-limpa          ← bootstrap ∥ produção
onda  2 (série): transcrever
onda  3 (2 paralelas): sincronizar, auditar-letra  ← bootstrap ∥ produção
onda  4..11 (série): sincronia, timeline, cenas-auto, chroma-auto, cenas-ia,
                     titulos, manga-auto, graficos-auto
onda 12 (2 paralelas): auditar-ritmo, planejar     ← produção ∥ produção
onda 13..15 (série): render-clipe, intro, qa-master
```

18 etapas → **15 ondas**, 3 com paralelismo (6 etapas). O master é uma cadeia e fica
serial — correto.

## Verificação empírica

`tools/_verificar_paralelismo.py` roda o mesmo projeto falso em serial e em ondas e
compara. Resultado (atraso artificial de 80 ms/etapa para o paralelismo ser observável):

| | serial (`--jobs 1`) | ondas (`--jobs 4`) |
|---|---|---|
| etapas chamadas | 13 | 13 |
| pico simultâneo | 1 | **2** |
| sobreposições reais | 0 | **2** |
| duração | 1.25 s | 1.08 s (**−14 %**) |

Com etapas reais (minutos cada), o ganho absoluto é proporcionalmente muito maior. Foi
verificado também que o conjunto de etapas é idêntico, que a composição nunca roda em
paralelo consigo mesma e que a ordem serial não regrediu.

## Consequências

- **Padrão não muda.** Nada de comportamento novo sem `--jobs`.
- **Ganho modesto, mas honesto.** A esteira é serial por construção; o DAG não inventa
  paralelismo que não existe. O valor maior é a **prova** de que nenhuma etapa edita o
  `timeline.json` ao mesmo tempo que outra o lê.
- **Novo comando:** `estudio.py dag` mostra as ondas e por que cada etapa está onde está.
- Regressão: `tests/test_dag.py` (39 testes) + `ProducaoEmOndasTests` em
  `tests/test_orquestrador.py`. Suíte: 562 OK.
