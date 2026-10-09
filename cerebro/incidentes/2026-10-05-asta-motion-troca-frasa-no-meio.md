# Incidente: take de motion troca a frase no meio (Asta, 05/10/2026)

**Relato do usuário:** no master, em 00:00:27 a kinetic text acende "O" em vermelho
na linha errada — a frase "O DE QUATRO FOLHAS / SUBIU PRO YUNO NO AR" já deveria ter
terminado. Depois, em 00:00:51 o take "O TOURO NEGRO…" aparece adiantado e em 00:00:55
está escrito só "FAÇA"; o take só termina em 00:00:56.

**Não é a motion entrando tarde: é a motion SAINDO CEDO e vestindo a linha vizinha.**

## Mecanismo

`linhas_no_trecho` (motion_lab.py:148) montava a janela do take com **toda linha que
apenas ENCOSTA nela**, não só as que estão dentro:

```python
if float(ln["end"]) <= de or float(ln["start"]) >= de + dur:   # so filtra por inicio/fim
    continue
```

`estilo_palavra_por_palavra` (e `maquina_escrever`, `letra_fundo`) chamam `linha_ativa`
a cada quadro, e ela devolve a **última** linha que casa com `start-0.05 <= t < end+0.65`.
A linha seguinte já entrou na lista com parte do canto consumida, então **assume a frase
antes do fim do take**:

- **vazamento de CAUDA** — a linha seguinte começa antes do take acabar:
  `03_touro` (51,10–55,20), linha seguinte "Faça o que ninguém faz" comeca54,54 →
  vira "FAÇA" em 54,8 s. `01_yuno` (23,93–27,93), seguinte comeca 27,28 → "O" errado aos 27,0 s.
- **vazamento de CABEÇA** — a linha anterior ainda esta segurada quando o take comeca:
  a janela do `01_yuno` comeca 23,93 e a anterior so termina 24,04.

3 dos 11 takes do Asta estavam afetados (`01_yuno`, `03_touro`, `04_raio`); os outros 8
nenhum because `06`/`07`/`11` casam refrão repetido e as linhas vizinhas caem fora da janela.

## Correção

`linhas_no_trecho` ganhou `so_linha`: o take **sabe** o que escreve
(`design.json -> line_text`), e `renderizar_take` passou esse valor até `preparar`. Com
`so_linha` a janela entrega só aquela linha, matando cabeça e cauda de uma vez.
O lab (`motion-lab`, sem take) não passa `so_linha` e continua vendo a janela inteira.

Junto: as pontas da linha do take passam a cobrir a janela inteira
(`ini = min(ini, 0)`, `fim = min(max(fim, dur - TAKE_LINHA_SOBRA), dur)`) — senão, com a
janela começando antes da linha, sobrava um vão em branco na cabeça do take (achado por
um teste antes de eu ver).

**Nada de limiar novo**: o take continua durando o que `janela_de_linha` planejou.

## Como verificar de novo (barato, sem render)

Qualquer take de estilo de linha: monte a janela com `so_linha` e varra `linha_ativa` em
passos de 0,1 s — a frase tem de ser a do `line_text` em **todos** os instantes, do
primeiro ao último. Só no fim entra o fade (`FADE_LINHA_DEPOIS 0,35` + `FADE_LINHA_DUR 0,3`),
que é o comportamento projetado. No Asta, os 3 takes re-renderizados passaram
("PERGUNTAR" aceso até 3,6 s de 4,0; "AR" até 3,5 s de 4,0).

Testes: `tests/test_motion_lab.py::GraficosAutoMotionTests` (5 novos) — cabeça, cauda,
lab intacto, `so_linha` chegando ao render, e a frase presente na janela toda. Suíte: **373 OK**.
Backup dos takes antigos: `projetos/asta/backups/vx_graphics_auto_pre_fix/`.