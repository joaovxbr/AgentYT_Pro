# Incidente: Douma "PARAÍSO ETERNO" — transcrição reprovada (30/09/2026)

Primeira música nova depois da reconstrução. Voz feminina do Suno, caixinha de música e coral.

| Sintoma | Causa real | Correção permanente |
|---|---|---|
| "voz sem transcrição" em 156,5–164 s | Vocalise/coro **depois da última linha** (voz −24 dB, some em 164 s). Não há letra ali | Porteiro só reprova lacuna com **letra pendente** (`transcrever.classificar_lacunas`); vale no `transcrever` e no `auditar-letra` |
| "voz sem transcrição" em 30,5–35,5 s | Whisper em bloco de 30 s parou em "Olhos de arco-íris como o meu" e pulou 3 linhas (29–42 s). A 2ª passada recortava **só** a lacuna de energia (começava no meio da frase) e não reconhecia nada | 3ª passada (`passada_guiada`): janela = da última palavra casada com a letra antes da lacuna até a primeira depois (`janela_da_letra_pendente`), num bloco só; sem prompt e, se falhar, com **só** as frases pendentes |
| Lacuna com letra escondida como "vocalise" | Alinhador aceita similaridade 0,24: "o"/"de" soltos contavam como casados | `letra_pendente` só considera casamento com sim ≥ 0,6 |
| 3ª passada aceitou "a a a" e apagou a 1ª linha | Vocalise de intro com 2 tokens pendentes; aceite frouxo | Passada guiada só em lacuna depois do 1º verso e com ≥ 4 tokens pendentes; aceite exige ≥ 3 casamentos reais, confiança média ≥ 0,45 e ≥ 70 % das palavras sobre voz |
| 3ª passada apagou "eu vim te libertar" | Troca feita na janela inteira (ia até o meio do refrão) | Troca só o trecho que a passada nova explicou (`trecho_explicado`) |

Resultado: transcrição OK, sincronia aprovada, `auditar-letra` APROVADO (256/265 palavras casadas). Testes em
`tests/test_auditor_letra.py::LetraPendenteTests`.

## Clipes
- `douma_twixtor_4k_a` falhou no yt-dlp (formato); os outros 10 baixaram.
- `douma_s3_cenas` (7,2 % tela morta, 35,6 % congelado) e `kanae_flashback` (45,7 % congelado) reprovaram no
  porteiro de fonte → movidos para `clips_raw/_reprovados/` (a esteira só lê `clips_raw/*.mp4`).

## Lição
A letra autoral diz **o que** falta; o áudio diz **se** foi cantado. Voz sem letra pendente não é erro; letra
pendente sem voz é. Retranscrever sempre a frase inteira, nunca um recorte que começa no meio dela.
