# Incidente — `scene_semantics` em lista derruba `cenas-auto`

**Data:** 2026-10-09
**Projeto:** `megumi_shadows` (Jujutsu Kaisen / Megumi Fushiguro)
**Etapa:** `cenas-auto` (4ª da esteira)
**Severidade:** alta — para a esteira inteira em 0.0 s, sem log util
**Status:** resolvido

---

## Sintoma

A esteira morreu na 4ª etapa:

```
fonte-limpa        concluido      22.2s
auditar-letra      concluido       1.1s
auditar-ritmo      concluido       0.0s
cenas-auto         falhou          0.0s   exit 1
ERRO: cenas-auto: AttributeError: 'list' object has no attribute 'get'
```

Agravante: **`qa/esteira/<run>/08_cenas-auto.log` tinha 0 bytes**. O log da etapa
existe mas vazio ⇒ impossível diagnosticar pelo caminho normal.

## Causa raiz

`projeto.json` deste projeto declara o campo na forma **curta**, uma lista de ids:

```json
"scene_semantics": [
  "megumi_fushiguro", "shikigami", "divine_dog", "shadow_technique",
  "hand_sign", "domain_expansion", "school_uniform", "night_tokyo",
  "curse_spirit_fight"
]
```

Mas **todo** consumidor assume a forma canônica (dicionário) e faz `.get(...)`
direto:

| arquivo | linha | expressão |
|---|---|---|
| `semantic_vision.py` | 30 | `cfg = manifesto.get("scene_semantics") or {}` → `cfg.get("labels")` |
| `semantic_scene_matcher.py` | 676 | `(manifesto.get("scene_semantics") or {}).get("required_score", 0.16)` |
| `semantic_scene_matcher.py` | 857 | `(manifesto.get("scene_semantics") or {}).get("strict", False)` |
| `shorts_pipeline.py` | 53 | `(manifest.get("scene_semantics") or {}).get("labels")` |
| `graphic_auto_pipeline.py` | 613 | `((manifesto.get("scene_semantics") or {}).get("labels") or [])` |
| `publicacao_doc.py` | 50 / 166 / 168 | idem |

O `or {}` só protege contra **ausência** (`None`). Uma **lista** é truthy ⇒ passa
direto ⇒ `.get()` estoura.

Cadeia exata do estouro:

```
semantic_scene_matcher.executar()
  └─ scene_intelligence.catalogar_projeto()          linha 563
       └─ semantic_vision.profile_from_manifest()    linha 31
            └─ cfg.get("labels")   ← AttributeError: 'list' object has no attribute 'get'
```

O log vazio é explicável: a exceção sobe **antes** de qualquer `print` da etapa, e
as etapas rodam in-process (`vx/runner.py`) — o traceback vai para a métrica, não
para o arquivo de log da etapa.

## Decisão

Normalizar num **único ponto** (`semantic_vision.scene_semantics_cfg`) e fazer
todos os consumidores passarem por ele. Aceitar as três formas:

| entrada | saída |
|---|---|
| `["megumi_fushiguro", "shikigami"]` | `{"enabled": True, "labels": [{id/name = texto, prompt = texto sem `_`, kind = "concept"}]}` |
| `"megumi_fushiguro"` | o mesmo, com um rótulo |
| `{"enabled":…, "labels":[…], …}` | **idêntico** (mesmo objeto, sem cópia) |
| ausente / `None` / `""` / `[]` | `{}` ⇒ perfil desligado, sem estouro |

A lista de ids vira `kind = "concept"` porque a forma curta **não carrega tipo**.
Quem precisa de `entity`/`action` (gráficos, shorts, publicação) deve usar a forma
longa — a curta é atalho para "quero o matcher semântico ligado nestes conceitos",
não um substituto.

## Consequências

- `cenas-auto` volta a rodar: `status=applied`, **111 segmentos casados**,
  30 clipes → 92 cenas, `failed: 0`.
- 6 módulos passam a aceitar a forma curta: `semantic_vision`,
  `semantic_scene_matcher`, `shorts_pipeline`, `graphic_auto_pipeline`,
  `publicacao_doc` (+ `scene_intelligence` pelo `profile_from_manifest`).
- Forma canônica preservada byte a byte (teste `assertIs` garante que não há cópia).
- **7 testes de regressão** em `tests/test_scene_intelligence.py :: SceneSemanticsShapeTest`.
- Nenhum portão afrouxado.

## Alternativas descartadas

1. **Corrigir só o `projeto.json`** (reescrever na forma longa) — resolve este
   projeto e deixa a armadilha armada para o próximo. O manifesto aceita a forma
   curta; se aceita, tem que funcionar. *Fix the tool, never the song.*
2. **`isinstance(cfg, dict) else {}`** em cada consumidor — 7 lugares repetindo a
   mesma guarda, e a forma curta passaria a ser silenciosamente ignorada (o matcher
   desligaria sozinho, sem dizer nada). Falha fechada é não estourar **e** não
   mentir.
3. **Validar no `estudio.py novo`** — não pega projeto já criado, e o campo é
   editado à mão depois.
4. **Forma curta = erro de manifesto** — hostil. O formato curto é legível e
   legítimo ("estes são os conceitos do projeto"); o motor é que tem que entender.

## Lição

> **Campo de manifesto com duas formas válidas precisa de um normalizador único,
> não de 7 `or {}` espalhados.**

O `or {}` é a armadilha específica: ele *parece* defensivo e protege só contra
`None`, deixando qualquer outro tipo passar para o `.get()`. Guarda por tipo
(`isinstance`) ou normalizador — nunca `or {}` como validação.

**Corolário:** etapa que falha em 0.0 s com log de 0 bytes quase sempre estoura
*antes* do primeiro `print` — é exceção de import/carregamento, não de execução.
