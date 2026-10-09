# 2026-10-09 — suíte vermelha em clone limpo (fixtures de projeto)

**Sintoma:** `python -m unittest discover -s tests` dava `FAILED (failures=1, errors=3)`
em qualquer máquina sem `projetos/sasuke/` — e o repositório nem era versionado.

**Medição:** exatamente 4 testes, todos lendo `projetos/<slug>/...` do disco:
- `test_motion_manga_ato2.Ato2ConfigTest` → `projetos/sasuke/motion_manga_ato2_rinnegan.json`
- `test_motion_manga_ato3_dispatch.Ato3ConfigAndEngineTest` → `projetos/sasuke/transcricao_canonica.json`
- `test_motion_manga_ato3_full.Ato3FullSpecificationTest` → idem
- `test_sasuke_canonical_v2.CanonicalTranscriptContract` → `projetos/sasuke/projeto.json`

**Causa:** os testes usavam o projeto de PRODUÇÃO como fixture. `projetos/` é material de
produção (GBs, pessoal, fora do Git por decisão), então a suíte não era portável. Isso
quebrava a regra sagrada 6 ("mudou código → suíte verde"): com a suíte já vermelha, verde
deixava de ser sinal.

**Correção:** `tests/_fixtures.py` monta projetos temporários e herméticos
(`projeto_sasuke_canonico()`), com o conteúdo mínimo que cada contrato verifica. Os 4
testes passam a usá-la e não leem mais `projetos/` real.

**Lição:** teste que depende de dado de produção não é teste, é monitoramento. Fixture
tem de ser hermética e implícita no próprio teste.

**Resultado:** suíte 441 testes, OK (428 originais + 13 de `test_metrics.py`).
