# Incidente — dois nomes para a mesma miniatura: a entrega reprovava quem tinha capa pronta

**Data:** 2026-10-09
**Porta afetada:** `estudio.py lancamento`, `estudio.py entrega`, `estudio.py capa`
**Descoberto por:** usuário — *"faltou o shorts cade e dados de publicaçao também para eu postar?"*
**Gravidade:** alta (bloqueava a entrega e publicava caminho inexistente)

---

## Sintoma

Depois de o `megumi_shadows` fechar a esteira inteira (17 etapas verdes) e de a porta `capa`
gerar as artes oficiais, o pacote de lançamento saiu assim:

```json
"artes": [],
"miniatura": "saidas/megumi_shadows_capa_ia.jpg"
"problemas": [
  "master ausente: .../projetos/megumi_shadows",
  "thumb ausente: .../saidas/megumi_shadows_capa_ia.jpg"
]
```

O `_revisao` mostrou o contrário do que a mensagem dizia:

| arquivo em `saidas/` | existe? |
|---|---|
| `megumi_shadows_capa_youtube.jpg` | **sim** (1280x720, 107 KB) |
| `megumi_shadows_banner_canal.jpg` | sim |
| `megumi_shadows_capa_streaming_3000.jpg` | sim |
| `megumi_shadows_capa_ia.jpg` | **não** |

A capa estava pronta. A ferramenta procurava outro nome.

---

## Causa raiz — dois nomes, quatro consumidores

A miniatura 1280x720 tem **duas portas geradoras**, e cada uma escreve um nome diferente:

| porta | função | arquivo escrito |
|---|---|---|
| `estudio.py capa` | `artes_base.compor_capa_youtube` | `<slug>_capa_youtube.jpg` |
| `estudio.py artes-ia` | `gerador_artes_ia.gerar_miniatura_completa` | `<slug>_capa_ia.jpg` |

Os **consumidores** cravavam o nome antigo (`_capa_ia.jpg`):

| consumidor | uso | consequência |
|---|---|---|
| `entrega.py` `conferir` | cobra o arquivo no checklist | entrega reprovada com capa pronta |
| `entrega.py` `executar` | decide se regenera as artes | regeneração desnecessária (ComfyUI) |
| `distribuicao_social_pro.py` `pacote_lancamento` | valida tamanho/peso | `thumb ausente` no pacote |
| `publicacao_doc.py` `_markdown` | escreve o caminho no `PUBLICACAO.md` | instrução de upload apontando arquivo inexistente |

Quem rodava **só** a porta `capa` (o caminho novo, mais barato, sem ComfyUI) ficava com a
entrega permanentemente bloqueada — e a mensagem de erro mandava rodar a porta que ele já
não precisava.

### Por que ninguém pegou antes

O teste `test_entrega.py::_completo` **criava `_capa_ia.jpg` à mão**. A fixture fabricava
exatamente o arquivo que a ferramenta real não escrevia, então o contrato parecia testado —
mas o teste validava a própria suposição, não a ferramenta.

---

## Correção

**Um resolvedor só**, em `entrega.py` (o módulo dono do checklist), e todos os consumidores
passam a chamá-lo:

```python
NOMES_THUMB = ("{slug}_capa_ia.jpg", "{slug}_capa_youtube.jpg")

def _thumb(d: Path) -> Path:
    saidas = Path(d) / "saidas"
    for modelo in NOMES_THUMB:
        p = saidas / modelo.format(slug=Path(d).name)
        if p.is_file():
            return p
    return saidas / NOMES_THUMB[0].format(slug=Path(d).name)
```

Ordem canônica: primeiro `_capa_ia.jpg` (nome que o pacote sempre usou), depois
`_capa_youtube.jpg`. Sem nenhum dos dois, devolve o nome canônico — a mensagem de erro e o
`publicar.py miniatura` continuam apontando o lugar esperado.

Aplicado em `entrega.py` (2 pontos), `distribuicao_social_pro.py` (1) e `publicacao_doc.py`
(1, via `_nome_thumb`, que alimenta `PUBLICACAO.md` e o campo `miniatura` do pacote).

### O que a correção NÃO afrouxa

`_thumb` só escolhe **qual** arquivo olhar. A validação continua a mesma, depois:

- 1280x720 exatos, senão `thumb fora do padrao`;
- < 2 MB, senão `thumb >= 2 MB`;
- projeto sem miniatura nenhuma continua reprovado.

O teste `test_thumb_tamanho_errado_ainda_reprova` prova isso: `_capa_youtube.jpg` em
1920x1080 continua **reprovado**. Aceitar o nome novo não é aceitar qualquer imagem.

---

## Alternativas descartadas

1. **Fazer `capa` também escrever `_capa_ia.jpg`** — duplica a miniatura no disco (dois
   arquivos idênticos) e mantém a ambiguidade; a próxima porta geradora recria o problema.
2. **Trocar todos os consumidores para `_capa_youtube.jpg`** — quebra qualquer projeto que
   já tenha `_capa_ia.jpg` pronto (`entrega` não deve invalidar trabalho existente).
3. **Escolher o mais recente por `mtime`** — não determinístico; a mesma árvore daria
   resultados diferentes entre execuções. Contraria a falha fechada.
4. **Procurar por glob `<slug>_capa*.jpg`** — casaria `_capa_streaming_3000.jpg` (3000 px,
   não é thumbnail 1280x720). O matcher de path do `vx/dag.py` já tinha ensinado essa lição.

---

## Corolários de método

1. **Teste que fabrica o arquivo que a ferramenta deveria escrever testa a suposição, não a
   ferramenta.** A fixture do `test_entrega` criava `_capa_ia.jpg` por conta própria; era
   impossível ela falhar. Contrato entre portas se prova gerando pela **porta de verdade**
   (ou no mínimo afirmando o nome que a porta escreve).
2. **Quando duas portas produzem o mesmo artefato lógico, o nome do arquivo é contrato
   público.** Escolher um "canônico" e deixar o outro implícito é como o bug nasce; um
   resolvedor único é a única forma barata de não voltar a divergir.
3. **Mensagem de erro que manda rodar a porta que o usuário já rodou não é erro claro.** O
   aviso dizia `thumb ausente: estudio.py artes-ia` para quem tinha acabado de rodar
   `estudio.py capa` — o diagnóstico apontava para o lado errado do contrato.

---

## Verificação

- `tests/test_entrega.py::MiniaturaContractTests` — 3 testes novos; os dois primeiros
  falhavam **antes** da correção com `thumb ausente: estudio.py artes-ia`, exatamente o
  sintoma em produção.
- Suíte completa: **618 testes, OK**.
- `megumi_shadows` real: miniatura resolvida, `artes` com 3 arquivos, `shorts` com 3,
  `publicar` apontando `saidas/megumi_shadows_capa_youtube.jpg` (existe).
- Único problema remanescente no pacote: `master ausente` — **correto**, o master só nasce
  na porta `promover`, que exige aprovação explícita do usuário.
