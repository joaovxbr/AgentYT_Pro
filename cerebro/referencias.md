# Vídeos de referência (raio-x de concorrentes/inspiração)

## Ferramenta
`estudio.py referencia <url|arquivo.mp4> [--comparar nosso.mp4]` → módulo `ferramentas/analisar_referencia.py`.
Saída em `referencias/<id>/`: `analise.md` (leitura humana), `analise.json` (dados), `folha_XX.png`
(1 quadro a cada 2 s, com timestamp — **olhe as folhas**), `video.mp4` e `video.info.json` (título, descrição, tags).
O vídeo baixado é só para estudo local: nunca vira footage nem é publicado. ~8 min para 4 min de vídeo (com comparação).

### O que é medido (e como)
| Métrica | Como | Leitura |
|---|---|---|
| cortes/min, plano médio/mediano, planos < 0,5 s | distância de histograma HSV a 24 fps (`LIMIAR_CORTE`) | ritmo de edição |
| cortes na batida / no onset (≤ 50/100 ms) | librosa `beat_track` e `onset_detect` | quanto o corte "cai" na música |
| flashes/min, tela preta, letterbox | salto de luma que volta; luma média; faixas pretas topo/base | efeitos de pontuação |
| movimento, tremor, zoom-in/out | phase correlation + divergência do fluxo óptico (160x90) | câmera/efeitos de zoom |
| tipo de quadro | OpenCLIP zero-shot a 2 fps (`ROTULOS`): texto grande, legenda, mangá, luta, close, kanji, card… | **estimativa**; confirmar nas folhas |
| cor dominante | histograma de matiz (`motion_lab.matiz_dominante`) | paleta/grade de cor |
| LUFS, pico, BPM | ffmpeg `ebur128`, librosa | loudness e andamento |

### Limites (dizer sempre ao usuário)
O agente **não assiste** ao vídeo: mede. Fonte, estilo de legenda, tipo de transição, overlays e qualidade de
motion só se confirmam olhando as folhas ou o vídeo. Tipos do CLIP erram em quadros mistos (ex.: legenda + luta).

## Referência 1 — MUGEN RAPS, "TODOS DE PÉ | Hiromi Higuruma" (analisado 30/09/2026)
`referencias/Vd0dlRTnWKw/analise.md` · 240 s · 1080p **60 fps** · publicado 27/09/2026 · ~550 views em 3 dias
(canal pequeno do mesmo nicho — referência de formato, não prova de sucesso). O nosso `legendas_mugen_pro.py`
já era inspirado nesse canal.

| métrica | Higuruma (ref.) | Gojo (nosso, `20260930T082128_a9967d63`) |
|---|---|---|
| cortes/min | 34,0 | 47,9 |
| plano mediano / máx. | 1,08 s / 11,25 s | 1,08 s / — |
| cortes ≤ 100 ms da batida | 32 % | 48 % |
| cortes ≤ 100 ms de onset | 70 % | 72 % |
| flashes/min | 2,0 | 2,0 |
| zoom-in / zoom-out (quadros) | 10 % / 16 % | 10 % / 11,5 % |
| texto grande dominante | 8 % | 14 % |
| mangá dominante | 6 % (fim: 80 % em 220–230 s) | 1 % |
| paleta | laranja 44 % + vermelho 23 % (**unificada**) | azul 27 %, vermelho 23 %, laranja 21 % (**misturada**) |
| LUFS / pico | −12,0 / −0,3 dBFS | −13,8 / −1,7 dBTP |
| fps | 60 | 30 |

### Fundos e cards gráficos (passada 4, `graficos/folha_graficos.png`)
20 momentos gráficos (texto grande, card, kanji, mangá) somando 47 s de 240 s — **um a cada ~12 s**.
- **13 de 20 sobre a cena do anime escurecida**: 60–85 % do quadro quase preto (`#03..`–`#1B..`), texto no
  meio/centro, 75–90 % de área lisa → a cena vira só "clima" atrás do título.
- 2–3 sobre **cenário temático** (o CLIP lê "tribunal" — o universo do Higuruma), paleta marrom/dourado.
- 4 de **mangá** P&B (2:27–2:48 e o fechamento 3:42–3:51, 9,5 s).
- Cor dos cards segue o momento: vermelho/laranja na maior parte, **azul** no trecho 3:22–3:35.
- Cards duram 1–3,5 s; os da abertura (0:00–0:17) são os mais longos (logo/título).

→ Virou o **lote 3** do motion (`card_cena_escura`, `card_cenario`, `card_retrato`, `card_manga`, `card_letra`),
em teste no lab; ver `cerebro/motion.md` seção 2b.

### O que a referência faz e nós não (backlog, em ordem de impacto)
1. **Paleta unificada por personagem** — 2/3 do vídeo numa só família de cor (laranja/vermelho do Higuruma).
   O nosso mistura as cores das cenas. Ideia: grade de cor por identidade (`projeto.json -> cor`) aplicada no
   render da footage, leve, preservando pele/branco; medir com este raio-x (meta: ≥ 55 % na família da identidade).
2. **60 fps** — a referência entrega 60 fps; o nosso render é 30 fps. Ideia: opção de 60 fps no `render_clipe`
   (NVENC aguenta), com interpolação só em planos lentos.
3. **Fechamento em mangá + plano final longo** — 220–230 s quase só mangá, depois ~11 s de quadro final parado
   sobre o fade. O nosso `manga-auto` põe 1–2 takes soltos; ideia: "sequência final de mangá" antes do End Card.
4. **Abertura mais longa e marcada** — 0–20 s com poucos cortes e card/logo (~25–40 % dos quadros). O nosso tem
   intro oficial (regra 1) + Title Card de 5 s; manter a regra, avaliar Title Card mais longo com motion.
5. **Descrição/SEO** (vale para `publicar.py`): título `MÚSICA | Personagem (Anime) | Rap Geek / Trap Anime | CANAL`;
   descrição abre com trecho da letra entre aspas, parágrafo de história canônica, "letra no comentário fixado",
   CTA com pergunta, créditos (faixa, produção, "100% canônico 1080p 60FPS", obra original), declaração de IA, hashtags;
   ~15 tags (personagem, anime, "Rap X", "Trap X", arco, técnica, "Rap Anime 2026", "AMV X").

### Onde já estamos à frente (manter)
Corte mais denso e mais na batida; mais motion tipográfico (e sobre a cena real); true peak seguro
(a referência bate −0,3 dBFS, risco de clipping; o YouTube normaliza para −14 LUFS de qualquer jeito, então o
master mais alto não ganha volume).
