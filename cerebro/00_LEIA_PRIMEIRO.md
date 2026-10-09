# Cérebro do AgentYT_Pro — leia antes de mexer

Ponto de entrada para qualquer agente (Hermes, Kiro, outro). Se algo aqui conflitar com
o código, **o código e os testes vencem**; corrija este documento (`tests/test_cerebro.py`
já reprova arquivo citado que não existe, comando que não existe e módulo não catalogado).

## O que é
Estúdio automático do canal VX RAPS: música (Suno) + letra + clipes de anime →
AMV longo com intro oficial, legenda sincronizada, cenas escolhidas pela letra,
takes gráficos e QA automático. Publicação é outra porta (`ferramentas/publicar.py`).

## Como rodar (Windows, raiz do repo)
```powershell
.venv\Scripts\python.exe ferramentas\estudio.py doutor               # ambiente
.venv\Scripts\python.exe ferramentas\estudio.py etapas <slug>        # ordem e o que falta
.venv\Scripts\python.exe ferramentas\estudio.py esteira <slug> --planejar
.venv\Scripts\python.exe ferramentas\estudio.py esteira <slug>       # produção
.venv\Scripts\python.exe ferramentas\estudio.py rebuild-total <slug> # recomeço limpo, com backup
.venv\Scripts\python.exe ferramentas\estudio.py cerebro              # regenera cerebro/etapas.md
.venv\Scripts\python.exe -m unittest discover -s tests               # sempre depois de mexer
```
ffmpeg/ffprobe são resolvidos sozinhos a partir de `ferramentas/bin` (`vx/ambiente.py`).

## Regras sagradas
Ver `AGENTS.md` (8 regras). Resumo: intro sempre, só GPU, letra = grafia e áudio = ordem/tempo,
master intocável, consertar a ferramenta, teste a cada mudança, porteiro não se afrouxa, registrar no cérebro.

## Mapa do cérebro
| Assunto | Onde |
|---|---|
| Produzir uma música nova; o que fazer quando um porteiro reprova | `cerebro/producao.md` |
| Etapas da esteira: ordem, o que cada uma lê/grava (gerado) | `cerebro/etapas.md` · `vx/etapas.py` |
| Regras editoriais e visuais (cenas, takes, render, estilos) | `cerebro/editorial.md` |
| Parâmetros, porteiros, caminhos, vocabulário | `cerebro/configuracao.md` · `config/` |
| Todos os módulos e quem usa cada um | `cerebro/modulos.md` |
| Criar módulo/etapa nova (receita + checklist) | `cerebro/novo_modulo.md` |
| Motion sobre a cena real: como funciona, escolha automática, cor pela letra, protagonista, legenda, diagnóstico | `cerebro/motion.md` |
| Biblioteca de efeitos (catálogo gerado: status, gatilhos, quando usar/evitar de cada efeito) | `cerebro/biblioteca_motion.md` · `assets/design/biblioteca_motion.json` |
| Raio-x de vídeos de referência (ferramenta, métricas, lições de cada referência) | `cerebro/referencias.md` |
| **Entrega ao usuário: pacote completo obrigatório** (vídeo, thumb, título, descrição, tags, Shorts e textos) | `cerebro/entrega.md` |
| Estado da reconstrução e dívidas | `cerebro/ROADMAP.md` |
| Por que decidimos X | `cerebro/decisoes/` |
| Falhas reais e correções | `cerebro/incidentes/` |
| Manual v3 anterior (só consulta) | `cerebro/historico/AGENTS_v3_legado.md` |

## Porteiros que bloqueiam a esteira
`fonte-limpa` (marca d'água/logo por borda parada + OCR; legenda/cartela lida pelo OCR tira a cena da escolha) → `auditar-letra` (letra × áudio) →
`sincronia` (ASR + legenda × silêncio vocal + **palavra a palavra** do POV) → render (quadros contados, junção H.264 por bytes) →
decode → imagem (tela morta/quase-morta) → **texto no render** (OCR no corpo: só letra/títulos nossos) →
áudio (LUFS −16..−10, TP ≤ −1 dBTP; medição que falha reprova).

## Ciclo de uma música (resumo; detalhe em `cerebro/producao.md`)
1. Projeto em `projetos/<slug>/` com `projeto.json`, letra (`LETRA.txt`, `LETRA_LINHAS.txt`) e áudio do Suno.
2. `estudio.py clipes <slug>` baixa os clipes e já roda o `fonte-limpa`.
3. `estudio.py esteira <slug>`: bootstrap (stems, transcrição, sincronia, timeline) + produção + master.
   Sai um **candidato** em `saidas/esteira/<run_id>/`; o master atual não muda.
4. O usuário assiste. Reclamou → achar a causa, **consertar a ferramenta**, teste, registrar incidente, rodar de novo.
5. Aprovou → `estudio.py promover <slug> <run_id>` e `estudio.py entrega <slug>` (pacote completo, `cerebro/entrega.md`).
