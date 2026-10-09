# Publicar no TikTok Studio por CDP — o que trava e como não travar

*(autor: Claude | 2026-09-01)*

Em 01/09/2026 o Hermes ficou **das 08:56 às 10:01 em loop** tentando publicar os cortes
do Kashimo. Foram 229 erros de tool em 24 h. Nenhum dos cortes do Hajime chegou ao ar
nesse período. As causas estão abaixo, todas reproduzidas e corrigidas.

## 1. 🔴 Nunca monte o JS como one-liner de shell

Foi o que matou o loop. O aninhamento **shell → Python → JavaScript** come as aspas:

```
File "<string>", line 19
  eval_res = await call('Runtime.evaluate', {'expression':
             'document.querySelector(input[type='file'])'})
                                     ^ o seletor perdeu as aspas
```

```
File "<string>", line 48
  has_editor = await eval_js('!!document.querySelector(div[contenteditable=\true\],
                             ^ SyntaxError: unterminated string literal
```

**Regra:** o JS mora em **arquivo**, dentro de string tripla `"""..."""`, e o arquivo vai
para o acer por `scp`. Nunca `python3 -c` com JS dentro. Cliente pronto e testado:
`~/Documentos/Video_Studio/assets/tiktok/cdp.py`.

## 2. Chrome morre quando o gateway reinicia

O Chrome de debug era filho do cgroup do `hermes-gateway.service`. No restart o systemd
manda `SIGKILL` nele:

```
hermes-gateway.service: Killing process 2301751 (chrome) with signal SIGKILL
```

**Regra (atualizada em 05/09/2026):** não suba Chrome à mão. Quem faz isso é o
`navegador-frota`, um serviço systemd do usuário `acer` que roda **fora** do cgroup do
gateway — o que resolve exatamente o `SIGKILL` acima — e abre o Chrome no display
virtual `:99` (Xvfb), invisível no monitor.

```bash
# levanta (ou reaproveita) o Chrome de trabalho e devolve o CDP na 9222
curl -s http://127.0.0.1:9222/json/version
```

Para os corpos Hermes não há nada a fazer: cada perfil já tem `browser.cdp_url` apontando
para a sua porta (9301–9314), e o navegador sobe sozinho na primeira conexão. Ver
`navegador-frota estado` e `/home/acer/Documentos/navegador-frota/README.md`.

> **Nunca** use `DISPLAY=:0` numa receita de automação: `:0` é a tela física do Acer, e
> era daí que vinham as janelas aparecendo no monitor. `setsid`/`nohup` também não
> substituem uma unidade systemd — não criam cgroup próprio.

## 3. `/json/new` exige **PUT**

Chrome ≥ 111 devolve `HTTP 405 Method Not Allowed` para `GET /json/new`.

## 4. ⚠️ `pgrep -f` casa com o próprio comando

Um `while pgrep -f "ffmpeg.*muzan_sheet"; do sleep 2; done` ficou **10 h 40 girando**:
a string do padrão está na própria linha de comando do `bash -c`, então o `pgrep` se
encontra e o laço nunca sai. Use `pgrep -f "padrao" | grep -v $$`, ou case por caminho
de binário, ou espere pelo PID guardado.

## 5. Confira a legenda ANTES de clicar em Publicar

A conta tinha **dois posts com o nome do arquivo como legenda**
(`corte_2_jackpot_v2_antidetect`, `corte_1_febre_inicio_9x16`) e um com o bloco de
hashtags repetido 4×. Sintoma clássico de clicar em Publicar antes da legenda entrar.

O TikTok preenche a descrição sozinho com o nome do arquivo. O fluxo correto é:
apagar o que ele pôs (≈80 backspaces), `Input.insertText` com a legenda, **ler de volta**
`div[contenteditable="true"]`, e só então publicar. Se voltar vazio ou com o nome do
arquivo, **aborte**.

## 6. Feche o autocomplete de hashtag antes de publicar

A legenda termina em hashtag, então a lista de sugestões fica aberta **por cima do botão
de publicar** e o clique cai nela. Liberar, do mais suave ao mais bruto, medindo de novo
depois de cada passo: digitar um espaço (encerra a hashtag) → `Escape` →
`document.activeElement.blur()`.

**Confirmar que liberou não é olhar o texto da página** — regex em `innerText` dá falso
negativo. Pergunte quem está no ponto do botão:

```js
b.scrollIntoView({block: 'center'});
const r = b.getBoundingClientRect();
const topo = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
const livre = b === topo || b.contains(topo) || topo.contains(b);
```

⚠️ O `[data-e2e=post_video_button]` fica **abaixo da dobra**. Sem o `scrollIntoView`,
`elementFromPoint` devolve `null` e você lê *"coberto por nada"* num botão limpo —
travou a postagem da prévia do Sukuna em 01/09/2026.

## 7. A última conferência é imediatamente antes do clique

Releia `.public-DraftEditor-content` **depois** de liberar o botão e **antes** de clicar.
Os passos de liberação digitam no editor; e é justamente aqui que o TikTok já apareceu
com o nome do arquivo no lugar da legenda.

## Fluxo que funcionou

```bash
cd ~/Documentos/Video_Studio/ferramentas
python3 publicar.py tiktok ARQ --legenda "copy + #hashtags + @VXRaps"
```

🔴 `assets/tiktok/postar_tiktok.py` está **aposentado**. A única porta é `publicar.py`,
que tem **porteiro de legenda** (recusa <25 chars, <3 hashtags, sem `@VXRaps`
ou com o nome cru do arquivo) e aborta em vez de publicar torto.

Os três cortes do Kashimo saíram assim em 01/09/2026 às 10:26, 10:28 e 10:29, todos
públicos e com legenda correta.
