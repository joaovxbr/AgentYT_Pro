# 003 — Takes gráficos usam motion typography sobre a cena real

**Data:** 2026-09-30 · **Status:** aprovada pelo usuário (os 5 estilos)

## Contexto
O overlay de tipografia sobre a cena do anime tinha sido rejeitado ("ficou colado/artificial"),
e o `graficos-auto` passou a usar fundo procedural. O usuário pediu texto escrito sobre o
anime em vários estilos, como motion/animação.

## Decisão
- `ferramentas/motion_lab.py` resolve o "colado": texto atrás do personagem (recorte rembg),
  cena tratada como plate (escurece/dessatura + push-in), texto segue a câmera (phase
  correlation), cor do brilho vem da cena, grão e vinheta por cima.
- Laboratório (`estudio.py motion-lab`) gerou 5 prévias do Gojo; **todas aprovadas**.
- `graficos-auto` com `motion_real=true` (padrão) renderiza cada take sobre a própria cena real
  que ele cobre. Escolha do estilo: nome do personagem → `atras_personagem`/`kanji_fundo`;
  808 forte → `glitch_slice`; linha curta (≤ `motion_max_linha`) → `palavra_por_palavra`/
  `maquina_escrever`; nunca repete os 2 últimos.
- Estilos de linha cobrem a linha inteira e **ocultam a legenda ASS nesse trecho**
  (`graphics_auto.oculta_legenda`), só na cópia queimada pelo render; `legenda_ass` não muda.
- Candidatos: além dos presets procedurais, valem termos do manifesto e conceitos com kanji
  (`assets/design/motion_lab.json`). Limites de frequência inalterados (≈1 take a cada 30 s).
- Sem footage real no intervalo → volta ao take procedural antigo.

## Adendo (mesmo dia) — lote 2, cor pela letra e ritmo
- Lote 2 aprovado e na esteira: `impacto_zoom`, `eco_repeticao`, `fragmentos`, `contorno_energia`,
  `letterbox_cinema`, `faiscas` (11 estilos no total). Não repete os 3 últimos.
- **Cor pela letra** (pedido do usuário): o brilho usa a cor do conceito cantado
  (`motion_lab.json -> cores`: azul, vermelho, purple, infinito, sangue, fogo, raio…).
  Prioridade: palavra do take > linha cantada > linha do take > cor da cena. Troca entre
  linhas com transição curta. Conceito novo = acrescentar no JSON, sem código.
- Ritmo: `motion_segundos_por_take = 20` (antes ~35 s). Gojo: 5 takes.

## Adendo 2 — edição "cheia" e variedade (após incidente "tormento")
- Pedido do usuário: vídeo completo e profissional, cheio de motion, e os novos efeitos visíveis.
- `motion_segundos_por_take = 12`, até 12 takes, densidade em ±15 s, palavra-tema repete até 3×.
- Escolha de estilo prioriza o menos usado → os 11 estilos aparecem. Gojo: 11 takes.
- Take de linha até o fim real da última palavra; legenda só oculta se ≥ 90% coberta.
  Ver `cerebro/incidentes/2026-09-30-tormento-sumiu.md`. Manual completo: `cerebro/motion.md`.

## Adendo 3 — cards com fundo próprio (lote 3, vindos da referência MUGEN RAPS)
- Aprovados: `card_cena_escura`, `card_cenario`, `card_manga` (preferido no último quinto = fechamento), `card_letra` (linha).
- `card_retrato` reprovado na 1ª versão (close gigante desfocado tapando o título); corrigido com critério de quadro
  e fallback, de volta ao lab até nova aprovação. Detalhe em `cerebro/motion.md` seção 2b.
- Esteira: 15 estilos em `motion_estilos`.

## Adendo 4 — biblioteca, kanji fora, contorno só com protagonista
- Pedido do usuário: "tudo registrado como biblioteca, usada automaticamente conforme a letra e o vídeo".
  → `assets/design/biblioteca_motion.json` é a fonte única de status e regras; `escolher_estilo` lê os gatilhos
  de lá; catálogo gerado em `cerebro/biblioteca_motion.md`.
- `kanji_fundo` **desativado temporariamente** (pedido do usuário). Código e lab mantidos.
- `card_retrato` ativado (usuário: "o restante pode deixar na biblioteca").
- `contorno_energia` (e `card_retrato`) **só com o personagem principal em cena**: verificação visual por
  aparência (OpenCLIP + `imagem_ia.tags_personagem`), porque o CLIP por nome errava 70 de 79 planos no Gojo.
- Gojo com perfil intenso (override no projeto): 12 takes, 12 estilos diferentes.

## Adendo 5 — tela verde vira cena composta (`chroma-auto`, Douma)
- Pedido do usuário: "quando for assim, crie uma cena, coloque o contorno de energia e uma pulsação".
- Packs de twixtor/mangá trazem o personagem sobre chroma key. A tela verde **nunca** vai crua para o vídeo.
- `fonte-limpa` grava a linha do tempo de chroma por clipe; `chroma-auto` (logo depois de `cenas-auto`) troca
  cada segmento com ≥ 50 % de quadros verdes por um take `vx_chroma`: fundo IA do projeto (pan lento e tinta
  da cor) + personagem recortado (despill) + aura de 2 camadas na cor da letra, respirando e socando no 808.
- É composição automática (não é estilo da biblioteca); aura aqui é permitida porque o recorte **é** o personagem
  do clipe. Detalhe em `cerebro/motion.md` §10.

## Consequências
- Gojo: 4 takes (SATORU, PURPLE, DOMÍNIO, LIMITLESS), antes 1.
- Render ~25 s por take (recorte na CPU). Cache por `.design.json` evita re-render.
- Para desligar num projeto: `projeto.json -> graphics_auto.motion_real = false`.
