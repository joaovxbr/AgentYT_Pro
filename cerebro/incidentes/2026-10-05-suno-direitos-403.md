# Incidente: `suno_dl.py` quebrado — endpoint de direitos do Suno devolvia 403 (05/10/2026)

**Relato do usuário:** link do Suno colado para baixar o áudio do projeto `asta`
(`https://suno.com/s/ImFANECey8FjXPOw`).

## Causa real (medida)
`skills/downloadmusic/suno_dl.py` fazia POST em `https://yellow-salad.aibiei.com/rights`
(`fetch_rights`). Esse host hoje devolve **403 Cloudflare "Attention Required"** para
qualquer cliente não-navegador: testado com `urllib` (UA do script), com `curl` (Origin
`usesuno.com`, `suno.com` e sem Origin) e com `curl_cffi` impersonando Chrome/Chrome131/
Safari/Firefox — **403 nos 7 casos**. Não é TLS, header nem IP: o host foi aposentado.

O site novo chama **`POST https://studio-api.prod.suno.com/api/mango/rights`** com o mesmo
corpo (`{"content_params": {"content_id": ..., "content_type": "clip"}}`) e devolve a mesma
trinca `key` / `iv` / `glt`. Achado no bundle do site
(`suno.com/_next/static/immutable/chunks/1r54r3aq4-jfn.js`, trecho `e.POST("/api/mango/rights",
{body:{content_params:{...}}, credentials: ...})`), confirmado com `curl` → **200**.

O passo 1 (metadados, `studio-api.prod.suno.com/api/clip/<uuid>`) e o passo 3 (CDN cifrada)
nunca falharam — só a chave de destrave.

## Correção permanente
- `skills/downloadmusic/suno_dl.py`: `RIGHTS_URL` virou `RIGHTS_ENDPOINTS`, uma lista de
  `(url, origem)` percorrida em ordem — **mango (suno.com)** primeiro, **yellow-salad
  (usesuno.com)** como fallback — e `fetch_rights` acumula o erro de cada tentativa e só
  lança no fim, com a lista de tentativas na mensagem. Assim um host cair de novo não mata
  a ferramenta e o erro diz o que foi testado.
- Conferido de ponta a ponta: download + destrave + MP3 320k + `loudnorm` →
  `projetos/asta/entradas/asta_normalizado.wav` (143,6 s, 44,1 kHz, estéreo s16).
- Suíte verde depois da mudança: `python -m unittest discover -s tests` → **347 testes, OK**.
- Nenhum teste cobria `suno_dl` (é rede real) — a regressão quebrou em produção primeiro.

## Armadilha documentada
Link curto `suno.com/s/<token>` não é aceito: `extract_uuid` só entende `suno.com/song/<uuid>`
ou o UUID cru. Resolver com `web_extract` no link curto (a página redireciona e traz o
`song/<uuid>`) — é resolução de URL, não captura de mídia. Para este projeto:
`36292923-bfe1-49a7-8730-07bb33e4605d` ("Anti-Magia", v6, 143,6 s).
