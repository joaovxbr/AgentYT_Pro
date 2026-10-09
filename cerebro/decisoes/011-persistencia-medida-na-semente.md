# Decisão 011 — A persistência da marca d'água é medida na SEMENTE, nunca no blob dilatado

Data: 2026-10-09
Módulo: `ferramentas/fonte_limpa.py` (`caixas_persistentes`)
Regressão: `tests/test_fonte_limpa.py::PersistenciaNaSementeTest` (4 testes)

## Problema

O porteiro de fonte reprovou 4 clipes do `megumi_shadows` por "marca d'água/logo":

| clipe | caixas | o que era de verdade |
|---|---|---|
| `megumi_sukuna_corredor` | **22 caixas** | corredor escuro com câmera quase parada — **nada** |
| `megumi_grupo_final` | 2 | idem |
| `megumi_final_sangue` | 1 | idem |
| `megumi_floresta_maldicao` | 1 | idem |

A folha de contato dos 26 clipes mostrou **zero marca d'água** em todos. Os "logos" eram as
**bordas estáticas do cenário** (batentes de porta, pilares), que persistem porque a câmera
mal se move num plano escuro.

## Causa raiz

`caixas_persistentes` monta a máscara assim:

```python
mascara = (persist >= persistencia_min)   # SEMENTE: pixels de borda persistentes
mascara = sem_linhas_de_borda(mascara)
mascara = cv2.dilate(mascara, ...)        # INCHA para virar caixa
n, rot, stats, _ = cv2.connectedComponentsWithStats(mascara, 8)
...
"persistencia": persist[rot == k].mean()  # ← BUG: media no componente DILATADO
```

A dilatação (`np.ones((5,9))`, 45 px) engrossa a semente com vizinhos que **não** passaram no
limiar. O `mean` sobre o blob inteiro então dilui o valor: os clipes reprovados reportaram
**0.079 – 0.208**, todos muito abaixo do próprio `persistencia_min = 0.55`.

Ninguém percebeu porque **o campo nunca era conferido contra o limiar** — uma vez que o blob
existe, ele entra na lista.

## A prova que fechou o diagnóstico

Medi o mesmo detector sobre um **logo sintético inequívoco** (a palavra "LOGO" fixa no canto
de 48 quadros sobre fundo aleatório que muda):

| caso | persistência no blob (código antigo) |
|---|---|
| logo REAL, 48/48 quadros | **0.242** |
| borda estática de cenário (falso positivo) | até **0.208** |

**Não havia separação.** A métrica estava quebrada, não o limiar — baixar ou subir
`persistencia_min` não resolveria nada (era inclusive ignorado na prática).

Medindo na **semente** (só os pixels acima do limiar):

| caso | persistência na semente | densidade da semente |
|---|---|---|
| logo REAL | **0.975** | 0.222 |
| borda de cenário | 0.58 – 0.73 | 0.06 – 0.16 |

Separação limpa. Um logo é denso e persistente; uma borda de cenário é esparsa.

## Decisão

1. `persistencia` passa a ser a **média de `persist` sobre os pixels da semente** dentro da
   caixa — nunca sobre o blob dilatado.
2. Nova guarda **`densidade_seed_min = 0.18`**: fração do blob que veio da semente. Logo tem
   preenchimento; borda solta não.
3. Um blob sem nenhum pixel de semente é descartado.

## Consequências

- `auditar_projeto` em `megumi_shadows`: **4 clipes reprovados → 0** (26/26 aprovados).
- Nenhum `delogo` desperdiçado em cena limpa (o pior caso ia re-encodar 22 caixas por ~10 s
  de corredor, borrando o quadro à toa).
- Limiar **não foi afrouxado**: `persistencia_min` continua 0.55 e agora é **de fato aplicado**.
  A regra ficou mais rígida, não mais frouxa — o falso positivo saiu por medição correta.
- Custo: `caixas_persistentes` só olha a semente dentro da bounding box; desprezível.

## Alternativas descartadas

- **Subir `variacao_min_cena`** — o corredor tinha variação 32.7 (limiar 8.0), não é clipe
  estático. Não era o caso.
- **Exceção humana em `qa/excecao_fonte_limpa.json`** — proibido pela decisão 002 (porteiro
  não se afrouxa por projeto) e pela doutrina "consertar a ferramenta, nunca a música".
  A causa era o motor.
- **Baixar `persistencia_min`** — não muda nada; o campo era ignorado após o blob existir.
- **Filtrar por posição (só canto/borda)** — as caixas falsas apareciam também no centro
  (`posicao: centro`, 5 das 22). Não separa.
