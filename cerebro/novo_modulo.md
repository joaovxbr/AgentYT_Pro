# Como criar um módulo ou etapa nova

Receita para o Hermes (ou qualquer agente) acrescentar capacidade ao estúdio sem
quebrar a esteira nem o cérebro. Exemplo real para copiar: `ferramentas/auditor_letra.py`
(porteiro) + `cmd_auditar_letra` em `ferramentas/estudio.py`.

## 1. O módulo (`ferramentas/<modulo>.py`)
```python
"""<O que faz em 1 frase>. Le: <arquivos>. Grava: qa/<modulo>.json."""
from __future__ import annotations

import json
from pathlib import Path

from _vx import config as _vx_config, projeto as _vx_projeto  # ponte para vx/

# Parametro editorial: codigo < config/estudio.json < projeto.json
PADRAO = {"intensidade": 0.5}
# Se for porteiro (reprova): use _vx_config.porteiro(...) -> sem override por projeto (decisao 002)


def executar(d: Path, manifesto: dict, slug: str) -> dict:
    """Funcao pura de verdade: recebe a pasta do projeto, devolve o relatorio."""
    cfg = _vx_config.secao("<modulo>", PADRAO, manifesto)
    audio = _vx_projeto.audio(d, manifesto)          # nunca montar "_normalizado" a mao
    rel = {"aprovado": True, "motivos": [], "cfg": cfg, "audio": str(audio)}
    (d / "qa").mkdir(exist_ok=True)
    (d / "qa" / "<modulo>.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return rel
```
Regras:
- Nada de `if slug == ...` nem caminho de uma música específica (regra 5).
- Dependência pesada (cv2, torch, librosa) só dentro da função, ou via `vx/lazy.py`.
- Render de vídeo só por `ferramentas/render_dispatch.py` (NVENC).
- Não escreve em `saidas/` fora de `saidas/esteira/<run_id>/`.

## 2. O comando (`ferramentas/estudio.py`)
- Função `cmd_<modulo>(slug) -> int` que chama `executar`, imprime o resumo e devolve
  `0` (ok) ou `1` (reprovou). Lógica não vai no `main()`.
- `sub.add_parser("<nome>", help=...)` + o despacho `if a.cmd == "<nome>"`.

## 3. Entrar na esteira (opcional) — `vx/etapas.py`
Adicionar um `Etapa(...)` na tupla certa (`BOOTSTRAP`, `PRODUCAO` ou `MASTER`) com
`le`, `escreve`, `bloqueante` e `notas`. O nome do `Etapa` é o subcomando.
- `bloqueante=True`: exit ≠ 0 reprova a esteira. `False`: vira aviso.
- Se a etapa altera `timeline.json`, ela precisa reaplicar sobre a base a cada execução;
  acrescente o `state.json` dela em `ESTADOS` e o `type` dos segmentos que ela cria em
  `TIPOS_DERIVADOS` (ambos em `vx/composicao.py`), senão a recomposição não a limpa.
- Depois: `.venv\Scripts\python.exe ferramentas\estudio.py cerebro` (regenera `cerebro/etapas.md`).

## 4. Configuração
- Parâmetro novo: default no código **e** a mesma chave em `config/estudio.json`
  (o teste de configuração reprova chave desconhecida ou valor divergente do código).
- Limiar de porteiro: `config/porteiros.json`. Nunca em `projeto.json`.

## 5. Teste e cérebro (obrigatório, regra 6 e 8)
- `tests/test_<modulo>.py` com projeto falso em `tempfile.TemporaryDirectory()`:
  um caso aprova, um caso reprova. Sem GPU, sem rede, sem arquivo real de música.
- Entrada do módulo em `cerebro/modulos.md` (`tests/test_cerebro.py` reprova módulo sem catálogo).
- Decisão de design nova → `cerebro/decisoes/NNN-*.md`. Falha real que motivou → `cerebro/incidentes/`.
- Suíte verde: `.venv\Scripts\python.exe -m unittest discover -s tests`.

## Checklist rápido
1. módulo com `executar(d, manifesto, slug)` → 2. `cmd_*` + parser → 3. `Etapa` (se for da esteira)
→ 4. config → 5. teste → 6. `modulos.md` → 7. `estudio.py cerebro` → 8. suíte verde.
