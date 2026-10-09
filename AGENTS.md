# AGENTS.md — AgentYT Pro (VX RAPS)

Estúdio automático do canal VX RAPS: música + letra + clipes de anime → AMV com intro,
legenda sincronizada e QA automático. **Toda a documentação vive em `cerebro/`.**

## Leia nesta ordem
1. `cerebro/00_LEIA_PRIMEIRO.md` — o que é, como rodar, onde está cada coisa.
2. `cerebro/producao.md` — como produzir uma música nova e o que fazer quando um porteiro reprova.
3. `cerebro/etapas.md` — etapas da esteira (gerado de `vx/etapas.py`).
4. `cerebro/ROADMAP.md` — estado da reconstrução e dívidas conhecidas.
5. `cerebro/novo_modulo.md` — receita para criar módulo/etapa nova.
6. `cerebro/motion.md` — motion sobre a cena real (estilos, cor pela letra, legenda, diagnóstico).
7. `cerebro/biblioteca_motion.md` — catálogo de efeitos (gerado de `assets/design/biblioteca_motion.json`).
8. `cerebro/entrega.md` — o pacote completo que TODA entrega precisa ter.

## Regras sagradas
1. **Intro oficial sempre no início** do vídeo longo (`assets/intro/Eu_preciso_criar_INTRO_para_o.mp4`).
2. **Só GPU (NVENC)**, via `ferramentas/render_dispatch.py`. Nunca libx264.
3. **Letra autoral é a grafia; o áudio é a ordem e o tempo.** Nunca editar a letra "no chute" a partir do ASR.
4. **Master aprovado é intocável.** A esteira gera candidato em `saidas/esteira/<run_id>/`; só o usuário aprova e só `estudio.py promover` troca o master (com backup).
5. **Consertar a ferramenta, nunca a música.** Sem script descartável, sem `if slug == ...`.
6. **Mudou código → teste de regressão + suíte verde** (`.venv\Scripts\python.exe -m unittest discover -s tests`).
7. **Porteiros não se afrouxam por projeto** (`config/porteiros.json`, decisão 002).
8. **Registrar no cérebro:** decisão nova em `cerebro/decisoes/`, falha real em `cerebro/incidentes/`, módulo novo em `cerebro/modulos.md`.
9. **Entrega = pacote completo** (`estudio.py entrega <slug>`, `cerebro/entrega.md`): vídeo + thumb + título +
   descrição + tags + Shorts + textos dos Shorts. Nunca entregar só o vídeo.

## Duas portas
| Porta | Arquivo |
|---|---|
| Criação e edição | `ferramentas/estudio.py` |
| Publicação | `ferramentas/publicar.py` |

O manual v3 anterior, completo, está preservado em `cerebro/historico/AGENTS_v3_legado.md`
(consulta histórica; onde divergir do `cerebro/`, vale o `cerebro/`).
