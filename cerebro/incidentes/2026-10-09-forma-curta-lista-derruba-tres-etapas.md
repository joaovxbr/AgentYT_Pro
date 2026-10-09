# Incidente — forma curta em lista derruba três etapas seguidas

**Data:** 2026-10-09
**Projeto:** `megumi_shadows` (Jujutsu Kaisen / Megumi Fushiguro)
**Etapas:** `cenas-auto` (4ª), `cenas-ia` (6ª), `titulos` (7ª)
**Severidade:** alta — para a esteira inteira, sempre em 0.1–0.0 s, sem log util
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

## Duas etapas, dois campos, a mesma armadilha

O bug nao apareceu de uma vez. Cada correção revelou o **mesmo padrão** no
consumidor seguinte — campo de manifesto que aceita forma curta em lista, lido
com `or {}` + `.get()`:

| # | etapa | campo | consumidor que estourou |
|---|---|---|---|
| 1 | `cenas-auto` | `scene_semantics` | `semantic_vision.profile_from_manifest` |
| 2 | `cenas-ia` | `scene_semantics` | `cenas_ia_pipeline._fraqueza` |
| 3 | `titulos` | `imagem_ia` | `titulos_pipeline.arte_titulo` (`.kanji`) |

Depois da 3ª ficou claro que procurar consumidor por consumidor era o caminho
errado — varredura **exaustiva** (`grep -rn --include=*.py .`) achou os 8 usos
restantes de `imagem_ia` de uma vez:

`cenas_ia_pipeline`, `gerador_artes_ia` (2), `gerador_imagem_local` (4),
`motion_lab`, `titulos_pipeline`.

**Lição de método:** corrigir um bug de contrato exige varrer **todos** os usos
do campo, não só o que estourou. A 1ª e a 2ª correção foram reativas; a 3ª foi
sistemática e fechou o caso.

---

## Terceiro defeito, campo diferente: `transcricao_canonica.json`

Passadas as três etapas, a esteira chegou em `sincronia` (a 11ª) e reprovou:

```
medidos 0/38 eventos
mediana=+0.000s  p90=0.000s
! sem onsets casados — relogio errado?
REPROVADO
```

A mensagem sugere relógio errado. **Não era.** O `.ass` tinha 38 eventos
começando em 15.72 s e a canônica tinha 38 linhas começando em 15.72 s —
perfeitamente alinhados. O defeito estava em `legenda.carregar_onsets`, que
conhecia só dois formatos:

| formato | origem | lido? |
|---|---|---|
| `{"words": [...]}` | Whisper cru | sim |
| `[{word,start,end}, ...]` | `palavras_vocal.json` | sim |
| `{"lines": [{text,start,end,words:[...]}]}` | **`transcricao_canonica.json`** | **não** |

A canônica **aninha** as palavras dentro de `lines`. Medido:

```
onsets lidos da canonica: 0
top-level keys: ['lines', 'model', 'lyrics_source', 'method', 'song_id', 'share_key']
linhas: 38
palavras DENTRO das linhas: 271
```

**271 palavras no arquivo, 0 lidas** ⇒ `desvios` vazio ⇒ o gate cai no ramo
"sem onsets casados" e reprova. O gate estava certo em reprovar: ele recebeu
zero informação. Quem mentiu foi o leitor.

Correção: terceiro ramo em `carregar_onsets`, com fallback para a linha inteira
quando não há word-level (nunca 0 onsets), e `add()` passando a aceitar `text`
(linhas não têm campo `word`).

Resultado: **38/38 eventos medidos, mediana +0.000 s, p90 0.000 s, APROVADO.**

**Lição de método (2ª):** quando o gate diz "0 de N medidos", o suspeito é o
**leitor de entrada**, não o alinhamento. Zero medições não é "medido e ruim" —
é "não medido". O gate só pode julgar o que conseguiu ler.

---

## Causa raiz

`projeto.json` deste projeto declara o campo na forma **curta**, uma lista de ids:

```json
"scene_semantics": [
  "megumi_fushiguro", "shikigami", "divine_dog", "shadow_technique",
  "hand_sign", "domain_expansion", "school_uniform", "night_tokyo",
  "curse_spirit_fight"
],
"imagem_ia": [
  "jujutsu kaisen anime style", "dark blue shadow energy",
  "shikigami summoned beast", "megumi fushiguro black hair spiky",
  "night urban tokyo japan"
]
```

Mas **todo** consumidor assume a forma canônica (dicionário) e faz `.get(...)`
direto:

| arquivo | linha | expressão |
|---|---|---|
| `semantic_vision.py` | 30 | `cfg = manifesto.get("scene_semantics") or {}` → `cfg.get("labels")` |
| `semantic_scene_matcher.py` | 676 | `(manifesto.get("scene_semantics") or {}).get("required_score", 0.16)` |
| `semantic_scene_matcher.py` | 857 | `(manifesto.get("scene_semantics") or {}).get("strict", False)` |
| `cenas_ia_pipeline.py` | 173 | `(manifest.get("scene_semantics") or {}).get("required_score", 0.16)` |
| `shorts_pipeline.py` | 53 | `(manifest.get("scene_semantics") or {}).get("labels")` |
| `graphic_auto_pipeline.py` | 613 | `((manifesto.get("scene_semantics") or {}).get("labels") or [])` |
| `publicacao_doc.py` | 50 / 166 / 168 | idem |
| `titulos_pipeline.py` | 98 | `(manifest.get("imagem_ia") or {}).get("kanji")` |
| `cenas_ia_pipeline.py` | 136 | `bloco = manifest.get("imagem_ia") or {}` |
| `gerador_artes_ia.py` | 54 / 292 | `bloco = manifesto.get("imagem_ia") or {}` |
| `gerador_imagem_local.py` | 200 / 212 / 390 / 401 | idem |
| `motion_lab.py` | 1328 | `(manifesto.get("imagem_ia") or {}).get("tags_personagem")` |

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

`imagem_ia` segue a mesma regra via `imagem_ia_cfg`: a forma curta é uma lista de
tags soltas que vira `tags_estilo` (o campo que os geradores já concatenam no
prompt). Os campos estruturados (`tags_personagem`, `kanji`, `tags_alvos`) ficam
ausentes e o consumidor cai no fallback documentado (`personagem, anime`) — nunca
em exceção.

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

**Corolário 1:** etapa que falha em 0.0 s com log de 0 bytes quase sempre estoura
*antes* do primeiro `print` — é exceção de import/carregamento, não de execução.

**Corolário 2:** gate que reporta "0 de N medidos" aponta para o **leitor**, não
para o dado. Confira o parser antes de mexer no alinhamento.

**Corolário 3:** ao corrigir bug de contrato de campo, varra **todos** os usos
(`grep -rn --include=*.py .`), não só o que estourou. Foram 3 rodadas reativas
antes da varredura exaustiva fechar o caso.

---

## Arquivos tocados

| arquivo | mudança |
|---|---|
| `semantic_vision.py` | +`scene_semantics_cfg`, +`imagem_ia_cfg` (normalizadores) |
| `semantic_scene_matcher.py` | 2 usos → `scene_semantics_cfg` |
| `cenas_ia_pipeline.py` | 2 usos → normalizadores |
| `shorts_pipeline.py` | 1 uso → `scene_semantics_cfg` |
| `graphic_auto_pipeline.py` | 1 uso → `scene_semantics_cfg` |
| `publicacao_doc.py` | 3 usos → `scene_semantics_cfg` |
| `titulos_pipeline.py` | 1 uso → `imagem_ia_cfg` |
| `gerador_artes_ia.py` | 2 usos → `imagem_ia_cfg` |
| `gerador_imagem_local.py` | 4 usos → `imagem_ia_cfg` |
| `motion_lab.py` | 1 uso → `imagem_ia_cfg` |
| `legenda.py` | +3º formato em `carregar_onsets`, `add()` aceita `text` |
| `tests/test_scene_intelligence.py` | +7 testes (`SceneSemanticsShapeTest`, `ImagemIaShapeTest`) |
| `tests/test_cenas_ia_pipeline.py` | +4 testes (`SemanticsShapeTests`) |
| `tests/test_legenda_ativa.py` | +6 testes (`OnsetsCanonicaTests`) |

Suíte: **596 tests, OK** (562 antes do incidente).
