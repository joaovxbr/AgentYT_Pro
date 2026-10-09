# Publicar Reels no Instagram por CDP — @mugenraps_oficial

*(autor: Claude | 2026-09-01)*

Validado em 01/09/2026 com **6 Reels publicados** (3 do Hakari + 3 do Kashimo).
Script: `~/Documentos/Video_Studio/assets/instagram/postar_instagram.py`.

## O fluxo real do Instagram web

`Criar` → `Postar` → `input[type=file]` → **Cortar** → `Avançar` → `Avançar` →
legenda → `Compartilhar`.

O botão **Criar** da sidebar só abre um submenu; quem abre o modal é o **`Postar`**
logo abaixo dele. Clicar em "Criar" e esperar o diálogo não funciona.

## 🔴 A armadilha: a etapa "Cortar" recorta

O preview abre com uma **máscara de recorte** por cima e o padrão não é o vídeo cheio.
Se passar batido, o Reel sai com topo e base cortados — o mesmo estrago do center-crop.

O ícone **"Selecionar corte"** (`svg[aria-label="Selecionar corte"]`) fica no **canto
inferior esquerdo do preview**, em ~`(618, 833)`. Ele abre a lista:
**Original · 1:1 · 9:16 · 16:9**. Clique em **9:16**.

**Confirme por número, não pelo print.** Meça o elemento de vídeo e exija ≈ `0.5625`:

```js
const d = document.querySelector('div[role="dialog"]');
const r = [...d.querySelectorAll('video')]
  .map(v => v.getBoundingClientRect())
  .filter(x => x.width > 100 && x.height > 100)
  .sort((a,b) => b.width*b.height - a.width*a.height)[0];
(r.width / r.height).toFixed(4)   // tem de dar ~0.5613
```

⚠️ **Escope no `div[role="dialog"]`.** `document.querySelector('video')` pega um vídeo
**do feed atrás do modal** — a primeira medição deu `1.3333` (4:3) e era um post alheio.
O script aborta se a proporção não bater.

## Legenda

Mesma disciplina do TikTok: escrever com `Input.insertText`, **ler de volta** o
`div[contenteditable="true"]` e abortar se vier vazia. Depois **fechar o autocomplete de
hashtag** (`Escape` + tirar o foco) — a legenda termina em hashtag e a lista aberta pode
injetar a sugestão destacada no clique.

Emoji na legenda **pode**: quem desenha é a UI do Instagram, não o `drawtext`.
No vídeo queimado é que não pode — ver §tofu abaixo.

## ⚠️ Tofu: emoji queimado no vídeo vira quadradinho

A fonte Ubuntu usada pelo `drawtext` do FFmpeg **não tem emoji nem `▶`**. Os cortes do
Hakari de 08:08 saíram com `VX RAPS - FEBRE DO JACKPOT □` na tarja. Em texto
**queimado no vídeo**, use só o que a fonte desenha (acento latino vai bem; emoji não).
Refeitos em `~/Documentos/Video_Studio/saidas/hakari_reels_v2/`.

## ⚠️ Avisos que o Instagram empilha por cima do wizard (01/09/2026)

Desde 01/09 o Instagram abre um cartão **"Agora os posts de vídeo são compartilhados
como reels"** com botão **OK** sobre a etapa Cortar. Enquanto ele está na tela o
"Avançar" **é clicado e nada acontece** — o sintoma é o wizard repetindo `Cortar` a cada
volta, como se o clique não pegasse. Feche todo aviso (`OK` / `Continuar` / `Entendi` /
`Agora não`) antes de começar **e a cada volta do wizard**.

Pelo mesmo motivo: **não abra o `Selecionar corte` se a proporção já for ~0.5625**. O
popover fica aberto por cima do "Avançar" e trava o wizard do mesmo jeito.

## ⚠️ A sugestão de hashtag cobre o "Compartilhar"

A legenda termina em `#algo` e a lista de sugestões abre **em cima do botão**. Foi assim
que a prévia do Sukuna ficou presa no modal com a legenda escrita e nada publicado
(01/09, ~23:0x UTC).

Detectar isso lendo texto da página **não funciona** — regex em `innerText` deu falso
negativo (`autocomplete ainda aberto? False` com a lista bem aberta na tela). Pergunte
**quem está no ponto do botão**:

```js
alvo.scrollIntoView({block: 'center'});
const r = alvo.getBoundingClientRect();
const topo = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
const livre = alvo === topo || alvo.contains(topo) || topo.contains(alvo);
```

⚠️ `elementFromPoint` devolve **null** fora da viewport. Sem o `scrollIntoView` você lê
*"coberto por nada"* num botão que não tem nada em cima — foi o que aconteceu com o botão
do TikTok, que fica abaixo da dobra.

Para liberar, do mais suave ao mais bruto, **medindo de novo depois de cada passo**:
digitar um espaço (encerra a hashtag) → `Escape` → `document.activeElement.blur()`.

## Uso

```bash
cd ~/Documentos/Video_Studio/ferramentas
python3 publicar.py instagram ARQ --legenda "copy + #hashtags + @VXRaps"
python3 publicar.py instagram-apagar <shortcode> --confirmo     # irreversível
```

🔴 `postar_instagram.py` está **aposentado**. A única porta é `publicar.py`, e ela tem um
**porteiro de legenda** que recusa antes de abrir o navegador: <25 chars, <3 hashtags,
sem `@VXRaps` ou com o nome cru do arquivo. Se ela abortar, ela está certa.

`[10] pos-publicacao: Compartilhando` é sucesso: o envio entrou na fila. Confirme depois
com `ver_reel_existente.py`, que lista os permalinks de `/reel/`.

## Conta

`@mugenraps_oficial` — 397 seguidores em 01/09/2026. ⚠️ O perfil tem **2 Reels antigos de
junho/2025 de outro assunto** (`#segundaguerra`), de quando a conta era outra coisa.
Não são do VX RAPS e **não devem ser apagados por agente**.

Apagar Reel é **irreversível** e só com pedido explícito do Álvaro. Aconteceu uma vez:
o Reel `DcwxS73NRDO` (prévia do Sukuna, 01/09 19:48) foi ao ar **sem legenda e sem
hashtag** e o Álvaro mandou apagar e repostar — refeito como `Dcw00yJtsJp`.
