# 002 — Porteiros de QA sem override por projeto

**Data:** 2026-09-30 · **Status:** aceita

**Contexto:** na Fase 3 os parâmetros saíram do código para `config/`. Parâmetros editoriais
(quantos cards, espaçamento) podem ser ajustados por música em `projeto.json`.

**Decisão:** os limiares que reprovam a esteira (LUFS, true peak, tela morta, cobertura de letra)
ficam só em `config/porteiros.json` e **não** leem `projeto.json` (`vx.config.porteiro` nem recebe
o manifesto). Ajustar um projeto para "passar no QA" é exatamente o erro que os porteiros existem
para impedir.

**Consequência:** se um projeto reprova, conserta-se o material ou a ferramenta; se a régua estiver
errada para o canal todo, muda-se `config/porteiros.json` com uma nova decisão registrada aqui.
