# Padrões e Referências de Renderização AMV (VX RAPS)

🔴 **Regra de economia de memória/recursos do navegador (01/09/2026):**
Sempre que uma operação de postagem, upload, checagem ou edição em qualquer plataforma (YouTube Studio, TikTok Studio, Instagram) for concluída com sucesso ou encerrada, a aba aberta correspondente **DEVE SER FECHADA IMEDIATAMENTE** no Chrome via CDP (`/json/close/<targetId>`) para não acumular dezenas de abas pesadas e saturar a memória RAM do sistema. Manter apenas 1 aba de controle quando necessário.

## 1. Localização dos Assets Compartilhados
- **Abertura Oficial v2 (4.0s, só vídeo longo):** `/home/acer/Documentos/Video_Studio/assets/intro/intro_mugen_v2_169_mudo.mp4`
  - 🔴 v1 aposentada (`nova_intro_mugen_oficial.mp4`): o emblema era o **logo do BTS**.
  - 🚫 **Já publicado fica com a v1** — não reenviar/substituir vídeo no ar; a v2 é da próxima faixa em diante.
  - Vertical/Short **não leva vinheta**; se precisar, `intro_mugen_v2_916_curta_mudo.mp4` (1,5 s).
  - Geradores: `/home/acer/Documentos/Video_Studio/assets/intro/scripts/build.sh`
- **Fonte Padrão de Legendas:** `/home/acer/.local/share/fonts/Cinzel.ttf`
- **WhatsApp Bridge Endpoint:** `http://127.0.0.1:3000/send-media`
- **Canal YouTube:** `@VXRaps`
- **Conta TikTok:** `@mugen_raps`

## 2. Paleta de Cores BGR para Legendas Cinematográficas (.ass)
- **Muzan Kibutsuji (Demon Slayer):** Carmesim Sangue `&H001515E8&`
- **Hajime Kashimo (Jujutsu Kaisen):** Ciano/Ouro Elétrico `&H0000FFFF&` ou `&H00FFF000&`
- **Hakari Kinji (Jujutsu Kaisen):** Verde Neon Pachinko `&H00A0F000&`
- **Texto Base:** Branco Puro `&H00FFFFFF&` com Sombra `&H00000000&`

## 2b. Corte vertical 9:16 — enquadrar, nunca recortar

🔴 Regra do Álvaro (01/09/2026). Vale para **TikTok, Reels e Shorts do YouTube**.
Frame 16:9 inteiro centralizado (`scale=1080:-2`) sobre fundo borrado do mesmo frame
(`gblur=sigma=35`). **Nunca `crop` no primeiro plano** — decepa rosto e corta a ponta
da legenda. Receita: `~/Documentos/Video_Studio/tiktok_cortes/gerar_cortes_antidetect.py`.
Confira um frame extraído antes de publicar.

## 3. Checklist de Sincronia Narrativa
- [ ] Transcrição de alta precisão via `Whisper medium` com `beam_size=5`.
- [ ] Mapeamento 1:1 de momentos e lore de anime com a letra (zero cenas genéricas de filler).
- [ ] **Vídeo longo:** vinheta v2 de 0s a 4s mutada, com o beat começando no frame 0.
- [ ] **Corte/Short/Reel/TikTok:** SEM vinheta — entra direto no conteúdo.
- [ ] **Reel do Instagram em 9:16 confirmado por medição** do `<video>` (≈0,5613), não pelo print — a etapa "Cortar" abre recortada.
- [ ] **Sem emoji em texto queimado no vídeo** (a fonte do `drawtext` não desenha: vira quadradinho).
- [ ] **Legenda conferida na tela antes de clicar em Publicar** (o TikTok preenche com o nome do arquivo sozinho — ver `publicar-tiktok-cdp.md`).
- [ ] **Tarjas de marca no corte** — topo com título ciano `#00ffcc` + subtítulo branco, rodapé com `@VXRaps` em `#ffcc00`.
- [ ] **Corte vertical enquadrado, não recortado** — frame inteiro + fundo borrado; frame conferido antes de publicar.
- [ ] Fala de abertura e primeira estrofe tratadas separadamente; por padrão, a estrofe entra em até ~20s após a vinheta, sem obrigação de começar imediatamente.
- [ ] Se houver corte no áudio, um único mapa temporal foi aplicado ao WAV, `.ass`, plano visual, Whisper e QA (ver `sincronia-musical.md`).
- [ ] Cortes visuais aproximados de ataques/kicks sem deslocar os timestamps vocais das legendas; relatório registra métrica antes/depois.
- [ ] Render duplo: Master 1080p (`crf=18`) + Compacto para WhatsApp (`crf=27–28`, `<100MB`).
- [ ] 🔴 **Fontes limpas de marca d'água E de legenda de dublagem antes de montar** (ver `limpeza-fontes.md`).
- [ ] 🔴 **Varredura do intermediário `temp_video_*.mp4` (sem o `.ass`) dando ZERO** antes de entregar.
- [ ] Master e compacto decodificam integralmente; loudness, true peak, duração, faststart e emenda foram verificados.

## 4. Cortes Verticais para TikTok / Reels / Shorts (9:16)
- **Filtro FFmpeg 9:16 Cinematográfico:** Fundo desfocado dinâmico (`gblur=sigma=28:steps=3`) + vídeo centralizado 1080p nítido.
  ```bash
  ffmpeg -ss <INICIO> -to <FIM> -i <VIDEO_MASTER> \
    -filter_complex "[0:v]split=2[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=28:steps=3[bg_blur];[fg]scale=1080:-1[fg_scaled];[bg_blur][fg_scaled]overlay=(W-w)/2:(H-h)/2[v]" \
    -map "[v]" -map 0:a -c:v libx264 -preset fast -crf 19 -c:a aac -b:a 192k -movflags +faststart <SAIDA_9x16.mp4>
  ```
- **Duração Ideal dos Cortes:** 30s a 45s (ganchos virais focados em: Abertura/Apresentação, Drop do Refrão e Clímax da Luta).
- **Publicação TikTok Studio:** Automação CDP via `https://www.tiktok.com/tiktokstudio/upload` preenchendo tags e disparando upload nativo.
- **Padrão Obrigatório de Legenda/Copy TikTok:** Sempre incluir o nome da faixa, chamada explícita para a música completa e o link/handle do canal no YouTube:
  `[FRASE DE IMPACTO / GANCHO DO REFRÃO] | [PERSONAGEM] - [NOME DA MÚSICA]`
  `Assista o AMV completo no canal oficial do YouTube: youtube.com/@VXRaps #mugenraps #[anime] #[personagem] #rapgeek #animerap #fyp`
- **🔴 A chamada do corte aponta para o VÍDEO, não para o canal** *(01/09/2026)*.
  Os cortes do Muzan mandam para `@VXRaps` — quem clica cai na home
  e tem que caçar o vídeo. Use o link direto:
  `🎬 AMV completo: youtu.be/<ID_DO_LONGO>`. No TikTok e no Instagram o link
  não é clicável no post: escreva `AMV completo no YouTube: VX RAPS` e
  mantenha o link na bio.
- **🔴 O corte só sobe DEPOIS do longo estar no ar** (2 a 4 h). Ver
  `lancamento-e-copy.md` §1.
- **Fluxo de Cortes Múltiplos:** Ao criar cortes para redes, gerar no mínimo 3 cortes por música (Abertura/Verso 1, Drop do Jackpot/Refrão e Clímax/Batalha final) e publicá-los/disponibilizá-los com chamada pro YouTube em todos.
