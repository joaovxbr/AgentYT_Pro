# Etapas da esteira (gerado de `vx/etapas.py`)

> Não edite à mão: rode `estudio.py cerebro`. Um teste falha se este arquivo ficar defasado.

Ordem: stems → transcrever → sincronizar → timeline → fonte-limpa → auditar-letra → auditar-ritmo → cenas-auto → chroma-auto → cenas-ia → titulos → manga-auto → graficos-auto → planejar → sincronia → render-clipe → intro → qa-master

**Composição:** antes da fase `producao`, a esteira restaura `timeline.json` a partir de `timeline_base.json` e arquiva os `state.json` de cenas-auto, cenas-ia, titulos, manga-auto e graficos-auto (backup em `qa/esteira/<run_id>/recomposicao/`). Cada etapa reaplica sobre a base; renders e imagens IA vêm do cache. Ver `vx/composicao.py`.

## Fase: bootstrap

### `stems` (bloqueia, só se a saída faltar, cacheável)

Separa voz/bateria/baixo/outros com Demucs (GPU).

- **Lê:** `entradas/{slug}_normalizado.wav`
- **Grava:** `entradas/stems/{slug}_normalizado_vocals.wav`, `entradas/stems/{slug}_normalizado_drums.wav`, `entradas/stems/{slug}_normalizado_bass.wav`, `entradas/stems/{slug}_normalizado_other.wav`

### `transcrever` (bloqueia, só se a saída faltar, cacheável)

Whisper large-v3 no stem vocal, em blocos, com 2a passada nas lacunas de voz.

- **Lê:** `entradas/stems/{slug}_normalizado_vocals.wav`, `LETRA_LINHAS.txt`
- **Grava:** `entradas/transcricao.json`
- **Nota:** Reprova se sobrar voz sem palavras depois do 1o verso.

### `sincronizar` (bloqueia, só se a saída faltar, cacheável)

Alinha a letra autoral (monotono) aos tempos do ASR e gera a legenda ativa.

- **Lê:** `entradas/transcricao.json`, `LETRA_LINHAS.txt`, `transcricao_canonica.json`
- **Grava:** `letra_sincronizada.json`, `<projeto.json:legenda_ass>`, `legendas/{slug}_pov.ass`

### `timeline` (bloqueia, só se a saída faltar, cacheável)

Timeline-base 0..fim sem lacunas, planos quebrados nos picos de 808.

- **Lê:** `letra_sincronizada.json`, `clips_raw/*.mp4`, `qa/vx_graphics_bass_peaks.json`
- **Grava:** `timeline.json`, `timeline_base.json`, `qa/composicao.json`
- **Nota:** Tambem roda sozinha se a letra sincronizada mudou desde a base (vx/composicao.py).

## Fase: producao

### `fonte-limpa` (bloqueia, cacheável)

Porteiro de fonte: marca d'agua/logo (limpa com recorte ou delogo) e legenda queimada (cena vira poluida).

- **Lê:** `clips_raw/*.mp4`
- **Grava:** `qa/fonte_limpa.json`, `qa/fonte_limpa.md`, `clips_raw/_originais/*`
- **Nota:** Reprova se sobrar marca d'agua depois da limpeza. Incidente Douma (clipes oficiais com legenda em ingles).

### `auditar-letra` (bloqueia, cacheável)

Porteiro letra x audio: voz sem transcricao, verso nao cantado, trecho cantado fora da letra.

- **Lê:** `LETRA_LINHAS.txt`, `entradas/transcricao.json`, `entradas/stems/{slug}_normalizado_vocals.wav`
- **Grava:** `qa/auditoria_letra.json`, `qa/auditoria_letra.md`

### `auditar-ritmo` (informativa, cacheável)

Mede cortes por minuto e retencao estimada.

- **Lê:** `timeline.json`
- **Grava:** —
- **Nota:** Informativo; nunca reprova.

### `cenas-auto` (bloqueia, sempre refeita)

Scene Intelligence + matcher: escolhe a cena real do anime para cada trecho da letra.

- **Lê:** `timeline.json`, `letra_sincronizada.json`, `clips_raw/*.mp4`, `projeto.json`
- **Grava:** `timeline.json`, `scene_intelligence.json`, `qa/scene_matcher/plano.json`, `qa/scene_matcher/state.json`
- **Nota:** Cenas mortas (tela preta, splash de streaming) sao excluidas (dead_scene).

### `chroma-auto` (bloqueia, sempre refeita)

Cena de tela verde (chroma key) vira cena composta: fundo do projeto + personagem recortado + aura pulsando no 808.

- **Lê:** `timeline.json`, `qa/fonte_limpa.json`, `artes_ia/fundo_*.png`
- **Grava:** `timeline.json`, `clips_raw/vx_chroma/*`, `qa/vx_chroma/state.json`
- **Nota:** Pedido do usuario (Douma): nunca mostrar a tela verde crua.

### `cenas-ia` (bloqueia, sempre refeita)

Gera cena nova no ComfyUI so onde a cena real ficou fraca.

- **Lê:** `timeline.json`, `projeto.json`, `assets/design/cenas_ia_map.json`, `artes_ia/fundo_*.png`
- **Grava:** `timeline.json`, `artes_ia/cena_*.png`, `artes_ia/escolhas.json`, `clips_raw/vx_cenas_ia/*.mp4`, `qa/vx_cenas_ia/plano.json`, `qa/vx_cenas_ia/state.json`
- **Nota:** ComfyUI offline = pula com aviso (cenas_ia.strict=true torna obrigatorio). Grava `artes_ia/cena_*.png` (e nao `artes_ia/*`): as `fundo_*.png` sao assets do projeto, lidas pela chroma-auto/titulos -- declarar o glob amplo criava aresta falsa (cenas-ia -> chroma-auto) e um ciclo no grafo (vx/dag.py).

### `titulos` (bloqueia, sempre refeita)

Title Card (abertura) e End Card (encerramento).

- **Lê:** `timeline.json`, `projeto.json`, `artes_ia/fundo_*.png`
- **Grava:** `timeline.json`, `clips_raw/vx_titulos/*`, `qa/vx_titulos/state.json`

### `manga-auto` (bloqueia, sempre refeita)

Insere 1-2 takes raros de manga em climax fortes.

- **Lê:** `timeline.json`, `letra_sincronizada.json`
- **Grava:** `timeline.json`, `clips_raw/vx_manga_auto/*`, `qa/vx_manga_auto/state.json`

### `graficos-auto` (bloqueia, sempre refeita)

Takes tipograficos pela letra + picos de 808, em motion sobre a cena real do anime.

- **Lê:** `timeline.json`, `letra_sincronizada.json`, `assets/design/semantic_style_map.json`, `assets/design/motion_lab.json`
- **Grava:** `timeline.json`, `clips_raw/vx_graphics_auto/*`, `qa/vx_graphics_auto/state.json`
- **Nota:** Estilos de linha ocultam a legenda so no trecho do take (decisao 003).

### `planejar` (bloqueia, cacheável)

Plano de camera por shot (respeita graphics_locked).

- **Lê:** `timeline.json`, `entradas/transcricao.json`
- **Grava:** `plano_visual.json`

### `sincronia` (bloqueia, cacheável)

Porteiro de legenda: ASR + linhas exibidas com a voz em silencio.

- **Lê:** `<projeto.json:legenda_ass>`, `entradas/transcricao.json`, `entradas/stems/{slug}_normalizado_vocals.wav`
- **Grava:** —

## Fase: master

### `render-clipe` (bloqueia, sempre refeita)

Render do corpo em NVENC com legenda ASS queimada.

- **Lê:** `timeline.json`, `plano_visual.json`, `<projeto.json:legenda_ass>`, `entradas/{slug}_normalizado.wav`
- **Grava:** `saidas/esteira/<run_id>/{slug}_corpo.mp4`
- **Nota:** Nao cacheavel: escreve em saidas/esteira/<run_id>/, que e da execucao atual.

### `intro` (bloqueia, sempre refeita)

Concatena a intro oficial + loudnorm -14 LUFS + limitador de true peak.

- **Lê:** `saidas/esteira/<run_id>/{slug}_corpo.mp4`, `assets/intro/Eu_preciso_criar_INTRO_para_o.mp4`
- **Grava:** `saidas/esteira/<run_id>/{slug}_master_final_com_intro.mp4`
- **Nota:** Interna ao orquestrador (compositor_master_gpu.concatenar_intro).

### `qa-master` (bloqueia, sempre refeita)

Decode completo + porteiro de imagem + porteiro de TEXTO (OCR no corpo) + porteiro de audio no master final.

- **Lê:** `saidas/esteira/<run_id>/{slug}_master_final_com_intro.mp4`, `saidas/esteira/<run_id>/{slug}_corpo.mp4`
- **Grava:** `qa/esteira/<run_id>/decode.log`, `qa/esteira/<run_id>/imagem.json`, `qa/esteira/<run_id>/texto_render.json`, `qa/esteira/<run_id>/audio.json`
- **Nota:** Interna ao orquestrador. Clareza vocal e so aviso. Texto que nao e da letra/titulos (logo de streaming, legenda em ingles, cartela) reprova (fonte_limpa.auditar_texto_render).

