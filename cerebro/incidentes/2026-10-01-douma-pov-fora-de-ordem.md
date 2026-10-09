# Incidente: legenda do POV (Shorts) fora de ordem com o canto (Douma, 01/10/2026)

**Relato do usuário:** "a nossa legenda do POV está fora de ordem na hora da música."

## Causa real (medida)
O POV (`pov_lyrics_official.build_ass`) acende a frase **palavra a palavra** pelo tempo de cada palavra em
`letra_sincronizada.json -> words`. A linha estava no tempo certo; as **palavras dentro dela**, não:
- `sincronizar_letra._palavras_da_linha` dava o tempo pela **posição**: 1ª palavra exibida ← 1º tempo casado,
  2ª ← 2º… Um token sem par no ASR ("o" engolido, o "—" do refrão) deslocava o resto da linha. O POV acendia
  "seu" quando o cantor cantava "choro". **18 de 36 linhas** do Douma tinham palavra no tempo da vizinha.
- O ASR entregou palavras "colapsadas" (duração zero, 6 no mesmo instante em 44,16 s).
- O evento de uma palavra podia durar além do início da próxima: 2 momentos com duas versões da frase na tela.
- Nenhum porteiro olhava o tempo **por palavra**; `sincronia` só media o início da linha.

## Correção permanente
- `_palavras_da_linha` usa o casamento **por token** do alinhador (Needleman-Wunsch):
  - cada palavra recebe o tempo da palavra cantada que casou com **ela**;
  - "—" e outra pontuação solta grudam na palavra anterior;
  - palavra sem par, que volta no tempo ou colapsada no ASR é **interpolada** entre as vizinhas
    (`origem: "estimada"`; casada = `origem: "asr"`).
- `pov_lyrics_official.build_ass`: o evento de cada palavra termina quando a próxima acende (nunca sobrepõe).
- Porteiro novo `sincronizar_letra.validar_palavras`, dentro de `estudio.py sincronia` (etapa da esteira):
  reprova palavra que volta no tempo ou que acende quando se canta **outra palavra da linha**. Nome mal ouvido
  pelo ASR ("Shinobu" → "novo") não reprova, porque o tempo está certo.
- A legenda do master (`legendas/douma.ass`, por linha) não mudou: mesmo hash antes e depois.
- Testes: `tests/test_pov_palavras.py`.

## Resultado no Douma
`sincronia`: palavra a palavra 0 problemas. Shorts refeitos com `estudio.py shorts douma`.

## Lição
Legenda que acende palavra a palavra precisa de porteiro por palavra. Tempo de linha certo não garante
palavra certa.
