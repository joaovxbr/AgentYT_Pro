# 010 — Quarta passada: linha condensada pelo ASR

- **Data:** 09/10/2026
- **Contexto:** primeira faixa do projeto `megumi_shadows`, gerada no **Mureka** (não Suno).
- **Relaciona:** decisão 001 (reconstrução incremental), incidente
  `2026-10-09-megumi-linha-condensada-asr.md`, incidente `2026-09-30-douma-transcricao.md`.

## Problema

O motor tinha **um** jeito de recuperar verso que o ASR perdeu: `passada_guiada` (3ª passada),
disparada por `lacunas_vocais` — trecho com **energia de voz e NENHUMA palavra transcrita**.

Isso não cobre o outro modo de falha: o Whisper ouve **algumas** palavras de uma linha e
**condensa** o resto. A voz tem transcrição, então não há lacuna, nada dispara, e o
`auditar-letra` reprova uma linha que **está cantada**.

Caso real: *"Cada shikigami meu sabe onde atacar"* → ASR devolveu `shikigami ... atacar`
(2 de 6 = 33 %). O timing do Mureka e uma retranscrição guiada provam que a linha inteira foi
cantada.

## Decisão

Adicionar uma **4ª passada** (`passada_por_linha_fraca`) com gatilho **disjunto** da 3ª:

| Passada | Gatilho | Função |
|---|---|---|
| 3ª | lacuna de voz (cobertura **zero**) | `passada_guiada` |
| 4ª | linha com cobertura **em (0, 45 %)** | `passada_por_linha_fraca` |

Regras:
1. **Não afrouxa porteiro.** Reaproveita `aceitar_passada_guiada` (≥ 3 casamentos reais,
   confiança média ≥ 0,45, ≥ 70 % sobre voz) e `trecho_explicado` (troca cirúrgica). Se não
   passar, **nada muda**.
2. **Sem prompt primeiro.** Com o prompt o Whisper "copia" a frase e casa menos. Guarda a
   tentativa **aceita**, nunca a última (bug pego no teste: a rejeitada apagava a aceita).
3. **`esperados` = linha inteira.** Filtrar só os buracos embaralha o alinhamento monotônico.
4. **Limites:** `min_palavras=3` (não retranscrever "Dez silhuetas"), `max_palavras=14`,
   `min_cobertura=0.45` — o mesmo limiar do porteiro, em `config/porteiros.json`.

## Consequências

- `auditar-letra` do Megumi: REPROVADO → **APROVADO** (243/271 casadas), sem exceção registrada.
- Suíte: **571 testes, OK** (9 novos em `tests/test_transcrever_linha_fraca.py`).
- O Mureka entrega tempo de linha; dois relógios independentes concordaram em **0,16 s**. O
  `transcricao_canonica.json` passa a ser caminho de primeira classe para faixas Mureka.
- Custo: uma passada extra só quando há linha fraca (zero em faixa bem transcrita).
