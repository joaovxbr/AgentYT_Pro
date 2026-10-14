# Catálogo de módulos

Todo arquivo `ferramentas/*.py` precisa aparecer aqui (um teste reprova módulo não catalogado).
**Uso:** `esteira` = roda na produção automática · `manual` = comando do `estudio.py`/`publicar.py`
· `órfão` = ninguém usa (vai para `legado/`).

## Núcleo `vx/`
| Módulo | Papel |
|---|---|
| `vx/ambiente.py` | ffmpeg/ffprobe de `ferramentas/bin` no PATH do processo |
| `vx/lock.py` | lock de esteira com PID (órfão é retomado) |
| `vx/lazy.py` | imports preguiçosos do `estudio.py` |
| `vx/etapas.py` | registro único das etapas (fonte de `cerebro/etapas.md`) |
| `vx/composicao.py` | timeline recomposta da base limpa a cada esteira |
| `vx/config.py` | configuração em camadas e porteiros |
| `vx/projeto.py` | caminhos de áudio e stems a partir do manifesto |
| `vx/metrics.py` | métricas por etapa (tempo, cache, bytes de saída, motivo de falha estruturado); grava `_metricas.json` ao lado do `execucao.json` e imprime a tabela no console. Medir nunca derruba a esteira. Decisão 005 |
| `vx/checkpoint.py` | retomada (`--resume`): decide pular/rodar cada etapa com prova tripla (concluído + entradas iguais + saídas no lugar). Falha fechada: na dúvida, roda. Grava `_checkpoint.json` por `run_id`. Decisão 006 |
| `vx/runner.py` | executa uma etapa in-process (`estudio.main(argv)`), com a saída espelhada no log da etapa; converte o `SystemExit` do `estudio.py` em `ErroDeEtapa` (não pode matar a esteira) e preserva cwd/stdout. `--isolado` volta ao subprocess. Decisão 007 |
| `vx/cache.py` | cache por hash de entrada com escopo de PROJETO (sobrevive entre execuções): reaproveita a etapa em vez de chamá-la, com as mesmas três provas do checkpoint. `hash_obj` é o hash canônico (substitui 6 cópias ad-hoc). Guarda variações (voltar a uma entrada antiga volta a reaproveitar). Decisão 008 |
| `vx/dag.py` | grafo de dependências derivado de `vx/etapas.py`: ondas paralelizáveis + corrente serial obrigatória para quem escreve `timeline.json`. `validar()` reprova ciclo/onda insegura; `ordem_topologica()` é o caminho serial; `diagnosticar()`/`ganho_estimado()` alimentam `estudio.py dag`. Decisão 009 |
| `ferramentas/_vx.py` | ponte para os módulos de `ferramentas/` importarem `vx/` |

## Orquestração e portas
| Módulo | Uso | Papel |
|---|---|---|
| `estudio.py` | porta | porta de criação (todos os comandos) |
| `publicar.py` | porta | porta de publicação (QA final, YouTube, Shorts, TikTok) |
| `pipeline_autonomo_pro.py` | esteira | executa o registro de etapas, lock, QA do master |
| `clean_rebuild.py` | esteira | `rebuild-total`: backup e limpeza |

## Áudio, transcrição e letra
| Módulo | Uso | Papel |
|---|---|---|
| `stems_ia_gpu.py` | esteira | Demucs na GPU |
| `transcrever.py` | esteira | Whisper em blocos, lacunas de voz, filtro de alucinação; 2ª passada sem prompt nas lacunas; 3ª passada guiada pela letra pendente (`passada_guiada`); porteiro só reprova lacuna com letra pendente (incidente Douma) |
| `sincronizar_letra.py` | esteira | alinhamento monótono letra↔ASR, vocabulário do manifesto. Tempo **por palavra** pelo casamento de cada token (`origem` asr/estimada); `validar_palavras` = porteiro palavra a palavra dentro de `sincronia` (incidente `2026-10-01-douma-pov-fora-de-ordem.md`) |
| `auditor_letra.py` | esteira | porteiro letra × áudio |
| `legenda.py` | esteira | geração de ASS, medição de sincronia, legenda × silêncio vocal |
| `audio.py` | esteira | porteiro de LUFS / true peak / clareza |
| `bass_shake.py` | esteira | picos de subgrave |
| `audio_reactive_fx.py` | esteira | cache de picos de 808 |
| `ritmo.py` | manual | grade de BPM |
| `legendas_mugen_pro.py` | manual | ASS com destaques (lê `LETRA.txt` fixo) |
| `legendas_word_by_word.py` | manual | ASS palavra a palavra (a partir do ASR bruto) |
| `legendas_neon_motion.py` | manual | ASS neon (a partir do ASR bruto) |

## Cenas, timeline e câmera
| Módulo | Uso | Papel |
|---|---|---|
| `scene_intelligence.py` | esteira | catálogo visual por cena, `dead_scene` |
| `semantic_vision.py` | esteira | encoder OpenCLIP opcional |
| `semantic_scene_matcher.py` | esteira | `cenas-auto` |
| `montar_timeline.py` | esteira | timeline-base, cortes nos picos de 808 |
| `timeline_clipe.py` | esteira | contrato e validação da timeline |
| `direcao_clipe.py` | esteira | `planejar` → `plano_visual.json` |
| `motion_match_director.py` | esteira | direção de câmera |
| `movimento.py` | esteira | zoom/pan do render |
| `manga_auto_pipeline.py` | esteira | `manga-auto` |
| `manga_panel_director.py` | esteira | render dos painéis de mangá |
| `paineis_manga.py` | esteira/manual | máscaras de painel, comando `paineis` |
| `analisador_movimento.py` | manual | optical flow |
| `curadoria_ia.py` | manual | curadoria de clipes brutos |
| `folha_por_quadro.py` | manual | `folha-quadro`: auditoria quadro a quadro do master (motion vazando, legenda escondida, cartão duplicado, cor, flicker) — não é porteiro, é diagnóstico |
| `particulas_overlay.py` | manual | LAB (em teste): overlay de partículas em camadas (`chuva`, `chuva_cinema`, `neve`, `fogo`, `faiscas`, `folhas`); profundidade por camada, log-uniforme, sem integração na esteira |
| `transicao_diagonal.py` | manual | LAB (em teste): máscaras de transição (diagonal, chevron, wipe) com brilho/rastro; sem integração na esteira |
| `baixar_clipes.py` | manual | `clipes` (yt-dlp) |
| `smart_crop_916.py` | manual | reenquadramento 9:16 |
| `motion_blur_pro.py` | manual | motion blur |
| `motion_manga.py` | manual | take motion-manga |
| `paralaxe_3d.py` | manual | usado por motion_manga |

## Gráficos e tipografia
| Módulo | Uso | Papel |
|---|---|---|
| `graphic_auto_pipeline.py` | esteira | `graficos-auto` |
| `render_impact_scene.py` | esteira | render do take tipográfico |
| `kinetic_typography.py` | esteira | animações de texto |
| `style_preset_engine.py` | esteira | presets e temas de `assets/design/` |
| `background_fx_engine.py` | esteira | fundos procedurais |
| `font_manager.py` | esteira | fontes e pareamento |
| `titulos_pipeline.py` | esteira | Title Card e End Card |
| `creative_impact_director.py` | manual | `impacto-pro` |
| `impact_scene_orchestrator.py` | manual | `impacto-pro` |
| `impact_frames.py` | manual | `impacto` (legado do Graphics Pro) |
| `speedlines_manga.py` | manual | speedlines |
| `card_apresentacao_saber.py` | manual | `card-saber` (precisa de rembg) |
| `intro_card.py` | manual | card para `pov` |
| `artes_base.py` | manual | capa/banner |
| `motion_lab.py` | esteira | motion typography sobre a cena real (15 estilos na esteira: 11 sobre a cena + 4 cards com fundo próprio; cor pela letra) usada pelo `graficos-auto`; comando `motion-lab` para prévias em `lab/motion/`. Manual: `cerebro/motion.md` |
| `lab_mugen_pro.py` | manual | gerador de prévias cinematográficas avançadas no estilo MUGEN RAPS (fenda de sombras, kanji vertical, tipografia frasal com speedlines e legenda neon) |

## Render e efeitos
| Módulo | Uso | Papel |
|---|---|---|
| `render_dispatch.py` | esteira | **todo** encode NVENC passa aqui |
| `render_clipe.py` | esteira | render do corpo |
| `compositor_master_gpu.py` | esteira | `concatenar_intro` + loudnorm + limitador |
| `filtros.py` | manual | `filtrar`, `filtros` |
| `revisao_master.py` | manual | prévias de revisão (Sasuke) |
| `loop_infinito_916.py` | manual | loop de short |
| `color_grade_pro.py` | esteira/manual | color grading cinematográfico por arquétipo (cursed_energy, titan_fire, etc) com lift seguro contra porteiro de imagem |
| `cinemascope_fx.py` | manual | imprime filtro |
| `snap_impact_transition.py` | esteira/manual | transição de corte com flash pop e snap zoom punch nos drops de grave 808 |
| `ghosting_fx.py` | manual | imprime filtro |
| `pixel_sort_glitch.py` | manual | imprime filtro |
| `color_splash.py` | esteira/manual | desaturação seletiva (preto e branco de alto contraste isolando cor) via chromahold |

## QA
| Módulo | Uso | Papel |
|---|---|---|
| `imagem.py` | esteira | porteiro de tela morta/congelada/página |
| `fonte_limpa.py` | esteira | porteiro de fonte: marca d'água/logo (recorte/delogo) e legenda queimada (cena `poluida`). Incidente `cerebro/incidentes/2026-09-30-douma-fonte-poluida.md`. Também acha marca que aparece só num trecho (`marcas_por_trecho` → `delogo enable=between`) e mede tela verde por instante (`linhas_chroma`). Desde 01/10/2026 lê texto com **OCR local** (RapidOCR): logo/copyright = mesmo texto no mesmo lugar ≥ 6 s (limpa e confere de novo com OCR); legenda/cartela de qualquer tamanho = cena `poluida`. Cache `qa/fonte_ocr/`. `auditar_texto_render` = porteiro de texto no corpo renderizado (dentro do `qa-master`) |
| `chroma_auto.py` | esteira | etapa `chroma-auto`: cena de tela verde vira take `vx_chroma` (fundo IA do projeto + personagem recortado com despill + aura pulsando no 808). Manual: `estudio.py chroma-auto <slug>`. Saída `clips_raw/vx_chroma/`, estado `qa/vx_chroma/state.json`, config: `PADRAO` do código < `config/estudio.json -> chroma_auto` < `projeto.json -> chroma_auto` |
| `auditor_ritmo.py` | esteira | cortes por minuto (informativo) |
| `qa.py` | manual | `relatorio` |
| `entrega.py` | manual (obrigatório após aprovação) | `promover` (candidato → master com backup) e `entrega` (pacote completo conferido). Ver `cerebro/entrega.md` |
| `analisar_referencia.py` | manual | `referencia`: raio-x de vídeo de referência (cortes, batida, câmera, cor, tipo de quadro, áudio) + comparação com o nosso. Ver `cerebro/referencias.md` |
| `pesquisa.py` | manual | `pesquisar`, `avaliar` (rede) |

## IA de imagem
| Módulo | Uso | Papel |
|---|---|---|
| `gerador_imagem_local.py` | esteira | cliente ComfyUI, sessão sob demanda, cache |
| `critico_imagem.py` | esteira | VX Image Critic (OpenCLIP) |
| `cenas_ia_pipeline.py` | esteira | `cenas-ia` |
| `gerador_artes_ia.py` | manual | `capa-ia`, `artes-ia` |
| `gerador_tumbas_ab.py` | manual | miniaturas A/B |

## Publicação e shorts
| Módulo | Uso | Papel |
|---|---|---|
| `shorts_pipeline.py` | manual | `shorts` |
| `pov_lyrics_official.py` | manual | layout POV dos shorts; acende palavra a palavra por `letra_sincronizada.json -> words`, evento termina quando a próxima acende |
| `pov_lyrics_bottom_v2.py` | manual | base do layout POV |
| `pov.py` | manual | `pov` |
| `distribuicao_social_pro.py` | manual | `social`, `lancamento` |
| `publicacao_doc.py` | manual | `PUBLICACAO.md` |
| `hook_retencao_shorts.py` | manual | overlay de gancho |
| `cdp.py` | manual | Chrome DevTools (via publicar) |

## Legado (fora da esteira, fase 5)
Movidos para `legado/ferramentas/` em 2026-09-30 (backup zip em `backups/`); ninguém importava.
Para reativar um: mover de volta para `ferramentas/`, catalogar acima e escrever teste.
sfx_engine, suno_dl e mureka_dl (cópias ativas em `skills/downloadmusic/`), neon_overlay_fx,
transicoes_vfx, autoteste, pov_cinematic_pro (+ seu teste em `legado/tests/`), `estudio.py.bak_vx_amv`.
