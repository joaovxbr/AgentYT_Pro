# 012 — Modularização de comandos do estúdio em handlers dedicados

- **Data:** 2026-10-11
- **Status:** aprovada e integrada
- **Módulo:** `ferramentas/estudio.py`
- **Regressão:** `tests/test_estudio_cli.py`, `tests/test_orquestrador.py`, `tests/test_runner.py` (suíte completa: 618 testes, OK)
- **Relaciona:** decisão 001 (reconstrução incremental), decisão 007 (etapas in-process), `cerebro/ROADMAP.md` ("Sobras: lógica que ainda está no main()").

## Contexto

A porta de criação do canal (`ferramentas/estudio.py`) acumulava 81 subcomandos. Embora 35 comandos delegassem para funções dedicadas `cmd_*`, nada menos que 40 comandos executavam blocos inteiros de lógica procedural e manipulação de arquivos diretamente dentro do laço `main()` (linhas 1872 a 2174).

Essa concentração inline gerava problemas estruturais:
1. **Dívida explícita no roadmap:** citada desde a fase 2 como pendência de engenharia.
2. **Fragilidade no runner in-process:** a esteira (`vx/runner.py`) executa etapas chamando `estudio.main(argv)` in-process. Manter lógicas extensas inline aumentava o risco de exceções não capturadas ou vazamento de estado.
3. **Dificuldade de teste isolado:** funções inline em `main()` só podiam ser exercitadas invocando o parser de CLI completo com argumentos artificiais.

## Decisão

1. **Extração de 40 handlers dedicados:** Toda a lógica que residia inline no `main()` foi extraída para funções `cmd_*` com tipagem explícita e tratamento de retorno padronizado (0 para sucesso, != 0 para erro):
   - Cenas e inteligência visual: `cmd_catalogar_cenas`, `cmd_cenas_auto`, `cmd_chroma_auto`, `cmd_movimento`, `cmd_curadoria`.
   - Áudio e ritmo: `cmd_subgrave`, `cmd_stems`, `cmd_auditar_ritmo_timeline`.
   - Efeitos e motion: `cmd_impacto`, `cmd_manga_auto`, `cmd_graficos_auto`, `cmd_folha_quadro`, `cmd_impacto_pro`, `cmd_cinemascope`, `cmd_colorgrade`, `cmd_speedlines`, `cmd_motionblur`, `cmd_card_saber`, `cmd_snap_impact`, `cmd_ghosting`, `cmd_paineis`, `cmd_color_splash`, `cmd_pixel_sort`.
   - IA e miniaturas: `cmd_capa_ia`, `cmd_gerar_imagem`, `cmd_artes_ia`, `cmd_comfy_parar`, `cmd_comfy_status`, `cmd_cenas_ia`.
   - Redes sociais e entrega: `cmd_social`, `cmd_tumbas_ab`, `cmd_promover`, `cmd_entrega`, `cmd_lancamento`, `cmd_shorts`, `cmd_titulos`, `cmd_loop_infinito`, `cmd_smartcrop`, `cmd_hook_retencao`.
   - Tipografia e legendas: `cmd_legendas_mugen`, `cmd_legenda_palavra`, `cmd_legenda_neon`.

2. **Dispatcher enxuto no `main()`:** O despachador em `main()` agora apenas valida os argumentos e faz a delegação direta de uma linha:
   ```python
   if a.cmd == "cenas-auto":
       return cmd_cenas_auto(a.slug, a.planejar, a.force_catalog)
   ```

3. **Preservação rigorosa de contratos:**
   - Nenhum subcomando CLI foi alterado ou renomeado.
   - Os testes estáticos por AST/regex (`test_todo_dispatch_tem_parser`, `test_every_stage_has_an_estudio_subcommand`, `test_cited_commands_exist`) continuam 100% satisfeitos.
   - `estudio.main(argv)` preserva exatamente a assinatura e semântica requeridas pelo `vx/runner.py`.

## Consequências

- **Roadmap limpo:** a dívida técnica histórica listada em "Sobras" de `cerebro/ROADMAP.md` foi formalmente liquidada.
- **Testabilidade direta:** qualquer funcionalidade do estúdio pode agora ser importada e testada unitariamente via sua função `cmd_*` sem necessidade de sintetizar strings de argv.
- **Suíte 100% verde:** todos os 618 testes continuam passando sem regressões.
