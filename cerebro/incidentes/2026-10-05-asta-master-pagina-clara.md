# Incidente: master reprovado com 3,0s de "página clara sem cor" (Asta, 05/10/2026)

**Relato:** a esteira passou de tudo (`fonte-limpa`, `auditar-letra`, `auditar-ritmo`,
`cenas-auto`, `chroma-auto`, `cenas-ia`, `titulos`, `manga-auto`, `graficos-auto`,
`planejar`, `sincronia` APROVADO, `render-clipe` com NVENC) e morreu no `qa-master`:

```
ERRO: QA da saida nova reprovado: ['3.0s de pagina clara sem cor / line-art (> 0.5 s)']
```

## Causa (medida, quadro a quadro)

Rodei o próprio `imagem.mascara_pagina` sobre o `asta_corpo.mp4` e localizei os 6 blocos
(0,33–0,83 s cada), depois mapeei cada um para o clipe e ao `src` exato do plano:

| corpo | clipe / src | natureza |
|---|---|---|
| 37,67 s | `asta_oficial_minha_magia` 41,95 | **fade para branco** do clipe oficial (fonte: 5/8 quadros páginas) |
| 39,83 s | `blackclover_flow_clips` 44,77 | **flash branco** do pack (3/8) |
| 47,67 s | `asta_oficial_minha_magia` 43,30 | mesmo fade (5/6) |
| 79,50 s | `asta_oficial_ataque_final` 182,36 | **branco final** do clipe (7/10) |
| 19,83 s e 123,67 s | `asta_twixtor_pack` 181,50 / 181,67 | **close de olho**: 0,03 de branco na **fonte**, 0,76 no **master** |

Metade era material podre que o catálogo deixava elegível; a outra metade era um plano
legítimo que **o grade do render** empurrou por cima do limiar (pele clara desaturada).

## Por que o catálogo não pegou

`ferramentas/scene_intelligence.py` já marcava `dead_scene` — mas só o **lado escuro** do
gate: `brightness < 0.11 and edge_density < 0.05` (tela preta, tail de clipe). O gate de
imagem tem dois lados (`morto` escuro e `pagina` claro) e só um deles tinha espelho no
catálogo. As 5 cenas culpadas estavam todas `dead=False, poluida=False` quando verifiquei.

## Correção permanente (ferramenta, não o material)

1. `ferramentas/imagem.py`: a fórmula do gate saiu de dentro de `analisar` para
   `mascara_pagina(frames)` — **fonte única** para o gate e para o catálogo. `analisar`
   passou a chamá-la; limiar nenhum mexido ("never weaken the gate to approve a render").
2. `ferramentas/scene_intelligence.py`: `marcar_cenas_pagina`, chamada junto de
   `marcar_cenas_poluidas` em todo build de catálogo (roda mesmo com cache, barata):
   - `runs_pagina` agrupa a máscara em janelas ≥ 0,33 s (2 amostras a 6 fps);
   - `cenas_alcancadas` devolve as cenas vivas sobrepostas → viram `dead_scene` + `pagina`;
   - `_marcar_cenas_claras_chapadas` é o chão de segurança pro lado que **não aparece na
     fonte**: `brightness > 0.60 and contrast < 0.28` — e `contrast < 0.28` **é** o limiar
     de detalhe do próprio gate (contrast = std/92, gate = std < 26). No catálogo do Asta:
     **4 cenas de 447**, 3 já pegues pelo vídeo, sobrava exatamente o close de olho.
3. `catalog["cenas_pagina"]` conta o **total**, não o da execução — as marcas vivem no
   catálogo em cache; na primeira versão o número caía de 15 para 1 na rodada seguinte.
4. Testes novos em `tests/test_scene_intelligence.py` (7): branco sem detalhe conta,
   flash com traço não conta, cena colorida não conta, janela de 0,17 s é ignorada,
   cena já morta é pulada, o `dead_scene` é aplicado, cena escura não é marcada e cena
   clara-chapada é marcada. **Suíte: 358 testes, OK.**

Resultado da recatalogação: `cenas_pagina: 16`, `dead_scene: 21`, **241 cenas vivas** — as
5 cenas que reprovaram o master agora estão fora do inventário do matcher.

## Lição

O gate de imagem é o contrato, e o catálogo tem de espelhar **os dois** lados dele. Quando
um porteiro reprova, a pergunta certa é "o que o outro lado do pipeline ainda não olha?",
não "como eu afrouxo o limiar".
