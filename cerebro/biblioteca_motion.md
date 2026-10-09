# Biblioteca de motion (gerado de `assets/design/biblioteca_motion.json`)

> Não edite à mão: mude o JSON e rode `estudio.py cerebro`. Um teste falha se este arquivo ficar defasado.
> Como funciona o sistema inteiro: `cerebro/motion.md`.

**15 ativos** · 0 em teste · 1 desativados

## Como a esteira escolhe (automático, pela letra e pelo vídeo)
1. O `graficos-auto` escolhe os momentos (palavra forte, nome, batida) e, para cada um, a **categoria**:
   - `nome`: letra cita o personagem
   - `batida`: 808 forte (beat ≥ 0,6)
   - `atmosfera`: demais momentos
   - `linha`: linha curta (frase inteira na tela)
   - `fechamento`: último quinto da música
2. Dentro da categoria, os estilos entram na ordem de prioridade (tabela abaixo); linha curta insere os estilos de `linha` logo depois do 1º; no fechamento, os de `fechamento` vêm antes de tudo.
3. Só entram estilos `ativo`. Quem `exige protagonista` só entra com o personagem principal verificado em cena (visual ≥ 0.5; ver regra abaixo).
4. Variedade: fora os 3 últimos, vence o menos usado no vídeo.

## Prioridade por categoria (1 = primeiro)

| categoria | estilos (ativos, em ordem) |
|---|---|
| `nome` | `atras_personagem` → `card_retrato` → `contorno_energia` → `card_cena_escura` → `letterbox_cinema` → `eco_repeticao` |
| `batida` | `impacto_zoom` → `glitch_slice` → `contorno_energia` → `fragmentos` → `faiscas` |
| `atmosfera` | `card_cenario` → `contorno_energia` → `eco_repeticao` → `card_cena_escura` → `card_retrato` → `faiscas` → `letterbox_cinema` → `atras_personagem` → `fragmentos` → `glitch_slice` |
| `linha` | `palavra_por_palavra` → `card_letra` → `maquina_escrever` |
| `fechamento` | `card_manga` |

## Regra do protagonista

Com projeto.json -> imagem_ia.tags_personagem: verificacao VISUAL (OpenCLIP pela aparencia, ex. 'white hair, blue eyes, blindfold'), protagonista se score >= protagonista_visual_min. Sem tags: usa scene_semantic_scores do cenas-auto (entity do protagonista >= protagonista_min e o maior entre os entities). O CLIP por NOME confunde personagens (Gojo virava Geto/Sukuna em 70 de 79 planos) - por isso a aparencia vem primeiro.

## Catálogo

### Ativo (15)

#### `atras_personagem` — palavra · camada tras · lote 1

Palavra gigante escrita da esquerda para a direita ATRAS do personagem, com cabeca de luz.

- **Quando usar:** Nome do personagem ou palavra de identidade; plano com personagem visivel e recortavel.
- **Evitar:** Plano sem personagem (o efeito de profundidade some).
- **Gatilhos:** nome 1, atmosfera 7

#### `palavra_por_palavra` — linha · camada frente · lote 1

Cada palavra entra no tempo cantado (pop + blur); a atual brilha na cor da letra; a ultima fica acesa.

- **Quando usar:** Linha curta e marcante que merece ser lida inteira.
- **Evitar:** Linha longa (> motion_max_take_linha): vira estilo de palavra.
- **Gatilhos:** linha 1

#### `glitch_slice` — palavra · camada frente · lote 1

Palavra entra fatiada com RGB split; treme e refatia nos picos de 808.

- **Quando usar:** Batida forte, palavras de ruptura (destruicao, dominio, poder).
- **Evitar:** Trechos calmos.
- **Gatilhos:** batida 2, atmosfera 9

#### `maquina_escrever` — linha · camada frente · lote 1

A linha e digitada no ritmo das palavras, com cursor piscando.

- **Quando usar:** Linhas narrativas, confissao, fala direta.
- **Evitar:** Refrao de alta energia.
- **Gatilhos:** linha 3

#### `impacto_zoom` — palavra · camada frente · lote 2

Palavra cai de 3x para 1x no tempo cantado; soco de camera (zoom + tremor na cena e no recorte) e flash.

- **Quando usar:** Maior batida do trecho; palavra de golpe.
- **Evitar:** Dois seguidos (anti-repeticao ja impede).
- **Gatilhos:** batida 1

#### `eco_repeticao` — palavra · camada tras · lote 2

Palavra atras do personagem com ecos em contorno que se expandem em ondas e pulsam no 808.

- **Quando usar:** Palavra-tema repetida (refrao), sensacao de ressonancia.
- **Evitar:** Palavras muito longas (ecos ficam poluidos).
- **Gatilhos:** atmosfera 3, nome 7

#### `fragmentos` — palavra · camada frente · lote 2

Letras voam de posicoes aleatorias girando, com motion blur, e montam a palavra.

- **Quando usar:** Tecnicas, transformacoes, algo se formando.
- **Evitar:** Palavras de 1-2 letras.
- **Gatilhos:** batida 3, atmosfera 8

#### `contorno_energia` — palavra · camada tras · lote 2

Aura de energia na cor da letra no CONTORNO do personagem (borda do recorte), pulsando no 808, com a palavra atras dele.

- **Quando usar:** SO com o personagem principal do projeto em cena (regra do usuario): momentos de poder, despertar, nome dele.
- **Evitar:** Inimigo/coadjuvante em cena, plano sem personagem, recorte vazio.
- **Gatilhos:** atmosfera 2, nome 3, batida 3
- **Exige:** protagonista

#### `letterbox_cinema` — palavra · camada tras+frente · lote 2

Barras de cinema fecham; titulo espacado atras do personagem; credito (personagem - anime) na barra.

- **Quando usar:** Momento solene, apresentacao, virada de ato.
- **Evitar:** Batidas rapidas (e lento de proposito).
- **Gatilhos:** nome 5, atmosfera 6

#### `faiscas` — palavra · camada frente · lote 2

Brasas da cor da letra sobem da palavra; rajada extra nos picos de 808.

- **Quando usar:** Fogo, energia, explosao, refrao.
- **Evitar:** Trechos frios/tristes (use card_cena_escura).
- **Gatilhos:** batida 4, atmosfera 5

#### `card_cena_escura` — card · camada fundo · lote 3

Cena congelada bem escura e desfocada com push-in e brilho radial; palavra gigante + credito entre filetes. (Tipo mais comum na referencia MUGEN RAPS: 13 de 20 cards.)

- **Quando usar:** Pausa dramatica, frase de efeito, pos-refrao.
- **Evitar:** Dois cards seguidos.
- **Gatilhos:** nome 4, atmosfera 4

#### `card_cenario` — card · camada fundo · lote 3

Cenario tematico do projeto (artes_ia/fundo_*.png, sem personagem) com pan lento e tinta da cor; palavra + brasas. Sem cenario IA: cena real bem desfocada.

- **Quando usar:** Conceito do universo (dominio, infinito, tribunal); melhor com fundo IA gerado.
- **Evitar:** Projeto sem artes_ia/fundo (cai no fallback desfocado).
- **Gatilhos:** atmosfera 2

#### `card_retrato` — card · camada fundo · lote 3

Personagem nitido recortado sobre fundo escuro com brilho; palavra ENORME atras (ou na frente se ele taparia o titulo); credito embaixo.

- **Quando usar:** Apresentacao do personagem principal (nome dele na letra).
- **Evitar:** Close gigante/desfocado (avaliar_retrato rejeita; sem quadro bom vira card_cena_escura).
- **Gatilhos:** nome 2, atmosfera 4
- **Exige:** protagonista
- **Notas:** 1a versao reprovada (close de ombro tapando o titulo); corrigida com avaliar_retrato/escolher_quadro_retrato.

#### `card_manga` — card · camada fundo · lote 3

Pagina de manga com 3 momentos da propria janela (P&B, reticula), paineis entrando em sequencia; palavra em balao.

- **Quando usar:** Fechamento do video (ultimo quinto), como a referencia.
- **Evitar:** Inicio/meio (fica deslocado).
- **Gatilhos:** fechamento 1

#### `card_letra` — linha · camada fundo · lote 3

Tela quase preta com degrade da cor; a linha palavra por palavra, grande e centralizada.

- **Quando usar:** Linha-chave que precisa de silencio visual.
- **Evitar:** Refrao agitado.
- **Gatilhos:** linha 2

### Desativado (1)

#### `kanji_fundo` — palavra · camada tras+frente · lote 1

Kanji enorme translucido (motion_lab.json -> kanji) + palavra em portugues fechando o espacamento.

- **Quando usar:** Conceitos com kanji mapeado (infinito, dominio, poder).
- **Evitar:** Conceito sem kanji (usa kanji_padrao, generico).
- **Gatilhos:** atmosfera 1, nome 6
- **Motivo do status:** Pedido do usuario: fora temporariamente. Codigo e prevista no lab mantidos; reativar = status ativo.

