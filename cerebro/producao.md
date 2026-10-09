# Produção: música nova do zero

Procedimento oficial. A música, a letra e o personagem mudam; a arquitetura não.
Comandos a partir da raiz do repo com `.venv\Scripts\python.exe ferramentas\estudio.py <cmd>`
(abaixo abreviado como `estudio.py`).

## Princípios
- **Produção automática, laboratório manual.** Na esteira nada de palavra, preset, layout ou timestamp escolhidos à mão. `impacto-pro --word`, presets forçados e prévias existem só para testar estilos.
- **Consertar a ferramenta, nunca a música.** Comportamento automático ruim → corrigir motor/regra/config + teste. Sem `if slug == ...`; específico de anime vai em `projeto.json` ou `assets/design/`.
- **Master aprovado é intocável.** A esteira gera candidato em `saidas/esteira/<run_id>/`.

## Fontes de verdade (em conflito, vence a de cima)
1. **Letra autoral** — grafia. Nunca "corrigir" com o que o Whisper ouviu.
2. **Áudio** — ordem e tempo do que foi cantado (provado pelo `auditar-letra` e pela energia do stem vocal).
3. `transcricao_canonica.json` — letra autoral + tempos do áudio, quando existir.
4. `letra_sincronizada.json` — derivado; regenerado por `sincronizar`.
5. `entradas/transcricao.json` — ASR: relógio e evidência, não ortografia.
6. `projeto.json` — identidade, caminhos, ajustes.
7. `timeline_base.json` → `timeline.json` — a base é limpa; a timeline é recomposta a cada esteira.

## Estrutura do projeto
```text
projetos/<slug>/
├── projeto.json              # manifesto (ver campos abaixo)
├── LETRA_LINHAS.txt          # uma frase cantada por linha, NA ORDEM DO ÁUDIO; [Refrão] etc. são ignorados
├── suno_lyrics.txt           # opcional (transcricao-canonica)
├── entradas/<audio_fonte>    # padrão: <slug>_normalizado.wav
├── entradas/stems/           # gerado: <nome-do-audio>_{vocals,drums,bass,other}.wav
├── clips_raw/*.mp4           # material narrativo bruto
└── legendas/ qa/ saidas/     # gerados
```

## Passo a passo
| # | O quê | Comando / arquivo |
|---|---|---|
| 0 | Diagnóstico (ffmpeg, NVENC, GPU) | `estudio.py doutor` |
| 1 | Criar projeto (nunca por cima de um existente) | `estudio.py novo <slug>` |
| 2 | Preencher o manifesto | `projeto.json` (campos abaixo) |
| 3 | Letra autoral, uma frase por linha | `LETRA_LINHAS.txt` |
| 4 | Áudio normalizado (WAV) | `entradas/<slug>_normalizado.wav` ou `audio_fonte` |
| 5 | Clipes (sem watermark, sem card CapCut, sem splash de streaming) | `clips_raw/`; `estudio.py clipes <slug>` se `clips_fontes` tiver URLs reais |
| 6 | Conferir o plano | `estudio.py esteira <slug> --planejar` e `estudio.py etapas <slug>` |
| 7 | Produzir | `estudio.py esteira <slug>` |
| 8 | Revisão humana do candidato | `saidas/esteira/<run_id>/` |
| 9 | Usuário aprovou → promover o candidato | `estudio.py promover <slug> <run_id>` |
| 10 | **Pacote completo** (vídeo + thumb + título/descrição/tags + Shorts + textos) — obrigatório | `estudio.py entrega <slug>` · `cerebro/entrega.md` |

A esteira faz sozinha o que faltar: stems → transcrição → sincronização → timeline-base
(`pendencias_bootstrap`), depois todas as etapas de `cerebro/etapas.md`. Não é preciso rodar
`stems`, `transcrever`, `sincronizar` ou `timeline` à mão num projeto novo.

### Campos do manifesto que importam
- `personagem` — nome real; o Graphics Auto reconhece aliases por ele (o título da faixa não conta).
- `anime`, `titulo_linhas`, `cor.destaque`, `cor.destaque_claro`.
- `audio_fonte` — WAV real. Todo o sistema usa `vx/projeto.py` para achar áudio e stems.
- `letra: {"arquivo": "LETRA.txt", "linhas": "LETRA_LINHAS.txt"}`.
- `palavras_vocal` — normalmente `entradas/transcricao.json`.
- `legenda_ass` — **a única** legenda ativa; sincronizar, sincronia e render leem este caminho.
- `master` — master aprovado; nunca aponte para um candidato.
- `vocabulario` — grafia canônica dos nomes do anime (ver `cerebro/configuracao.md`).
- `imagem_ia` — tags para ComfyUI; `scene_semantics` — rótulos visuais para o matcher.
- Ajustes editoriais por música: `graphics_auto`, `cenas_ia`, `manga_auto`, `titulos`, `edicao`.

## Quando um porteiro reprova
| Porteiro | Significado | O que fazer |
|---|---|---|
| `fonte-limpa` | sobrou marca d'água/logo que o recorte/delogo não tirou | ver `qa/fonte_limpa.md`; trocar o clipe por fonte sem marca ou mover para `clips_raw/_reprovados/`. Legenda queimada não reprova: a cena só sai da escolha. "precisa do OCR" = rodar `pip install -r requerimentos.txt` (rapidocr_onnxruntime) |
| `qa-master` "QA de texto do render" | OCR leu no corpo texto que não é nosso (logo, legenda em inglês, cartela) | ver `qa/esteira/<run_id>/texto_render.json` (tempo + texto); achar o clipe na `timeline.json` e conferir `qa/fonte_limpa.md`. Texto nosso novo (card novo) → acrescentar em `fonte_limpa.corpus_permitido`, nunca afrouxar o porteiro |
| `transcrever` | "voz sem transcrição … letra pendente: …" = versos cantados sem palavra do ASR (vocalise sem letra pendente já não reprova) | a 3ª passada tenta sozinha; se continuar, ver `cerebro/incidentes/2026-09-30-douma-transcricao.md` e retranscrever; nunca apagar a linha da letra |
| `auditar-letra` | voz sem transcrição / verso não cantado / trecho cantado fora da letra | ler `qa/auditoria_letra.md`; ajustar `LETRA_LINHAS.txt` à ordem do áudio **com base no relatório**, ou `estudio.py transcrever <slug>` |
| `sincronia` | legenda fora do tempo ou linha exibida com a voz em silêncio | `estudio.py sincronizar <slug>` e reavaliar `auditar-letra` |
| `sincronia` "palavra a palavra (POV)" | palavra do POV/karaoke acende quando se canta outra palavra, ou volta no tempo | `estudio.py sincronizar <slug>` (o tempo por palavra é refeito do casamento por token); se persistir, o ASR daquele trecho está ruim: retranscrever. Ver `cerebro/incidentes/2026-10-01-douma-pov-fora-de-ordem.md` |
| motion (takes do `graficos-auto`) | palavra sumida, frase duplicada, poucos takes, cor errada | tabela de diagnóstico em `cerebro/motion.md` |
| `cenas-auto` alvo semântico | nenhuma cena satisfaz um alvo obrigatório | conferir `qa/scene_matcher/plano.json`; mais material ou ajustar `scene_semantics` |
| imagem (quase-morto, morto) | tela escura/preta | ver `imagem_suspeitos.png`; clipe com tail preto/splash vira `dead_scene` após `estudio.py catalogar-cenas <slug> --force` |
| áudio | LUFS fora de −16..−10, pico > −1 dBTP ou medição falhou | ver `qa/esteira/<run_id>/audio.json`; conferir o WAV de entrada |
| lock | outra esteira viva no projeto | esperar; lock de processo morto é removido sozinho |

## Recomeço limpo
`estudio.py rebuild-total <slug>`: backup em `backups/clean_rebuild_<slug>_<ts>/`, remove derivados
e estados, regenera sincronização e timeline-base e roda a esteira. Preserva áudio, letra,
transcrições, legendas, clipes narrativos, imagens IA e masters. `--planejar` só audita.
Com a composição a partir da base (`vx/composicao.py`), mudanças de letra ou parâmetro já entram numa
esteira normal; o rebuild é para herança antiga ou clipes trocados.

## Critério de entrega ao usuário
`estudio.py entrega <slug>` terminou com **PACOTE COMPLETO** (os 10 itens de `cerebro/entrega.md`). Nunca entregar
só o vídeo: sempre vídeo + thumb + título + descrição + tags + Shorts + textos dos Shorts.

## Critério de pronto para revisão humana
Esteira `aprovado_qa_automatico` · `auditar-letra` aprovado · suíte de testes verde ·
sem card duplicado · master anterior intocado · alguém assistiu o candidato.
