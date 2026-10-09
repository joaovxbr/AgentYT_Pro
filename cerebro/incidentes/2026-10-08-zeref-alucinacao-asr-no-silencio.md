# 2026-10-08 — Zeref: alucinação do ASR no silêncio reprovava o auditor-letra

**Sintoma:** esteira do Zeref parou no `auditar-letra`: `CANTADO FORA DA LETRA 364.94s–366.34s:
CIDADE deus NO BRASIL ajoelhar,`.

**Medição:** o stem vocal em 362–366,4 s está entre −75 e −82 dBFS (silêncio). As 5 palavras
foram inventadas pelo Whisper no fim do arquivo (probabilidade 0,25–0,99, duração 0–1,4 s). Em
todo o transcrito, exatamente 5 de 760 palavras caíam em silêncio, todas nesse trecho.

**Causa:** `limpar_alucinacoes` só removia palavra com probabilidade < 0,15 ou
< 0,30 e duração > 1,2 s. As palavras de fim de arquivo passavam.

**Correção:** `transcrever.palavra_em_silencio` remove palavra com nível RMS < −55 dBFS **e**
(probabilidade < 0,8 **ou** duração ≤ 0,05 s). `estudio.cmd_transcrever` passa a energia do stem
vocal. Resultado: 19 palavras removidas no Zeref, última palavra em 350,98 s (antes 366,34 s).
Testes: `tests/test_transcrever_silencio.py` (6). Palavra com voz nunca cai nessa regra.

**Remanescente (não resolvido):** a linha falada "Natsu..." (Breakdown, 281,4–282,26 s; voz medida
em 279–282 s) não tem palavra no ASR, então o porteiro dá 0% e reprova. A letra não foi alterada
e o limiar não foi afrouxado. Decisão pendente do dono.
