# Lançamento e copy — o que faz o vídeo pegar

*(autor: Claude | 2026-09-01)*

Montar não é publicar, e publicar não é lançar. Este arquivo é a parte do
lançamento: **ordem de subida, texto e leitura de métrica**. A mecânica de
clicar em cada plataforma está em `publicar-tiktok-cdp.md`,
`publicar-instagram-reels.md` e na skill `publicar-canal-mugen`.

Tudo aqui saiu de uma auditoria dos números públicos do canal em
**01/09/2026, 15:52 BRT** — as três faixas que estavam no ar (Hakari, Kashimo,
Muzan), longo e Shorts, lidos do `ytInitialPlayerResponse` de cada vídeo.

---

## 0. O que a auditoria mediu

**Vídeos longos**

| Faixa | No ar desde (UTC) | Idade | Views | Likes | Tags | Descrição |
|---|---|---:|---:|---:|---:|---:|
| Hakari — Febre do Jackpot | 31/08 22:49 | 20h03 | 177 | 14 | 15 | 1.397 car. |
| Kashimo — Deus do Trovão | 01/09 11:48 | 7h04 | 27 | 9 | 16 | 1.421 car. |
| **Muzan — O Progenitor do Sangue** | 01/09 16:59 | **1h53** | **10** | **4** | **0** | **402 car.** |

**Shorts (3 por faixa)**

| Lote | No ar desde | Idade | Views somadas | Views/hora |
|---|---|---:|---:|---:|
| Hakari | 01/09 02:43 | 16h09 | 3.451 | ~214 |
| Kashimo | 01/09 11:49 | 7h03 | 2.694 | ~383 |
| **Muzan** | 01/09 16:09 | **2h42** | 1.278 | **~473** |

### As três conclusões

1. **Os cortes do Muzan não estão fracos.** Em views/hora são o lote mais
   rápido que o canal já teve. O total bruto é menor só porque os do Hakari
   tiveram 6× mais tempo de relógio.
2. **A música não é o problema.** O Muzan tem a maior taxa de like do canal
   (4 em 10 = 40%, contra 33% do Kashimo e 7,9% do Hakari). Quem chega, gosta.
3. **O gargalo é o longo, e é do canal inteiro.** Shorts puxam milhares,
   longos puxam dezenas. Conversão Short→longo: Hakari **5,1%**,
   Kashimo **1,0%**, Muzan **0,8%**.

---

## 1. 🔴 O longo sobe PRIMEIRO. Os cortes vêm depois.

A ordem de subida foi diferente nas três faixas, e a conversão acompanhou:

| Faixa | Ordem | Conversão Short→longo |
|---|---|---:|
| Hakari | longo **4 h antes** dos cortes | **5,1%** |
| Kashimo | longo e cortes juntos (3 min) | 1,0% |
| Muzan | **cortes 50 min antes** do longo | 0,8% |

O corte gasta a primeira hora — a de pico — mandando gente para um vídeo que
**ainda não existe**. Regra: publique o longo, confirme que ele abre pelo
`youtu.be/<ID>`, aplique a capa, **e só então** suba os cortes.

Intervalo recomendado: **2 a 4 h** entre o longo e os cortes. É o único
espaçamento do canal que já produziu conversão de 5%.

> ⚠️ Isso é correlação em 3 lançamentos, não prova. Mas cortes-antes-do-longo
> é indefensável em qualquer leitura: não existe motivo para apontar o
> público para um link que não responde.

---

## 2. Contrato de metadados do vídeo longo

🔴 **Nenhum longo sobe sem os três: título, descrição completa e tags.**

O Muzan foi o primeiro publicado pela ferramenta única e saiu com **0 tags e
402 caracteres** de descrição genérica — sem gancho, sem CTA, sem créditos e
**sem a declaração de IA** que os outros dois têm. Não foi descuido: o
`publicar.py` não tinha o argumento `--tags`. **Agora tem** (01/09/2026).

### Título — o padrão do canal

```
<NOME DA FAIXA EM CAIXA ALTA> | <Personagem> (<Anime>) | Rap Geek / Trap Anime | VX RAPS
```

### Descrição — os 7 blocos obrigatórios

Alvo: **1.300 a 1.500 caracteres**. O modelo é a descrição do Kashimo.

1. **Fala de impacto entre aspas** — é a única linha que o YouTube mostra
   embaixo do título antes do "mais". Sai da própria letra.
2. **Parágrafo do tributo** — personagem, anime, arco, estilo do beat, BPM.
3. **`👇 A LETRA COMPLETA ESTÁ NO COMENTÁRIO FIXADO ABAIXO!`** — só escreva
   se for cumprir (ver §3).
4. **CTA** — like, inscrever, e **"comenta qual o próximo personagem"**
   (pergunta aberta puxa comentário; o canal está com zero).
5. **Créditos da faixa** — letra, faixa, estilo/BPM, mixagem, anime, personagens.
6. **📌 Declaração de IA** — `Sim, este vídeo contém conteúdo gerado ou
   alterado com IA (áudio musical e assistência técnica).` **Nunca omitir.**
7. **Hashtags** — 6 a 8, terminando a descrição.

⚠️ **Não escreva especificação que você não mediu.** A descrição do Muzan diz
"1080p 60FPS" e o arquivo é 30 fps. Tire o dado do `ffprobe`, não do hábito.

### Tags — 12 a 16, nesta ordem de prioridade

```
<Personagem>, <Nome completo>, <Anime>, Rap <Personagem>, Trap <Personagem>,
VX RAPS, Rap Geek, Anime Rap, <Personagem> vs <Rival>, <Arco>,
<Habilidade/bordão>, <Nome da faixa>, Rap Anime 2026, Anime MV, AMV <Personagem>
```

```bash
python3 publicar.py youtube-longo ARQ --titulo "T" --desc "D" \
  --tags "Nezuko,Nezuko Kamado,Demon Slayer,Rap Nezuko,..."
```

> ✅ **Exercitado de verdade em 01/09/2026** no longo da Nezuko
> (`XoS4o5nbcSg`): escreveu as 15 tags certas, conferidas nos chips do Studio.
> Se algum dia imprimir `!! tags NAO escritas`, o envio continua normalmente —
> ponha as tags à mão e **corrija o seletor aqui**. Tag nunca aborta publicação.

### 🔴 O envio não termina sozinho — duas armadilhas que geram rascunho

O longo da Nezuko e os três Shorts dela ficaram **de rascunho** com o arquivo
inteiro já no servidor. Duas causas, as duas silenciosas:

1. **A pergunta de público infantil é obrigatória.** Sem resposta o "Avançar"
   fica **desabilitado** e parece "carregando". O rótulo é
   **"Não é conteúdo para crianças"** — o texto antigo procurava
   `"não, não é conteúdo para crianças"` e nunca achava.
2. **Publicar com o envio em curso salva rascunho calado.** Espere a barra.

E a regra geral, que custou caro: **clicar em "Publicar" não é publicar.**
A prova é a coluna de **visibilidade** dizer "Público" — e Short e longo ficam
em **abas diferentes** do Studio. Eu dei três Shorts como publicados porque a
linha não tinha um botão; os três estavam de rascunho.

Conserto sem reenviar (reenviar cria um **segundo** rascunho):
`publicar.py youtube-publicar-rascunho --titulo-contem "TRECHO"`.

---

## 3. Comentário fixado com a letra

A descrição do Hakari e a do Kashimo prometem a letra no comentário fixado.
**Auditado em 01/09/2026: não existe comentário nenhum em nenhum dos dois** —
seção aberta, zero threads. É promessa quebrada na primeira coisa que o
espectador lê.

Desde 01/09/2026 isso é um subcomando — o longo da Nezuko (`XoS4o5nbcSg`) é o
primeiro do canal com a promessa **cumprida**:

```bash
python3 publicar.py youtube-comentar <ID> --arquivo-texto letra.txt --fixar
python3 publicar.py youtube-fixar <ID>        # se só faltou fixar
```

Pegadinhas embutidas: a seção de comentários só renderiza depois de entrar na
viewport (espere `ytd-comment-thread-renderer`, não o `#comments`); no diálogo
de confirmação, casar "fixar" por prefixo acerta o **título** e não o botão; e
`[role=dialog]` solto pega um diálogo **invisível** ("Você não fez login").
A marca de sucesso é **"Fixado por"** — não "pelo".

Se a letra não couber, publique a primeira estrofe + refrão e a frase
"letra completa nos comentários abaixo". **Ou cumpra, ou tire a linha da
descrição** — as duas coisas resolvem; deixar como está, não.

---

## 4. Capa: o que reprova no card de 210 px

A regra da capa própria continua valendo integralmente
(`publicar-canal-mugen` §Regra 1). O que a auditoria acrescenta é
**luminância**:

- Muzan é o **único** dos três longos com capa própria de verdade — e é o
  mais escuro. No card de 210×118 o personagem vira silhueta e o subtítulo
  em Cinzel fino vermelho-sobre-preto some.
- Hakari e Kashimo estão com **frame cru** (o do Hakari ainda com a legenda
  queimada). O do Hakari é verde saturado com uma frase enorme — é o mais
  visto dos três.

Regra prática: **o ponto focal da capa tem que ser a área mais clara do
quadro.** Rosto claro sobre fundo escuro passa; personagem escuro sobre fundo
escuro não. Se o frame bom for escuro, use o esquema da capa da Nezuko
(`artes_nezuko.py`): fundo borrado e escurecido do próprio frame + o quadro
nítido inteiro encostado à direita — a mesma regra de "enquadra, nunca
recorta" dos cortes verticais, aplicada a foto parada.

> ⚠️ Isso é **hipótese de CTR**, não fato medido: CTR e impressões só existem
> no Studio, e o vídeo tinha 1h53 quando a auditoria rodou. O que é fato é a
> ilegibilidade no card reduzido — essa dá para ver com `previa_card()`.

---

## 5. Copy dos cortes (Shorts, TikTok, Reels)

> 🔴 **Antes da copy, a duração: corte vertical passa de 30 s, sempre**
> (regra do Álvaro, 01/09/2026, em qualquer PC e para todo corpo do Hermes).
> Escolha o trecho por **punchline** — um arco que fecha numa frase forte — e
> estenda o início até passar de 30 s. Os três da Nezuko: 31,8 s / 31,2 s /
> 31,0 s.

Os cortes já performam. A copy existe para **converter** para o longo.

**Título do Short (YouTube):** frase-gancho gritada do próprio verso, em caixa
alta, + emoji + `#Shorts` + `#<Anime>`. É o padrão que já roda e vai bem —
não mexer.

**Descrição/legenda — o que muda:** hoje os cortes do Muzan mandam para
`@VXRaps`, que é o **canal**, não o vídeo. Quem clica cai na home e
tem que caçar. Troque pelo **link direto do vídeo**:

```
<uma linha de contexto do trecho> 🩸

🎬 AMV completo: youtu.be/<ID_DO_LONGO>

#mugenraps #<anime> #<personagem> #rapgeek #animerap #shorts
```

- **YouTube Shorts:** link `youtu.be/<ID>` na descrição.
- **TikTok:** o link não é clicável no post — escreva
  `AMV completo no YouTube: VX RAPS` e mantenha o link na bio.
- **Instagram:** mesma coisa, `link na bio`.

Mantenha as **tarjas de marca** no vídeo (título ciano + `@VXRaps`
amarelo) — é o que sobrevive ao repost sem descrição.

---

## 6. Como ler a métrica — por idade, nunca por total bruto

🔴 **A regra que evita o diagnóstico errado.** Foi exatamente isso que fez o
Muzan parecer um fracasso: 465 views contra 1,2 mil do Hakari, ignorando que
um tinha 2 h e o outro 16 h de vida.

Antes de dizer que um vídeo "não pegou":

1. **Pegue a idade real**, não o "há X horas" arredondado —
   `ytInitialPlayerResponse.microformat.playerMicroformatRenderer.uploadDate`;
2. **Compare na mesma idade.** Sem o Studio, o mais honesto é views/hora, e
   **diga que é uma aproximação**: view de Short é concentrada nas primeiras
   horas, então a média por hora sempre favorece o vídeo mais novo;
3. **Um longo com menos de 24 h não tem diagnóstico.** O Hakari levou 20 h
   para chegar a 177;
4. **Olhe a taxa de like antes de culpar o conteúdo.** Like alto com view
   baixa = problema de distribuição (capa, título, funil), não de música.

---

## 7. Checklist de lançamento

```
[ ] ffprobe no master — duração, fps, resolução (a descrição vai dizer isso)
[ ] true peak ≤ -1.0 dBTP e -10 a -11 LUFS (SKILL.md §4.7)
[ ] capa 1280x720 de frame REAL, personagem conferido em HD
[ ] previa_card(210) — título e personagem legíveis?
[ ] LONGO no ar, público, abrindo por youtu.be/<ID>
[ ] descrição com os 7 blocos (1.300-1.500 car.) e a declaração de IA
[ ] --tags com 12 a 16 tags (confira no Studio se saiu)
[ ] capa aplicada e conferida em i.ytimg.com/vi/<ID>/maxresdefault.jpg
[ ] comentário com a letra publicado E fixado
[ ] --- esperar 2 a 4 h ---
[ ] 3 Shorts com link direto youtu.be/<ID> na descrição
[ ] 3 TikToks + 3 Reels
[ ] publicar.py estado nas 3 plataformas
[ ] arquivar em PUBLICADOS/<NN>_<PERSONAGEM>/
[ ] registrar no Segundo Cérebro (pipeline-amv-geek.md + 06-changelog.md)
```
