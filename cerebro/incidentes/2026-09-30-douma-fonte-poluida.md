# Incidente: cenas poluídas no Douma — marca d'água e legenda queimada (30/09/2026)

**Relato do usuário:** "o nosso QA que é para marcas de direito e legendas está poluído nas cenas… acabou deixando
essas falhas."

## Causa real
- Os clipes mais fortes do Douma são **oficiais** (Crunchyroll/Aniplex no YouTube) e vêm com **legenda em inglês
  queimada**; o trailer e os raw clips têm **logo/marca** no rodapé.
- O QA de fonte (`imagem.auditar_fonte`) só olhava tela morta/congelada. Nenhum porteiro olhava texto na imagem.
- O Scene Matcher escolhe por semântica: as cenas oficiais legendadas são justamente as de maior score.

## Correção permanente — porteiro `fonte-limpa` (`ferramentas/fonte_limpa.py`)
| Problema | Detecção (sem OCR) | Ação |
|---|---|---|
| Marca d'água / logo | Borda **parada** em ≥ 55 % de ~48 quadros enquanto o resto do quadro muda (`caixas_persistentes`); ignora limite de letterbox e emenda do pad borrado | Recorte mínimo (mesma proporção, ≤ 1,18×) que deixa a marca fora (`enquadramento_limpo`); se não couber, `delogo` na caixa. Original em `clips_raw/_originais/` |
| Legenda queimada | Faixa de baixo com glifos claros de contorno escuro, alinhados e centralizados, comparada à faixa de cima (`legenda_no_quadro`, 2 fps) | Cena com legenda em ≥ 30 % dos quadros vira `poluida` no catálogo (`scene_intelligence.marcar_cenas_poluidas`) e o matcher nunca escolhe (igual `dead_scene`) |

- Roda sozinho: etapa `fonte-limpa --corrigir` no início da esteira (bloqueia se sobrar marca) e ao final de
  `estudio.py clipes`. Manual: `estudio.py fonte-limpa <slug> [--corrigir]`.
- Relatório: `qa/fonte_limpa.md` / `qa/fonte_limpa.json`. Limiares: `config/porteiros.json -> fonte`.
- Testes: `tests/test_fonte_limpa.py`.

## Reincidência — "watermark tá cheio" (mesmo dia)
- **Causa:** packs de twixtor juntam vários sub-clipes, cada um com a sua marca. A detecção do clipe inteiro
  (persistência ≥ 55 % de todos os quadros) não via marca que dura só alguns segundos.
- **Correção:**
  - `varrer` (4 fps) roda `marcas_por_trecho`: janela deslizante de 6 s, caixa confirmada por
    `contraste_temporal` (traços parados dentro, entorno mexendo; `contraste_max`).
  - `limpar_trechos` aplica `delogo enable='between(t,a,b)'` só no intervalo da marca.
  - `separar_trechos` tira dois falsos positivos: **legenda parada** (caixa na faixa de legenda num trecho
    com legenda queimada → vira só `legenda_parada` no relatório, sem delogo e sem reprovar) e **tela verde**
    (contorno do personagem sobre chroma; o `chroma-auto` troca o fundo).
  - `--corrigir` é **idempotente**: sempre parte de `clips_raw/_originais/` (sem delogo sobre delogo).
  - Relatório mostra marca do clipe todo, marca por trecho, legenda parada e % de tela verde.
- Testes: `MarcaPorTrechoTests`, `ChromaTests`, `SepararTrechosTests` em `tests/test_fonte_limpa.py`.
- Tela verde crua no vídeo: resolvida pela etapa `chroma-auto` (`cerebro/motion.md` §10).

## Reincidência 2 — prints do usuário (01/10/2026)
O usuário mandou 4 prints do corpo: **logo Crunchyroll** no canto (0:07 e 0:09, inclusive semitransparente num
flash), legenda em inglês de **uma palavra** ("DESTROY", 0:09) e a **cartela do filme** "Demon Slayer Infinity
Castle" com legenda embaixo (0:24).

**Causas medidas:**
- Logo: as bordas do logo **eram** persistentes (100 % no canto), mas encostavam na linha da moldura/letterbox.
  A dilatação fundiu os dois num componente com 93 % da largura e o filtro de letterbox jogou o logo fora junto.
  O copyright no rodapé ("© Koyoharu Gotoge/SHUEISHA…") teve o mesmo destino.
- "DESTROY": score de legenda 0,33–0,53 (< 0,55): palavra única tem poucos glifos para a heurística.
- Cartela: logo do filme no meio + legenda ("You look so young and tasty!"), fora da faixa que a heurística olha.

**Correção (troca de abordagem: medir texto de verdade em vez de só bordas):**
- `sem_linhas_de_borda`: tira linhas longas (moldura/letterbox) da máscara **antes** da dilatação.
- **OCR local** (RapidOCR/ONNX, `rapidocr_onnxruntime` em `requerimentos.txt`) a 1 fps no original, com cache
  em `qa/fonte_ocr/<clipe>.json`:
  - **mesmo texto no mesmo lugar por ≥ `ocr_marca_min_s` (6 s)** = marca (logo de streaming, copyright, @ de
    canal); em ≥ 50 % do clipe vai para a limpeza do clipe todo, senão vira marca de trecho;
  - todo o resto (legenda de qualquer tamanho, cartela, título) entra na linha de legenda: a cena vira `poluida`;
  - ignora confiança < 0,6 e texto sem 3 letras/dígitos latinos (kanji do cenário não é poluição).
- `plano_limpeza`: recorte que esconde a **maior área de marca** dentro de 1,18× (o logo grande); o que não
  couber (copyright fino) leva `delogo` antes do recorte.
- **Prova real:** depois de limpar, OCR de novo (0,5 fps) no clipe limpo. Se ainda ler a marca, reprova.
  Texto de trecho que ainda aparece (cartela final "Watch on Crunchyroll" cortada pelo recorte) vira trecho poluído.
- **Cena poluída ficou estrita:** basta **1 leitura do OCR** dentro da cena (`texto_ocr > 0`), além da regra antiga de
  ≥ 30 % de legenda pela heurística. Legenda no topo ("Constantly…", "I am angry.") e cartela parcial escapavam.
- **Porteiro final no render** (`fonte_limpa.auditar_texto_render`, dentro do `qa-master`): OCR a 2 fps no corpo.
  Só pode aparecer texto nosso (letra, `projeto.json`, "VX RAPS APRESENTA", "INSCREVA-SE NO CANAL"); OCR com letra
  trocada é tolerado. Marca conhecida (Crunchyroll, Aniplex, "Watch on"…) reprova na hora; texto estranho reprova se
  for lido 2× em 1,5 s. Relatório: `qa/esteira/<run_id>/texto_render.json`.
  - Rodado no candidato `20261001T015549_42206c7d`: **reprovou** com exatamente o que o usuário viu (Crunchyroll e
    "Watch on" no take de mangá, "Constantly…", "I am angry.").
  - Na esteira seguinte (`20261001T024934_057835e5`) as legendas já tinham sumido e o porteiro **reprovou** só o
    take de mangá (1:29, "Watch on Crunchyroll"). Causa: `manga_auto_pipeline` reaproveitava o take pelo **nome do
    arquivo** e não re-renderizava quando as cenas-fonte mudavam. Corrigido: cache por conteúdo (`_spec_render`:
    texto, duração e cenas-fonte em `.design.json`).
- Testes: `OcrTests`, `TextoRenderTests` e `LinhasDeBordaTests` em `tests/test_fonte_limpa.py`; `RenderCacheTests` em
  `tests/test_manga_auto_pipeline.py`.

**Lição:** cache de take gerado sempre pelo **conteúdo**, nunca pelo nome. E todo vídeo passa pelo OCR do render
antes de virar candidato: é a prova final de que não sobrou texto de terceiros.

## Resultado no Douma
- Marca em 3 clipes (raw clips, Shinobu Aniplex, trailer) → recorte 1,06×–1,15× ancorado em cima.
- 31 cenas com legenda queimada marcadas como poluídas e fora da escolha.
- Clipes reprovados antes pelo porteiro de imagem continuam em `clips_raw/_reprovados/`.

## Limites conhecidos (dizer ao usuário)
- Marca **sem texto** (só um símbolo) e semitransparente depende da borda parada e ainda pode escapar.
- O OCR amostra a 1 fps: texto que aparece por menos de ~1 s pode escapar.
- Solução definitiva para material legendado: preferir fonte sem legenda (raw/twixtor sem texto).

## Lição
Clipe "oficial" não é clipe limpo. Todo clipe passa pelo porteiro de fonte antes de virar cena.
