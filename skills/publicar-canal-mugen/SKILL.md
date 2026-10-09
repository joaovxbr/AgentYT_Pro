---
name: publicar-canal-mugen
description: "Publica os vídeos do canal VX RAPS — AMV longo no YouTube, Shorts, TikTok e Reels do Instagram — e cria a capa obrigatória de cada vídeo. Use em pedidos como: posta o vídeo do <personagem>, sobe os cortes nas plataformas, faz a capa/thumbnail, retoma o envio que travou, confere o que já está publicado."
---

# Publicar no canal VX RAPS

Motor: **acer**, Chrome com CDP na porta 9222 (perfil `google-chrome-debug`),
já logado em YouTube Studio, TikTok Studio e Instagram.

> **Uma ferramenta só:** `~/Documentos/Video_Studio/ferramentas/publicar.py`.
> Entre 31/08 e 01/09/2026 foram criados **~40 scripts descartáveis** para esta
> mesma tarefa (`post_cdp_safe.py`, `post_bulletproof.py`, `post_c3_fast.py`,
> `postar_shorts_definitivo.py`, `postar_direto_ws.py`…). Cada um refazia a
> conexão CDP e falhava num ponto diferente. **Se algo não funciona, conserte
> `publicar.py`. Não crie outro script.**

```bash
cd ~/Documentos/Video_Studio/ferramentas
python3 publicar.py estado                                   # SEMPRE primeiro
python3 publicar.py youtube-longo  ARQ --titulo T --desc D --tags T1,T2,...
python3 publicar.py youtube-short  ARQ --titulo T --desc D
python3 publicar.py tiktok         ARQ --legenda L
python3 publicar.py instagram      ARQ --legenda L
python3 publicar.py miniatura      VIDEO_ID capa_1280x720.jpg
python3 publicar.py retomar-youtube ARQ --titulo-contem TRECHO
python3 publicar.py instagram-apagar SHORTCODE --confirmo         # irreversível
python3 publicar.py youtube-publicar-rascunho --titulo-contem T   # NÃO reenvia
python3 publicar.py youtube-apagar-rascunhos --titulo-contem T --confirmo
python3 publicar.py youtube-comentar VIDEO_ID --arquivo-texto letra.txt --fixar
python3 publicar.py youtube-fixar   VIDEO_ID
python3 publicar.py tiktok-apagar --legenda-contem T --duplicado --confirmo
```

`cdp.py` (mesma pasta) é o helper de navegador: `nova_aba`, `anexar`,
`avaliar`, `esperar`, `enviar_arquivo`, `digitar`, `clicar_real`, `clicar_texto`.

---

## A outra porta: criar

Esta skill é o que **sai** do estúdio. O que acontece **dentro** dele — capa,
banner, capa quadrada, corte vertical — é a skill **`criar-canal-mugen`**, com
a ferramenta `estudio.py` na mesma pasta. Mesma regra, mesmo motivo.

```bash
python3 estudio.py estado           # o que existe, o que já foi ao ar
python3 estudio.py capa <slug>      # as 3 artes do lançamento
python3 estudio.py corte <slug> --de 63.5 --dur 34.5 --tema "..."
```

Cada faixa tem um manifesto em `projetos/<slug>/projeto.json` — cor, frames,
master, estado de publicação. **Depois de publicar, anote ali**
(`publicado.estado`, `publicado.youtube`): é o que faz o `estudio.py estado`
ser confiável na próxima faixa.

O estúdio inteiro está versionado em `github.com/alvaro209890/mugen-studio`
(privado). Os scripts aposentados dos dois surtos de descartáveis estão em
`Video_Studio/_arquivo_morto/` — **não use nada de lá.**

---

## Regra 00 — vertical: passa de 30 s e sai com copy

🔴 **Corte vertical passa de 30 segundos, SEMPRE** (regra do Álvaro, 01/09/2026,
válida em qualquer PC e para todo corpo do Hermes). Short, Reel e TikTok.
Cortes de 23–28 s foram reprovados e refeitos.

Corte curto não entrega o punchline: o gancho da letra não tem tempo de armar e
pagar. Ao escolher o trecho, procure um arco que **fecha numa frase forte** e
**estenda o início** até passar de 30 s — não corte no meio de um verso só para
caber. `gerar_corte_marcado.py` tem `DURACAO_MINIMA = 30.0` e **recusa**
`dur <= 30`; se reprovar, pegue um trecho maior da letra, **não baixe a
constante**.

> 🔊 O mesmo gerador aplica limiter no áudio (`alimiter` com oversampling 4× +
> AAC 256k) e imprime o true peak do arquivo. Sem isso o corte sai **clipando
> em 0.00 dBTP**: o master já chega perto do teto e o AAC soma overshoot.

---

## Regra 00b — vertical nenhum sai sem copy e hashtags

Short, Reel e TikTok **sempre** levam legenda completa + hashtags + chamada para
`@VXRaps`. Isso não é estilo, é regra do Álvaro — e já foi quebrada
três vezes:

| quando | o que foi ao ar | como |
|---|---|---|
| 31/08 20:26 | TikTok com a legenda `corte_1_febre_inicio_9x16` | o campo do TikTok já vem preenchido com o nome do arquivo e ninguém limpou |
| 01/09 07:26 | TikTok com a legenda **quadruplicada** | `execCommand` token a token reabrindo o autocomplete |
| 01/09 19:48 | Reel do Sukuna **sem legenda nenhuma** | script descartável que pulou a etapa da legenda |

Por isso o `publicar.py` tem um **porteiro de legenda** (`_validar_legenda`)
que roda **antes de abrir o navegador** e recusa a publicação quando a legenda:

- tem menos de 25 caracteres;
- contém o nome cru do arquivo;
- tem menos de 3 hashtags;
- não cita `@VXRaps`.

> 🔴 **O porteiro não se contorna.** Se ele reprovar, escreva uma legenda de
> verdade. Se a ferramenta falhar em outro ponto, **conserte a ferramenta** —
> não escreva outro script. Entre 31/08 e 01/09 nasceram ~40 scripts
> descartáveis para esta mesma tarefa e foi por eles que os três erros da
> tabela acima saíram.

**Abortar é o comportamento certo.** `publicar.py` prefere não publicar a
publicar torto: sem 9:16 confirmado, sem legenda conferida na tela ou com algo
cobrindo o botão, ele para e explica. Isso não é bug para contornar.

---

## Regra 00d — 🔴 o segundo porteiro: a IMAGEM do arquivo *(05/09/2026)*

Desde 05/09/2026 `youtube-longo`, `youtube-short`, `tiktok` e `instagram` chamam também
`_validar_imagem`, que roda `ferramentas/imagem.py` sobre o arquivo **antes de abrir o
navegador**. Regra do Álvaro: *"às vezes são colocadas imagens de telas pretas apenas com
avisos ou até imagens não condizentes"*.

Ele **recusa a publicação** quando o vídeo tem:

- um bloco de **tela morta** (escura e chapada) de **1,0 s ou mais**, ou mais de **1 %** do
  vídeo em tela morta;
- mais de **5 %** quase-morto (no celular isso é tela preta);
- mais de **6 %** congelado (plano parado, cara de slideshow);
- mais de **0,5 s** de página clara sem cor — **line-art de mangá** dentro de um AMV de anime.

O que foi medido no dia em que o porteiro nasceu, nos masters **que já estão no ar**:
`hakari` com **9,8 s de tela morta (6,1 %)** e **39,7 s de página de mangá**; `kashimo`
com 19,3 s de página; `muzan v5` com 18,7 s quase-morto.

```bash
python3 estudio.py imagem <slug>       # o relatório + a folha de contato dos suspeitos
python3 publicar.py youtube-longo ARQ --titulo T --desc D --ignorar-qa   # exceção
```

> 🔴 **`--ignorar-qa` publica e IMPRIME o motivo.** A decisão editorial é do Álvaro, mas a
> exceção fica no log em vez de virar hábito. **Não use para "destravar" o comando** —
> tela preta não se conserta com filtro: o plano tem de mudar, no estúdio.

⚠️ O porteiro **não lê texto**. Cartela de terceiro, marca d'água e legenda de dublagem se
provam com o olho, na folha `projetos/<slug>/qa/imagem_suspeitos.png`.

---


## Regra 00c — a prévia de faixa não publicada *(02/09/2026)*

A **Regra 0** (longo primeiro, cortes 2–4 h depois) vale para **corte de vídeo já no ar**.
A **prévia é outra coisa**: é teaser de faixa que ainda não existe no canal, e sobe sozinha.
Foi assim com o Sukuna (`7MhTqirzwiE`, `Rq_0PpBIYwk`) e com o Gojo.

**Molde do corte:** `gerar_previa_gojo.py` / `gerar_previa_2_sukuna.py` — enquadra o 16:9
inteiro sobre fundo borrado do próprio frame (nunca center-crop) e aplica as duas tarjas
da Regra 00, com **a cor do título trocada pela cor do personagem** amostrada do clipe
(Sukuna `#D20D2F`, Gojo `#00C0C0`).

**Molde da copy** — a prévia **não aponta para `youtu.be/<ID>`** (o longo não existe);
aponta para o handle:

| Plataforma | Padrão |
|---|---|
| YouTube Short | `PRÉVIA: <PERSONAGEM> (<Faixa>) 🌀 Música em Produção! #Shorts #<Anime>` |
| TikTok / Reels | `<GANCHO EM CAIXA ALTA> 🌀 Prévia exclusiva da próxima faixa da VX RAPS: <Personagem> — <Faixa>. Faixa completa em breve no canal: @VXRaps + 7–8 hashtags` |

⚠️ **O `estado` não cobre Instagram.** Depois de `instagram`, confirme lendo
`/mugenraps_oficial/reels/` pelo `cdp.py` e comparando a legenda do reel mais novo — o
"Compartilhar" já deu falso negativo duas vezes com o Reel no ar.

### Prévia do Gojo — no ar em 02/09/2026

`gojo_previa_9x16.mp4` (30 s, janela 50 s–1:20 do master, 20,9 MB):

| Plataforma | Referência |
|---|---|
| YouTube Shorts | `dfyRR3Npi3c` |
| TikTok @mugen_raps | publicado 02/09 11:08 |
| Instagram @mugenraps_oficial | `/reel/DcyayqStb96/` |

## Regra 0 — a ordem do lançamento

⭐ **O vídeo longo sobe PRIMEIRO. Os cortes vêm 2 a 4 h depois.**
*(medido em 01/09/2026 — ver `amv-rap-geek/references/lancamento-e-copy.md`)*

🔴 **Regra de economia de memória/recursos do navegador (01/09/2026):**
Sempre que uma operação de postagem, upload, checagem ou edição em qualquer
plataforma (YouTube Studio, TikTok Studio, Instagram) for concluída ou
encerrada, a aba correspondente **DEVE SER FECHADA IMEDIATAMENTE** no Chrome via
CDP (`/json/close/<targetId>`, que exige **PUT**) para não acumular dezenas de
abas pesadas e saturar a RAM. O `cdp.py` fecha sozinho, no fim da sessão, toda aba que o próprio `publicar.py`
abriu — inclusive quando a execução termina por erro ou retorno antecipado
(corrigido em 05/09/2026; antes disso nenhuma das 14 funções tinha `try/finally`).
Aba obtida por `anexar()` **não** é fechada: ela é de outra tarefa. Se houver upload
em andamento ou rascunho a conferir, marque com `pg.reter("motivo")` e ela sobrevive.

Conversão Short→longo das três faixas auditadas:

| Faixa | Ordem de subida | Conversão |
|---|---|---:|
| Hakari | longo **4 h antes** dos cortes | **5,1%** |
| Kashimo | longo e cortes juntos | 1,0% |
| Muzan | **cortes 50 min antes** do longo | 0,8% |

Corte publicado antes do longo gasta a hora de pico apontando para um vídeo
que ainda não existe. Sequência: **longo → capa → comentário fixado →
esperar → cortes**.

### Contrato de metadados do longo — os três, sempre

🔴 Nenhum longo sobe sem **título no padrão, descrição de 1.300–1.500
caracteres e 12 a 16 tags**.

O Muzan foi o primeiro publicado por esta ferramenta e saiu com **0 tags e
402 caracteres**, sem gancho, sem CTA e **sem a declaração de IA** que os
outros dois têm. A causa não foi descuido: o `publicar.py` não tinha `--tags`.
**Agora tem.** Os 7 blocos obrigatórios da descrição, o formato das tags e o
comentário fixado com a letra estão em
`amv-rap-geek/references/lancamento-e-copy.md`.

⚠️ **Não escreva no texto público especificação que você não mediu.** A
descrição do Muzan diz "1080p 60FPS" e o arquivo é 30 fps. Dado sai do
`ffprobe`.

---

## Regra 1 — todo vídeo do YouTube sai com capa própria

⭐ **Ordem do Álvaro (01/09/2026): não existe vídeo publicado sem capa.**
Publicar e deixar a miniatura automática do YouTube não conta como entregue.

🔴 **A instrução que estava aqui — "copie o `artes_muzan.py` para
`artes_<personagem>.py`" — produziu 8 scripts quase idênticos e foi aposentada
em 03/09/2026.** Não copie script: preencha o manifesto.

```bash
cd ~/Documentos/Video_Studio/ferramentas
python3 estudio.py novo <slug>      # se a faixa ainda não tem manifesto
python3 estudio.py capa <slug>      # as três peças de uma vez
```

Detalhe na skill **`criar-canal-mugen`**. Ele produz três peças:

| Peça | Tamanho | Para quê |
|---|---|---|
| `<slug>_capa_youtube.jpg` | 1280×720 | miniatura do vídeo |
| `<slug>_banner_canal.jpg` | 2560×1440 | banner / arte de divulgação |
| `<slug>_capa_streaming_3000.jpg` | 3000×3000 | capa quadrada de áudio |

### A imagem é do personagem, tirada do próprio vídeo

🔴 **Nada de arte gerada por IA que "pareça" com ele.** O frame sai do MP4.
Ver a memória `logo-do-canal-tambem-passa-por-auditoria-de-marca`.

**E confira QUEM está no frame antes de fechar a arte.** Em 01/09/2026 a
primeira capa do Muzan usou o frame de 86,5 s — cabelo **branco** e olhos
**dourados com kanji**: era uma **Lua Superior**, não o Muzan. O Álvaro pegou.

- Muzan = cabelo escuro ondulado, olhos **vermelhos** de pupila fendida; na era
  Taisho, terno claro e chapéu.
- Olho com kanji dentro **nunca** é o Muzan (é a marcação de Lua Superior).

Como escolher o frame:

```bash
# 1 frame a cada 2 s, pulando a vinheta
ffmpeg -v error -ss 8 -i VIDEO.mp4 -vf "fps=1/2,scale=480:-1" -q:v 3 f_%03d.jpg
# folhas de contato (o acer NÃO tem ImageMagick; tile do ffmpeg exige -update 1)
ffmpeg -v error -start_number 1 -i "f_%03d.jpg" -frames:v 1 \
  -vf "scale=300:-1,tile=6x5" -update 1 -q:v 3 folha_0.jpg
```

Copie as folhas para o Windows e **olhe** com a tool Read. Escolha um frame
**sem legenda queimada** — ou corte a faixa da legenda na origem
(`src.crop((0, 150, w, h))`); tentar tirar via `foco_y` não funciona, porque o
zoom encolhe a folga junto e a faixa volta.

### O que o card do YouTube exige

- **1280×720 exatos**, JPG < 2 MB. Outro tamanho o Studio reescala e borra.
- **Margem segura de 80 px** nos quatro lados — as bordas somem no card do
  celular, na sugestão lateral e na tela final.
- **Canto inferior direito é do selo de duração** — não ponha texto ali.
- 🔴 **O ponto focal tem que ser a área mais CLARA do quadro.** Personagem
  escuro sobre fundo escuro vira silhueta no card — foi o que aconteceu com a
  capa do Muzan, a única capa própria dos três longos e a mais escura das
  três. Rosto claro sobre fundo escuro passa. Se o frame bom for escuro, use o
  esquema de `artes_nezuko.py`: fundo borrado e escurecido do próprio frame +
  o quadro nítido inteiro encostado à direita ("enquadra, nunca recorta"
  aplicado a foto parada), em vez de só `cobrir()` com zoom — num frame de
  retrato o zoom que empurra a figura para o lado também a decapita.
- O card menor tem **210×118 px**. Título abaixo de ~72 px (em 1280) vira
  borrão. Rode `previa_card()` e **olhe a prévia reduzida** antes de subir.
- Composição que funciona: **personagem de um lado, coluna de texto do outro**,
  com uma faixa escura (scrim) por baixo do texto. Texto centralizado por cima
  da figura sempre fica ilegível.

### Tipografia e cor

- Título em **Cinzel** caixa alta (mesma família das legendas do AMV).
- Subtítulos em **Bebas Neue**. Fontes em `~/.local/share/fonts/`.
- A palavra de destaque sai **na cor do personagem, amostrada do próprio
  clipe** — não chute. Muzan deu `#E00000`:

```bash
python3 -c "
import subprocess, collections
c=collections.Counter()
for t in ('40','78.5','128.5'):
    raw=subprocess.run(['ffmpeg','-y','-ss',t,'-i','VIDEO.mp4','-frames:v','1',
      '-vf','scale=160:90','-f','rawvideo','-pix_fmt','rgb24','-'],
      capture_output=True).stdout
    for i in range(0,len(raw),3):
        r,g,b=raw[i],raw[i+1],raw[i+2]
        if r>120 and r>g+60 and r>b+60: c[(r//16*16,g//16*16,b//16*16)]+=1
print(['#%02X%02X%02X'%k for k,_ in c.most_common(3)])"
```

Aplique com `publicar.py miniatura <VIDEO_ID> <capa.jpg>` e **confirme baixando
a imagem do CDN** — `https://i.ytimg.com/vi/<VIDEO_ID>/maxresdefault.jpg`.

---

## Regra 2 — conferir antes, sempre

`publicar.py estado` lê YouTube (longos e Shorts) e TikTok e marca cada linha
como `PUBLICADO` ou `!! PENDENTE !!`. Rode antes de qualquer publicação: já
aconteceu de o Hermes tentar republicar o que já estava no ar.

Uma linha do YouTube **sem `id` e sem duração** não é vídeo publicado — é
rascunho com envio interrompido (veja abaixo).

---

## Envio interrompido no YouTube (o que travou em 01/09/2026)

Sintoma: a linha aparece no Studio com título e descrição certos, mas **sem
duração e sem link**, e o texto da linha diz:

> «Envio interrompido — Clique em "Retomar o envio" e selecione
> `<arquivo>.mp4` para continuar o processo»

**Subir o arquivo de novo cria um segundo rascunho e não resolve.** O YouTube
guarda o rascunho e quer o **mesmo arquivo** de volta:

```bash
python3 publicar.py retomar-youtube \
  ~/Documentos/Video_Studio/saidas/<arquivo>.mp4 --titulo-contem "TRECHO DO TÍTULO"
```

Isso clica em "Retomar o envio" e injeta o arquivo por
`DOM.setFileInputFiles` — **o seletor de arquivos do sistema não abre por
automação**, então é sempre por injeção, nunca por clique no botão de procurar.

**Por que o Hermes não conseguiu:** não foi o vídeo. Foi a pilha de modelos
caindo toda junta às 13:23–13:27 — `custom` (9router do server) recusando
conexão, `ninerouter` em 403, `opencode-go` em 429 (limite mensal), `groq` em
413 (TPM 8000 contra 46 mil pedidos) — e aí a compressão de contexto também
falhou: *"413 payload too large. Cannot compress further."* A sessão morreu no
meio do upload. Se der isso de novo: cheque `~/.hermes/logs/agent.log`, não o
vídeo.

---

## Pegadinhas de cada plataforma

### YouTube Studio
- Não use `?d=ud` na URL para **ler** a lista: esse parâmetro abre o diálogo de
  upload e esconde as linhas (a lista parece vazia).
- Linha publicada tem `a[href*="/video/"]` e duração; rascunho não tem nenhum.
- **Apagar rascunho travado:**
  `publicar.py youtube-apagar-rascunhos --titulo-contem TRECHO --confirmo`.
  A trava contra apagar vídeo no ar é estrutural: a rotina só age em linha
  **sem** `a[href*="/video/"]` **e** com o botão `aria-label="Excluir vídeo"` —
  linha publicada não expõe esse botão.
- No diálogo *"Excluir permanentemente este vídeo rascunho?"* o botão
  **"Excluir vídeo rascunho" nasce desabilitado** até marcar *"Estou ciente..."*.
  Duas armadilhas, as duas já vividas em 01/09/2026 (12 voltas em falso):
  1. varrer shadow DOM acha **a mesma caixa por dois caminhos** — clicar nas
     duas ocorrências marca e **desmarca**. Marque uma só, escopada no diálogo
     cujo texto contém "rascunho";
  2. `el.click()` de JS na `ytcp-checkbox-lit` muda o `aria-checked` mas **não
     habilita o botão** — o componente quer gesto real (`Input.dispatchMouseEvent`).
  Depois de marcar, **espere o botão habilitar** antes de clicar; se não
  habilitar, pare em vez de repetir a volta.

### 🔴 Por que um vídeo fica de rascunho (as duas causas reais)

Medido em 01/09/2026 no lançamento da Nezuko — o longo e os três Shorts ficaram
de rascunho, e eu cheguei a **reportar os três Shorts como publicados**.

1. **A pergunta de público infantil é obrigatória e trava o wizard.** Sem
   resposta, o botão **"Avançar" fica desabilitado** — e o sintoma parece
   "carregando". O rótulo real é **"Não é conteúdo para crianças"**; procurar
   por `"não, não é conteúdo para crianças"` (como era até 01/09) **não acha**.
2. **Clicar em "Publicar" com o envio em curso salva rascunho em silêncio.**
   Espere a barra terminar (`_esperar_upload`) antes de publicar.

E a regra que fecha as duas:

> **Clicar em "Publicar" não é publicar.** A prova é a **coluna de
> visibilidade** dizer "Público". A ausência de um botão na linha **não é
> prova de sucesso** — foi assim que dei três rascunhos como publicados.
> ⚠️ Short e longo ficam em **abas diferentes** (`videos/short` e
> `videos/upload`): procurar só numa faz a ferramenta dizer "não achei" para um
> rascunho que existe.

Para consertar sem reenviar (reenviar cria um **segundo** rascunho):

```bash
python3 publicar.py youtube-publicar-rascunho --titulo-contem "TRECHO"
```

### Comentário fixado e capa

- `youtube-comentar VIDEO_ID --arquivo-texto letra.txt --fixar` publica e fixa.
  ⚠️ A seção de comentários só **renderiza** depois de entrar na viewport:
  espere `ytd-comment-thread-renderer`, não o `#comments`.
- No diálogo de fixar, `clicar_texto("fixar")` acerta o **título**
  ("Fixar este comentário no topo?"), não o botão; e `[role=dialog]` solto pega
  um diálogo **invisível** ("Você não fez login"). Escope por diálogo visível e
  case o texto exato. A marca de sucesso é **"Fixado por"** (não "pelo").

### TikTok Studio
- Publicação duplicada se apaga com
  `tiktok-apagar --legenda-contem T --duplicado --confirmo` (exige 2+ iguais e
  remove só a mais recente). O TikTok guarda por **30 dias** na Central de
  Atividades, então dá para restaurar.
- O submit é **`[data-e2e="post_video_button"]`** e fica **desabilitado** até o
  upload terminar. Clicar por texto "Publicar" acerta **"Publicações"** da barra
  lateral e não faz nada.
- `el.click()` de JS **não** submete — o botão exige gesto confiável. Use
  `pg.clicar_real(...)` (`Input.dispatchMouseEvent`).
- Depois do clique abre o modal **"Continuar publicando?"** (verificação de
  direitos autorais incompleta). Enquanto ele está aberto, um
  `DIV.TUXModal-overlay` cobre a página e **todo clique cai no overlay**.
  Confirme em "Publicar agora".
- A legenda é DraftJS e **já vem preenchida com o nome do arquivo** — limpe.
- Para escrever a legenda use **`Input.insertText`**. O que não funciona:
  - `execCommand('insertText')` token a token → o autocomplete de `@`/`#`
    reinsere a menção (`@VXRaps@VXRaps`); foi assim que a
    legenda do post das 07:26 de 01/09 saiu **quadruplicada**;
  - `ClipboardEvent('paste')` sintético → o DraftJS engole o começo (colou 98
    de 207 caracteres).
  - Sempre **releia a legenda do editor e compare o tamanho** antes de publicar.
- Confirmação real = a URL virar `/tiktokstudio/content`.

### Instagram web
- O menu lateral **não tem texto clicável "Criar"**: o alvo é
  `svg[aria-label="Novo post"]`, com **clique de mouse real**.
- O `input[type=file]` só existe **depois** de clicar em "Postar".
- Wizard: `Cortar → Avançar` · `Editar → Avançar` · `Novo reel` (legenda) ·
  `Compartilhar`.
- Ao clicar em vários candidatos com o mesmo texto, pegue o **último**
  (o mais interno é o clicável de verdade).
- **"Compartilhar" não muda `document.body.innerText`** — o feed fica atrás do
  modal. Confirme pelo texto "compartilhado" **dentro** do `div[role=dialog]`
  ou olhando `/mugenraps_oficial/reels/`. Já deu falso negativo com o post no ar.
- **Proporção (etapa Cortar).** Meça o `<video>` **escopado em
  `div[role=dialog]`** — `document.querySelector('video')` pega o vídeo do
  *feed* atrás do modal (já mediu 4:3). Alvo: `~0.5625`. Se já estiver certo,
  **não toque no `Selecionar corte`**: abrir o popover à toa deixa ele por cima
  do "Avançar" e o wizard trava na etapa Cortar para sempre.
- **Avisos por cima do wizard.** Desde 01/09/2026 o Instagram exibe
  *"Agora os posts de vídeo são compartilhados como reels"* com um botão **OK**
  sobre a etapa Cortar. Enquanto ele está na tela o "Avançar" não anda — e o
  sintoma é justamente esse: cliques que "funcionam" e uma tela que não muda.
  Feche todo aviso (`OK` / `Continuar` / `Entendi` / `Agora não`) antes e a cada
  volta do wizard.
- **A sugestão de hashtag cobre o "Compartilhar".** A legenda termina em `#algo`
  e a lista de sugestões abre por cima do botão. Não tente descobrir isso lendo
  o texto da página (regex em `innerText` dá falso negativo — foi o que deixou o
  Reel do Sukuna preso no modal em 01/09 23:0x). Pergunte **quem está no ponto
  do botão**:

```js
alvo.scrollIntoView({block: 'center'});          // sem isto, ver abaixo
const r = alvo.getBoundingClientRect();
const topo = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
const livre = alvo === topo || alvo.contains(topo) || topo.contains(alvo);
```

  ⚠️ `elementFromPoint` devolve **null** para pontos fora da viewport. Sem o
  `scrollIntoView` você lê *"coberto por nada"* num botão que não tem nada em
  cima — aconteceu com o botão do TikTok, que fica abaixo da dobra.
- **Apagar um Reel:** `publicar.py instagram-apagar <shortcode|url> --confirmo`.
  É irreversível e sem o `--confirmo` a ferramenta se recusa.

---

## Depois de publicar

1. **Publique e fixe o comentário com a letra.** As descrições do Hakari e do
   Kashimo prometem "A LETRA COMPLETA ESTÁ NO COMENTÁRIO FIXADO ABAIXO" e
   auditoria de 01/09/2026 mostrou que **não existe comentário em nenhum dos
   dois**. Ou cumpra, ou tire a linha da descrição.
2. Copie os arquivos para
   `~/Documentos/Video_Studio/PUBLICADOS/<NN>_<PERSONAGEM>/` nas pastas
   `amv_youtube_master/`, `shorts_youtube/`, `cortes_tiktok/`,
   `reels_instagram/`, `artes_capas/`.
3. Rode `publicar.py estado` e confira as três plataformas.
4. Registre no Segundo Cérebro (`02-projetos/pipeline-amv-geek.md`) e no
   `06-changelog.md`.

## Contas

| Plataforma | Conta |
|---|---|
| YouTube | VX RAPS — canal `UC3L86WQn5VmHoSvRtvvUhoQ` |
| TikTok | `@mugen_raps` |
| Instagram | `@mugenraps_oficial` |

**Publicar é ação pública e irreversível: só com pedido explícito do Álvaro.**

---

## Como ler a métrica antes de dizer que "não pegou"

🔴 Compare **na mesma idade**, nunca por total bruto. Em 01/09/2026 os cortes
do Muzan pareciam um fracasso (465 views contra 1,2 mil do Hakari) e eram o
lote **mais rápido** que o canal já teve — o do Hakari só tinha 6× mais tempo
de relógio. Idade real sai de
`ytInitialPlayerResponse.microformat.playerMicroformatRenderer.uploadDate`.

Longo com menos de 24 h **não tem diagnóstico**. E antes de culpar o
conteúdo, olhe a taxa de like: like alto com view baixa é problema de
distribuição, não de música. Detalhe em
`amv-rap-geek/references/lancamento-e-copy.md` §6.
