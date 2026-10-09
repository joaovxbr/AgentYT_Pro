# 004 — Exceção de porteiro por clipe, registrada e restrita

**Data:** 2026-10-08 · **Status:** aceita pelo dono (resposta explícita à opção 2)
**Relaciona-se a:** 002 (porteiros sem override por projeto) — esta decisão **não revoga** a 002.

**Contexto:** o clipe `zeref_mavis_confronta_zeref.mp4` foi reprovado no `fonte-limpa` por
duas caixas de "marca d'água" nas bordas (t 66–72 s e 90–96 s). Medição: o `delogo` não alterou
nenhum pixel visível (diferença original × limpo ≤ 20 em todos os pixels; diferença média 1,31 e
1,58), e as caixas são estáticas em todo o clipe (mediana de diferença entre quadros 0,01–0,03).
A conclusão é de falso positivo, mas o porteiro não tem critério confiável para distinguir
"marca parada" de "área parada de cena". Não foi possível comprovar que é falso positivo.

**Decisão:** o dono autorizou liberar **somente este clipe**, com registro explícito. O porteiro e
o limiar continuam iguais (`config/porteiros.json` não mudou). A exceção é lida de
`projetos/<slug>/qa/excecao_fonte_limpa.json` por `fonte_limpa._aplicar_excecao`:
- só casa com o nome exato do clipe;
- só remove caixas com mesmo tempo (±0,6 s) e mesma posição (±0,02);
- toda outra caixa continua reprovando (testes em `tests/test_fonte_limpa.py::ExcecaoRegistradaTest`).

**Consequência e risco:** a 002 fica tensionada. Se virar hábito, o porteiro perde valor. Por isso
a exceção é por clipe, fica no `qa/` visível, e o `fonte_limpa.json` registra
`excecoes_aplicadas` com o motivo. Uma exceção por projeto precisa de decisão nova.
