# AgentYT Pro — VX RAPS

Estúdio de AMVs de rap geek: montagem, cenas IA, motion graphics, legendas, render NVENC,
QA, artes e pacote de lançamento. Duas portas: `ferramentas/estudio.py` (criação) e
`ferramentas/publicar.py` (publicação). Regras completas de produção: `AGENTS.md`.

## Ambiente (Windows, RTX 3090)

O estúdio roda com o venv local `.venv/` (Python 3.10, torch 2.5.1+cu121) — `python` já
responde por ele quando o PATH do usuário inclui `D:\hermes\AgentYT_Pro\.venv\Scripts` e
`D:\hermes\AgentYT_Pro\ferramentas\bin` (ffmpeg/ffprobe/yt-dlp locais). Dependências em
`requerimentos.txt`. O ComfyUI vive em `D:\hermes\ComfyUI` (venv próprio, torch ≥2.7 —
exigência do ComfyUI 0.38) com o checkpoint `animagine-xl-3.1.safetensors`; caminho
registrado em `assets/design/imagem_local.json -> comfy_dir`.

Reconstruir o ambiente do zero (ex.: após migrar de máquina):

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python -m pip install -U pip setuptools wheel
.venv\Scripts\python -m pip install -r requerimentos.txt
.venv\Scripts\python -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
```

## Começar

```powershell
python ferramentas\estudio.py doutor              # FFmpeg, NVENC, GPU
python ferramentas\estudio.py comfy-status        # ComfyUI + checkpoint (sobe sozinho quando preciso)
python ferramentas\estudio.py esteira <slug> --planejar
```

## Produção de um clipe

```powershell
python ferramentas\estudio.py rebuild-total <slug>   # do zero, sem herança de gerações antigas
python ferramentas\estudio.py esteira <slug>         # retomada/idempotente
```

A esteira gera o que faltar de um projeto novo (stems, transcrição, legenda, timeline) e roda:

`auditar-ritmo → cenas-auto → cenas-ia → titulos → manga-auto → graficos-auto → planejar → sincronia → render-clipe → intro → qa-master`

- **Timeline:** planos de ~2 s cortados nos picos reais de 808.
- **Cenas:** o Scene Intelligence escolhe as cenas reais pela letra. O Cenas IA (ComfyUI/SDXL, com VX Image Critic) gera cenas novas só onde o material ficou fraco.
- **Títulos e takes:** Title Card e End Card; takes de manga e tipografia automáticos.
- **Master:** limitador de true peak e fade da música. O QA reprova por imagem, decode, LUFS ou true peak.

O candidato sai em `saidas/esteira/<execucao>/`. O master do manifesto nunca é sobrescrito em silêncio.

## Lançamento

```powershell
python ferramentas\estudio.py artes-ia <slug>      # thumb 1280x720 + banner 2560x1440 + capa 3000px
python ferramentas\estudio.py shorts <slug>        # 3 Shorts 9:16 + saidas/shorts/pacote.json
python ferramentas\estudio.py lancamento <slug>    # saidas/pacote_lancamento.json (copy, tags, checagens)
```

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `ferramentas/` | módulos das duas portas (render sempre via `render_dispatch.py`, NVENC) |
| `assets/design/` | presets, temas, mapa semântico, `imagem_local.json`, `cenas_ia_map.json` |
| `assets/intro/` | intro oficial do canal (obrigatória em vídeo longo) |
| `projetos/<slug>/` | manifesto, letra, entradas, clipes, legendas, `artes_ia/`, `qa/`, `saidas/` |
| `referencias/` | material de estudo visual |
| `skills/` | skills do agente (download de música, publicação) |
| `tests/` | suíte de contratos |

## Testes

```powershell
python -m compileall -q ferramentas tests
python -m unittest discover -s tests
```

Os testes usam mocks para encode/ComfyUI e não substituem um render real na GPU.
Se sobrar um `.esteira.lock` depois de uma queda, confirme que nenhuma esteira está ativa antes de removê-lo.
