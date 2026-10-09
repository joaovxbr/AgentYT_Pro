# A folha acusou defeito onde a motion já estava certa (Asta, 07/10/2026)

**Contexto:** depois de corrigir o vazamento de frase (`so_linha`, incidente
`2026-10-05-asta-motion-troca-frasa-no-meio.md`), a esteira #6 foi aprovada com todos os
porteiros verdes e os 3 takes re-renderizados. A folha por quadro, rodando no **candidato novo**,
continuou acusando `HEAD/CAUDA` em **6 takes (4,10 s somados)** — a mesma assinatura do defeito
que já tinha sido corrigido.

Não era defeito: **era o detector que estava errado**, e por um motivo estrutural.

## Por quê

A folha comparava "a linha vigente da letra" com a frase do take. Dentro da janela do take isso
não funciona:

1. o take **esconde a legenda de canto** (`oculta_legenda` em `graphics_auto`/`design.json`), e
2. `linha_ativa`/`linha_em` segura a linha **anterior** por `FADE_LINHA_DEPOIS` (0,65 s) depois do
   fim dela — a janela do take começa ~0,1 s **antes** da linha que ele escreve.

Resultado: nos primeiros 0,5–0,8 s de cada take o detector via a linha anterior e marcava
"vazamento de CABECA". Confirmado no frame: aos 34,20 s (janela do Yuno) **não há texto nenhum
no centro** — só a legenda de canto da linha anterior. A kinetic text do take nem tinha começado.

## Correção: ler a tela em vez de deduzir

`folha_por_quadro.texto_do_take()` roda o **RapidOCR do próprio projeto** (`fonte_limpa.cfg()`,
2 fps) na janela de cada take, junta as caixas da metade superior (a legenda de canto fica embaixo
e é ignorada) e devolve o que está escrito. `HEAD/CAUDA` passa a ser: "o texto lido na tela não
pertence à frase do take".

`_ini_do_take_no_video()` converte tempo de corpo → tempo de vídeo (soma a intro oficial); sem
isso o OCR leria a intro no lugar do take.

## Casos que o matcher precisou decidir

O OCR lê a frase em montagem (palavra a palavra) e come letras (`PORTASEM`, `SUBUPRO`, `ODE
QUATRO O FOLHAS`). Duas decisões do dono:

- **só metade das palavras de conteúdo bater já passa** — menos alarme falso;
- **leitura parcial é normal se a 1ª palavra de conteúdo da frase já apareceu** em algum quadro
  anterior do take (`_conteudo_ja_saiu`).

E um detalhe que só apareceu depois: comparar por palavra **sem** filtrar palavra curta deixa a
linha vizinha passar por "metade das palavras" — `O meu desceu rasgado, sujo, sem par` acha `o`,
`de` (dentro de "desceu") e `ar` (dentro de "rasgado") na frase `O de quatro folhas...`. Daí
`PALAVRA_MIN = 4` e `_conteudo()`.

## O que a folha custou até aqui

Cinco bugs meus, todos pagos por ela: conversor de cor chamado por nome que não existe no módulo,
regra de cor reinventada em vez de chamada, falso positivo de vazamento de cabeça, falso positivo
de "linha vigente" dentro do take, e matcher por palavra curta. **Diagnóstico que dá alarme falso
vira ferramenta que ninguém liga** — por isso a folha compara com o que está escrito, e não com
o que ela deduz.

Suíte: **406 testes OK** (`tests/test_folha_por_quadro.py`, 29 testes).