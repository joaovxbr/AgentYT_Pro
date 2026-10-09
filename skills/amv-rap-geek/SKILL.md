---
name: amv-rap-geek
description: "Crie AMVs de rap geek com narrativa e beat precisos."
version: 2.3.0
author: Álvaro (alvaro209890), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [anime, amv, rap-geek, beat-sync, ffmpeg]
    related_skills: [anime-amv-edit]
---

# amv-rap-geek

Guia executável para criação e montagem de videoclipes musicais e AMVs de Rap Geek (estilo RM Raps / VX RAPS) a partir de áudio, transcrição e clipes brutos de anime.

## 1. Estrutura do Projeto

Todo projeto deve residir em `/home/acer/Documentos/Video_Studio/projetos/<slug>/`:
```
projetos/<slug>/
├── audio/<slug>.mp3             # Áudio oficial da música
├── raw/                         # Clipes brutos baixados via yt-dlp (1080p/4K twixtor/animation)
├── cortes/                      # Cenas cortadas e normalizadas
├── legendas/                    # Arquivo .ass de legendas cinematográficas
├── transcricao.json             # Alinhamento Faster-Whisper (palavra por palavra)
└── PROMPT_CODEX_CRIACAO_AMV.md  # Especificação narrativa e de cortes
```

## 2. Regras de Ouro da Produção

1. **Pureza Total do Universo:** Exclusividade aos personagens e cenas canônicas do anime do tributo.
   ⚠️ **Nome de arquivo e título do vídeo não são prova.** Fontes que se anunciam como clipe do
   anime podem ser animação vetorial de fã (`wWi5gVmXfmY` = "Guii Animz Presents") ou compilação
   com outros animes. Audite frame a frame — 1 fps em folha de contato — antes de montar.
2. 🔴 **Zero Marcas d'Água E Zero Legenda de Dublagem:** nenhum clipe sai com marca de canal
   nem com legenda de dublagem de terceiro — só ficam as legendas da MÚSICA (o `.ass`).
   A fonte sai limpa **antes** de entrar na montagem. **Três técnicas, uma só não resolve:**
   - logo pequeno e fixo → `delogo=x=:y=:w=:h=`
   - marca sobre line-art de mangá → `curves=all=0/0 0.60/0.60 0.803/1 1/1` (ponto branco)
   - **legenda de dublagem no rodapé → recorte 16:9 acima dela + zoom** (`crop=1546:870:<x>:0,scale=1920:1080`).
     ⭐ O topo do texto de legenda ficou em **y=885** nas 3 fontes de anime auditadas — comece por aí.
     **Nunca `delogo` em legenda:** a caixa larga deixa borrão horizontal atravessado, pior que a legenda.
   - **texto grande espalhado no quadro (fan-edit) → não tem filtro: RETIMAR o corte** para uma janela limpa.
   Registre as janelas limpas por fonte num dict `JANELAS_LIMPAS` e faça o validador do render
   barrar qualquer corte fora delas **antes** de gastar CPU.
   📄 Receita completa, como medir a linha de corte e o mapa de contaminação das fontes já
   auditadas: `references/limpeza-fontes.md`.

   🔴 **De onde vem fonte limpa — o oposto do que parece** *(Akaza, 03/09/2026)*.
   Das 36 fontes baixadas, **11 passaram**. Os clipes **OFICIAIS foram os piores**:
   o material Crunchyroll/Aniplex vem com `BUY NOW ON DIGITAL`, logos de Apple TV /
   Google Play / prime video, `Watch Full Episodes` e **legenda em inglês queimada**.
   Trailer de filme carrega `絶賛公開中` e `NOW PLAYING… IN THEATRES IN 2025`.
   **Quem salva o clipe são os packs `twixtor` / `clips for edits`** que editores
   publicam limpos de propósito — procure por eles primeiro. E confira a pureza:
   "Akaza Backstory" (`bs_JhEEkRfQ8cg`, 215 s) era **slideshow de painéis de mangá**,
   não anime.
3. **Todo corte novo leva as tarjas de marca.** 🔴 Regra do Álvaro (01/09/2026), no
   padrão dos cortes do Hakari. **Os já postados não são refeitos** — vale de agora em diante.

   | Elemento | Especificação |
   |---|---|
   | Tarja de cima | `drawbox=x=0:y=180:w=1080:h=180:color=black@0.75:t=fill` |
   | Título | ciano `#00ffcc`, `fontsize=48`, `y=210` — ex. `VX RAPS - FEBRE DO JACKPOT` |
   | Subtítulo | branco `#ffffff`, `fontsize=36`, `y=280` — ex. `KINJI HAKARI (JUJUTSU KAISEN)` |
   | Tarja de baixo | `drawbox=x=0:y=1540:w=1080:h=150:color=black@0.75:t=fill` |
   | Assinatura | amarelo `#ffcc00`, `fontsize=34`, `y=1595` — `@VXRaps` |

   Tudo centralizado (`x=(w-text_w)/2`) com sombra. ⚠️ **Sem emoji nesses textos** — a fonte
   do `drawtext` não desenha e vira quadradinho. Gerador pronto:
   `~/Documentos/Video_Studio/assets/tiktok/gerar_corte_marcado.py`.

4. **Corte vertical (9:16): ENQUADRA, nunca RECORTA.** 🔴 Regra do Álvaro (01/09/2026),
   vale para **TikTok, Reels e Shorts do YouTube**. O frame 16:9 **inteiro** entra centralizado
   sobre um fundo borrado do próprio frame — nunca `crop` no primeiro plano:

   ```
   [0:v]split=2[bg][fg];
   [bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,
       gblur=sigma=35:steps=3,eq=brightness=-0.15[bgb];
   [fg]scale=1080:-2,eq=contrast=1.08:saturation=1.15:brightness=0.02,
       unsharp=5:5:0.8:5:5:0.0[fgs];
   [bgb][fgs]overlay=(W-w)/2:(H-h)/2
   ```

   `scale=1080:-2` (não `-1`): altura par, senão o x264 recusa. Center-crop **decepa o rosto e
   corta as pontas da legenda** — foi exatamente o que aconteceu nos cortes do Kashimo de
   01/09 08:03, que tiveram de ser refeitos. **Confira um frame antes de publicar.**
   Receita canônica: `~/Documentos/Video_Studio/tiktok_cortes/gerar_cortes_antidetect.py`.

   **Publicar o corte:** 📄 `references/publicar-tiktok-cdp.md` — o CDP por one-liner de shell
   travou o Hermes por 1 h em 01/09/2026 (aspas comidas no aninhamento shell→Python→JS) e
   já pôs **dois posts no ar com o nome do arquivo como legenda**. Scripts que funcionam:
   `~/Documentos/Video_Studio/assets/tiktok/` — `postar_tiktok.py <n>` faz **ensaio**
   (sobe, escreve a legenda, tira print e para); com `--publicar` é que clica.

   **Instagram Reels:** 📄 `references/publicar-instagram-reels.md`. Fluxo
   `Criar → Postar → arquivo → Cortar → Avançar ×2 → legenda → Compartilhar`, scripts em
   `~/Documentos/Video_Studio/assets/instagram/`. 🔴 A etapa **Cortar** abre recortada —
   escolha **9:16** no ícone `Selecionar corte` e **confirme medindo o `<video>`**
   (≈ 0,5613), escopando a busca em `div[role="dialog"]`: `document.querySelector('video')`
   pega vídeo **do feed atrás do modal**. Validado com 6 Reels em 01/09/2026.

4. **Vinheta Oficial v2 — obrigatória em vídeo longo, proibida em corte (0.0s a 4.0s):**
   - Arquivo Oficial: `/home/acer/Documentos/Video_Studio/assets/intro/intro_mugen_v2_169_mudo.mp4`.
   - 🔴 **A v1 está aposentada.** `nova_intro_mugen_oficial.mp4` e `intro_canal.mov` **não podem
     mais ser usados**: o emblema central deles era o **logo do BTS** (marca registrada da HYBE),
     herdado de arte gerada por IA. A v2 traz um **torii** original no lugar.
   - 🚫 **Vídeo já publicado fica com a v1.** Decisão do Álvaro (01/09/2026): nada que já
     está no ar é reenviado, substituído ou tem a abertura trocada — nem Muzan, nem Nezuko,
     nem Hakari, nem Kashimo. Republicar custa views, comentários e ranqueamento de um vídeo
     que já performa, e 4 s de abertura não pagam esse preço. **A v2 vale da próxima faixa em
     diante.** O canal conviver com as duas vinhetas é **esperado** — não "corrija" isso.
   - ⭐ **Só vídeo longo (16:9) leva vinheta.** Short, Reel, TikTok e qualquer corte vertical
     entram **direto no conteúdo** — 4 s de marca queimam a retenção justamente onde ela decide
     se o vídeo vive. Se o Álvaro pedir marca no vertical, use o corte de 1,5 s
     `intro_mugen_v2_916_curta_mudo.mp4`.
   - Vídeo mutado na abertura com a música tocando desde o segundo `0.00s`.
   - Corte seco para a animação principal no segundo `4.00s`.
   - Variantes em `assets/intro/`: `169`/`916`, cada uma em `4.0s` e `curta` (1,5 s), cada uma com
     par `_mudo`. Regerar tudo: `assets/intro/scripts/build.sh`.
4. **Abertura Curta, mas com Espaço Narrativo:**
   - Diferencie **fala/monólogo de abertura** da **primeira estrofe cantada**. Preserve uma fala
     icônica e o título quando eles sustentarem a narrativa; a letra não precisa começar logo aos 4 s.
   - Como referência, faça a primeira estrofe cantada entrar em até cerca de **20 s depois da
     vinheta de 4 s**. Esse valor é uma preferência editorial, não uma obrigação para músicas cuja
     construção musical peça outro tempo.
   - 🔴 **Às vezes NÃO se corta a intro** *(Akaza, 03/09/2026)*. Antes de tirar qualquer coisa
     do começo, veja onde cai a **primeira voz em relação aos 4 s da vinheta MUDA**. No Akaza
     a voz entrava em 6,32 s: remover um período do loop (3,0 s) a jogaria para 3,3 s, **dentro
     da cartela** — letra ouvida sem imagem e legenda por cima da vinheta. O corte saiu do
     instrumental **depois** do gancho (12,77 s disponíveis), e a 1ª estrofe caiu para 20,1 s
     pós-vinheta, batendo a preferência editorial. **O "só hit" que dá para cortar nem sempre
     é o do começo.**
   - Encurte somente silêncio, sintetizador ou beat repetitivo sem nova informação. A emenda deve
     remover um número inteiro de beats/compassos e ser refinada em zero crossing ou microcrossfade,
     sem cortar a cauda da última palavra nem o ataque da próxima.
   - Nunca altere só o áudio. Registre um **mapa de tempo por trechos** e aplique a mesma transformação
     ao áudio, `.ass`, plano visual, referências do Whisper e relatórios de QA. Veja
     `references/sincronia-musical.md`.
5. **Legendas Cinematográficas (.ass):**
   - Fonte: `Cinzel` (romana clássica, CAIXA ALTA, branca).
     ⚠️ **A V5 do Akaza voltou para Impact sem que ninguém percebesse.** Impact é o estilo
     ANTIGO. Confira a fonte de todo `.ass` que você não gerou antes de renderizar.
   - Destaque cinético em palavra-chave com a cor do personagem (ex: Ciano/Ouro para Kashimo, Carmesim `&H001515E8&` para Muzan, Verde Neon `&H00A0F000&` para Hakari).
   - ⭐ **A cor da aura precisa de um plano B — a aura também está no fundo.** *(Akaza V6,
     03/09/2026)* A Agulha de Compasso do Akaza **é ciano e ocupa a tela inteira**: palavra
     ciano ali some. Meça, na faixa onde a legenda vai cair, a fração de pixel da cor da
     aura e a luz média; se `aura > 0,18` ou (`luz > 150` e `aura > 0,08`), troque para uma
     **segunda cor do próprio personagem** (no Akaza, o ouro dos olhos de Lua Superior Três).
     Amostre as duas dos clipes: aura `#68C8F8`, ouro `#F6BA06`. 7 das 51 linhas caíram na
     regra — todas as da bússola. **A V5 alternava ouro e ciano sem critério nenhum.**
   - ⭐ **A POSIÇÃO se mede, cena a cena — não é tudo no rodapé.** Leia o picture lock a 4
     quadros/s em 320×180, calcule a energia de detalhe (soma dos gradientes) em faixas
     candidatas (topo, superior-esq/dir, centro, rodapé, rodapé-esq/dir) e escolha a faixa
     livre na janela de cada linha. No Akaza duas linhas estavam num rodapé com **detalhe 40**
     contra **3,8** no topo. Regras: o rodapé é o padrão e só se sai dele se estiver mesmo
     ocupado (detalhe > 13, ou 1,6× pior que a melhor com diferença > 4); 🔴 **se o rodapé já
     É a melhor faixa, "estar cheio" não é motivo para sair**; histerese para não pular de
     posição a cada verso; e reforce o `ord` de 3,8 para 5,2 quando a faixa tiver `luz > 150`.
   - 🔴 **`WrapStyle 2` não quebra linha: linha larga demais é CORTADA sem aviso.** Estime a
     largura (`nº de caracteres × (corpo × 0,62 + fsp)`) contra os 1740 px úteis e **encolha o
     corpo até caber**. Perder texto é pior que perder 4 % de corpo.
   - Fade suave de linha inteira sem varredura de karaokê.
   - 🔴 **UMA LINHA VISÍVEL = UM ONSET PRÓPRIO. Nunca um relógio para duas falas.**
     *(medido em 04/09/2026 — era esta a causa do "a legenda sempre fica dessincronizada")*

     Até aqui a letra era digitada como uma tupla por **dupleto**
     (`(início, fim, estilo, "LINHA A\\NLINHA B")`), e o gerador quebrava o `\N`
     em dois eventos empilhados dando ao de baixo **o tempo do de cima + 90 ms**.
     Só que as duas metades **não são cantadas juntas** — a de baixo entra 1 a 2
     segundos depois. Resultado medido contra o onset de palavra do Whisper:

     | faixa | 1ª linha do grupo | 2ª linha (empilhada) | eventos que são 2ª metade |
     |---|---|---|---|
     | Rengoku V2 | −0,120 s | *não usa dupleto* | **0 %** |
     | Akaza V6 | +0,255 s | **+1,225 s** (p90 +1,675) | 45 % |
     | Mahoraga v2 | +0,250 s | **+1,000 s** (p90 +2,110) | 45 % |
     | Imensidão v1 | −0,056 s | **+1,544 s** (p90 +2,144) | 50 % |

     Ou seja: **metade das legendas do canal aparecia 1–2 s antes de ser cantada**,
     e a correlação é perfeita — o Rengoku, que escreve **uma linha por evento**,
     é o único aprovado. Não era deriva de áudio, nem o corte da intro, nem o
     `.ass` "perdendo o sincronismo".

     O dado que resolve **já existia em todo projeto** e era usado só para acender
     a palavra-chave: `palavras_vocal.json`. Ele é o relógio de TODA linha.

     ```bash
     cd ~/Documentos/Video_Studio/ferramentas
     python3 estudio.py sincronia   <slug>   # porteiro: mede e REPROVA
     python3 estudio.py sincronizar <slug>   # reescreve SÓ os tempos do .ass
     ```
     O `sincronizar` preserva estilo, posição, cor e animação de entrada, e faz o
     pulso `\t(...)` da palavra-chave andar junto com o evento. Dupleto continua
     empilhado na tela: a de cima **estende o fim** até o fim da de baixo, e a de
     baixo **entra no tempo dela**. O visual do canal não muda; o relógio sim.

     ⚠️ Linha que o ASR não ouviu sai com tempo **interpolado** entre as vizinhas e
     é listada no relatório — confira essas à mão. E a regra do Álvaro continua de
     pé: [linha sem confirmação dupla não vira legenda](#31).

     🔴 **ESCREVER A RECEITA NÃO CONSERTA A FAIXA** *(medido em 05/09/2026)*. Esta
     seção foi escrita em 04/09 às 21:48 e no dia seguinte o `sincronia` **reprovava
     todas as faixas** — o `sincronizar` nunca tinha sido rodado em nenhuma. Consertadas
     em 05/09 (akaza, imensidão, mahoraga, rengoku, sukuna, toji: p90 de até 1,654 s
     para **≤ 0,005 s**), cada uma **no lugar**, com o original em `<nome>.ass.bak-dessincronizado-<data>`. ⚠️ **O `.ass`
     consertado só vale depois de um render novo** — o master no ar tem o antigo
     queimado. Rode o porteiro **antes** de renderizar, não depois de entregar.

     ⚠️ **O Álvaro chama isto de "legenda atrasada"; medido, é ADIANTADA.** Não
     "corrija" na direção que o relato sugere. Confirmado por três caminhos no Akaza
     V6: onset de palavra do ASR **+0,635 s**, energia do stem de voz do Demucs (sem
     ASR) **+0,390 s**, e o quadro entregue aos **24,30 s** mostrando `LUA SUPERIOR
     TRÊS` enquanto se canta *"Olhe nos meus olhos"* (a palavra `três` só cai em
     25,57 s). ⭐ **Por que parece atraso:** no dupleto as duas linhas entram juntas,
     então quem olha vê **a próxima frase já escrita** e **não vê a que está
     ouvindo**. A frase atual "não chegou" — sensação de atraso, mecanismo de
     adiantamento.
   - 🔴 **Desvio mediano acima de 3 s não é dessincronia: são arquivos de cortes
     DIFERENTES.** O porteiro recusa e manda achar a transcrição certa. Foi o caso
     do Muzan (`muzan_cinema_trimmed.ass` × `transcricao.json` do corte antigo,
     +15,6 s). Reparar ali produziria lixo com cara de conserto.
   - 🔴 **Três armadilhas do próprio `legenda.py`, consertadas em 05/09/2026 — não
     as reintroduza ao mexer nele:**
     1. **Desenho vetorial não é letra.** O filete das cartelas é um `Dialogue` com
        `\p1` e corpo `m 0 0 l 420 0 l 420 3 l 0 3`. Ele entrava no alinhamento
        (os tokens `M 0 0 L 420 …` disputando palavra com o ASR) e o `reparar` lhe
        dava tempo **interpolado**, **soltando o filete da cartela que ele
        sublinha**. Desenho não tem onset: é **seguidor** da fala que mais se
        sobrepõe a ele.
     2. **Refrão repetido ancora na repetição errada.** A DP é monótona e isso **não**
        protege: no Rengoku, `SOB A FUMAÇA…` casou a **+21,3 s** e `DUZENTAS VIDAS…`
        a **+22,6 s**, na 2ª passagem do refrão, porque o trecho à volta não ancorou.
        Sem o descarte por mediana/MAD o `sincronizar` **gravaria** esses tempos.
     3. **O porteiro fica cego em silêncio.** Com 4 nomes de relógio na lista, 5 dos
        13 projetos respondiam `palavras=NAO ACHEI` e o QA simplesmente não
        acontecia. Relógio se escolhe **medindo** o `.ass` contra todos os
        candidatos, nunca pelo nome do arquivo.
   - O timestamp acompanha a **voz**. O corte visual pode ser aproximado do kick/ataque mais próximo
     sem deslocar a legenda junto.
6. **Corte Narrativo Canônico e Específico (1:1):**
   - As imagens não podem ser apenas conceituais ou genéricas: devem refletir a cena/evento específico mencionado no verso (ex: se fala das Luas Inferiores, usar o massacre do Ep 26; se fala de Yoriichi, usar o corte da Respiração Solar; se fala de Nezuko sob o sol, usar a cena do Ep 11 da S3; se fala de Tanjiro Rei dos Demônios, usar a animação do Tanjiro Demon King).
7. **Formatação de Textos e Bios para Redes Sociais:**
   - Ao fornecer cópias de bio, descrições ou copys curtas para redes sociais (TikTok, Reels, Shorts), enviar sempre em mensagem única e limpa pronta para copiar e colar, sem blocos fragmentados ou texto intermediário desnecessário.
8. **Distribuição e Upload via TikTok Studio:**
   - Conta oficial TikTok: `@mugen_raps` (autenticada via Google `alvaroemanuel642@gmail.com`).
   - Upload automatizado via Chrome CDP na rota `https://www.tiktok.com/tiktokstudio/upload`.
   - **Regra Obrigatória da Descrição no TikTok:** Toda postagem DEVE conter o nome da música, frase de impacto/gancho e chamada explícita para o canal oficial do YouTube com o link (`Assista completo no YouTube: youtube.com/@VXRaps`).
   - **Estratégia de Cortes (3 Cortes por Faixa):** Para cada rap lançado no YouTube, produzir imediatamente 3 cortes verticais 9:16 (~35s a 45s):
     1. *Abertura & Gancho Inicial* (Fala icônica + Verso 1)
     2. *O Drop do Refrão / Habilidade Principal* (ex: Jackpot, Respiração Solar, Domínio)
     3. *Clímax da Batalha / Duelo* (Trecho de luta intensa e rima rápida)
   - O painel aceita injeção via `DOM.setFileInputFiles`, preenchimento de legendas com hashtags segmentadas (`#mugenraps #rapgeek #animerap`) e clique no botão `Publicar`.
   - **Gotchas do TikTok Web Studio:** Contas novas (primeiras 24-48h de criação) podem ter limite diário rígido anti-spam para publicações via Web Studio (*"Você atingiu o limite de verificações para hoje"*). Nesses casos, o primeiro corte sobe via web e os demais devem ser enviados imediatamente no WhatsApp para postagem manual sem bloqueio pelo app móvel ou agendados para o dia seguinte.
9. **Estratégia de YouTube Shorts para Divulgação do AMV:**
   - **Postagem Simultânea dos 3 Cortes no YouTube Shorts:** Para cada AMV longo/oficial lançado, postar os 3 mesmos cortes no YouTube Shorts via automação no YouTube Studio (`studio.youtube.com/channel/<ID>/videos/upload?d=ud`).
   - **Padrão dos Shorts:**
     - Resolução: 1080x1920 (9:16 vertical com blur nas bordas e ação centralizada).
     - Títulos: Foco no gancho da cena + `#Shorts` + `#Anime` (ex: `#JujutsuKaisen`, `#DemonSlayer`).
     - Descrição Obrigatória: Link direto e clicável para o videoclipe principal completo em 4K (`youtu.be/...`).
     - Metadados: Público `PUBLIC`, não infantil (`VIDEO_MADE_FOR_KIDS_NOT_MFK`).
     - O YouTube Shorts não possui limite diário de conta nova como o TikTok, permitindo publicar todos os 3 cortes no mesmo dia para tracionar o lançamento principal.

## 2z. Ambiente deste PC — o que existe e o que não existe *(03/09/2026)*

⚠️ **Não há `scipy` neste PC** — nem no python do sistema, nem no `.venv_whisper`,
nem no `.venv_demucs`. Os scripts de sinal do Gojo importam `scipy.signal` e **não
rodam mais**. O substituto pronto, só com numpy, é
`projetos/akaza/sinal.py`: filtro de banda por **FFT** (fase zero, equivalente ao
`sosfiltfilt`), envelope RMS e detector de picos. **Reaproveite esse arquivo em vez
de instalar scipy.**

⚠️ **`np.correlate(x, x, mode="full")` é O(n²)** e trava em 92 k amostras (envelope
de 185 s a 500 Hz). Autocorrelação por FFT resolve em milissegundos:
`F = np.fft.rfft(f, n2); ac = np.fft.irfft(F*np.conj(F), n2)[:len(f)]`.

Existe: `ffmpeg`/`ffprobe` com VAAPI, `yt-dlp` novo em `~/.local/bin` (o do apt está
quebrado), `faster-whisper` no `.venv_whisper`, `demucs` no `.venv_demucs`, `numpy`
e `PIL` no python do sistema, fonte `Cinzel` em `~/.local/share/fonts`.

## 3. Transcrição & Alinhamento Temporal de Alta Precisão

Leia `references/sincronia-musical.md` antes de encurtar a música ou reajustar cortes ao beat.
Ele define o mapa temporal único, a tolerância para snap visual e as provas mínimas de sincronia.

🔴 **O `palavras_vocal.json` que sai daqui é o RELÓGIO DE TODA LINHA de legenda e de toda
fronteira de plano** — não é só o dado que acende a palavra-chave. Foi tratá-lo como
enfeite que produziu meia década de legenda 1–2 s adiantada (§5) e uma montagem
metronômica fora do beat (§4d). Antes de entregar qualquer faixa:
`python3 estudio.py sincronia <slug>` tem de dar **APROVADO**.

Utilizar Faster-Whisper local com modelo `medium` ou `small` com `beam_size=5` e `word_timestamps=True` para evitar defasagem rítmica nas legendas:
```python
from faster_whisper import WhisperModel
import json

model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=4)
segments, _ = model.transcribe(
    "audio/<slug>.mp3",
    language="pt",
    word_timestamps=True,
    beam_size=5
)
data = [{"id": s.id, "start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
         "words": [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)} for w in s.words]}
        for s in segments]
with open("transcricao.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

### 3.1 Quando o Whisper não fecha a letra *(Gojo, 02/09/2026)*

Em faixa de trap o 808 mascara a voz e o Whisper na mixagem deixa buracos — no Gojo
foram **12 linhas indecifráveis**. Duas fontes resolvem, e a regra é **só aceitar o que
duas leituras independentes confirmam**, deixando o canon do anime desempatar.

**a) A partitura em MusicXML é fonte de letra.** O `.zip` que o Álvaro exporta da música
traz `<lyric><text>` preso a cada nota, com `divisions` e `<sound tempo=>` para virar
tempo absoluto. Acumule `<duration>` respeitando `<backup>`/`<forward>` e as trocas de
tempo. Sozinha ela resolveu *"Desculpa, **Amanai**"* (a Riko Amanai, que o Toji matou),
*"em nanossegundos"*, *"o ápice"*, *"Nove cordas"* e *"rasgando a neblina"*.
⚠️ **Ela também é ASR** — trocou "Lapso" por "Lápis" e "Choque" por "Shoki". Não é folha
do Suno. Parser: `projetos/imensidao-vazio/ler_musicxml.py`.

**b) Separação de fontes.** `demucs --two-stems=vocals -n htdemucs`, ~6 min para 228 s em
16 núcleos. Com o vocal limpo o Whisper acertou de primeira *"24 de dezembro em
Shinjuku"*, *"0,2 segundos e o cérebro congelou"* e *"essa cura no fluxo reverso"*.
⚠️ Venv próprio (`~/.venv_demucs`) e **instale `numpy` e `soundfile` explicitamente** — o
pacote do `demucs` não puxa `numpy` e quebra no import.

⚠️ 🔴 **Nunca passe `initial_prompt` em clipe curto.** Em **5 de 9** trechos de 5–15 s o
Whisper cuspiu o próprio prompt de volta como se fosse transcrição — e isso passa fácil
por letra boa. Em janela curta: sem prompt, e varie `temperature` (0,0 / 0,2 / 0,4) para
ver se a leitura é estável.

⭐ **Peça a partitura ao Álvaro quando a letra não fechar** — ele exporta em segundos, e
foi o que destravou esta faixa.

**Confirmado no Akaza (03/09/2026), com números.** A partitura destravou **8 linhas**
que o Whisper não fechava — `morte destrutiva`, `Mas na eternidade nós podemos combater`,
`Punho do vazio`, `Cem anos de sangue` e, a que mais importa, **`A casa se foi, HAKUJI vai
renascer`** (o Whisper ouvia *"a Cujifai renascer"*). Parser pronto:
`projetos/akaza/ler_musicxml.py` (acumula `<duration>` respeitando `<backup>`/`<forward>`
e as trocas de `<sound tempo=>`).

⚠️ **E em 3 linhas o Whisper corrigiu a partitura** (`Prefiro o inferno a continuar a
viver` saiu de "Prefiro internar, Banshee na viva"). São **duas ASRs discordando** — nenhuma
é gabarito.

⭐ **O canon é o terceiro juiz, e ele resolve nome próprio.** As três leituras erravam
foneticamente **Muzan** ("Musa"), **Keizo** e **Koyuki** ("Toshibo"/"Kibuki") e os
**sessenta e sete** homens que o Hakuji matou com as mãos ("607"). Nome de personagem e
número canônico **sempre** se conferem na obra, nunca no ASR.

🔴 **Linha sem confirmação dupla NÃO vira legenda.** O gancho do Akaza (6,0–11,5 s) deu
quatro leituras totalmente divergentes — `Precisa de um chão` / `It's just so wrong` /
`Pulsou no chão, estilou o soro` / `Do seu luxo, Still so wrong`. É ad-lib processado, e
**ficou sem legenda**: o clipe abre a letra aos 12,6 s, no primeiro verso que as três
fontes confirmam. **Buraco na legenda é melhor que letra inventada** — o que está queimado
na tela é assinado pelo Álvaro.


## 4. Pipeline de Renderização em Duas Vias (Master 1080p + WhatsApp)

1. A vinheta v2 **já sai em 1080p@30fps H.264/yuv420p** — não precisa normalizar; concatene direto. (Só vídeo longo; corte vertical não leva vinheta.)
2. Cortar cada plano com `scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1` e filtros de contraste/saturação.
3. Concatenar com `concat` e muxar com áudio original e legenda `.ass`.
4. Gerar simultaneamente:
   - **Master 1080p (`crf=18`, `b:a=256k`)** para publicação no YouTube.
   - **Versão Otimizada WhatsApp (`crf=26`, `b:a=128k`)** garantindo arquivo < 100MB para envio direto via bridge.
5. ⭐ **Audite o intermediário, não o master.** O passo 3 gera um `temp_video_<versao>.mp4`
   ainda **sem** o `.ass` queimado. É nele que a auditoria de contaminação roda: ali qualquer
   texto na tela é de terceiro, sem chance de confundir com a legenda da música. Só entregue
   depois que essa varredura der zero. Ver `references/limpeza-fontes.md` §5.
6. Valide a música editada e o plano visual com as métricas de
   `references/sincronia-musical.md`: emenda sem clique, grid preservado, primeira voz no tempo
   editorial aprovado, legendas transformadas pelo mesmo mapa e melhora mensurável dos cortes.

7. 🔴 **Meça o true peak antes de entregar — o pipeline estoura sozinho.**
   Auditoria de 01/09/2026: **os quatro AMVs anteriores saíram clipando.**

   | Faixa | LUFS | True peak |
   | :--- | ---: | ---: |
   | Kashimo | −9.08 | **+4.88 dBTP** |
   | Hakari | −9.42 | **+1.12 dBTP** |
   | Muzan V5 intro v2 | −10.31 | **+0.67 dBTP** |
   | Sukuna (antes da correção) | −9.43 | **+0.86 dBTP** |

   A causa não é a edição: o master do Suno já chega em **+0.55 dBTP** e o
   encoder AAC ainda **acrescenta** overshoot — quanto menor o bitrate, pior
   (medido: +0.55 dB a 320k, +2.10 dB a 128k). Muxar o mp3 direto, como o
   pipeline fazia, carrega o estouro para o arquivo final.

   Receita validada no Sukuna (não reencoda o vídeo, só a trilha):

   ```bash
   # 1) limita em oversampling 4x — pega o pico intersample, não só o sample
   ffmpeg -i audio/<faixa>.mp3      -af "aresample=192000:resampler=soxr,          alimiter=limit=0.7674:attack=5:release=60:level=0,          aresample=48000:resampler=soxr"      -c:a pcm_s24le render/audio_tp.wav          # limit 0.7674 = −2.3 dBFS

   # 2) AAC com bitrate ALTO nas duas vias (a do WhatsApp também: 256k)
   ffmpeg -i render/audio_tp.wav -c:a aac -b:a 320k -ar 48000 render/a_master.m4a
   ffmpeg -i render/audio_tp.wav -c:a aac -b:a 256k -ar 48000 render/a_whats.m4a

   # 3) remux sem tocar na imagem
   ffmpeg -i saidas/<master>.mp4 -i render/a_master.m4a      -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -movflags +faststart -shortest      saidas/<master>_tpfix.mp4

   # 4) confirme: I entre −10 e −11 LUFS, TP ≤ −1.0 dBTP
   ffmpeg -i saidas/<master>_tpfix.mp4      -af "loudnorm=I=-14:TP=-1:LRA=11:print_format=json" -f null -
   ```

   Não baixe o bitrate do áudio do WhatsApp para "caber": o arquivo é dominado
   pelo vídeo (o do Sukuna ficou em 56 MB com AAC 256k) e 128k só devolve o
   clipping. Alvo de entrega: **−10 a −11 LUFS, TP ≤ −1.0 dBTP**.

   ⚠️ Kashimo, Hakari e Muzan **já estão no ar com o áudio estourado**. A
   correção é remux (passo 3) sem republicar o vídeo — decisão do Álvaro
   pendente sobre substituir os arquivos publicados.

## 4b. Transições: o `dissolve` do FFmpeg chuvisca *(Akaza V6, 03/09/2026)*

🔴 **`xfade=transition=dissolve` NÃO é um cross-fade.** No FFmpeg, `dissolve` é
**dissolução por pixel aleatório**: a cada quadro ele sorteia, pixel a pixel, se mostra A
ou B. O resultado é **chuvisco sal-e-pimenta na tela inteira** no meio da transição. O
cross-fade suave chama-se **`fade`**.

O Akaza V3 e V5 usaram `dissolve` nos **21** pontos de transição e o chuvisco foi para o
vídeo **entregue no WhatsApp do Álvaro**. A 6 quadros (0,20 s) passa por "granulado da
fonte"; alongando para 0,30 s fica escancarado. Conferido quadro a quadro no master da V5,
recorte 960×540 em 1:1, aos 101,57 s e 110,63 s.

**Vocabulário corrigido:**

| Sentido do corte | Filtro | Duração |
|---|---|---|
| Memória / passado | **`fade`** | 0,30 s |
| Virada de ato | **`fade`** | 0,36 s |
| Expansão de domínio | `circleopen` / `radial` | 0,28–0,30 s |
| Técnica / impacto | `fadewhite` | 0,13 s |
| Ação dentro da luta | `smoothleft` | 0,18 s |
| Respiro instrumental | `hblur` | 0,16 s — **um por vídeo** |

⚠️ **`hblur` é whip-blur, não respiro.** No meio da transição a imagem vira borrão
horizontal ilegível. Eu pus quatro no Akaza (dois a 1,8 s um do outro) e ficou grosseiro.

🔴 **Transição também passa por QA de imagem.** A folha de contato a 1 quadro/s **não a
vê**: ela dura 4 a 12 quadros e cai entre as amostras — o mesmo buraco dos quadros pretos
da fonte. Extraia o **meio de cada transição** (`start − duração/2`) e olhe todas em folha.

⚠️ Transição custa janela limpa: 0,30 s exige 9 quadros da fonte *antes* do ponto de
entrada. O validador tem que conferir isso antes de gastar CPU.

## 4c. Montagem sem letra também tem ritmo *(Akaza V6, 03/09/2026)*

O outro do Akaza eram **12 planos de 2,80 s cravados** — 19 % do vídeo com cara de
slideshow, e 2,80 s não é múltiplo de nada na música. Recorte a montagem em **múltiplos de
compasso com padrão variado** (usei 2,1,2,1,2,2,1,2,2,2 compassos + resto) e mova o
`source_start` junto, para o mesmo instante continuar no centro do plano. Em plano parado
de 3 s ou mais, um **push-in lento de 5–7 %** (`zoompan` com `d=1`) tira o ar de slideshow.

🔴 **Meça o BPM no áudio FINAL, não no original.** O `beatgrid.json` do Akaza foi feito
antes das duas emendas de −6,025 s e apontava 186 BPM. Refeito na trilha entregue:
**140,05 BPM, compasso de 1,714 s**, erro mediano de 63 ms. O número se confirma sozinho —
as linhas da letra estão espaçadas exatamente 1,714 s (30,000 → 31,714 → 33,429 …). Se a
grade não explica o espaçamento da letra, a grade está errada.

## 4d. A imagem troca no BEAT, não no dupleto *(medido em 04/09/2026)*

O mesmo relógio errado da legenda estava na montagem: a tabela `PLANO` dos
`render_vN.py` tem **uma fronteira de plano por dupleto de letra** — literalmente os
mesmos números da tabela `LETRA` do `gerar_ass*.py`. Medido no "Imensidão do Vazio"
(95 planos, 220 s, grade real de 136,05 BPM):

| | montagem atual | uma fronteira por LINHA CANTADA, encaixada no beat |
|---|---:|---:|
| planos | 95 | 112 |
| duração mediana | 2,17 s | 1,76 s |
| **faixa dinâmica** (p90/p10) | **2,16×** | **3,25×** |
| planos < 1 s / > 4 s | 1 / 1 | 21 / 7 |
| na grade musical (≤ 50 ms) | **44/95** | **112/112** |
| distância mediana ao beat | **55 ms** | **0 ms** |

Dois defeitos, uma raiz:

1. 🔴 **É um metrônomo.** 93 dos 95 planos duram entre 1 e 4 s. Não há rajada curta na
   rima densa nem plano longo segurando o verso que pesa — a montagem não respira.
2. 🔴 **O corte não cai no tempo forte.** Só 5 dos 95 caíam em downbeat. 107 ms fora do
   beat a 136 BPM é **um quarto de tempo** — o olho não nomeia, mas sente que a imagem
   não pulsa com a música.

E a consequência direta do dupleto: **a segunda linha cantada nunca ganha imagem própria**,
porque o plano foi cortado para o par inteiro.

```bash
python3 estudio.py ritmo <slug>            # grade da faixa + grade de corte sugerida
python3 estudio.py ritmo <slug> --gravar   # grava projetos/<slug>/grade_corte.json
```

⭐ **A regra: a letra diz QUAL imagem, o beat diz QUANDO ela entra.** Uma fronteira por
linha cantada, encaixada no beat mais próximo (downbeat na virada de ato, colcheia quando
o verso é sincopado), dentro dos ±110 ms que a §"Cortes visuais versus voz" já autorizava.

🔴 **Grade errada é pior que grade nenhuma.** O `ritmo` devolve uma `confiança`; abaixo de
**0,25** ele **não encaixa nada** e deixa a fronteira no onset da voz — e diz isso na tela.
Foi por não ter esse freio que a detecção antiga travava numa periodicidade pontuada de 3/2
e devolvia 90,7 BPM para uma faixa de 140. O detector do `ritmo.py` é pente + prior de
andamento (não `argmax` de autocorrelação, que premia qualquer periodicidade); confere 1:1
com as grades conhecidas de Akaza (139,86 × 140,05), Mahoraga (143,89 × 143,67),
Imensidão (136,05 × 136,00) e Inosuke (139,86 × 140,00).

⚠️ A grade é **sugestão**. Quando mais de 30 % das fronteiras ficam abaixo de 1 s a
ferramenta avisa: em flow denso isso é proposital, senão junte linhas vizinhas no mesmo
plano. Quem manda no corte é o sentido do verso.

## 4e. 🔴 O quadro entregue passa por porteiro — `estudio.py imagem` *(medido em 05/09/2026)*

Regra do Álvaro: *"às vezes são colocadas imagens de telas pretas apenas com avisos
ou até imagens não condizentes"*. Até 05/09 **nada media o vídeo final** — o estúdio
media fonte (`blackdetect`, `pretos.json`), legenda e beat, e cada projeto reescrevia
o seu próprio auditor à mão. Medido em todos os masters:

| master | morto | quase-morto | congelado | página clara |
|---|---:|---:|---:|---:|
| **hakari** *(NO AR)* | **9,8 s (6,1 %)** | 13,3 s | 16,0 s | **39,7 s** |
| **kashimo** *(NO AR)* | 2,7 s | 4,2 s | 11,5 s | **19,3 s** |
| **muzan v5** *(NO AR)* | 3,2 s | **18,7 s (7,9 %)** | 21,7 s | 0 |
| mahoraga v2 | **10,8 s (5,0 %)** | 15,7 s | 9,7 s | 0,8 s |
| toji | **10,2 s (5,3 %)** | 11,5 s | **29,7 s (15,3 %)** | 0,2 s |
| rengoku V2 | 2,8 s | 8,7 s | **39,0 s (17,4 %)** | 0 |
| akaza V6 | **0,3 s (0,2 %)** | 3,8 s | 19,2 s | 3,7 s |

O que a folha de contato mostrou e nenhuma métrica tinha dito:

- **Tela preta com só a legenda escrita nela** — `hakari` 65,3 s (2,3 s), 19,5 s, 71,0 s;
  `mahoraga` 32 s, 144 s, 146 s, 179 s, 217 s; `kashimo` 136 s.
- 🔴 **`hakari` e `kashimo` são, em boa parte, slideshow de PÁGINA DE MANGÁ** em line-art
  preto no branco (24,6 % e 19,3 s) — vários quadros são página quase branca com só a
  legenda. A regra de pureza já proibia; nada media.
- 🔴 **Cartela japonesa de terceiro em tela cheia** no `hakari`: `坐殺博徒` aos 12 s e 48 s,
  `領域展開` aos 92 s.

```bash
python3 estudio.py imagem <slug>     # mede o master e grava a folha de suspeitos
python3 estudio.py qa    <slug>      # UM portão: legenda + imagem
```

| medida | critério | reprova |
|---|---|---|
| `morto` | luz < 14 **e** detalhe < 16 | bloco ≥ 1,0 s, ou > 1 % do vídeo |
| `quase-morto` | luz < 24 e detalhe < 22 | > 5 % |
| `congelado` | diferença entre vizinhos < 0,8 por ≥ 1 s | > 6 % |
| `página` | branco (>210) sem cor (sat < 0,12) em > 55 % do quadro | > 0,5 s |
| `reuso` | hash igual (≤ 6 bits) a > 8 s, **com persistência** | avisa |
| `descontinuidades` | `scene` do FFmpeg > 0,35 | avisa se faixa < 2,6× |

🔴 **O porteiro roda dentro do `publicar.py`**, antes de abrir o navegador, em
`youtube-longo`, `youtube-short`, `tiktok` e `instagram`. Master reprovado **não sobe**.
A saída editorial é `--ignorar-qa`, que publica e **imprime o motivo** — a exceção fica
no log em vez de virar hábito.

⭐ **Ele não lê texto, e não finge ler.** Cartela de terceiro, marca d'água e legenda de
dublagem se provam com o **olho**: todo relatório grava
`projetos/<slug>/qa/imagem_suspeitos.png`, etiquetada em segundos. **A folha é a prova;
o número é só o índice dela.**

**Calibrações que custam tempo se refeitas:**
- ⭐ **Não se detecta corte na amostragem de 6 fps.** Histograma e diferença média deram
  **64/91 com 37 falsos** contra o `plano_v6.json` do Akaza. A 1/30 s (o `scene` do
  FFmpeg) o corte volta a ser descontinuidade e o movimento de câmera volta a ser contínuo.
- ⭐ **E o yardstick estava errado, não o detector:** das 91 fronteiras do manifesto,
  **32 são cross-fade** (invisíveis de propósito). Sobre os 59 cortes secos ele acha **57**;
  os "falsos" são cortes do próprio anime dentro do clipe. 🔴 Por isso o campo se chama
  `descontinuidades`, não `planos` — **não case esse número com a contagem do render.**
- ⭐ **Reuso exige persistência.** Sem exigir que o vizinho de 0,5 s também case, o `hakari`
  acusava **186** reusos; com ela, **13** — e os 13 são reais.
- 🔴 **`ffmpeg -ss` ANTES do `-i` zera o relógio que o filtro `subtitles` lê** e a legenda
  some do quadro **sem erro nenhum**. Para conferir legenda num instante: `-copyts -ss <t> -i`.

## 4f. 🔴 O porteiro de imagem NÃO lê texto — a varredura é `estudio.py texto` *(Inosuke V4, 06/09/2026)*

O `estudio.py imagem` (§4e) mede preto, congelado, página e reuso. Ele **não lê texto, e
diz isso de si mesmo**. Até 06/09 nada varria **legenda de fansub queimada no master** — e
o buraco custou caro.

**O que estava no ar:** o `inosuke_amv_v2_master_1080p.mp4`, salvo em `saidas/` desde
04/09 e registrado no changelog como *"100 % de fontes puras"*, tinha **duas legendas em
inglês queimadas**:

| onde | plano | fonte | texto |
|---|---|---|---|
| 152,78 – 155,52 s | 78 | `cena_doma 393,5` | `Calm down.` e `Don't worry` |
| 159,36 – 162,10 s | 81 | `cena_doma 324,5` | `What is this?` |

As duas janelas **não estavam** em `JANELAS_PROIBIDAS`: o mapa que o
`detectar_legendas.py` gerou para a `cena_doma` tem buracos (47 janelas proibidas em 530 s
e ainda passou).

### 🔴 Dois detectores automáticos foram construídos e os DOIS reprovaram

Isto está aqui para ninguém tentar de novo. Os controles positivos foram
`cena_doma` em 357,5 s / 232,5 s e, depois, os dois trechos do próprio picture lock.

| tentativa | resultado no controle |
|---|---|
| pixel quase-branco **com vizinho escuro** (a assinatura do contorno de legenda) | positivos: 261 e 213 px · negativos limpos: **518** e 252. **Não separa** — line-art de anime *é* branco com contorno preto |
| o mesmo + **estabilidade temporal** (texto fica parado, desenho se mexe) | achou o `What is this?` mas **perdeu o `Calm down.`**; 25 suspeitos, pico de 8101 em plano sem texto |

Vale a mesma regra do §4e: **a folha é a prova, o número é só o índice dela** — só que
aqui não existe nem número que preste. Então a ferramenta gera **só a folha**.

### A ferramenta

```bash
python3 estudio.py texto <slug>                 # as duas faixas, no picture lock
python3 estudio.py texto <slug> --faixa baixo   # só o rodapé
python3 estudio.py texto <slug> --arquivo X.mp4
```

Módulo em `ferramentas/texto.py`. O que ela faz: recorta **a faixa onde o texto mora**,
amplia até ficar legível, escreve **o segundo em cada quadro** e monta as folhas.

| faixa | recorte | o que já pegou |
|---|---|---|
| `baixo` | `1920×300` a partir de `y=780` | legenda de fansub, assinatura de editor (`Denji Suke`, `Calm down.`) |
| `alto` | `1920×240` a partir de `y=0` | banner de streaming, **nome de técnica** (`Sixth Fang…` da `cena_gyutaro_limpa`) — a faixa que o `detectar_legendas.py` nunca varreu |

Amostra a **2 quadros/s** (legenda de fansub dura ~1,5 s, não escapa) e miniatura de
**640 px** de largura — abaixo disso o texto some. 13 folhas para 222 s.

⚠️ **Rode no PICTURE LOCK, não no master**: no master a legenda da própria música ocupa a
mesma faixa de baixo. O comando escolhe o lock sozinho quando existe.

Validado nos dois sentidos: no lock da V3 ela mostra `Calm down.` em **153,0 s** e
`What is this?` em **161,5 s**; no lock da V4, limpo.

### 🔴 Duas armadilhas do FFmpeg que a ferramenta contorna — e você também precisa

**a. Em picture lock feito por `concat -c copy`, o `-ss` ANTES do `-i` MENTE.**
Três folhas pedidas em `-ss 126`, `-ss 144` e `-ss 162` saíram **idênticas**. Não é o mesmo
problema do §4e (lá o `-ss` zera o relógio que o filtro `subtitles` lê); aqui **o conteúdo
devolvido está errado**. Decodifique em **uma passada, sem seek**, com saída numerada. Para
quadro avulso nesses arquivos use seek de saída (`-i arq -ss t`) — lento, mas honesto. No
**master** (reencodado) o seek de entrada funciona normal.

**b. `-vf tile` montando as folhas direto no ffmpeg PULOU 18 s.** Duas folhas vizinhas
saíram byte a byte idênticas (07 == 08 de 13) — ou seja, dezoito segundos ficaram sem
inspeção nenhuma. Por isso a montagem é feita em PIL a partir dos quadros numerados, e o
relatório imprime **`cobertura: OK — todo quadro entrou em uma folha`**. Se essa linha não
aparecer, a varredura não vale.

> Isto soma-se ao que o §4c já avisava (`tile` com `-update 1` exige `-frames:v 1`).
> Resumo: **não confie no `tile` para segmentar tempo.**

---

## 4g. Legenda: três consertos medidos no Inosuke *(06/09/2026)*

### a. A cor de plano B tem um segundo caso — e uma regra de ouro

O Akaza (§4b/§13 do vault) descobriu que a cor da aura some quando a **aura também está no
fundo**. O Inosuke repetiu exatamente: aos **49,6 s** o título `SÉTIMA PRESA NO AR` saía em
ciano `#00D2FF` **em cima da própria Respiração da Fera**, que é ciana e toma a tela.

⭐ **A segunda cor não é decoração, é seguro.** Amostre-a junto com a aura, no mesmo dia, e
guarde as duas no `projeto.json` (`cor.destaque` e `cor.destaque_plano_b`).

| personagem | aura | plano B | de onde saiu o plano B |
|---|---|---|---|
| Akaza | `#68C8F8` | `#F6BA06` | o ouro dos olhos de Lua Superior Três |
| **Inosuke** | `#00D2FF` | **`#F09018`** | o âmbar do pelo de javali e das lanternas do Distrito (`raw_4k60 @40 s`, sat 0,90 / brilho 0,94) |

Critério (o mesmo do Akaza): mede-se **na faixa onde a legenda vai cair** a fração de pixel
na cor da aura e a luz média; troca se `aura > 0,18` ou (`luz > 150` e `aura > 0,08`).
Escolha um plano B **complementar** da aura — âmbar contra ciano é contraste máximo.

### b. 🔴 A histerese de posição vira cola sem uma segunda ressalva

A regra do Akaza já tinha uma guarda ("se o rodapé JÁ É a melhor faixa, estar cheio não é
motivo para sair dele"). Falta**va** a outra: na primeira medição do Inosuke, **30 das 73
linhas ficaram presas no topo** depois de UMA linha que precisou subir — o refrão inteiro
saiu do rodapé, que é onde ele mora.

**A histerese só pode valer quando a regra já mandou sair do padrão.** Se a regra diz
rodapé, vai para o rodapé, ponto. Com a ressalva: `rodapé 60 · rodapé-esq 2 · topo 7 ·
topo-esq 4`.

### c. Casar a palavra-chave: aceite qualquer palavra da expressão

O Gojo estabeleceu que a palavra-chave acende no tempo do Whisper `large-v3` rodado no
vocal isolado pelo Demucs. Medido no Inosuke: casar só a **primeira** palavra da expressão
dá **31 de 73** linhas; aceitar **qualquer** palavra da mesma expressão sobe para
**35 de 73**. Quando o Whisper erra justamente a primeira, a seguinte está no mesmo compasso
e serve igual.

### d. Miudezas que mudam a leitura

- **`Fala` e `Verso` sem negrito leem como fansub.** Cinzel 56/58 no canto não é cartaz de
  canal. Vá para negrito e corpo maior (62/64). O `Grito` foi de 86 para **104** — é um
  berro, tem que ocupar.
- **O `Grito` não pode sair com a linha inteira em destaque.** `SAI DO CAMINHO!` estava
  100 % ciano, o que é karaokê, não o padrão da casa. Vire `SAI DO <<CAMINHO!>>`.

---

## 4h. Dois defeitos que nenhum validador pega *(Inosuke V4, 06/09/2026)*

**a. Planos repetidos com janela diferente.** O validador recusa *janela de fonte* usada
duas vezes — mas os planos 49, 50, 51 e 52 do Inosuke usavam janelas **diferentes do mesmo
plano de câmera**: 7,5 s seguidos com o mesmo enquadramento (braços abertos no escuro), e
nenhum deles dizia o que o verso dizia. **Só a folha de contato dos meios de plano pega
isso** — um quadro do meio de cada plano, tudo em folha, olhado de uma vez.

**b. `whip` de 2 quadros com raio 44 passa por corte seco.** Na folha dos meios de
transição, vários whips do Inosuke eram indistinguíveis de corte. Vire **3 quadros em duas
etapas** (`boxblur` raio 104 nos 2 primeiros, 46 no terceiro). Aí lê como chicote sem virar
o `hblur` ilegível do §4b.

## 5. Estado das faixas

| Faixa | Versão final | Arquivo |
| :--- | :--- | :--- |
| **Muzan Kibutsuji** | **V5 intro v2 (01/09/2026) — PUBLICADA** | `saidas/muzan_amv_v5_introv2_1080p.mp4` |
| **Sangue Explosivo — Nezuko** | **V2 (01/09/2026) — FINAL** | `projetos/sangue-explosivo/saidas/sangue_explosivo_nezuko_amv_v2_master_1080p.mp4` |
| **Ryomen Sukuna — O Rei das Maldições** | **PUBLICADO** — `youtu.be/fG3g99jXts8` | `saidas/sukuna_amv_oficial_master_1080p.mp4` |
| **Satoru Gojo — Imensidão do Vazio** | **Master v2 02/09/2026 — FECHADO, não publicado** (prévia 9:16 no ar) | `projetos/imensidao-vazio/saidas/imensidao_vazio_gojo_v2_master_1080p.mp4` |
| **Akaza** (Demon Slayer) | **V6 03/09/2026 — FECHADO, não publicado** | `projetos/akaza/saidas/akaza_amv_v6_master_1080p.mp4` (2:59) |
| **Inosuke Hashibira — O Deus da Montanha** | **V4 06/09/2026 — FECHADO, não publicado** (prévia 9:16 no ar) | `projetos/inosuke/saidas/inosuke_amv_v4_master_1080p.mp4` (3:42) |

🔴 **Inosuke: use a V4, nunca a V1 nem a V2.** A V1 tem a cartela de crédito do editor
`@baseking99` aos 17,5 s; a **V2 tem duas legendas em inglês queimadas** (§4f) — e estava
registrada no changelog como "100 % de fontes puras". A prévia de 34 s já publicada nas
três redes sai de 140–174 s, **antes** do primeiro trecho contaminado, e continua limpa.

⚠️ **Akaza: use a V6, não a V3/V5.** As duas anteriores saíram com as 21 transições em `xfade=dissolve` (chuvisco de pixel aleatório — §4b) e a V5 ainda trocou a Cinzel por Impact. A V6 tem o mesmo áudio e a mesma montagem verificada, com transições, legendas e outro corrigidos. Evidência em `projetos/akaza/revision_v6_20260903/`.

⚠️ **Muzan está fechado e publicado.** O que foi ao ar em 01/09/2026 é a **V5 com a
intro v2** (`saidas/muzan_amv_v5_introv2_1080p.mp4`, 3:56) — não a V4. Não voltar para
V1/V2/V3: elas têm `Subscribe`, `4KAnime`, `4K ANINOMI`, cartelas `UPPER FIVE/FOUR/ONE`
e legendas em inglês/português queimadas. Pendência conhecida: `tanjiro_demon_king`
(203–214 s) é animação de fã, não o anime — trocar numa próxima rodada.

## 5b. Onde fica o master que ainda não foi ao ar *(03/09/2026)*

`~/Documentos/Video_Studio/NAO_PUBLICADOS/`, espelhando `PUBLICADOS/`, com
**links simbólicos** — o arquivo real continua no `saidas/` do projeto, então não
há cópia divergindo nem disco gasto duas vezes. Ao publicar, mova a pasta para
`PUBLICADOS/` (aí sim copiando) e apague os links.

## 6. Publicação — skill separada

Montar não é entregar. Para subir nas plataformas, use a skill
**`publicar-canal-mugen`** (ferramenta única:
`~/Documentos/Video_Studio/ferramentas/publicar.py`).

🔴 **Todo vídeo do YouTube sai com capa própria** (ordem do Álvaro, 01/09/2026).
Publicar e deixar a miniatura automática não conta como entregue. A capa é
1280×720, feita de **frame real do próprio vídeo** — nunca arte de IA — e o
gerador de referência é `ferramentas/artes_muzan.py`.

**Confira quem está no frame.** A primeira capa do Muzan usou um frame de Lua
Superior (cabelo branco, olhos dourados com kanji) achando que era ele. Muzan
tem cabelo escuro e olho **vermelho**; olho com kanji nunca é ele.

Dois geradores servem de modelo: `ferramentas/artes_muzan.py` e
`ferramentas/artes_sukuna.py` (este importa as funções daquele — reaproveite em
vez de duplicar). A composição que funciona é sempre a mesma: personagem de um
lado, coluna de texto do outro, scrim escuro por baixo do texto, nada no canto
inferior direito (selo de duração) e conferência no card de 210 px.

**Tire o frame do picture lock, não do master.** O `render/<slug>_picture_lock_
sem_legenda.mp4` ainda não tem o `.ass` queimado, então não é preciso recortar
faixa de legenda antes de enquadrar — foi o remendo que a capa do Muzan exigiu.

**Identidade por faixa:** Sukuna encarnado tem marca em losango na testa, duas
listras pretas sob **cada** olho, listras no queixo e olho vermelho. Frame do
Yuji sem essas marcas é o Yuji, não o Sukuna.


## 7. Lançamento: ordem, copy e leitura de métrica

📄 `references/lancamento-e-copy.md` *(01/09/2026)* — o que a auditoria dos
números públicos do canal mostrou e o que virou regra.

🔴 **O longo sobe primeiro, os cortes 2 a 4 h depois.** Conversão Short→longo:
Hakari (longo 4 h antes) **5,1%** · Kashimo (juntos) 1,0% · Muzan (cortes
antes) 0,8%.

🔴 **Nenhum longo sobe sem descrição completa e 12–16 tags.** O Muzan saiu com
0 tags e 402 caracteres porque o `publicar.py` não tinha `--tags` — agora tem.

🔴 **A copy do corte manda para o VÍDEO, não para o canal.** Hoje os cortes
apontam para `@VXRaps`; o certo é `youtu.be/<ID_DO_LONGO>`.

🔴 **Métrica se lê por idade, nunca por total bruto.** Os cortes do Muzan
pareciam fracos e eram o lote mais rápido do canal — só tinham 2 h de vida.

⚠️ **A música não costuma ser o problema.** O Muzan tem a maior taxa de like
do canal (40%) e a menor view: isso é distribuição, não faixa.

### Muzan — o que está no ar (01/09/2026)

| Onde | Link / id |
| :--- | :--- |
| YouTube (AMV 3:56) | `kHzEpNzJqCI` — youtu.be/kHzEpNzJqCI |
| YouTube Shorts | `ue_kcuHPDak` · `rtn800PkISI` · `P4mkxtqRq7E` |
| TikTok @mugen_raps | 3 cortes |
| Instagram @mugenraps_oficial | `DcwEs0uNHyS` · `DcwNaL6tqSx` · `DcwN_LVtzDo` |
| Artes | `saidas/muzan_capa_youtube.jpg`, `muzan_banner_canal.jpg`, `muzan_capa_streaming_3000.jpg` |
