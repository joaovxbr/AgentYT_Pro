# Configuração

Três camadas, da mais fraca para a mais forte:

1. **Código** — o padrão de cada módulo (`DEFAULTS`, `DEFAULT_CONFIG`, `EDICAO_PADRAO`). Define quais chaves existem.
2. **`config/estudio.json`** — padrões editoriais do canal inteiro.
3. **`projeto.json`** — ajuste de uma música, na mesma chave (`graphics_auto`, `cenas_ia`, `manga_auto`, `titulos`, `edicao`).

Chave que não existe no código é ignorada, e `tests/test_configuracao.py` reprova chave desconhecida em `config/estudio.json` (pega erro de digitação).

## Motion sobre a cena real — `graphics_auto.motion_*` e `assets/design/motion_lab.json`
| Chave (`graphics_auto`) | Padrão | Efeito |
|---|---|---|
| `motion_real` | `true` | takes sobre a cena real; `false` volta ao fundo procedural |
| `motion_estilos` | todos os implementados | lista **permitida**; o status (ativo/em teste/desativado) vem de `assets/design/biblioteca_motion.json` |
| `motion_segundos_por_take` | 12 | ritmo alvo (~1 take a cada N s) |
| `motion_max_scenes` | 12 | teto de takes no vídeo |
| `motion_min_gap` | 6 | distância mínima entre centros de takes (s) |
| `motion_max_por_30s` | 3 | takes numa janela de ±15 s |
| `motion_max_linha` | 3,6 | linha até esse tamanho pode usar estilo de linha |
| `motion_max_take_linha` | 5,5 | take de linha maior que isso vira estilo de palavra |
| `motion_repetir_palavra` / `motion_distancia_mesma_palavra` | 3 / 25 | palavra-tema do refrão pode repetir, afastada |

`assets/design/motion_lab.json`: plate, recorte, tracking, grão, vinheta, fontes, `kanji`, **`cores`** (cor pela letra),
`estilos` (padrão do lab). Override por música em `projeto.json -> motion_lab`. Detalhes: `cerebro/motion.md`.

## Porteiros (QA) — `config/porteiros.json`
Limiares de `audio`, `imagem_master`, `auditar_letra` e `fonte` (marca d'água: `persistencia_min`, `zoom_max`;
legenda queimada: `legenda_score_min`, `legenda_fracao_cena`, `max_poluido_clipe`). **Não aceitam override por projeto**: um projeto não pode afrouxar QA. Mudar aqui muda a régua do canal inteiro; registre o motivo em `cerebro/decisoes/`. Ver decisão 002.

## Caminhos do projeto — `vx/projeto.py`
- Áudio: `projeto.json -> audio_fonte`; sem ele, `entradas/<slug>_normalizado.wav`.
- Stems: `entradas/stems/<nome-do-áudio>_{vocals,drums,bass,other}.wav`.
Nunca montar esses nomes à mão; use `vx_projeto.audio()` / `vx_projeto.stem()`.

## Vocabulário canônico do anime — `projeto.json -> vocabulario`
```json
"vocabulario": {"termos": ["Mangekyō", "Danzō"], "variantes": {"tomoes": "tomoe"}}
```
Usado por `transcricao-canonica` para corrigir grafia de nomes. Antes era fixo no código (Sasuke) e valia para todo anime.
