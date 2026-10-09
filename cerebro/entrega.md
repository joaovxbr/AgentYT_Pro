# Entrega — o pacote completo (REGRA: nunca entregar só o vídeo)

> Reclamação real do usuário (30/09/2026): "não esqueça da thumb e também do vídeo completo, os textos do título e
> descrição — tá esquecendo muito isso". A partir daqui, **toda** entrega ao usuário é o pacote inteiro abaixo,
> gerado e conferido pela ferramenta. Nunca responder "está pronto" com item faltando.

## O pacote (10 itens, conferidos por `ferramentas/entrega.py`)
| # | Item | Arquivo / origem |
|---|---|---|
| 1 | Vídeo completo (master promovido) | `saidas/<slug>_master.mp4` ← `estudio.py promover` |
| 2 | Thumbnail YouTube 1280x720, < 2 MB | `saidas/<slug>_capa_ia.jpg` ← `estudio.py artes-ia` (ComfyUI) |
| 3 | Título (≤ 100) + alternativos A/B | `saidas/PUBLICACAO.md` ← `publicacao_doc.py` |
| 4 | Descrição (≤ 5000) com capítulos, letra, créditos, hashtags | idem |
| 5 | Tags (≤ 500 caracteres) | idem |
| 6 | Capítulos (≥ 3, 1º em 0:00) | idem (já dentro da descrição) |
| 7 | Comentário fixado | idem |
| 8 | Shorts 9:16 | `saidas/shorts/NN_<slug>_<inicio>s.mp4` ← `estudio.py shorts` |
| 9 | Título, descrição e legenda TikTok de **cada** Short | `saidas/shorts/pacote.json` e `PUBLICACAO.md` |
| 10 | Artes extras: banner do canal + capa 3000 px | `saidas/<slug>_banner_canal.jpg`, `saidas/<slug>_capa_streaming_3000.jpg` |

## Fluxo obrigatório depois que o usuário aprova o vídeo
```powershell
.venv\Scripts\python.exe ferramentas\estudio.py promover <slug> <run_id>   # candidato -> master (backup do anterior)
.venv\Scripts\python.exe ferramentas\estudio.py entrega <slug>             # gera o que falta e confere os 10 itens
```
- `promover` só aceita execução com status `aprovado_qa_automatico`; o master anterior vai para
  `backups/masters/`; histórico em `qa/promocoes.json`. É a **única** forma de mudar o master (regra 4).
- `entrega` gera Shorts se a timeline mudou depois deles, artes se faltarem (ComfyUI sobe sozinho) e sempre
  regenera os textos; escreve `saidas/ENTREGA.md` (checklist + caminhos) e `saidas/PUBLICACAO.md` (textos
  prontos para copiar). Exit ≠ 0 se faltar qualquer item.
- **Resposta ao usuário:** listar os caminhos de todos os arquivos e colar o título, a descrição (ou apontar
  `PUBLICACAO.md`), as tags e os textos dos Shorts. Nada de "falta só a thumb".

## Textos: de onde vêm e como personalizar
`projeto.json -> lancamento` sobrescreve o que for dado: `titulo`, `descricao` (gancho do topo), `tags`,
`creditos`, `links`, `comentario_fixado`. Sem isso, `publicacao_doc.py` monta do manifesto:
- título `PERSONAGEM – FAIXA | Rap de ANIME | VX RAPS` + 3 alternativos;
- descrição: gancho → inscreva-se → capítulos → links → letra → créditos → hashtags (corta a letra se passar de 5000);
- tags a partir de personagem, anime, faixa, técnicas e entidades do `scene_semantics`;
- modelo de SEO observado na referência MUGEN RAPS: `cerebro/referencias.md`.
Shorts: `shorts_pipeline.metadados` (gancho | personagem #Shorts; descrição com trecho da letra; legenda TikTok).
