# Incidente: entrega incompleta (30/09/2026)

**Relato do usuário:** "não esqueça da thumb e também do vídeo completo, os textos do título e descrição — tá
esquecendo muito isso, já deixe isso no cérebro pra nunca esquecer."

## Causa real
- O agente entregava só o que foi pedido na hora (o vídeo, depois os Shorts) e esquecia o resto do lançamento.
- O candidato aprovado nunca era promovido: `saidas/` não tinha master, então `lancamento` nem podia montar os textos.
- As peças existiam em comandos separados (`artes-ia`, `shorts`, `lancamento`), sem nada conferindo o conjunto.

## Correção permanente
- `ferramentas/entrega.py` + comandos `estudio.py promover` e `estudio.py entrega`: gera o que falta e confere os
  10 itens; só diz **PACOTE COMPLETO** se nada faltar (testes em `tests/test_entrega.py`).
- Regra sagrada 9 no `AGENTS.md`; procedimento em `cerebro/entrega.md`; passos 9–10 em `cerebro/producao.md`.

## Lição
Entrega é sempre o pacote inteiro. Antes de dizer "pronto", rodar `estudio.py entrega` e responder com todos os
caminhos e textos.
