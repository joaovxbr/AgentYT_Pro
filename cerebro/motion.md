# Motion sobre a cena real — manual completo

Sistema que coloca tipografia em movimento **em cima da cena real do anime** nos takes do
`graficos-auto`. Aprovado pelo usuário (decisão 003). Este documento é a referência única:
como funciona, como decide, onde ajustar, como diagnosticar e como estender.

Código: `ferramentas/motion_lab.py` (render e estilos) + `ferramentas/graphic_auto_pipeline.py`
(escolha dos momentos, janelas e injeção na timeline) + `ferramentas/render_clipe.py` (legenda oculta).
Parâmetros visuais: `assets/design/motion_lab.json`. Parâmetros editoriais: `config/estudio.json -> graphics_auto`.
Testes: `tests/test_motion_lab.py`.

## 0. A biblioteca (fonte única) — `assets/design/biblioteca_motion.json`
Todo efeito de motion vive **catalogado** na biblioteca: status, tipo, camada, gatilhos por categoria,
exigências, quando usar e quando evitar. A esteira lê a biblioteca e escolhe **sozinha**, pela letra e pelo
vídeo de cada música nova — ninguém escolhe efeito à mão. O catálogo legível (gerado) é
`cerebro/biblioteca_motion.md` (`estudio.py cerebro`; teste reprova se ficar defasado).

| Campo | Significado |
|---|---|
| `status` | `ativo` (esteira usa) · `em_teste` (só no lab) · `desativado` (fora da esteira, código mantido) |
| `tipo` | `palavra` (a palavra do take) · `linha` (a frase inteira; oculta a legenda) · `card` (troca o fundo) |
| `gatilhos` | categoria → prioridade: `nome`, `batida`, `atmosfera`, `linha`, `fechamento` (1 = primeiro) |
| `exige` | `protagonista` = só com o personagem principal verificado em cena |
| `descricao`, `quando_usar`, `evitar`, `notas`, `motivo` | explicação obrigatória (teste reprova campo vazio) |

**Mudar status/regra = editar o JSON** (sem código). Ex.: reativar o kanji = `"kanji_fundo": {"status": "ativo"}`.
`graphics_auto.motion_estilos` (config) é só a lista permitida; **quem manda no status é a biblioteca**.

**Estado em 30/09/2026:** 15 ativos · `kanji_fundo` **desativado** (pedido do usuário, temporário).

### Regra do protagonista (`exige: protagonista`)
Pedido do usuário: **`contorno_energia` só em pontos onde o personagem principal está em cena** (o mesmo vale
para `card_retrato`, que é um retrato dele).
1. **Verificação visual** (padrão): `motion_lab.DetectorProtagonista` monta a aparência a partir de
   `projeto.json -> imagem_ia.tags_personagem`, sem nomes e tags genéricas (Gojo: *white hair, blue eyes,
   blindfold, black blindfold, uniform*), e compara com OpenCLIP em 3 quadros da footage real do take contra
   "outro personagem" e "sem personagem". Protagonista se score ≥ `protagonista_visual_min` (0,50).
   Calibração no Gojo: planos do Gojo 0,64–0,99; Sukuna 0,00–0,14; Jogo 0,00; tela de efeito 0,00.
2. **Sem `tags_personagem`**: usa `scene_semantic_scores` do cenas-auto (entity do protagonista ≥ 0,40 e o maior).
   É o plano B porque o CLIP **por nome** confunde personagens (no Gojo, 70 de 79 planos saíam como Geto/Sukuna/Jogo).
3. Auditoria: o quadro de cada take avaliado fica em `qa/vx_graphics_auto/protagonista/<tempo>s_score<x>.jpg`,
   e o `qa/vx_graphics_auto/plano.json` mostra `protagonista` e `protagonista_score` por take.
4. Música nova: basta preencher `imagem_ia.tags_personagem` com a aparência (cabelo, olhos, roupa, marcas).

## 1. Por que não fica "colado"
O overlay antigo foi rejeitado por parecer adesivo. Cada take agora tem, em camadas:
1. **Plate**: a cena real, escurecida (`plate.escurecer`), dessaturada (`plate.saturacao`) e com push-in lento (`plate.push_in`).
2. **Texto de trás** (camada `atras`).
3. **Personagem** recortado com rembg (`recorte.modelo`, padrão `u2net`), um pouco mais vivo que o plate (`plate.sujeito_brilho`). O texto de trás fica **atrás dele**.
4. **Texto da frente** (camada `frente`).
5. **Acabamento**: grão (`grao`) e vinheta (`vinheta`) por cima de tudo.

O texto acompanha a câmera (phase correlation entre quadros → `tracking`), e o recorte é suavizado no tempo, zerando em cada corte.

## 2. Estilos sobre a cena ao vivo (lotes 1 e 2, 11 estilos) — mais os 4 cards da seção 2b = 15 na esteira
| Estilo | Camada | Tipo | O que faz |
|---|---|---|---|
| `atras_personagem` | trás | palavra | palavra gigante escrita da esquerda p/ direita com cabeça de luz |
| `kanji_fundo` | trás+frente | palavra | kanji enorme translúcido (mapa `kanji`) + palavra PT fechando o espaçamento |
| `eco_repeticao` | trás | palavra | ecos em contorno que se expandem em ondas; pulsam no 808 |
| `contorno_energia` | trás | palavra | aura da cor no contorno do personagem (borda do recorte), pulsa no 808 |
| `letterbox_cinema` | trás+frente | palavra | barras de cinema fecham; título espaçado; crédito (personagem/anime) na barra |
| `glitch_slice` | frente | palavra | entra fatiada com RGB split; treme e refatia nos picos de 808 |
| `impacto_zoom` | frente | palavra | cai de 3x→1x; **soco de câmera** (zoom+tremor na cena e no recorte) + flash |
| `fragmentos` | frente | palavra | letras voam de posições aleatórias girando e montam a palavra |
| `faiscas` | frente | palavra | brasas sobem da palavra; rajada extra nos picos de 808 |
| `palavra_por_palavra` | frente | **linha** | cada palavra entra no tempo cantado; a atual brilha; a última fica acesa |
| `maquina_escrever` | frente | **linha** | a linha é digitada no ritmo das palavras, cursor piscando |

## 2b. Lote 3 — cards com fundo próprio
**Status (30/09/2026):** `card_cena_escura`, `card_cenario`, `card_manga` e `card_letra` **aprovados e na esteira**.
`card_retrato` **reprovado na 1ª versão** e de volta ao lab (`EM_TESTE`) com correção — ver abaixo.
Derivados do raio-x da MUGEN RAPS (`cerebro/referencias.md`). Em vez de escrever sobre a cena ao vivo, o
estilo **troca o fundo inteiro** do take via `c.plate_custom = (plate, sujeito|None)` (com `c.mascara_custom`
se trouxer o próprio recorte). Todos seguem a cor da letra e têm flash curto de entrada.

| Estilo | Fundo | Texto |
|---|---|---|
| `card_cena_escura` | 1º quadro da janela congelado, luz 30 %, desfocado, tinta da cena, push-in 8 %, brilho radial da cor | palavra gigante + crédito (personagem · anime) entre filetes |
| `card_cenario` | cenário temático do projeto (`artes_ia/fundo_*.png`, sem personagem) com pan lento e tinta da cor; sem ele, cena bem desfocada | palavra + brasas de luz |
| `card_retrato` | quadro com mais personagem recortado: fundo escuro desfocado + brilho, personagem nítido na frente | palavra ENORME **atrás** do personagem + crédito embaixo |
| `card_manga` | página de mangá com 3 momentos da janela (P&B, retícula, contornos), painéis entrando em sequência | palavra num balão branco |
| `card_letra` | tela quase preta com degradê sutil da cor | a linha palavra por palavra (estilo de **linha**: oculta a legenda) |

Para aprovar: `estudio.py motion-lab <slug> --estilos card_...` → usuário aprova → seguir a seção 8.

Na esteira: `card_manga` vem primeiro no **último quinto da música** (fechamento em mangá, como a referência);
`card_letra` entra junto com os estilos de linha; `card_cena_escura`/`card_cenario` entre os de atmosfera e de nome.

### `card_retrato` — por que foi reprovado e o que mudou
- **1ª versão:** escolhia o quadro da janela com **mais** área recortada. No Gojo (47,6 s) isso foi um ombro/braço
  em close, desfocado, ocupando ~59 % do quadro: o título ficou atrás de uma mancha rosa ("ficou feio, sem sentido").
- **Correção** (`avaliar_retrato`, `escolher_quadro_retrato`, `tapa_texto`):
  - só vale quadro com recorte entre 10 % e 45 % do quadro (`RETRATO_COBERTURA`), caixa do recorte que não ocupe o quadro
    inteiro (`RETRATO_MAX_CAIXA`), personagem longe da borda e **nítido** (variância do Laplaciano ≥ 25 dentro do recorte);
  - entre os válidos, vence o mais nítido com cobertura perto de 28 %;
  - se o personagem cobrir mais de 45 % da faixa do título (`RETRATO_MAX_TAPA_TEXTO`), o título vai **na frente**;
  - nenhum quadro serve → o take vira `card_cena_escura` (nunca um retrato ruim).
- Regressão em `tests/test_motion_lab.py::RetratoTests`.

Estilo de **palavra** usa a palavra escolhida pelo `graficos-auto` e dura o take. Estilo de **linha**
mostra a frase inteira e por isso **oculta a legenda ASS** naquele trecho (seção 5).

Efeito de câmera: um estilo pode pedir `c.efeito_plate = {"zoom", "dx", "dy"}` no quadro; o mesmo
transform (`motion_lab.transformar`) é aplicado à cena e ao recorte, para o texto continuar atrás do personagem.

## 3. Como o `graficos-auto` decide
1. **Candidatos** (uma linha → no máximo um candidato): palavra dominante da linha por
   presets procedurais (`semantic_style_map.json`), nome do personagem, **termos do manifesto**
   (`vocabulario.termos`, força 0,90), **conceitos com kanji** (`motion_lab.json -> kanji`, 0,74) ou
   palavra longa fora das stopwords (0,62). Score = semântica + batida do 808 + confiança + posição; corta em `min_score`.
2. **Seleção** (`_select`), com `motion_real=true`:
   - até `motion_max_scenes` takes e ~1 a cada `motion_segundos_por_take` s;
   - centros a ≥ `motion_min_gap` s; no máximo `motion_max_por_30s` takes em ±15 s;
   - a mesma palavra (tema do refrão, ex.: INFINITO) pode repetir até `motion_repetir_palavra` vezes, a ≥ `motion_distancia_mesma_palavra` s;
   - nunca sobre intro/outro/cards/mangá/cena IA (faixas protegidas) nem nos guardas de início/fim.
3. **Estilo** (`motion_lab.escolher_estilo`):
   - nome do personagem → presença: atrás, aura, cinema, kanji, eco;
   - 808 forte (beat ≥ 0,6) → impacto: soco de câmera, glitch, fragmentos, faíscas, aura;
   - demais → atmosfera: kanji, eco, faíscas, cinema…;
   - linha curta (≤ `motion_max_linha` s) → estilos de linha entram logo depois do 1º preferido;
   - **variedade**: fora os 3 últimos, vence o **menos usado no vídeo** → todos aparecem antes de repetir (com 12 takes e 15 estilos, não repete nenhum);
   - último quinto da música → `card_manga` primeiro (fechamento).
4. **Janela**: estilo de palavra usa a janela do candidato; estilo de linha usa `janela_de_linha` (seção 5).
   Se a janela de linha colidir com outro take/faixa protegida ou passar de `motion_max_take_linha`, cai para estilo de palavra.
5. **Sem footage real** no intervalo → mantém o take procedural antigo (fundo gerado).

Resultado do Gojo (30/09/2026): 11 takes, um de cada estilo (ver `qa/vx_graphics_auto/plano.json`).

## 4. Cor pela letra (regra do usuário)
A cor do brilho segue **o que está sendo cantado**, nunca contradiz a letra.
- Mapa `motion_lab.json -> cores` (azul, vermelho, purple, infinito, sangue, fogo, raio, ouro, sombra, domínio…).
- Casamento: palavra inteira, ou começo de palavra para chaves com ≥ 4 letras (vermelh**a**, explod**indo**); chaves compostas ("hollow purple", "seis olhos") casam como trecho. Havendo várias, vence a que aparece **primeiro** na linha.
- Prioridade: palavra do take > linha cantada no instante > linha do take > cor dominante da cena (histograma de matiz).
- Entre linhas a cor faz transição curta (~0,2 s), sem piscar.
- Conceito novo = acrescentar no JSON (sem código). Ex.: `"gelo": "#9FE8FF"`.

## 5. Estilos de linha e a legenda (incidente "tormento")
- O take de linha cobre do início da linha até o **fim real** + `TAKE_LINHA_SOBRA` (tempo do fade).
- **Fim real** (`motion_lab.fim_da_linha`): máximo entre fim da linha, fim da última palavra e
  início da última palavra + 0,09 s por letra (mín. 4). O ASR costuma encurtar a última palavra
  sustentada; sem isso ela sumia. Nunca invade a linha seguinte.
- A frase fica até `FADE_LINHA_DEPOIS` após o fim real e some em `FADE_LINHA_DUR`; a última palavra fica acesa até o fim.
- Legenda ASS: só a **cópia queimada** no render perde os eventos cobertos em **≥ 90%** pelo take
  (`render_clipe.ass_sem_intervalos`). Evento só parcialmente coberto fica (melhor duplicar um instante do que perder palavra). `legenda_ass` original nunca muda.

### 5b. A frase do take não pode trocar no meio (incidente Asta 05/10/2026)

A janela do take é montada por `motion_lab.linhas_no_trecho(sync, de, dur, so_linha)`.
**O `so_linha` é obrigatório quando há take** — é o `design.json -> line_text`, a frase que
aquele take escreve. Sem ele a janela traz as linhas vizinhas que só *encostam* nela, e
`linha_ativa` (devolve a última que casa, segurando 0,65 s após o fim) troca o texto no meio:

- **cauda**: a linha seguinte começa antes do take acabar e assume antes da hora
  (`03_touro` 51,10–55,20 virou "FAÇA" aos 54,8 s);
- **cabeça**: a linha anterior ainda está segurada quando o take começa.

Com `so_linha` as pontas da linha também cobrem a janela inteira, senão sobra um vão em
branco na cabeça. O **lab** (`motion-lab`) não passa `so_linha` e continua vendo a janela toda.

Para auditar um take sem renderizar: varra `linha_ativa(linhas_no_trecho(sync, ini, dur,
line_text), t)` em passos de 0,1 s — a frase tem de ser a do `line_text` do primeiro ao
último instante; só no fim entra o fade, que é o esperado.

## 6. Onde ajustar (sem tocar em código)
| Quero… | Onde |
|---|---|
| mais/menos takes | `config/estudio.json -> graphics_auto.motion_segundos_por_take`, `motion_max_scenes`, `motion_min_gap`, `motion_max_por_30s` |
| tirar um estilo | remover de `graphics_auto.motion_estilos` |
| desligar motion num projeto | `projeto.json -> graphics_auto.motion_real = false` |
| cor de um conceito | `assets/design/motion_lab.json -> cores` |
| kanji de um conceito | `assets/design/motion_lab.json -> kanji` |
| cena mais clara/escura sob o texto | `motion_lab.json -> plate.escurecer` / `saturacao` |
| recorte melhor para anime | `motion_lab.json -> recorte.modelo = "isnet-anime"` (baixa ~170 MB na 1ª vez) |
| ajuste só de uma música | mesma chave em `projeto.json -> motion_lab` ou `graphics_auto` |

## 7. Laboratório
`estudio.py motion-lab <slug> [--de S] [--dur D] [--estilos a,b]` → `projetos/<slug>/lab/motion/`:
MP4 com áudio, folha de contato PNG (4 quadros) e `lab_<de>s.json` com trechos, cor e cobertura do recorte.
Não toca timeline, legenda nem master. Sem `--de`, usa o 1º refrão. Custo: ~45 s por estilo de 4 s
(recorte na CPU); o recorte é calculado uma vez por janela e reaproveitado entre estilos.

## 8. Criar estilo novo (processo obrigatório)
1. Função `estilo_<nome>(c, t, i, off) -> (atras, frente)` em `motion_lab.py`; use `c.janela_palavra(t)`
   (palavra) ou `linha_ativa(c.linhas, t)` (linha). Cor sempre `c.acento` (já vem da letra). Câmera via
   `c.efeito_plate`; card via `c.plate_custom` (+ `c.mascara_custom`).
2. Registrar em `ESTILOS` e na biblioteca com `"status": "em_teste"`, `tipo`, `camada`, `gatilhos`,
   `descricao`, `quando_usar`, `evitar` (e `exige` se precisar do protagonista). `tipo: linha` já entra em
   `ESTILOS_DE_LINHA` sozinho.
3. Prévia: `estudio.py motion-lab <slug> --estilos <nome>` → usuário assiste e aprova.
4. Aprovado: `status: ativo` + `aprovado_em`, incluir em `graphics_auto.motion_estilos` (código **e**
   `config/estudio.json`), `estudio.py cerebro`, registrar na decisão 003.
5. Reprovado: `status: desativado` + `motivo` (ou corrigir e manter `em_teste`).
6. Testes já cobrem: todo estilo desenha algo sem footage; biblioteca ↔ código; campos obrigatórios; estilo não
   ativo nunca é escolhido; `exige protagonista` respeitado.

## 8b. Perfil de densidade por música
Padrão do canal: ~1 take/12 s, até 12 (`config/estudio.json`). Música que pede edição "fora da curva": override
em `projeto.json -> graphics_auto` (Gojo, 30/09/2026: `motion_segundos_por_take` 9, `motion_max_scenes` 16,
`motion_min_gap` 5, `motion_max_por_30s` 4 → 12 takes; o limite real foi o de candidatos fora das faixas protegidas).

## 9. Diagnóstico
| Sintoma | Onde olhar | Causa provável |
|---|---|---|
| palavra/linha some antes da hora | `letra_sincronizada.json` (tempo da última palavra); `qa/vx_graphics_auto/plano.json` (janela do take) | ASR encurtou a última palavra; conferir `fim_da_linha` |
| frase aparece duas vezes | plano: `oculta_legenda` do take | evento ASS cobre < 90% (fica de propósito) ou estilo de palavra sobre linha com legenda |
| poucos takes | rodar `graphic_auto_pipeline.planejar(slug)` e ver `candidate_count` | faixas protegidas, `min_score`, densidade (`motion_max_por_30s`) |
| texto não fica atrás do personagem | `lab_<de>s.json -> recorte` (média ~0 %) | recorte vazio (cena sem personagem ou modelo fraco) → testar `isnet-anime` |
| cor "errada" | `motion_lab.json -> cores` | conceito não mapeado → acrescentar chave |
| take não re-renderiza após mudar parâmetro | `clips_raw/vx_graphics_auto/*.design.json` | cache compara spec + hash do `motion_lab.json`; mudar o JSON força re-render |
| QA de imagem reprova (quase-morto) após motion | `qa/esteira/<run_id>/imagem.json` | plate escuro demais sobre cena já escura → subir `plate.escurecer` |
| tela verde aparecendo no vídeo | `qa/fonte_limpa.json -> chroma_linha`; `qa/vx_chroma/state.json` | `fonte-limpa` não rodou depois do download, ou o verde fugiu da faixa HSV de `chroma_no_quadro` |

## 10. Tela verde → cena composta (`chroma-auto`, decisão 003 adendo 5)
- **Quem detecta:** `fonte_limpa.chroma_no_quadro` (verde saturado e uniforme ≥ `chroma_min` = 25 % do quadro),
  gravado por instante em `qa/fonte_limpa.json -> chroma_linha`.
- **Quem troca:** `ferramentas/chroma_auto.py` (etapa `chroma-auto`, logo depois de `cenas-auto`). Segmento de
  footage real com ≥ `chroma_fracao_cena` (50 %) de quadros verdes vira take `vx_chroma` em `clips_raw/vx_chroma/`.
- **Camadas do take:** fundo `artes_ia/fundo_*.png` do projeto (pan lento, tinta da cor; sem arte, degradê da cor)
  → aura de 2 camadas (blur 6 e 22 px) na borda do recorte → personagem com despill → push-in 4 % → grão/vinheta.
- **Cor:** a da letra (`cor_da_letra`), senão `cor.destaque_claro` do projeto.
- **Pulsação:** `forca_aura` = respiração 0,8 Hz + soco nos picos de 808 (`audio_reactive_fx`).
- **Ajuste:** `config/estudio.json -> chroma_auto` (`aura_forca`, `fundo_luz`, `chroma_fracao_cena`, `enabled`).
- Manual: `estudio.py chroma-auto <slug>`. O `fonte-limpa` não aplica delogo em trecho de tela verde
  (o contorno parado do personagem sobre fundo liso parece logo, e o fundo é trocado de qualquer jeito).
