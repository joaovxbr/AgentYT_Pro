# 001 — Reconstrução incremental, não do zero

**Data:** 2026-09-30 · **Status:** aceita

**Contexto:** `estudio.py` monolítico (~1.700 linhas, 70 comandos), esteira que chama
o próprio estudio por subprocess, 5 estágios editando `timeline.json` no lugar,
limiares no código e documentação divergente. Ao mesmo tempo a esteira funciona e
tem 200+ testes.

**Decisão:** trocar o esqueleto em fases (ver `ROADMAP.md`), mantendo os módulos
existentes e o comportamento testado. Cada fase entrega suíte verde e o Gojo
passando na esteira.

**Alternativa rejeitada:** reescrever do zero — perderia comportamento testado e
reintroduziria bugs já corrigidos (ver `incidentes/2026-09-gojo-infinito.md`).
