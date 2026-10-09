# Roadmap da reconstrução

Estratégia: **incremental**. Trocar o esqueleto (orquestrador, config, cérebro)
reaproveitando os módulos que funcionam. Cada fase termina com suíte verde e o
Gojo (`projetos/gojo_infinito`) passando na esteira.

| Fase | Objetivo | Status |
|---|---|---|
| 1. Fundação | ffmpeg sem PATH do usuário, lock com PID antes de tudo, porteiros sem aprovação silenciosa | **concluída** |
| 2. Orquestrador | registro único de etapas (`vx/etapas.py`); timeline recomposta da base em toda esteira; ComfyUI sob demanda | **concluída (2a + 2b)** — sobras listadas abaixo |
| 3. Configuração | parâmetros em `config/estudio.json` (override por projeto), porteiros em `config/porteiros.json` (sem override), `audio_fonte` respeitado, vocabulário no manifesto | **concluída** |
| 4. Cérebro completo | AGENTS.md índice; manual migrado para `cerebro/`; teste impede doc de mentir sobre o código | **concluída** |
| 5. Limpeza | órfãos → `legado/` com backup; `.rar` e logs antigos já não existiam | **concluída** |
| 6. Modelo de módulo novo | template de etapa para o Hermes criar módulos (`cerebro/novo_modulo.md`) | **concluída** |

## Fase 1 — o que foi feito
- `vx/ambiente.py`: coloca `ferramentas/bin` no PATH do processo; chamado por `estudio.py`, `pipeline_autonomo_pro.py`, `render_dispatch.py`.
- `vx/lock.py`: lock JSON com PID; lock órfão (PID morto) é retomado e registrado em `execucao.json -> lock_orfao_removido`; lock ilegível falha fechado. Lock agora cobre bootstrap e clean-rebuild.
- `audio.py`: medição de loudness que falha (ou −inf) **reprova** em vez de aprovar com 0.
- `sincronia`: além do ASR, checa se alguma linha de legenda aparece com o stem vocal em silêncio (`legenda.eventos_sobre_silencio`). Gojo: 0 falsos positivos.
- Testes: `tests/test_fundacao.py`.

## Fase 2a — o que foi feito
- `vx/etapas.py`: registro único (nome, descrição, lê, grava, bloqueante, fase). A esteira itera `PRODUCAO` e usa `render-clipe` do registro; o preflight lista a ordem a partir dele.
- Etapa `bloqueante=False` que falha fica como `aviso` no `execucao.json` e a esteira segue.
- `vx/lazy.py`: os 51 imports do topo do `estudio.py` viraram preguiçosos. Um módulo quebrado só derruba o comando que o usa; `estudio.py` carrega sem cv2/librosa.
- Comandos novos: `estudio.py etapas [slug]` (ordem + entradas que faltam) e `estudio.py cerebro` (regenera `cerebro/etapas.md`).
- Testes: `tests/test_orquestrador.py` (inclui teste que falha se `cerebro/etapas.md` ficar defasado). Dois testes antigos que procuravam a ordem como texto na pipeline agora checam o registro.
- Prova: esteira do Gojo `20260930T032526_a1c399a2` pelo registro novo → aprovada; LUFS −13,82, TP −1,68, quase-morto 0,55% (mesmos números da execução anterior aprovada `20260930T024424_a03a5d4a`).

## Fase 2b — o que foi feito
- `vx/composicao.py`: `estudio.py timeline` grava `timeline_base.json` + hash da letra sincronizada (`qa/composicao.json`). No início de toda esteira a `timeline.json` é restaurada da base e os `state.json` das 5 etapas de composição são arquivados em `qa/esteira/<run_id>/recomposicao/`; cada etapa reaplica sobre a base.
  - Resolve: "preserved_after_downstream_visuals" (mudança de letra/parâmetro não era aplicada) e "alterada externamente; falha fechada" (só `rebuild-total` destravava).
  - Letra sincronizada mudou → a base é regenerada sozinha antes de compor.
  - Timeline editada fora da esteira é copiada para o backup da execução antes de ser substituída.
  - Projeto antigo sem base: adota `base_timeline` do estado do scene matcher; sem base limpa, mantém o comportamento antigo (`modo: legado`).
- `gerador_imagem_local.sessao_comfy`: o ComfyUI só sobe se alguma imagem não estiver em cache (antes subia a cada esteira em cenas-ia e titulos).
- Cliente ComfyUI local ignora proxy do sistema (Charles devolvia 503 para 127.0.0.1; 2 testes falhavam por isso).
- Prova: esteira `20260930T034948_edf53122` recompôs do zero → timeline idêntica à anterior (81 segmentos, 0 diferenças), QA aprovado, LUFS −13,82, TP −1,68, quase-morto 0,55%; ComfyUI não foi iniciado.
- Testes: `tests/test_composicao.py`, teste de proxy em `test_gerador_imagem_local.py`.

## Fase 3 — o que foi feito
- `vx/config.py`: `secao()` (código < `config/estudio.json` < `projeto.json`) usada por graphics_auto, cenas_ia, manga_auto, titulos e edicao; `porteiro()` (código < `config/porteiros.json`, sem projeto) usada por audio, imagem_master e auditar_letra.
- `vx/projeto.py`: `audio()` e `stem()` a partir de `audio_fonte`. Removidos os 9 caminhos `_normalizado` montados à mão (pipeline, transcrever, sincronia, auditor de letra, social, transcrição canônica, 3 pipelines).
- `ferramentas/_vx.py`: ponte única para os módulos de `ferramentas/` usarem `vx/`.
- Vocabulário do Sasuke saiu de `sincronizar_letra.py` para `projetos/sasuke/projeto.json -> vocabulario`; Gojo ganhou o seu.
- Docs: `cerebro/configuracao.md`, decisão 002. Testes: `tests/test_configuracao.py` (inclui chave desconhecida no config e valores do config iguais aos do código).

## Fase 4 — o que foi feito
- `AGENTS.md` virou índice (~35 linhas): ordem de leitura, 8 regras sagradas, duas portas.
- Manual v3 inteiro preservado em `cerebro/historico/AGENTS_v3_legado.md` (só consulta).
- Novos: `cerebro/producao.md` (passo a passo + "porteiro reprovou, e agora?"), `cerebro/editorial.md` (cenas, takes, render, estilos, o que foi rejeitado), `cerebro/modulos.md` (todos os 85 módulos com uso esteira/manual/órfão).
- Corrigido do manual antigo: numeração duplicada, `legado/` e `graphics_overlay_lab.py` inexistentes, "CLIP é evolução futura" (já existe), `compositor_master_gpu` descrito como motor 1-pass (só concatena intro), texto corrompido.
- `tests/test_cerebro.py`: reprova arquivo citado inexistente, `estudio.py <cmd>` inexistente, módulo de `ferramentas/` sem entrada no catálogo, catálogo com módulo fantasma e AGENTS.md que volte a crescer. Prova: um doc proposital citando `graphics_overlay_lab.py` e `comando-fantasma` foi reprovado.

## Fase 5 — o que foi feito
- 7 módulos órfãos + `estudio.py.bak_vx_amv` movidos para `legado/ferramentas/`; `test_pov_cinematic_pro.py` para `legado/tests/`. Backup zip em `backups/fase5_legado_*.zip`.
- Removidos de `estudio.py` os 3 imports preguiçosos sem uso (transicoes_vfx, sfx_engine, neon_overlay_fx).
- `AgentYT_Pro.rar` (5 GB) e logs antigos: já tinham sido removidos da raiz/`logs/` quando a fase foi executada.

## Fase 6 — o que foi feito
- `cerebro/novo_modulo.md`: modelo de módulo, comando, `Etapa`, config, teste e checklist. Teste garante que o modelo compila.

## Sobras (quando mexer no arquivo)
- Lógica que ainda está no `main()` do `estudio.py` (cenas-auto, graficos-auto…) → funções `cmd_*`.
- `state.json` das etapas podem ser simplificados (hoje só cache dentro de uma execução).
- Limiares internos de detecção (`imagem.py`: luz<24 etc., `scene_intelligence`) ainda no código.

## Dívidas resolvidas depois da fase 6
- Legenda ativa: `legenda`, `sincronizar`, `karaoke`, o porteiro de sincronia, o `pov --karaoke` e o `relatorio` (`qa.py`) usam `_ass_ativo` = `projeto.json -> legenda_ass`. `karaoke` e `legenda` gravavam em `legendas/<slug>.ass` fixo (render queimava a legenda antiga se o manifesto apontasse outro arquivo). Variantes de estilo (`legendas-mugen`, `legenda-palavra`, `legenda-neon`) gravam em arquivo próprio de propósito e não são queimadas. Teste: `tests/test_legenda_ativa.py`.
- Requirements: um só, `requerimentos.txt` na raiz, fixado nas versões do `.venv` real (Python 3.10, numpy 2.2.6, torch 2.5.1+cu121). O antigo requirements.txt de ferramentas (Python 3.11, numpy 2.4.6) foi removido. Teste em `tests/test_cerebro.py` reprova segundo arquivo ou versão solta.

## Motion sobre cena real (aprovado e integrado)
- `estudio.py motion-lab` → 5 estilos aprovados pelo usuário → `graficos-auto` renderiza os takes sobre a cena real (decisão 003). Estilos de linha ocultam a legenda só no trecho. Testes: `tests/test_motion_lab.py`.
- Lote 2 (6 estilos) aprovado e integrado; cor do brilho segue a letra (adendo da decisão 003).
- Edição "cheia": ~1 take/12 s, até 12, os 11 estilos aparecem; take de linha até o fim real da última palavra (incidente `cerebro/incidentes/2026-09-30-tormento-sumiu.md`). Manual: `cerebro/motion.md`.
- Lote 3 (cards com fundo, da referência MUGEN RAPS): 5 ativos (adendo 3 da decisão 003).
- **Biblioteca de motion** (`assets/design/biblioteca_motion.json` → `cerebro/biblioteca_motion.md`): 15 ativos, `kanji_fundo` desativado; regra do protagonista visual para `contorno_energia`/`card_retrato` (adendo 4).
- Backlog vindo do raio-x da MUGEN RAPS (`cerebro/referencias.md`): paleta unificada por personagem, 60 fps, abertura mais marcada, modelo de descrição/SEO no `publicar.py` (fechamento em mangá: feito via `card_manga`).
- Próximas ideias (não feitas): efeitos entre takes na footage normal (speed ramp, flash/zoom no 808 fora dos takes), transições temáticas entre planos, sombra projetada do texto na cena.
- Possível melhoria: recorte com `isnet-anime` (modelo próprio para anime, download ~170 MB) via `motion_lab.json -> recorte.modelo`.

## Dívidas conhecidas (não resolvidas ainda)
- Nenhuma além das sobras acima.
