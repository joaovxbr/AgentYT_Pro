# Incidente: corpo do Douma renderizado cortado (30/09/2026)

**Sintoma:** a música tem 179,9 s, mas o corpo saiu com 105,8 s na primeira tentativa e 89,2 s na segunda. A esteira
`20260930T220431_8e524fbf` falhou no `render-clipe`.

## Causa real
- `render_clipe.previa` renderizava cada plano em `.mp4` e juntava tudo com o **concat demuxer** do ffmpeg.
- Alguns clipes (twixtor/fontes recortadas pelo `fonte-limpa`) tinham timestamp/edit list irregular; o demuxer
  estimava a duração pelo container e **parava no meio** sem erro.
- `tpad`, `setpts=N/30`, `-video_track_timescale` e `+genpts` não resolveram (duas abordagens falharam → troca).

## Correção permanente
- Cada plano vira **fluxo H.264 puro (Annex B)**: `-bsf:v h264_mp4toannexb -f h264`, sem container nem timestamp.
- A junção é **concatenação de bytes** (`bruto.h264`), remontada em `bruto.mp4` com `-framerate 30 -f h264`.
- Conferência de quadros (`contar_quadros`): cada plano precisa ter exatamente `round(fim*30) - round(ini*30)`
  quadros e o fluxo total também. Se faltar, o render **reprova com o plano culpado** no erro.
- Plano menor que meio quadro (ex.: 7 ms) é pulado; como o arredondamento telescopa, o total continua exato.
- Erro de encode de um plano cita índice, clipe, `src` e intervalo.
- Diagnóstico: `VX_MANTER_TMP=<pasta>` guarda as partes do render.
- Teste: `tests/test_render_juncao.py`.

## Lição
Nunca confiar na duração que o container informa. Contar quadros e reprovar alto.
