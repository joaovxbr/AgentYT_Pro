# Incidente: "tormento" não apareceu (Gojo, 30/09/2026)

**Relato do usuário:** no take LIMITLESS (`palavra_por_palavra`, ~1:51 do vídeo) a frase parou em
"TRANSCENDE O" e "tormento" nunca apareceu. Também: "os novos efeitos não apareceram".

## Causa real
1. `letra_sincronizada.json`: "o" 111,32–112,38 e **"tormento" 112,38–112,58** (0,2 s). O ASR encurtou a
   última palavra, que é sustentada no canto; a linha termina em 112,38, **antes** do fim da última palavra.
2. O take de linha era cortado em `início da linha + 4 s` e o fade usava o fim da linha (112,38): "tormento"
   entrava e já saía no fade, e o take acabava em 112,67.
3. A legenda ASS daquele trecho estava oculta (regra do estilo de linha), então a palavra não aparecia em lugar nenhum.
4. "Novos efeitos não apareceram": só 5–6 takes no vídeo e o seletor sempre começava pelos mesmos estilos;
   5 dos 6 novos nunca eram escolhidos. A densidade contava ±30 s (60 s) com limite 3, e a mesma palavra nunca repetia.

## Correções permanentes (com teste em `tests/test_motion_lab.py`)
- `motion_lab.fim_da_linha`: fim real = máx(fim da linha, fim da última palavra, início da última + 0,09 s/letra), sem invadir a próxima linha. `linhas_no_trecho` já entrega esse fim.
- `graphic_auto_pipeline.janela_de_linha`: take de linha vai até o fim real + fade; se passar de `motion_max_take_linha`, usa estilo de palavra. Sem corte fixo de 4 s.
- Última palavra fica acesa até o fim da linha; `linha_ativa` segura a linha durante todo o fade.
- `render_clipe.ass_sem_intervalos`: só oculta evento ASS coberto em ≥ 90% pelo take.
- Variedade: estilo menos usado vence (os 11 aparecem antes de repetir); densidade de motion em ±15 s; palavra-tema pode repetir até 3× a ≥ 25 s. Gojo passou de 6 para 11 takes, um de cada estilo.

## Lição
Tempo de palavra do ASR é evidência, não verdade — principalmente a **última palavra da linha**. Todo
texto que depende de tempo deve usar o fim real da linha, e nunca ocultar a legenda sem garantir que a frase
inteira está visível no take.
