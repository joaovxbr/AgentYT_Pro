# Incidente — QA de texto reprova screentone e a nossa própria cartela

**Data:** 2026-10-09
**Projeto:** `megumi_shadows`
**Etapa:** `qa-master` (17ª e última), passe `render-clipe` → `auditar_texto_render`
**Severidade:** alta — reprovou o render já pronto (208 s de NVENC) por 12 falsos positivos
**Status:** resolvido

---

## Sintoma

O `render-clipe` terminou com sucesso (207.9 s, NVENC) e o `qa-master` derrubou a esteira:

```
ERRO: QA de texto do render reprovado (12):
  0.5s 'MEGUMI FUSHIGURNJUJUTSU KAISEN'
  1.0s 'MEGUMI FUSHIGUROJUJUTSU KAISEN'
  1.5s 'MEGUMI FUSHIGUROJUJUTSU KAISEN'
  ...
  4.0s 'MEGUMI FUSHIGURO JUJUTSU KAISEN'
```

O gate estava certo em **sinalizar** algo — mas o que ele sinalizou era **a nossa
própria cartela de abertura**.

---

## Defeito 1 — a cartela composta nunca casa

A cartela é escrita assim (`titulos_pipeline.arte_titulo`):

```python
sub = f"{str(manifest.get('personagem', '')).upper()}  \u2022  {anime}"
# -> "MEGUMI FUSHIGURO  •  JUJUTSU KAISEN"
```

E o `corpus_permitido` montava a lista de textos nossos assim:

```python
return "|".join(_norm(p) for p in partes)
```

O problema é o `_norm`:

```python
def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if ch.isascii() and ch.isalnum())
```

`_norm` mantém **só** `isascii() and isalnum()`. Mas o `"|"` é aplicado **depois**
da normalização de cada parte. Então o `|` **sobrevive** no corpus final — mas o
`texto_e_nosso` comparava contra o **corpus inteiro**, não contra os campos:

```python
if n in corpus:
    return True
```

Medido:

```
'MEGUMI SHADOWS'                  -> 'megumishadows'                in corpus=True
'MEGUMI FUSHIGURO JUJUTSU KAISEN' -> 'megumifushigurojujutsukaisen' in corpus=False
```

A string composta **não existe em nenhum campo isolado**. `megumifushiguro` vem do
campo `personagem` e `jujutsukaisen` do campo `anime` — só que estão separados por
`|`, e o texto lido pelo OCR atravessa essa fronteira.

**Correção (duas partes):**

1. O corpus passa a incluir as cartelas **compostas** que os nossos cards escrevem
   (`"{pers} {anime}"`, `"{pers} • {anime}"`, `"VX RAPS @VXRaps"`, etc.).
2. `texto_e_nosso` casa **dentro de um campo por vez** — nunca no blob concatenado:

```python
campos = [c for c in corpus.split("|") if c]
if any(n in c for c in campos):
    return True
for c in campos:
    ...  # janela deslizante DENTRO de um campo só
```

---

## Defeito 2 — screentone de quadrinho vira "texto intruso"

Depois da correção 1, sobraram **3** amostras:

```
143.0s marca=False '888888'
143.5s marca=False '888888'
144.0s marca=False '888888'
```

Localizado no tempo exato: `clips_raw/vx_graphics_auto/11_megumi_motion_card_manga.mp4`
em **142.57–144.50 s** — um **manga take** gerado pelo nosso próprio `graficos-auto`,
com retícula de meio-tom (halftone). O OCR lê a retícula como `888888`.

O frame confirma: painel de quadrinho com `MEGUMI` numa cartela e a letra legítima
`MEGUMI FUSHIGURO, VOCE VAI ME SENTIR`. O `888888` está em `pos=(0.03, 0.95)`,
tamanho `0.03x0.01` — um **fio** no canto inferior esquerdo.

Medição de todas as 346 caixas do render:

| caixa | px em 960×540 | área |
|---|---|---|
| `888888` ×3 (screentone) | **25–31 × 8** | **0.00039–0.00048** |
| menor texto REAL (`MEGUMI-FUSHIGURO`) | 112 × 17 | 0.00367 |
| maior (`SOMBRA`) | 902 × 468 | 0.814 |

**Vão de 8× entre ruído e texto.** E as três caixas de screentone têm **8 px de
altura** — são fios, não linhas de texto.

O gate já tinha um critério anti-ruído (exigir 2 leituras em 1.5 s), mas **nenhum
critério de tamanho**: um fio de retícula passava.

**Correção:** dois limiares novos em `config/porteiros.json`, na seção `fonte`:

```json
"texto_area_min": 0.0015,
"texto_altura_min_px": 11
```

Escolhidos no **meio** do vão medido, com folga de ~3× para cada lado (ruído 0.0005,
texto 0.00367, limiar 0.0015).

**Salvaguarda crítica:** o filtro de tamanho **não** se aplica a marcas conhecidas.
`MARCAS_TERCEIROS` reprova **antes** da checagem de tamanho, então um logo de canal
pequeno (Crunchyroll num canto) continua caindo pelo **nome**, não pelo tamanho:

```python
marca = any(m in _norm(b["texto"]) for m in MARCAS_TERCEIROS)
if marca:
    estranhos.append({...}); continue          # marca nao passa por tamanho
if _caixa_pequena(b, area_min, alt_min):
    continue                                   # screentone/ruido
```

---

## Prova de que o gate NÃO afrouxou

Os dois lados foram verificados com o corpus real do projeto:

| texto | antes | depois | esperado |
|---|---|---|---|
| `MEGUMI FUSHIGURO JUJUTSU KAISEN` | ❌ repr. | ✅ passa | nosso |
| `MEGUMI FUSHIGUROJUJUTSU KAISEN` | ❌ repr. | ✅ passa | nosso (OCR come o bullet) |
| `VX RAPS APRESENTA` | ✅ | ✅ | nosso |
| `SOMBRAS SE ABREM NO CHAO` | ✅ | ✅ | nossa letra |
| `ANIME FLV` | ❌ | **❌ ainda reprova** | intruso |
| `Canal do Joao` | ❌ | **❌ ainda reprova** | intruso |
| `ASSISTA AGORA EM HD` | ❌ | **❌ ainda reprova** | intruso |
| `naruto shippuden opening` | ❌ | **❌ ainda reprova** | intruso |
| `GLICINIA TV` | ❌ | **❌ ainda reprova** | intruso |
| `Constantly...` (texto real, tamanho normal) | ❌ | **❌ ainda reprova** | intruso |

Resultado no render real: **12 intrusos → 0**, `APROVADO: True`.

---

## Lição

> **Normalizador que apaga separador transforma campos distintos num blob.**

O `|` sobrevivia no corpus, mas o comparador usava o corpus **inteiro** — então a
fronteira existia e era ignorada. Ou o separador é **semântico** (e o casamento
respeita a fronteira), ou não deveria existir. Meio-termo é bug.

**Corolário 1:** todo gate de OCR precisa de um piso de **tamanho**. Ruído de
textura (screentone, grão, padrão de compressão) produz leituras de alta confiança
em caixas minúsculas — a confiança do OCR **não** separa os dois casos (as três
leituras de screentone tinham conf 0.82–0.96).

**Corolário 2:** filtro de tamanho e filtro de nome cobrem coisas diferentes e
devem ser **independentes**. Marca pequena se pega pelo nome; ruído pequeno se pega
pelo tamanho. Encadear os dois (marca → tamanho → corpus) preserva ambos os poderes.

**Corolário 3:** quando o gate reprova e o frame mostra a nossa própria arte, o bug
está no **corpus/permitido**, não no limiar. Conferir sempre: "o gate sabe que este
texto é meu?"

---

## Arquivos tocados

| arquivo | mudança |
|---|---|
| `ferramentas/fonte_limpa.py` | `corpus_permitido` inclui cartelas compostas; `texto_e_nosso` casa por campo; `+_caixa_pequena`; `intrusos_render` aceita `c` e filtra tamanho |
| `config/porteiros.json` | `+texto_area_min`, `+texto_altura_min_px` |
| `PADRAO` (código) | mesmos dois defaults documentados |
| `tests/test_fonte_limpa.py` | `+CartelaCompostaTests` (6), `+CorpusPermitidoTests` (2), `+ScreentoneOcrTests` (6) |

Suíte: **615 tests, OK** (596 antes deste incidente, 562 antes de toda a série).
