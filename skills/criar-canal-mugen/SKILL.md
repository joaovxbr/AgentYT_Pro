---
name: criar-canal-mugen
description: "Cria as peças de um lançamento do canal VX RAPS — capa do YouTube, banner do canal, capa quadrada de streaming e corte vertical 9:16 para Short/Reel/TikTok. Use em pedidos como: faz a capa do <personagem>, gera os cortes da faixa, tira um corte de tal a tal segundo, prepara a arte do lançamento, cadastra a faixa nova. Para PUBLICAR o que saiu daqui, use a skill publicar-canal-mugen."
---

# Criar peças do canal VX RAPS

Motor: **acer**. Ferramenta única: `~/Documentos/Video_Studio/ferramentas/estudio.py`.

> **Duas portas, e só duas.**
> `estudio.py` = o que acontece **dentro** do estúdio (capa, banner, corte).
> `publicar.py` = o que **sai** dele (YouTube, TikTok, Instagram).
>
> 🔴 **Se algo não funciona, conserte a ferramenta. Não escreva outro script.**
> Isso é cicatriz, não estilo — leia a seção "Por que a porta é única" no fim.

```bash
cd ~/Documentos/Video_Studio/ferramentas

python3 estudio.py estado                    # panorama de todas as faixas
python3 estudio.py estado akaza              # ficha de uma faixa
python3 estudio.py doutor                    # confere o ambiente
python3 estudio.py novo <slug>               # cadastra faixa nova
python3 estudio.py capa <slug>               # as 3 artes
python3 estudio.py capa <slug> --saida-dir /tmp/previa    # sem sobrescrever
python3 estudio.py corte <slug> --de 63.5 --dur 34.5 --tema "O UNICO HONRADO"
python3 estudio.py cortes <slug>             # todos os cortes do manifesto

python3 estudio.py sincronia <slug>          # a legenda bate com a voz?  (porteiro)
python3 estudio.py sincronizar <slug>        # reescreve os tempos do .ass pela voz
python3 estudio.py ritmo <slug>              # grade musical + grade de corte sugerida
python3 estudio.py imagem <slug>             # tem IMAGEM no quadro?      (porteiro)
python3 estudio.py qa <slug>                 # os dois porteiros num comando
```

⭐ **Antes de entregar qualquer faixa: `python3 estudio.py qa <slug>`.** É um comando e
cobra as duas coisas que já saíram erradas no ar.

---

## Regra 00 — o corte vertical passa de 30 segundos, SEMPRE

Regra do Álvaro (01/09/2026), válida em qualquer PC e para todo corpo do
Hermes. Short, Reel e TikTok. Cortes de 23–28 s foram reprovados e refeitos.

Corte curto não entrega o punchline: o gancho da letra não tem tempo de armar
e pagar. Ao escolher o trecho, procure um arco que **fecha numa frase forte** e
**estenda o início** até passar de 30 s — não corte no meio de um verso só
para caber.

A trava está em dois lugares (`estudio.py` antes do encode e
`gerar_corte_marcado.py` no gerador). **Se ela reprovar, pegue um trecho maior
da letra — não baixe a constante.**

---

## Regra 02 — a legenda e o corte seguem a VOZ, não o dupleto

*(medido em 04/09/2026, nas quatro faixas que guardam onset de palavra)*

A letra era digitada como uma tupla por **dupleto** — `"LINHA A\NLINHA B"` com **um
tempo só** — e o gerador quebrava o `\N` em dois eventos, dando ao de baixo o tempo do
de cima + 90 ms. As duas metades não são cantadas juntas: a de baixo entra **1 a 2
segundos depois**.

| faixa | 2ª linha do dupleto | eventos que são 2ª metade | veredito |
|---|---:|---:|---|
| Rengoku V2 | *não usa dupleto* | 0 % | **aprovado** (\|mediana\| 0,120 s) |
| Akaza V6 | +1,225 s | 45 % | reprovado (61 linhas fora) |
| Mahoraga v2 | +1,000 s | 45 % | reprovado (47 linhas fora) |
| Imensidão v1 | +1,544 s | 50 % | reprovado (60 linhas fora) |

A correlação é perfeita: **a única faixa que escreve uma linha por evento é a única
aprovada.** Era isso que o Álvaro via como "a legenda sempre fica dessincronizada".

🔴 **Uma linha visível = um onset próprio.** O relógio é o `palavras_vocal.json` do
projeto (Whisper sobre o vocal isolado pelo Demucs), que já existia em toda faixa e era
usado só para acender a palavra-chave.

```bash
python3 estudio.py sincronia   <slug>   # mede e REPROVA — rode antes de entregar
python3 estudio.py sincronizar <slug>   # reescreve SÓ os tempos, NO LUGAR (guarda o .bak)
```

O `sincronizar` não toca estilo, posição, cor nem animação de entrada, e faz o pulso
`\t(...)` da palavra-chave andar junto com o evento. O dupleto continua empilhado: a de
cima estende o fim até o fim da de baixo, a de baixo entra no tempo dela.

⚠️ Linha que o ASR não ouviu sai **interpolada** e vem listada no relatório — confira à
mão. E desvio mediano acima de **3 s** não é dessincronia: são arquivos de **cortes
diferentes**, e o porteiro recusa em vez de "consertar" (caso do Muzan, +15,6 s).

**A mesma raiz estava na imagem.** A tabela `PLANO` dos `render_vN.py` tinha uma fronteira
por dupleto — os mesmos números da tabela da letra. No Imensidão isso deu 93 dos 95 planos
entre 1 e 4 s (faixa dinâmica 2,16×) e só 5 cortes em downbeat, 107 ms fora do beat.

⭐ **A letra diz QUAL imagem; o beat diz QUANDO ela entra.** `estudio.py ritmo <slug>`
mede a grade da faixa e propõe uma fronteira por linha cantada encaixada no beat. Se a
`confiança` da grade for < 0,25 ele **não encaixa nada** — grade errada é pior que grade
nenhuma.

---

## Regra 03 — tela preta não é plano: o quadro entregue passa por porteiro

Regra do Álvaro (05/09/2026): *"às vezes são colocadas imagens de telas pretas apenas com
avisos ou até imagens não condizentes"*. Até então **nada media o vídeo final** — o
estúdio media a FONTE (`blackdetect`) e nunca o master.

```bash
python3 estudio.py imagem <slug>     # mede e grava projetos/<slug>/qa/imagem_suspeitos.png
```

Medido em 05/09 nos masters do canal: `hakari` (**no ar**) com **9,8 s de tela morta
(6,1 %)** e **39,7 s de página de mangá** em line-art; `kashimo` (**no ar**) com 19,3 s de
página; `mahoraga` com 10,8 s de tela morta; `toji` com 10,2 s morto e 29,7 s congelado;
`rengoku V2` com 39,0 s congelado. Em `hakari` aos 65,3 s a tela é **preta com só a legenda
escrita nela** — em `mahoraga` isso acontece cinco vezes.

| medida | reprova |
|---|---|
| `morto` (luz < 14 e detalhe < 16) | bloco ≥ 1,0 s, ou > 1 % do vídeo |
| `quase-morto` (luz < 24, detalhe < 22) | > 5 % |
| `congelado` (vizinhos quase iguais ≥ 1 s) | > 6 % |
| `página` (branco sem cor em > 55 % do quadro) | > 0,5 s |

🔴 **O porteiro roda dentro do `publicar.py` também**, antes de abrir o navegador, nos
quatro comandos que sobem vídeo. Master reprovado **não sobe**; a saída editorial é
`--ignorar-qa`, que publica e **imprime o motivo**.

⭐ **Ele não lê texto, e não finge ler.** Cartela de terceiro (`坐殺博徒` em tela cheia no
`hakari` aos 12 s e 48 s), marca d'água e legenda de dublagem se provam com o **olho**:
olhe a folha de contato. **A folha é a prova; o número é só o índice dela.**

🔴 **Tela preta não se conserta com filtro** — o plano tem de mudar. E aumentar brilho num
quadro morto só revela que não havia imagem ali.

---

## Regra 01 — o manifesto é a fonte da verdade

Cada faixa tem `projetos/<slug>/projeto.json`: cor amostrada, frames
escolhidos, master atual, cortes, onde foi publicada.

**Personagem novo não pede código novo — pede manifesto.**

```bash
python3 estudio.py novo rengoku
# preencha: faixa, personagem, anime, titulo_linhas, cor.destaque,
#           arte.frames_dir, arte.frame_capa, arte.frame_banner, master
python3 estudio.py capa rengoku
```

Se o manifesto estiver incompleto, `estudio.py capa` **recusa** e lista o que
falta. Ele está certo: arte feita com dado chutado sai errada e vai ao ar.

### Como escolher a cor

**Amostre do próprio clipe**, não escolha de cabeça. Toda cor do canal saiu
assim — o ciano do Gojo é o Lapso Azul aos 32–33 s, o rosa da Nezuko são as
labaredas da Arte Demoníaca aos 22/170/172 s. E é a mesma cor que o `.ass` da
faixa usa nos destaques, então a arte e a legenda ficam da mesma família.

O campo `cor.destaque_claro` é opcional — sem ele o `artes_base.py` levanta a
cor sozinho para o texto pequeno no escuro.

### Como escolher os frames

Precisa de dois: `frame_capa` (o rosto, para capa e quadrada) e `frame_banner`
(plano mais aberto). Extraia com `ffmpeg` para `projetos/<slug>/frames_capa/hd/`
no padrão `t_<segundo>.jpg`.

🔴 **Confira a identidade em HD, não na folha de contato.** A 1ª capa do Muzan
usou uma **Lua Superior** achando que era ele (cabelo branco, olho dourado com
kanji). O Álvaro pegou. Muzan tem cabelo escuro e olho vermelho — olho com
kanji nunca é ele.

🔴 **A arte sai de frame real do MP4, nunca de imagem gerada por IA.**

---

## Fazer a arte

```bash
python3 estudio.py capa akaza
python3 estudio.py capa akaza --quais capa           # só a miniatura
python3 estudio.py capa akaza --saida-dir /tmp/x     # prévia, sem tocar no que está no ar
```

Saem três, sempre:

| arte | tamanho | onde vai |
|---|---|---|
| `<slug>_capa_youtube.jpg` | 1280×720 | miniatura do vídeo |
| `<slug>_banner_canal.jpg` | 2560×1440 | cabeçalho do canal |
| `<slug>_capa_streaming_3000.jpg` | 3000×3000 | capa quadrada de áudio |

### A conferência que a ferramenta cobra no fim

1. **É o personagem certo?** (o erro do Muzan)
2. **O título se lê no card de 210 px?** O `estudio.py` salva
   `/tmp/previa_card_210.jpg` — **abra e olhe**. Se o título não se lê nele, a
   capa está reprovada por mais bonita que esteja em 1280. A capa do Muzan
   virou silhueta nesse tamanho.
3. **A coluna de texto caiu fora do rosto?** A composição que funciona é
   sempre a mesma: personagem de um lado, texto do outro, com o scrim escuro
   por baixo do texto. Texto centralizado cai em cima da figura.

> ⚠️ Nome comprido: o `cabe()` reduz o corpo da fonte até caber na coluna, mas
> título de 3+ palavras longas fica pequeno. Prefira `titulo_linhas` quebrado
> em duas linhas curtas ("O REI DAS" / "MALDIÇÕES").

---

## Fazer o corte vertical

```bash
python3 estudio.py corte akaza --de 63.5 --dur 34.5 --tema "MORTE DESTRUTIVA"
python3 estudio.py corte akaza --de 63.5 --ate 98.0 --tema "MORTE DESTRUTIVA"
```

O que sai é o padrão do canal, sem você pedir:

- **1080×1920, enquadrado — nunca recortado.** O quadro 16:9 inteiro entra
  centralizado sobre fundo borrado do próprio frame. Center-crop decepa o
  rosto e corta a ponta da legenda.
- **Tarjas de marca**: topo com `VX RAPS - <FAIXA>` em ciano + o tema em
  branco; rodapé com `@VXRaps` em amarelo.
- **Limiter** com oversampling 4× e AAC 256k, e o true peak impresso no fim
  (alvo ≤ −1,0 dBTP). Sem isso o corte sai clipando em 0,00 dBTP: o master já
  chega perto do teto e o AAC soma overshoot.
- **Sem vinheta.** A vinheta é só do vídeo longo — 4 s de marca no vertical
  queimam a retenção na janela que decide se o vídeo vive. Se o Álvaro pedir
  marca no vertical, use `assets/intro/intro_mugen_v2_916_curta_mudo.mp4` (1,5 s).

> ⚠️ **Sem emoji nos textos das tarjas.** A fonte Ubuntu do `drawtext` não
> desenha e vira quadradinho (tofu). A ferramenta recusa. **Acento vai bem** —
> "MALDIÇÕES" renderiza.

Cortes recorrentes moram no manifesto, em `cortes[]`, e saem todos de uma vez
com `estudio.py cortes <slug>`.

### Onde o encode roda

`render_dispatch.py` procura o PC Windows (`pcque001imap`, RTX 3050) e manda o
encode pra NVENC de lá. Windows offline = cai pra CPU do acer, transparente.
Não há nada a configurar.

---

## Depois de criar

Publicar é a **outra** skill: `publicar-canal-mugen`.

Ordem de lançamento medida no canal: **o longo sobe primeiro, os cortes 2–4 h
depois.**

E anote o resultado no manifesto — `publicado.estado`, `publicado.youtube`.
É o que faz o `estudio.py estado` ser confiável na próxima faixa.

---

## Por que a porta é única

Entre 31/08 e 01/09/2026 nasceram **~40 scripts descartáveis** para publicar a
mesma coisa. Foi por eles que foram ao ar um TikTok com a legenda
`corte_1_febre_inicio_9x16`, uma legenda quadruplicada e um Reel sem legenda
nenhuma. A cura foi o `publicar.py`.

Em **03/09/2026** a mesma doença estava viva um estágio antes, na criação:
**8 scripts de capa** (`artes_akaza`, `artes_gojo`, `artes_muzan`,
`artes_nezuko`, `artes_sukuna`, `artes_sukuna_v2`, `artes_toji`,
`artes_toji_clean`) e **7 de corte** (`gerar_previa_*`,
`gerar_cortes_oficiais_*`, `gerar_corte_4_gojo`), cada um copiado do anterior
e gravando numa pasta diferente. Cada lição aprendida num deles ficava presa
nele. A cura foi o `estudio.py`.

Os 15 estão em `Video_Studio/_arquivo_morto/`, com o motivo escrito. **Não use
nada de lá.**

Repositório: `github.com/alvaro209890/mugen-studio` (privado — inclui letras de
faixas não lançadas).

(autor: Claude | 2026-09-03)
