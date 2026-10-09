# Limpeza de Fontes: Marca d'Água e Legenda de Dublagem

> 🔴 **Ordem do Álvaro (31/08/2026):** nenhum clipe sai com **marca d'água** nem com
> **legenda de dublagem** de terceiro. Só ficam as legendas da MÚSICA (o `.ass`).
> Vale para todo agente e todo vídeo, não só AMV. A fonte sai limpa **antes** de
> entrar na montagem — nunca depois, no vídeo já montado.

## 1. Três técnicas — uma só não resolve

| Problema na fonte | Técnica | Como |
| :--- | :--- | :--- |
| Logo de canal pequeno e fixo (`Subscribe`, `4KAnime`, `ADAMATIX`) | `delogo` interpola da borda da caixa | `delogo=x=:y=:w=:h=` |
| Marca sobre line-art de mangá (preto no branco) | levanta o ponto branco | `curves=all=0/0 0.60/0.60 0.803/1 1/1` |
| **Legenda de dublagem no rodapé** | **recorte 16:9 acima da legenda + zoom de volta** | `crop=W:H:x:y,scale=1920:1080` |
| **Texto grande espalhado no quadro** (fan-edit) | **não existe filtro: RETIMAR o corte** | escolher janela limpa da fonte |

⚠️ **Nunca `delogo` em legenda.** A caixa fica larga demais e o `delogo` deixa um
borrão horizontal atravessado no quadro — pior que a legenda original.
⚠️ **Nunca `delogo` em mangá.** Deixa borrão vertical sobre as linhas de velocidade.

## 2. A linha de corte da legenda

⭐ **Medida que se repetiu nas 3 fontes de anime auditadas: o topo do texto de
legenda de dublagem fica em `y=885`** (varredura de 0,25 s dentro das janelas
usadas). Daí sai o recorte padrão:

```
crop=1546:870:<x>:0,scale=1920:1080:flags=lanczos
```

870 = 885 − 15 px de folga. 1546 fecha 16:9 com 870. Zoom resultante: **1,24×**.
O `x` desloca o recorte para também matar um logo lateral (ver §4).

Comece por esse número numa fonte nova; só remeça se não bater. Para medir:

```bash
# amostre a faixa inferior a cada 0,25 s dentro das janelas que o plano usa
ffmpeg -ss <t> -i <fonte> -frames:v 1 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,crop=1920:400:0:680" faixa.png
```

Depois conte, por linha, as transições fortes (`|Δ| > 65`) na faixa central e pegue
a **primeira** linha acima do limiar. Linha de legenda tem pico bem acima da arte.

## 3. Janelas limpas + validador (o que impede a legenda de voltar)

Fonte de fan-edit não tem filtro que salve: o texto ocupa o quadro inteiro e muda
de posição. A saída é usar só as **janelas limpas** da fonte. Registre-as no script
de render num dict e **valide o plano antes de gastar CPU**:

```python
JANELAS_LIMPAS = {
    "manga_anim":  [(2.0, 4.9), (16.2, 24.9), (44.6, 48.9)],
    "upper_moons": [(0.0, 9.5), (15.1, 36.4), (41.0, 144.2)],
}
# no validador, além de checar entrada+duração <= duração da fonte:
janelas = JANELAS_LIMPAS.get(fonte)
if janelas and not any(a <= entrada and entrada + dur <= b for a, b in janelas):
    erros.append(f"corte {i} usa {fonte} fora das janelas limpas")
```

Foi esse validador que pegou uma cartela de *disclaimer* que a auditoria manual
tinha deixado passar. **Copie o padrão** — custa segundos e evita re-render.

## 4. Mapa de contaminação — projeto `muzan` (auditado 31/08/2026)

Pasta: `/home/acer/Documentos/Video_Studio/projetos/muzan/`
Script: `limpar_fontes_muzan.sh` → escreve as fontes limpas em `raw_limpo/`.

| Fonte (id do YouTube) | O que tinha | Tratamento |
| :--- | :--- | :--- |
| `P7cfokcyQFU` upper_moons | botão **Subscribe** (x1590-1913, y20-107) + legenda EN + cartelas `GYOKKO/UPPER FOUR HANTENGU/UPPER ONE KOKUSHIBO` na borda esquerda (9,6-14,4 e 36,5-40,2 s) | `crop=1546:870:40:0` (o x=40 mata o Subscribe) + retiming p/ fugir das cartelas |
| `r0_UJ7SibKs` lower_moons | **4KAnime** no rodapé direito + legenda EN | `crop=1546:870:187:3` |
| `pKeTc7BOddE` yoriichi_anime | **4K ANINOMI** no canto sup. dir. + legenda EN; termina com **cartela do Akatsuki (Naruto)** a partir de ~25,5 s | `crop=1546:870:187:0` |
| `aso_PwDO4sw` manga_anim | fan-edit PT: disclaimer EN de 0 a 1,75 s + `VIRAR UM DEMÔNIO?`, `ANOS DEPOIS COM O SANGUE DO MUZAN`, `EU SER UM DEMÔNIO`, `O REI DEMONIO ONI`, `CORAÇÃO` | **só janelas limpas: 2,0-4,9 · 16,2-24,9 · 44,6-48,9** |
| `XlwPZwRKSKQ` yoriichi_manga | mesmo fan-edit PT, em cima do único trecho que o AMV usava | **descartada** |
| `wWi5gVmXfmY` tanjiro_demon_king | 🔴 **não é o anime** — animação vetorial de fã (`Guii Animz Presents` aos 19 s); legenda bilíngue por volta de 103 s | sem legenda nas janelas usadas, mas **fere a pureza do anime — trocar** |

**Limpas, entram direto:** `twixtor_4k` (GhB1zqpqiLI), `castle_60fps` (uXXyqnoYRlc),
`s4e8_entrance` (Llmr2tEWMyY), `hashiras_vs` (QfoLT-6sQm4), `mansion_exp` (N_7pQX18WQk),
`nezuko_sun` (6J7XW_1zksA), `tanjiro_sun` (1t5mwO5mdbA), `muzan_pack` (eKp_UFOlkVw).

## 5. A auditoria que vale

⭐ **Audite a montagem SEM o `.ass` queimado** (o `temp_video_v*.mp4` intermediário
do render). Ali qualquer texto na tela é contaminação de terceiro — não tem como
confundir com a legenda da música. Auditar o master com a letra queimada é ruído.

Varredura automática a 0,4 s sobre 4 regiões (rodapé + os 3 cantos onde moram logo
e cartela), procurando faixa horizontal de ≥12 linhas com muitas transições fortes.
Depois monte folha de contato só com os quadros suspeitos e **olhe**. No Muzan V4 o
resultado foi **0 ocorrências em 589 quadros**.

Texto japonês nativo da arte (ex.: `燃えた` na animação de mangá, kanji de nome de
Lua Superior) **não é legenda de dublagem** — é arte da fonte e pode ficar. O que sai
é legenda/cartela adicionada por quem subiu o clipe.

## 6. Escrita atômica no script de limpeza

O `limpar_fontes_muzan.sh` grava em `<saida>.tmp.mp4` e só então dá `mv`. Sem isso,
um run interrompido no meio deixa um `.mp4` truncado que o teste `[ -f ]` aceita
como bom na próxima execução — foi exatamente o que aconteceu e gerou uma fonte
de 75 s onde o original tinha 202 s.

## 7. Média temporal — o teste que pega o que a folha a 1 fps não pega *(02/09/2026)*

🔴 **A auditoria a 1 fps deixou passar um `9anime.to`.** No AMV do Gojo, 51 folhas de
contato foram olhadas uma a uma e a marca — pequena, semitransparente, no canto superior
esquerdo do `U2ja8ZLRwrA` — não apareceu em nenhuma.

O que pegou: **somar todos os quadros a 4 fps e olhar uma imagem só por fonte.** Conteúdo
de anime se move e vira borrão; marca fixa, badge de canal, cartela de disclaimer e
legenda queimada ficam no mesmo lugar e sobrevivem nítidas. Na mesma passada apareceram
os créditos de abertura do `CVLgOPflhzM` (74 s+) e do `TKc0VPEwsu8` (11–13 s).

Gere **dois painéis**: a média (a marca aparece como texto fantasma) e o mapa de
estabilidade `255 · (1 − desvio/média_do_desvio)` (texto fixo fica claro sobre fundo escuro).

⚠️ **Acumule em streaming.** A primeira versão carregou todos os quadros num array
float32 e morreu por memória num vídeo de 258 s (1.032 × 960×540×3 → 6,4 GiB). Some
`x` e `x²` quadro a quadro e divida no fim.

⚠️ **Em canto, `crop`, não `delogo`.** No canto o `delogo` só tem duas bordas para
interpolar e borra. Para o `9anime.to`: `crop=1846:1039:74:41,scale=1920:1080`.

A folha a 1 fps **continua necessária** — é ela que diz o que existe em cada segundo para
escolher os planos. As duas são complementares: a folha é conteúdo, a média é marca.

Script: `projetos/imensidao-vazio/media_temporal.py`.

## 8. Mapa de contaminação — projeto `akaza` (auditado 03/09/2026)

**36 fontes baixadas, 11 aprovadas.** O achado que muda a estratégia de busca:

🔴 **Os clipes OFICIAIS foram os piores.** O material da Crunchyroll/Aniplex —
justamente o que parece "fonte boa" — vem com cartela de venda e legenda em inglês
queimada. Trailer de filme carrega promo japonesa por cima da imagem.

| fonte | o que tinha | veredito |
| :--- | :--- | :--- |
| `bLSQgT_So7Y`, `s3kYr2OVoUc` (Infinity Castle, oficiais) | `BUY NOW ON DIGITAL` + Apple TV / Google Play / YouTube / prime video + legenda EN + `©Koyoharu Gotoge…` | descartadas |
| `HFAzgHHITVM`, `Be72PFBKWso` (Crunchyroll) | logo Crunchyroll + `Watch Full Episodes` / `Continue Watching` + `NOW PLAYING EXCLUSIVELY IN THEATRES IN 2025` | descartadas |
| `gkXS7_5GOgc` (VS Trailer oficial) | cartelas `UPPER THREE AKAZA`, `ONLY IN MOVIE THEATRES SEPTEMBER 12` | descartada |
| `tw_WBUeHjhcoCE`, `tw_vfw_AhARHyY`, `tw_O25UfE8I8OI` | `絶賛公開中` (promo JP queimada no trailer) + `NOW SCREEN RECORD THIS` | descartadas |
| `9p3uVC9mexQ` | cartela `FIRE ANIME MERCH 20%-60% OFF / LINK IN DESCRIPTION` + faixa de legenda | descartada |
| `q2uoZxOBfn0` | marca `B EDITS` + `SUBSCRIBE`/`LIKE` + legenda EN | descartada |
| `gvOxWaNWVZ8` | `MUKULWAGHXD` no canto sup. esq. + legenda EN | descartada (há versão limpa da MESMA cena) |
| `I_CpKjEcjt0` | legenda EN no rodapé + `Flashback A` no canto sup. dir. | recuperável por recorte, não foi usada |
| `bs_JhEEkRfQ8cg` "Akaza Backstory" (215 s) | 🔴 **slideshow de painéis de MANGÁ**, não anime | descartada por **pureza** |

⭐ **Quem salvou o clipe foram os packs `twixtor` / `clips for edits`**, que editores
publicam **limpos de propósito**. Aprovadas inteiras: `tw_rQSWOUXsTnE` (123 s),
`tw_dhN-DqTWAE8` (118 s), `tw_IWuavJgh1IA` (88 s), `tw_QxFAz2IGalw` (49 s),
`tw_y3PkkoLkKHA` (61 s), `tw_6XAyyHGuLr0` (183 s — traz o backstory Hakuji/Koyuki
inteiro em 146–182 s), `5ZgAoM7-Bs4` (208 s), `6gACQZ83_1Q`, `Mmjw39tE2HI`,
`WF2gbMxaDik`, `dQa1h6RAVKY`.

**Busque nesta ordem:** `<personagem> twixtor 4k clips for edits` → `<personagem>
scene pack raw clips` → `<personagem> no subtitle no copyright`. Só depois o clipe
oficial.

### Falso positivo que se repete: kanji nativo

A varredura do picture lock deu **3 suspeitos em 449 quadros** e os três eram os
kanji **上弦 / 参** nos olhos do Akaza — arte do próprio anime. Confirma a §5:
**kanji nativo não é legenda de terceiro**. O detector não sabe a diferença; quem
sabe é quem olha o quadro.
