# Regras editoriais e visuais

## Estrutura do vídeo longo
1. Intro oficial (10 s, `assets/intro/Eu_preciso_criar_INTRO_para_o.mp4`, áudio próprio).
2. Title Card (5 s) com fade-in da música — a música nunca começa em silêncio.
3. AMV sincronizado: cenas reais, legenda ASS, takes especiais raros.
4. End Card (5 s) com fade-out.

## Render
- Só GPU: tudo passa por `ferramentas/render_dispatch.py` (`h264_nvenc`, preset p7). Nunca libx264.
- Legenda sempre ASS nativo do FFmpeg (`Style:` + `Dialogue:`); nunca overlay Pillow contínuo.
- Master final: `loudnorm I=-14` + limitador de true peak (`compositor_master_gpu.LIMITADOR_TRUE_PEAK`).
- Footage de anime recebe lift leve de sombras (`render_clipe._lift_sombra`); takes gráficos, cards e cenas IA não.

## Escolha de cenas (`cenas-auto`)
- `scene_intelligence.py` cataloga os clipes (OpenCV + OpenCLIP opcional); `semantic_scene_matcher.py` casa letra ↔ cena.
- Pontuação: semântica letra↔tags, alvos visuais (`scene_semantics`), intensidade, qualidade, duração, penalidade de repetição.
- Cada linha cantada fica ancorada no segmento de maior sobreposição; alvos obrigatórios dessa linha entram no score.
- Cenas mortas (quase pretas, sem detalhe: tail de clipe, splash Prime/Netflix) são `dead_scene` e nunca entram.
- Assets gerados (`impact_*`, `take_saber_*`, `vx_*`) não são fonte narrativa.

## Takes especiais (raros por design)
- **Cenas IA** (`cenas-ia`): só onde a cena real ficou fraca (`max_match_score`); cena real sempre vence. Prompt automático por conceitos da letra + `assets/design/cenas_ia_map.json` + `imagem_ia`. VX Image Critic escolhe a melhor variação.
- **Mangá** (`manga-auto`): 1–2 takes em clímax fortes.
- **Graphics Auto** (`graficos-auto`): palavra dominante + pico de 808 + espaçamento. Estilos por `assets/design/semantic_style_map.json`. Nomes do personagem rotacionam `neon_write_on`, `neon_letter_reveal`, `neon_outline_fill`, `neon_trace`. Com `legenda_ass` ativa, o card não repete a frase inteira.
- Todo take especial é `graphics_locked` no plano (câmera 1.0→1.0, sem efeito extra por cima).
- Limites em `config/estudio.json` (ver `cerebro/configuracao.md`).

## Novo estilo visual
1. Implementar como preset/módulo reutilizável, parâmetros em `assets/design/`.
2. Teste + prévia isolada (`estudio.py impacto-pro <slug>`, `estudio.py previa-clipe <slug> --de S --dur D --legenda`).
3. Só depois deixar `graficos-auto` escolher; manter anti-repetição e limites; suíte verde.

## Motion sobre a cena real (aprovado, decisão 003) — manual completo em `cerebro/motion.md`
- Módulo `ferramentas/motion_lab.py`, parâmetros `assets/design/motion_lab.json`. Texto atrás do personagem (recorte rembg), cena como plate (escurece/dessatura + push-in), texto segue a câmera, cor do brilho tirada da cena, grão e vinheta.
- Estilos: `atras_personagem`, `palavra_por_palavra` (cada palavra no tempo cantado), `glitch_slice` (reage ao 808), `kanji_fundo`, `maquina_escrever`.
- Na esteira: `graficos-auto` usa estes estilos por padrão (`graphics_auto.motion_real`). Estilos de linha ocultam a legenda ASS só no trecho do take.
- **Lote 2 (aprovado, na esteira):** `impacto_zoom` (palavra cai 3x→1x com soco de câmera e flash), `eco_repeticao` (ecos em contorno atrás do personagem), `fragmentos` (letras voam e montam a palavra), `contorno_energia` (aura no contorno do personagem, pulsa no 808), `letterbox_cinema` (barras de cinema + título espaçado), `faiscas` (brasas saindo da palavra).
- **Cor pela letra:** o brilho de todo estilo usa a cor do conceito cantado (`assets/design/motion_lab.json -> cores`); sem conceito de cor na letra, usa a cor dominante da cena. Nunca inventar cor que contradiga a letra ("Vermelho repelindo" é vermelho).
- **Estilo novo daqui para frente:** implementar em `ESTILOS`, listar em `motion_lab.EM_TESTE` (um teste impede que entre em `motion_estilos`), prévia no lab, aprovação, então tirar de `EM_TESTE` e incluir em `motion_estilos`.
- Laboratório para testar estilo novo ou outro trecho: `estudio.py motion-lab <slug> [--de S --dur D --estilos a,b]` → `projetos/<slug>/lab/motion/` (não toca timeline, legenda nem master). Estilo novo: implementar em `ESTILOS`, testar no lab, aprovar, só então incluir em `motion_estilos`.

## Rejeitado / fora da produção
- Overlay "chapado" de tipografia sobre a cena (sem recorte/tracking/plate): rejeitado (ficou colado/artificial). Substituído pelo motion sobre cena real (decisão 003).
- SFX sintético no master (`legado/ferramentas/sfx_engine.py`): soa artificial sobre a mix.
