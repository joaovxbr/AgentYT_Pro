# Incidente: `sincronia` REPROVADO + texto de estilo queimado na legenda (Asta, 05/10/2026)

**Relato:** esteira do `asta` parou na etapa `sincronia` (`CalledProcessError`, exit 1) depois
de 23 min — `fonte-limpa`, `auditar-letra`, `auditar-ritmo`, `cenas-auto`, `chroma-auto`,
`cenas-ia`, `titulos`, `manga-auto`, `graficos-auto` e `planejar` tinham passado.

## Causa 1 (medida): refrão repetido + ASR caindo palavra

`sincronia` mediu 6 linhas fora de ±0,30 s (p90 0,560) e 3 problemas palavra-a-palavra, todos
nas 4 linhas do refrão:

```
77.08s  -5.700s  ANTI-MAGIA — EU NASCI COM ZERO DE MAGIA
80.34s  -2.440s  ANTI-MAGIA — E MESMO ASSIM EU CHEGO PRIMEIRO
linha 24 'Rei' acende quando canta '-MAGIA'
```

O Whisper ouviu `-MAGIA` **sem** `ANTI` em 77,08 e sem `Rei`/`sem` em 87,22 (vocal dobrado no
refrão). O alinhamento monotônico então grudou o token `ANTI` da letra na ocorrência
idêntica **5,7 s depois** — a linha estava no tempo certo, o casamento por palavra é que
andou. É o mesmo formato de falha do incidente `2026-10-01-douma-pov-fora-de-ordem`, só que
por palavra faltante e não por token sem par.

## Causa 2 (medida, e a mais grave): `transcricao-canonica` comia o `[Style of Music]`

Para destravar, gerei a fonte de verdade nº 3 do `cerebro/` (`transcricao_canonica.json`).
Ela veio com **41 linhas para uma letra de 36** e, ao conferir, as 5 primeiras eram o
parágrafo de estilo do `suno_lyrics.txt`:

```
Brazilian rap, hard trap beat, dark orchestral, heavy 808 bass,
anime battle energy, male vocalist aggressive confident delivery, ...
```

`cmd_transcricao_canonica` lê `suno_lyrics.txt` e `extrair_linhas_suno` só descartava linhas
que **começam com `[`** — o cabeçalho `[Style of Music]` saía, o corpo não. Uma dessas linhas
ainda ganhou janela (`10,98–12,38 s`) e entrou em `letra_sincronizada.json`, ou seja: a
legenda teria queimado *"anime battle energy, male vocalist aggressive confident delivery"*
no master, antes da primeira linha cantada. Os outros projetos não pegaram porque só o
Sasuke tem `suno_lyrics.txt` com bloco de style — o Douma/Gojo começam direto no `[Intro]`.

## Correção permanente

- `ferramentas/sincronizar_letra.py` (`extrair_linhas_suno`) agora ignora a prosa que **segue** uma
  tag não-lírica (`_BLOCO_NAO_LIRICO = style/meta/creditos/credits/descrição`) até a próxima
  tag. Tags de seção continuam comportadas como antes.
- 3 testes novos em `tests/test_auditor_letra.py::ExtrairLinhasSunoTests` (style ignorado,
  letras depois do style sobrevivem, arquivo sem style inalterado).
  Suíte: **350 testes, OK** (antes 347).
- Para a letra em questão, a fonte passou a ser a transcrição canônica (letra autoral + tempos
  do áudio), que resolve os dois problemas de uma vez: `transcricao-canonica asta` →
  `sincronizar asta` → **`sincronia` APROVADO, mediana +0,000 s, p90 0,000 s, POV 0 problemas**,
  36 linhas canônicas = 36 linhas sincronizadas = 36 eventos no `legendas/asta.ass`.
  Lacunas/baixa confiança caíram de 62 para 22.

## Sequência operacional (o que atrasou de verdade)

1. A 1ª esteira morreu na interrupção da sessão (`exit -15`, `process.kill`) e deixou
   `.esteira.lock` com PID morto. `vx_lock.adquirir` remove lock órfão sozinho, mas o `rm`
   manual antes de relançar é mais rápido que descobrir.
2. A 2ª foi a que expôs o bug do style. Não adianta re-rodar `sincronizar` sem trocar a
   fonte: o alinhador monotônico é determinístico e reprova igual.
