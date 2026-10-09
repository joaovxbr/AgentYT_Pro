# Incidente: QA de texto do render — hard sub de terceiro no master (Asta, 05/10/2026)

**Relato:** a esteira passou por tudo, inclusive `sincronia` e `render-clipe`, e caiu no
`qa-master` com o porteiro de texto:

```
ERRO: QA de texto do render reprovado (19): 24.5s 'Withinafifthleaf'; 35.5s
'Withina fourthleafdwellsgoodluck.'; 42.0s 'What in theworld is that grimoire?!'; ...
```

## Como mapeei (reutilizável)

1. `qa/esteira/<run_id>/texto_render.json` dá os tempos — **medidos no `asta_corpo.mp4`**
   (sem a intro de 10,0 s).
2. Pra cada tempo, achar o plano: vale `plano_visual.json` (shots), não só `timeline.json`
   — os dois podem divergir nos limites.
3. O texto identifica a fonte sozinho: carreguei o OCR de cada clipe
   (`qa/fonte_ocr/<clipe>.json`) e procurei a string normalizada. **As 19 leituras todas
   apontavam para o mesmo arquivo: `asta_oficial_cinco_folhas.mp4`.**
4. Confirmei nos `design.json` dos takes: o clipe também era **fundo** dos takes de gráfico
   (YUNO, MAGI, TOURO) e **fonte** do take de mangá (`sources[0] = scene_035`) — o mesmo hard
   sub reaparecia em três camadas diferentes.

## Por que os dois detectores do `fonte-limpa` não pegaram

- `qa/fonte_limpa.json` dizia `texto_ocr = 0` e `legenda_queimada = 0.0` na `scene_035`
  [105,28–108,88], **enquanto o cache de OCR antigo** tinha "What in the world is that
  grimoire?!" de 105,0 a 107,5 com conf 0,97.
- Refiz o OCR no clipe **já corrigido**: os samples daquela janela voltaram com conf abaixo
  de `ocr_conf_min` (0,6) — o recorte de 1,058x do `--corrigir` mudou a caixa do texto e o
  OCR deixou de ler; o detector de imagem (`legenda_score_min` 0,55) também ficou em 0/7.
- Ou seja: a prova do `fonte-limpa` foi feita no clipe corrigido e **acha** o clipe limpo;
  a prova do render, feita no vídeo composto, **acha** o texto. As duas estão certas — o
  texto está lá, só com confiança menor na fonte.

## Remédio aplicado (o que o `cerebro/` manda)

Trocar a fonte, nunca afrouxar o porteiro:

- `asta_oficial_cinco_folhas.mp4` → `clips_raw/_rejeitados/` (arquivo preservado) e fora de
  `projeto.json -> clips_fontes`, com o motivo em `_clipes_rejeitados`;
- takes gerados (`clips_raw/vx_graphics_auto/`, `vx_manga_auto/`) movidos para
  `backups/takes_antigos_*` — eles embutiam o clipe e são regenerados pela esteira;
- `catalogar-cenas asta` + `timeline asta` **depois** de mexer em `clips_raw/` (senão
  `esteira --planejar` reprova com "fonte ausente"): catálogo 10 clipes, 402 cenas,
  14 `pagina`, 161 `poluidas`, 228 vivas; timeline 87 segmentos, auditoria OK.

Texto **nosso** na lista (`ANTEMAGIA` aos 45,0 s e `Raio,cx` aos 64,0 s) não era intruso de
verdade: `intrusos_render` mantém uma leitura solta só quando há outra a ≤1,5 s — e as duas
estavam ao lado de hard sub de verdade. Com a fonte removida elas caem sozinhas.
