# Incidente 2026-10-09 — Falso positivo de marca d'água em cenário estático

**Onde:** `ferramentas/fonte_limpa.py` → `caixas_persistentes` (porteiro de fonte)
**Quando:** 09/10/2026, produção `megumi_shadows`
**Quem sofreu:** 4 de 26 clipes reprovados indevidamente (`sukuna_corredor` com **22 caixas**)
**Gravidade:** alta — reprovava material limpo e ia gastar `delogo` borrando o quadro

## Sintomas

| sintoma | causa | correção |
|---|---|---|
| 22 "marcas" num corredor sem marca nenhuma | a persistência era medida no blob **já dilatado**; a dilatação engordou a semente com pixels abaixo do limiar e o `mean` caiu de 0.9 para 0.08 | medir a persistência na **semente** (`persist_seed`) |
| caixas reportadas com persistência 0.08–0.21, **abaixo do limiar 0.55** | o campo nunca era conferido — uma vez que o blob existia, entrava na lista | guarda explícita `if persist_seed < persistencia_min: continue` |
| bordas de cenário passando como logo | semente de borda é **esparsa** (grande parte do blob é dilatação) | nova guarda `densidade_seed_min = 0.18` |

## Prova

Logo sintético inequívoco (palavra "LOGO" fixa no canto por 48 quadros, fundo aleatório):

| caso | blob diluído (antigo) | semente (novo) |
|---|---|---|
| logo REAL | **0.242** | **0.975** |
| borda estática de cenário | até **0.208** | 0.58 – 0.73 |

O antigo **não separava** logo real de cenário — a métrica estava quebrada.

## Lição

**Métrica derivada de máscara morfológica tem que ser medida na SEMENTE, nunca no resultado
da dilatação.** A dilatação existe para *agrupar* pixels em caixas; ela não é a evidência.
Misturar as duas coisas fez um 0.9 virar 0.08 e ninguém notou porque o valor final nunca era
comparado ao limiar que o gerou.

Corolário: **todo campo que dá nome a um limiar deve ser conferido contra esse limiar.**
`persistencia >= persistencia_min` era assumido, nunca verificado.

## Estado

- `auditar_projeto` em `megumi_shadows`: 4 reprovados → **0** (26/26 aprovados), 45.7 s.
- Suíte: **579 testes, OK** (+4 em `PersistenciaNaSementeTest`).
- Decisão registrada: `cerebro/decisoes/011-persistencia-medida-na-semente.md`.
- Nenhuma exceção humana criada, nenhum limiar afrouxado.

## Bônus do mesmo dia: `_quadros` sem teto de silêncio

Durante a investigação o `estudio.py clipes` ficou **54 min** parado. Diagnóstico com
`faulthandler.dump_traceback_later` mostrou que **não era deadlock**: era OCR caro
(~0.19 s/quadro × 2 passadas × 26 clipes). Mesmo assim corrigi duas coisas reais:

1. **`_quadros` lia o pipe do ffmpeg sem timeout.** Um ffmpeg travado congelava a esteira para
   sempre — nem terminava nem falhava. Agora há teto de silêncio (`TIMEOUT_S = 60`) via thread
   de leitura + fila, com erro alto e `p.kill()`. **Tentativa inicial com `select.select()`
   falhou no Windows** (`WinError 10038`: `select` só aceita soquete, não pipe) — pego pelo
   teste antes de valer em produção.
2. **`_duracao` era chamado 3× por clipe** (`_quadros`, `detectar_marca`, `auditar_projeto`)
   para o mesmo arquivo. Agora `dur` é calculado uma vez e repassado.
3. **O OCR de verificação rodava com `cache=None`**, relendo o clipe inteiro depois de cada
   `delogo`. Agora tem cache próprio (`<clipe>__poslimpeza.json`), invalidado sozinho pela
   chave nome+tam+mtime do arquivo reescrito.
