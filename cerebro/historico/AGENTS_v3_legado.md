# AGENTS.md — Regras do AgentYT Pro (VX Studio v3)

> **Agentes: comecem por `cerebro/00_LEIA_PRIMEIRO.md`.** O sistema está em reconstrução
> incremental; o estado atual e o que falta estão em `cerebro/ROADMAP.md`. Este arquivo
> é o manual legado e está sendo migrado para `cerebro/`.

O **AgentYT_Pro** é a evolução oficial do estúdio de criação e publicação do canal **VX RAPS**.
Ele consolida a arquitetura canônica de duas portas (`estudio.py` e `publicar.py`), blindando o render em GPU e trazendo módulos visuais avançados (Motion Graphics, Optical Flow, Transições Cinemáticas e Reatividade ao 808).

---

## 🔴 REGRA SAGRADA DE OURO: A INTRO OFICIAL É OBRIGATÓRIA NO INÍCIO

**NUNCA RENDERIZAR OU PUBLICAR UM VÍDEO LONGO SEM A INTRO DO CANAL NO INÍCIO!**
- **Arquivo da Intro**: `assets/intro/Eu_preciso_criar_INTRO_para_o.mp4` (10s com logo e áudio oficial).
- **Estrutura Temporal Canônica**:
  1. **Intro do canal (10s)** com logo e áudio original de branding.
  2. **Title Card** (5s) com o início suave e fade-in da música do personagem.
  3. **AMV Principal Sincronizado** (com o master de áudio, legendas Cinzel ASS e efeitos de flow).
  4. **Outro**.
- O módulo `compositor_master_gpu.py` e a esteira `pipeline_autonomo_pro.py` estão blindados para concatenar a intro automaticamente em todo render final.

---

## 🚪 As Duas Portas Sagradas

| Porta | Arquivo | Responsabilidade |
|---|---|---|
| **Criação & Edição** | `ferramentas/estudio.py` | Timeline, cortes, filtros, áudio, karaoke, motion, artes e porteiros |
| **Publicação** | `ferramentas/publicar.py` | QA final, YouTube Longo/Shorts, TikTok, Reels, Miniaturas e Metadados |

> 🔴 **Regra de Ouro**: Se algo não funcionar, conserte a ferramenta. **Nunca crie scripts descartáveis**.
>
> `legado/` guarda scripts `temp_*` da raiz e módulos órfãos retirados de `ferramentas/` (demos, chroma duplicado, `qa_karaoke` com libx264, variantes POV não usadas, `graphics_overlay_lab`). Não importar de `legado/` em produção.

---

## ⚡ Regras de Render e Infraestrutura
1. **GPU Sempre (NVENC)**: Toda renderização passa por `render_dispatch.py` usando `h264_nvenc` preset p7 na RTX 3090. É terminantemente proibido renderizar por CPU (`libx264`).
2. **Sem Overlays Pillow Contínuos**: Legendas sempre rodam nativas via filtro ASS do FFmpeg com prefixo obrigatório `Style:`.
3. **Música Contínua**: O áudio musical começa no Title Card com fade-in suave, nunca deixando a transição da intro em silêncio.

---

## 🧭 MANUAL OPERACIONAL DO HERMES — CRIAR UMA NOVA MÚSICA DO ZERO

Esta seção é o **procedimento oficial de produção para qualquer música nova**. O Hermes deve ler esta seção antes de alterar um projeto, criar módulos ou rodar a esteira. O objetivo é manter o AgentYT_Pro genérico, reproduzível e automático: a música/letra/personagem mudam; a arquitetura não.

### Princípio central: produção automática, laboratório manual

- No fluxo de produção, **NÃO escolher manualmente palavra, preset, layout ou timestamp de tipografia**.
- `graficos-auto` deve decidir esses elementos pela letra, identidade do personagem, estrutura temporal e picos reais de 808.
- `impacto-pro --word ...`, presets forçados e tempos manuais existem somente para laboratório, comparação visual e desenvolvimento de novos estilos.
- Se um comportamento automático estiver ruim, **corrigir o motor/regra/configuração e adicionar teste**. Não criar um script descartável para uma música específica.
- Regras específicas de personagem/anime devem preferir `projeto.json`, `assets/design/` e metadados. Evitar `if slug == ...` no código de produção.
- Nunca substituir silenciosamente o master aprovado do manifesto. A esteira cria candidato novo em `saidas/esteira/<execucao>/`.

### Hierarquia das fontes de verdade

Quando houver divergência entre arquivos, usar esta prioridade:

1. **Letra autoral**: texto que o artista escreveu. Nunca corrigir a letra usando uma alucinação do ASR.
2. **`transcricao_canonica.json`**, quando existir e for confiável: letra autoral preservada + timings obtidos do áudio. O comando `sincronizar` deve priorizá-la automaticamente.
3. **`letra_sincronizada.json`**: derivado word-level. Se existir transcrição canônica, deve ser regenerado dela; não preservar uma versão antiga contaminada por ASR/timestamps impressos.
4. **`entradas/transcricao.json`**: Whisper/ASR é relógio e evidência; não é autoridade ortográfica.
5. **`projeto.json`**: identidade, caminhos, cores, personagem, anime e configurações do projeto.
6. **`timeline.json`**: montagem temporal atualmente aplicada.
7. **`qa/vx_graphics_auto/state.json`**: estado/base do Graphics Auto para idempotência e recuperação.

Nunca usar a grafia errada do Whisper para substituir nomes canônicos, técnicas, clãs ou versos oficiais. Um `LETRA_LINHAS.txt` antigo contendo prefixos como `12.10s | 17.00s | ...` ou nomes corrompidos pelo ASR é legado e **não pode vencer `transcricao_canonica.json`/letra autoral**.

### Estrutura mínima recomendada de um projeto novo

```text
projetos/<slug>/
├── projeto.json
├── LETRA_LINHAS.txt              # recomendado: uma frase cantada por linha
├── LETRA.txt / LETRA.md           # opcional conforme o projeto
├── suno_lyrics.txt                # opcional; usado pelo fluxo canônico atual
├── entradas/
│   ├── <slug>_normalizado.wav     # nome esperado pelo preflight da esteira
│   ├── transcricao.json
│   └── stems/
│       ├── <slug>_normalizado_vocals.wav
│       ├── <slug>_normalizado_drums.wav
│       ├── <slug>_normalizado_bass.wav
│       └── <slug>_normalizado_other.wav
├── clips_raw/
├── legendas/
├── qa/
└── saidas/
```

`catalogo_cenas.json`, frames de capa e outros artefatos são adicionados quando o projeto usar esses módulos.

### PASSO 0 — Diagnóstico do estúdio

Antes de começar um projeto novo:

```powershell
python ferramentas\estudio.py doutor
```

Confirmar FFmpeg/FFprobe, NVENC e ambiente da RTX 3090. Corrigir infraestrutura antes de produzir.

### PASSO 1 — Criar o projeto

```powershell
python ferramentas\estudio.py novo <slug>
```

Exemplo:

```powershell
python ferramentas\estudio.py novo luffy_nika
```

O comando cria `projetos/<slug>/projeto.json` e a estrutura inicial de capa. Não rodar `novo` por cima de projeto existente.

### PASSO 2 — Preencher `projeto.json`

Para produção longa, preencher no mínimo identidade e caminhos reais. Modelo recomendado:

```json
{
  "faixa": "NOME DA FAIXA",
  "personagem": "Nome Canônico do Personagem",
  "anime": "Nome do Anime",
  "titulo_linhas": ["TÍTULO", "PERSONAGEM"],
  "cor": {
    "destaque": "#7B1FA2",
    "destaque_claro": "#00E5FF"
  },
  "audio_fonte": "entradas/<slug>_normalizado.wav",
  "letra": {
    "arquivo": "LETRA.txt",
    "linhas": "LETRA_LINHAS.txt"
  },
  "palavras_vocal": "entradas/transcricao.json",
  "clips_dir": "clips_raw",
  "legenda_ass": "legendas/<slug>.ass",
  "master": "saidas/<slug>_master.mp4"
}
```

Também preencher `arte`, `clips_fontes`, `_notas_canon` e outros campos quando disponíveis.

#### Regras do manifesto

- `personagem` deve conter a identidade real do personagem; o Graphics Auto usa esse campo para reconhecer nomes/aliases.
- O título da faixa **não conta automaticamente como nome do personagem**.
- `audio_fonte` deve apontar para o WAV normalizado real.
- Para a esteira atual, manter também o arquivo físico `entradas/<slug>_normalizado.wav`.
- `palavras_vocal` deve normalmente apontar para `entradas/transcricao.json`.
- `legenda_ass` é a única legenda ativa de produção. `sincronizar`, o gate `sincronia` e `render-clipe` devem ler/gravar exatamente esse mesmo caminho do manifesto; nunca gerar `legendas/<slug>.ass` e renderizar outro ASS legado em paralelo.
- `legenda_ass` deve existir e conter `Style:` e `Dialogue:` antes do preflight final.
- Ao regenerar a legenda canônica, preservar backup do ASS anterior antes de substituir o arquivo ativo.
- Não apontar `master` para um candidato temporário.

### PASSO 3 — Colocar a letra autoral

Preferência: `LETRA_LINHAS.txt`, com **uma frase cantada por linha**, na ordem da música.

Exemplo:

```text
Olhos vermelhos na escuridão
Você não conhece a dor de perder tudo em uma noite
Agora o mundo vai queimar
Eu sou o vingador
```

A letra é fonte de verdade. O ASR serve para localizar quando cada palavra foi cantada.

Se o projeto usar `LETRA.txt` com timestamps, respeitar o formato já suportado pelo sincronizador. Não inventar timestamps manualmente quando o áudio puder fornecê-los.

### PASSO 4 — Preparar o áudio

O master de trabalho da música deve estar em:

```text
projetos/<slug>/entradas/<slug>_normalizado.wav
```

Formato de trabalho esperado: WAV estável para análise, stems e sincronização.

Nunca alterar a duração do áudio depois que transcrição, timeline e Graphics Auto estiverem aprovados sem regenerar os derivados temporais.

### PASSO 5 — Material visual

Colocar/obter clipes em `clips_raw/`. Se `clips_fontes` estiver corretamente configurado com fontes reais, pode-se usar:

```powershell
python ferramentas\estudio.py clipes <slug>
```

Se as URLs forem placeholders, **não fingir download bem-sucedido**. Providenciar material válido primeiro.

Auditar material quando necessário:

```powershell
python ferramentas\estudio.py curadoria <video.mp4>
python ferramentas\estudio.py movimento <video.mp4>
```

Evitar watermarks, cartões CapCut, baixa resolução e fontes inadequadas.

### PASSO 6 — Stems e transcrição

A esteira produz stems se eles estiverem ausentes, mas durante o bootstrap é válido gerar explicitamente:

```powershell
python ferramentas\estudio.py stems projetos\<slug>\entradas\<slug>_normalizado.wav --saida projetos\<slug>\entradas\stems
```

Depois gerar ASR word-level:

```powershell
python ferramentas\estudio.py transcrever <slug> --modelo large-v3
```

Saída esperada:

```text
entradas/transcricao.json
```

A transcrição precisa cobrir o áudio vocal de forma suficiente para sincronização. Nomes errados do Whisper não autorizam alterar a letra autoral.

### PASSO 6.5 — Porteiro LETRA x ÁUDIO (obrigatório, a esteira já chama)

```powershell
python ferramentas\estudio.py auditar-letra <slug>
```

Relatório em `qa/auditoria_letra.md`. Reprova (e a esteira para antes de renderizar) quando:
- há **voz no stem vocal sem nenhuma palavra transcrita** (o Whisper pulou trecho cantado);
- uma **linha da letra não aparece no áudio** (o Suno pulou/trocou o verso);
- há **trecho cantado que não está na letra** (vai ficar sem legenda; ex.: o Suno reordenou um refrão).

Blocos de alucinação do Whisper (confiança média baixa) aparecem como "ruído do ASR" e não reprovam.
Correção: ajustar `LETRA_LINHAS.txt` à **ordem que o áudio realmente canta** (a grafia continua autoral) ou retranscrever. Nunca remover um bloco da letra "no chute": confira o relatório linha a linha.

Regras da transcrição (`transcrever`), aprendidas no Gojo:
- fonte = stem vocal; Whisper `large-v3` em blocos de 30 s com sobreposição (passada única pulou 27 s cantados);
- 2ª passada **sem prompt** só nas lacunas de voz (o prompt com a letra faz o Whisper "achar" que já cantou o trecho);
- remove alucinações conhecidas ("inscreva-se", "sininho", "tchau"...) e palavras degeneradas (prob ~0 esticada por segundos);
- marcadores `[Intro]`, `[Verso]`, `[Refrão]` nunca viram legenda nem prompt;
- o alinhador (`sincronizar_letra.alinhar`) é monótono token a token: refrões repetidos ficam na própria ocorrência.

### PASSO 7 — Sincronizar letra e gerar legenda

Para um projeto novo, antes de existir timeline canônica:

```powershell
python ferramentas\estudio.py sincronizar <slug>
```

Isso gera `letra_sincronizada.json` e, no fluxo padrão, `legendas/<slug>.ass`.

Depois garantir que `projeto.json -> legenda_ass` aponta para a legenda que realmente será queimada no master.

Se usar outro gerador de legenda (Mugen, karaoke, neon etc.), atualizar `legenda_ass` deliberadamente e validar sincronia. Nunca queimar duas legendas simultaneamente.

### PASSO 8 — Transcrição canônica: opcional e controlada

`transcricao_canonica.json` é a melhor entrada para o Graphics Auto quando existe: mantém a grafia autoral e usa o áudio apenas como evidência/timing.

O comando atual:

```powershell
python ferramentas\estudio.py transcricao-canonica <slug>
```

usa `suno_lyrics.txt` e atualmente contém vocabulário canônico específico herdado do projeto Sasuke. **Não tratar esse comando como obrigatório para todo anime até o vocabulário ser generalizado.**

Mesmo sem `transcricao_canonica.json`, o `graphic_auto_pipeline.py` já faz fallback seguro:
- usa `letra_sincronizada.json`, se existir;
- ou alinha a letra autoral do manifesto ao `entradas/transcricao.json`;
- só em último caso cai em frases derivadas do ASR.

### PASSO 9 — Construir a timeline-base

Depois de `letra_sincronizada.json` e dos clipes:

```powershell
python ferramentas\estudio.py timeline <slug>
```

A timeline deve cobrir **0 até o fim do áudio sem lacunas/sobreposições** e sem exceder a duração das fontes. O builder deve ignorar assets derivados (`impact_*`, `take_saber_*`, `take_chroma_*`, `vx_graphics_*`, overlays/demos e diretórios auto) e usar somente clipes narrativos brutos. Micro-gaps/overlaps word-level inferiores a 150 ms são ajustados na fronteira editorial para manter cobertura contínua.

Não inserir manualmente Graphics Auto neste momento. Primeiro construir uma timeline-base válida e limpa.

**Ritmo de edição:** `montar_timeline.subdividir` quebra janelas longas em planos de até 2.6 s (cantado) / 3.2 s (intro/gap/outro), cortando no pico de 808 mais próximo (cache `qa/vx_graphics_bass_peaks.json`), no grid de 30 fps e com mínimo de 0.9 s. Cada pedaço mantém linha/texto, então o Scene Matcher escolhe uma cena diferente para cada um. Ajuste por projeto em `projeto.json -> edicao` (`max_plano_lyric`, `max_plano_outros`, `min_plano`, `janela_snap`). Referência Sasuke: 16 → 30 CPM, retenção estimada 40 → 100.

### PASSO 9.5 — VX Scene Intelligence + Cenas Auto

Antes do Graphics Auto, a produção deve decidir **qual cena do anime combina com cada trecho da letra**. O fluxo oficial usa dois módulos:

- `scene_intelligence.py`: analisa o conteúdo real de `clips_raw/*.mp4` e cria `scene_intelligence.json`.
- `semantic_scene_matcher.py`: cruza letra/narrativa com esse catálogo e atualiza os segmentos normais da timeline.

Portas:

```powershell
python ferramentas\estudio.py catalogar-cenas <slug>
python ferramentas\estudio.py cenas-auto <slug>
```

Para auditoria sem alterar a timeline:

```powershell
python ferramentas\estudio.py cenas-auto <slug> --planejar
```

#### O que o Scene Intelligence mede

Por cena: movimento/optical flow, direção predominante, brilho, contraste, saturação, nitidez, densidade de borda, razão de sombras/luzes, presença de rosto quando detectável, centralidade do sujeito, cores dominantes e scores semânticos visuais como `action`, `fight`, `impact`, `fire`, `blood`, `electric`, `purple_energy`, `dark`, `calm`, `portrait`, `closeup`, `power` e `destruction`.

O catálogo divide scene packs longos em janelas visuais menores e marca assets gerados pelo próprio sistema (`impact_*`, Saber, Chidori chroma, demos etc.) como **não elegíveis** para seleção narrativa normal.

#### Cache

`scene_intelligence.json` guarda fingerprint por tamanho + `mtime_ns`. Clipe sem alteração é reutilizado; não reanalisar centenas de frames em toda esteira. Use `catalogar-cenas --force` somente quando precisar invalidar o cache intencionalmente.

#### Como o matcher escolhe

O `semantic_scene_matcher.py` lê o texto do segmento. Se `note` estiver vazio, recupera automaticamente a linha autoral/canônica que cruza aquele intervalo. Depois pontua as cenas por:

1. compatibilidade semântica letra ↔ tags visuais;
2. proximidade da intensidade desejada;
3. qualidade visual;
4. duração disponível;
5. penalidade de repetição de clip/cena.

Exemplos já validados no Sasuke:
- `CHAMAS DO AMATERASU` → cenas com `fire`;
- `KIRIN / TROVÃO` → `electric/energy`;
- `ÓDIO / VINGANÇA` → `fight/impact`;
- identidade/personagem → `portrait/closeup/center_subject` quando disponível.

Cenas especiais (`impact_typography`, Saber, Graphics Auto etc.) são protegidas e nunca devem ser substituídas pelo matcher.

#### Idempotência e ordem obrigatória

A ordem de produção é **`cenas-auto` -> `cenas-ia` -> `titulos` -> `manga-auto` -> `graficos-auto`**. O Scene Matcher grava estado em `qa/scene_matcher/`. Se a timeline já contiver `vx_graphics_auto`, a aplicação normal de `cenas-auto` preserva a timeline e não tenta rebasear silenciosamente o estado do Graphics Auto. Para recalcular seleção depois de uma grande mudança de clipes/letra, regenere a timeline-base e rode os estágios novamente na ordem oficial.

#### Regra de legado

Os diretores antigos (`selecao_cenas`, `catalogo_cenas`, `diretor_semantico`) foram removidos. A sele??o de cenas ? exclusivamente `scene_intelligence.py` + `semantic_scene_matcher.py`.

### PASSO 9.7 — VX Cenas IA (ComfyUI gera cenas novas)

Módulo `cenas_ia_pipeline.py`. Porta: `estudio.py cenas-ia <slug> [--planejar]` (a esteira já chama).

- **Cena real do anime sempre vence.** A IA só entra em trechos cantados onde o Scene Matcher ficou fraco: `scene_match.score < max_match_score` (0.36) ou alvo semântico obrigatório reprovado. Alvos `entity:*` (outro personagem) não contam: SDXL não desenha esse personagem com fidelidade.
- **Prompt 100% automático:** conceitos da letra (`semantic_scene_matcher.CONCEPTS`) + palavras concretas + alvos → tags SDXL via `assets/design/cenas_ia_map.json`, somados à identidade `projeto.json -> imagem_ia` (`tags_personagem`, `tags_alvos` opcional por id de alvo). Expandir o mapa/manifesto, nunca o Python.
- Raro: `max_scenes=4`, `min_gap_seconds=20`, 1.2–3.2 s, guardas de intro/outro, sem repetir a mesma linha. Override por projeto em `projeto.json -> cenas_ia`.
- **VX Image Critic** (`critico_imagem.py`, OpenCLIP local): cada cena gera `variacoes` (3) e o crítico pontua alinhamento com a intenção + identidade do personagem (`imagem_ia.clip_identidade`) + qualidade (contra blur/anatomia quebrada/texto) + exposição. Só a vencedora fica em disco; ranking em `artes_ia/escolhas.json` (rerodar reaproveita a escolha).
- Cada imagem vira take 1080p30 com câmera própria (push_in, pan_lr, pull_out, pan_rl, rise; zoompan com easing sobre upscale 4K + grão/vinheta) em NVENC → `clips_raw/vx_cenas_ia/`. Segmento `type = vx_cena_ia`, sempre `graphics_locked` no plano.
- ComfyUI sobe sozinho se estiver offline (e desliga ao final se foi o estúdio que subiu). Indisponível = estágio pulado com aviso; `cenas_ia.strict=true` torna obrigatório.
- Idempotente: `qa/vx_cenas_ia/state.json` + `plano.json` (prompts auditáveis). Timeline aplicada editada por fora = falha fechada. Imagens ficam em `artes_ia/` (cache determinístico; o `rebuild-total` preserva).

### PASSO 9.8 — VX Títulos (Title Card + End Card)

Módulo `titulos_pipeline.py`. Porta: `estudio.py titulos <slug> [--planejar]` (a esteira já chama).

- Title Card nos primeiros `title_dur` (5 s) do corpo, só antes da 1ª frase cantada (folga 0.4 s; encolhe até 2.5 s ou é pulado). Fundo = capa IA escolhida pelo VX Image Critic com push-in; tipografia "VX RAPS APRESENTA" + faixa (Cinzel com glow na cor destaque) + personagem • anime + kanji do manifesto.
- End Card nos últimos `end_dur` (5 s), só depois da última frase: fundo IA escurecido, marca + CTA + handle, fade para preto.
- Música: `concatenar_intro` aplica fade-in de 1.2 s no início do corpo e fade-out de 2.5 s no fim, além do limitador de true peak.
- Sem ComfyUI, usa frame real do anime como fundo. Tipos `vx_title_card`/`vx_end_card` são `graphics_locked`, protegidos pelos estágios seguintes e tratados como downstream pelo Scene Matcher e pelo Cenas IA.
- Config por projeto: `projeto.json -> titulos` (`enabled`, `title_dur`, `end_dur`, `cta`, `marca`, `handle`).

### PASSO 10 — VX Graphics Auto

#### Regra de produção

Na produção normal, não chamar com `--word`, preset ou timestamp. A porta é:

```powershell
python ferramentas\estudio.py graficos-auto <slug>
```

Na esteira oficial esse estágio já é chamado automaticamente antes de `planejar`.

Para apenas inspecionar a decisão, sem tocar na timeline:

```powershell
python ferramentas\estudio.py graficos-auto <slug> --planejar
```

#### Como o Graphics Auto decide

O motor:
1. carrega letra canônica/autoral;
2. localiza as palavras no tempo;
3. identifica palavras semanticamente fortes;
4. reconhece nome/identidade pelo campo `personagem`;
5. cruza o trecho com picos de 808/subgrave;
6. calcula score combinado;
7. protege cenas especiais já existentes;
8. aplica espaçamento editorial;
9. impede repetição de palavra;
10. escolhe preset/layout/tema automaticamente;
11. renderiza o take em NVENC;
12. divide a timeline original exatamente nos limites do take;
13. injeta o segmento `vx_graphics_auto`;
14. valida novamente a timeline antes de promover.

#### Defaults editoriais atuais

Valores padrão em `graphic_auto_pipeline.py`:

```text
max_scenes                = 6
min_gap_seconds           = 9.0
max_per_minute            = 2
min_score                 = 0.56
intro_guard_seconds       = 8.0
outro_guard_seconds       = 4.0
protect_existing_specials = true
```

Além disso, o número efetivo é naturalmente limitado pela duração da música; o motor não tenta preencher o clipe inteiro com cards.

#### Estilos e semântica

O mapa semântico vive em:

```text
assets/design/semantic_style_map.json
```

Exemplos existentes:
- sangue/ódio/vingança -> `blood_burn` / brutal;
- fogo/chamas -> `fire_burst`;
- destruição -> `manga_brutal_pro`;
- raio/chidori/kirin -> `thunder_strike`;
- clã/rei/lore -> `cinematic_gold` / `neon_royal`;
- nomes do personagem -> família neon de escrita.

Para nomes reconhecidos, rotacionar entre:
- `neon_write_on`;
- `neon_letter_reveal`;
- `neon_outline_fill`;
- `neon_trace`.

Não hardcodar uma nova música dentro do Python para obter um preset. Expandir o mapa/configuração e testes.

#### Legenda-aware

Se `legenda_ass` estiver configurada, o take automático **não deve repetir a frase inteira** no próprio card. A palavra dominante vira o elemento de motion design e a legenda oficial continua carregando a linha completa.

Isso evita o problema visual de frase no card + mesma frase na legenda e reduz competição de hierarquia.

#### Proteção do plano de câmera

Todo segmento injetado recebe:

```text
type = vx_graphics_auto
preset do plano = graphics_locked
camera = 1.0 -> 1.0
efeitos extras = []
```

Motivo: o take já contém seu próprio motion. `direcao_clipe.py` não deve adicionar zoom/pan/flash sobre ele.

### Idempotência, cache e recuperação do Graphics Auto

Arquivos:

```text
clips_raw/vx_graphics_auto/        # MP4s automáticos + .design.json
qa/vx_graphics_auto/plano.json     # decisão auditável
qa/vx_graphics_auto/state.json     # timeline-base + hashes + estado aplicado
qa/vx_graphics_bass_peaks.json     # cache dos picos de subgrave
```

Regras:
- Rodar `graficos-auto` novamente **não pode duplicar** segmentos.
- Se o `.design.json` for igual e o MP4 existir, reutilizar o render.
- Se uma timeline com `vx_graphics_auto` foi modificada externamente e o hash não bate, **falhar fechado** em vez de sobrescrever edição desconhecida.
- No Windows, se `os.replace` for bloqueado por editor/antivírus, `_atomic_json` mantém backup `.vxg.bak` antes do fallback de escrita.
- Para reconstruir intencionalmente após grande mudança de letra/clipes, regenere a timeline-base com `estudio.py timeline <slug>` e depois aplique `graficos-auto` novamente. Não apagar segmentos no braço sem entender o `state.json`.

### PASSO 11 — Planejamento visual

Depois que o Graphics Auto estiver aplicado:

```powershell
python ferramentas\estudio.py planejar <slug>
```

Saída:

```text
plano_visual.json
```

O plano deve enxergar os takes gráficos já presentes na timeline e respeitar `graphics_locked`.

### PASSO 12 — Preflight antes do master

```powershell
python ferramentas\estudio.py esteira <slug> --planejar
```

O resultado deve retornar `aprovado: true`.

O preflight verifica, entre outros:
- áudio normalizado;
- intro oficial;
- `legenda_ass`;
- ASS com `Style:` e `Dialogue:`;
- FFmpeg/FFprobe;
- timeline válida;
- fontes dos segmentos.

Não iniciar render longo com preflight reprovado.

### PASSO 13 — Esteira oficial

Quando o bootstrap do projeto estiver pronto:

```powershell
python ferramentas\estudio.py esteira <slug>
```

Ordem atual:

```text
[bootstrap de projeto novo, só o que faltar: stems -> transcrever -> sincronizar -> timeline]
stems
-> transcrever (se necessário)
-> auditar-letra     (letra x áudio: ordem, versos faltando, voz sem transcrição)
-> auditar-ritmo
-> cenas-auto
-> cenas-ia          (ComfyUI auto-inicia; pula com aviso se indisponível)
-> titulos           (Title Card 0-5s + End Card nos últimos 5s; fallback frame real)
-> manga-auto
-> graficos-auto
-> planejar
-> sincronia
-> render-clipe
-> intro             (com limitador de true peak)
-> qa-master         (decode + imagem + áudio: LUFS -16..-10 e true peak <= -1 dBTP bloqueiam)
```

Projeto novo com `projeto.json`, WAV normalizado, letra e `clips_raw/` já pode ir direto para `esteira <slug>`: `pendencias_bootstrap` detecta o que falta (stems, transcrição, legenda do manifesto, timeline-base) e gera antes do preflight completo. `esteira --planejar` lista essas pendências em `bootstrap`.

### Rebuild limpo obrigatório quando houver herança de produção antiga

Quando um projeto antigo contiver timeline/cards/takes de gerações anteriores, usar:

```powershell
python ferramentas\estudio.py rebuild-total <slug>
# equivalente:
python ferramentas\estudio.py esteira <slug> --rebuild-clean
```

O `rebuild-total` cria backup em `backups/clean_rebuild_<slug>_<timestamp>/`, isola assets derivados/legados, remove estados/cache de Scene Matcher, Cenas IA, Títulos, Manga Auto e Graphics Auto (o catálogo `scene_intelligence.json` é cache por fingerprint e fica), regenera sincronização oficial, cria uma timeline-base apenas com fontes narrativas e executa toda a esteira nova. Áudio, letra/canônica, transcrições, legendas, clipes narrativos e masters anteriores são preservados. **Nunca apagar legado diretamente sem backup.**

Use `rebuild-total --planejar` para auditar a rota sem modificar arquivos. O rebuild é a porta correta quando o objetivo for avaliar a geração atual do sistema sem mistura com uma timeline histórica.

A esteira:
- cria lock `.esteira.lock`;
- cria um `run_id`;
- grava logs por etapa em `qa/esteira/<run_id>/`;
- renderiza o corpo;
- concatena a intro oficial;
- decodifica/valida o candidato;
- passa pelo gate de imagem;
- preserva o master aprovado do manifesto.

### PASSO 13.5 — Pacote de lançamento

Depois do master aprovado:

```powershell
python ferramentas\estudio.py artes-ia <slug>      # thumb + banner + capa streaming (IA local)
python ferramentas\estudio.py shorts <slug>        # 3 shorts 9:16 + saidas/shorts/pacote.json
python ferramentas\estudio.py lancamento <slug>    # saidas/PUBLICACAO.md + pacote_lancamento.json
```

`publicacao_doc.py` monta o documento de publicação a partir do projeto: 4 títulos (principal + A/B, ≤100), descrição completa (gancho, capítulos com offset da intro oficial, letra por seção Verso/Refrão/Final, créditos, hashtags; ≤5000), tags (≤500), comentário fixado, checklist do upload e copy dos Shorts/TikTok/Reels. Overrides em `projeto.json -> lancamento` (`titulo`, `descricao`, `tags`, `creditos`, `links`, `comentario_fixado`).

`shorts_pipeline.py` escolhe os trechos pela letra + energia (começa numa frase, termina no fim de outra, favorece refrão e takes especiais, sem sobreposição), gera o gancho da frase mais intensa (ou `projeto.json -> shorts.ganchos`), renderiza fonte limpa da própria timeline e aplica o layout POV oficial com letra word-by-word. Palavras em destaque vêm de `scene_semantics` (ações) + faixa. Títulos/descrições/TikTok ficam em `pacote.json`.

### PASSO 14 — Prévia visual durante desenvolvimento

Para conferir um intervalo sem renderizar tudo:

```powershell
python ferramentas\estudio.py previa-clipe <slug> --de 43.8 --dur 3.2 --legenda
```

Usar prévias para validar entrada/saída de Graphics Auto, legibilidade, ausência de texto duplicado, continuidade com a cena anterior/posterior e sincronização com a frase/beat.

Uma prévia é ferramenta de QA; não substituir a validação final da esteira.

### PASSO 15 — Testes obrigatórios depois de mexer no sistema

Após alterar pipeline, Graphics Auto, render, timeline, tipografia ou direção:

```powershell
python -m compileall -q ferramentas tests
python -m unittest discover -s tests -v
```

Não considerar a mudança concluída com teste vermelho.

Ao adicionar uma feature, criar regressão correspondente. Exemplos já cobertos:
- seleção semântica;
- alias do personagem;
- espaçamento entre cards;
- proteção de cenas especiais;
- split correto da timeline e avanço de `src`;
- fallback para letra autoral;
- `graphics_locked`;
- animações neon;
- idempotência estrutural.

### Como desenvolver novos estilos sem quebrar produção

Quando quisermos testar algo novo:
1. implementar como preset/módulo reutilizável;
2. colocar parâmetros em `assets/design/` quando possível;
3. adicionar teste;
4. testar isoladamente via `impacto-pro`;
5. gerar preview;
6. só depois permitir que `graficos-auto` selecione o estilo;
7. manter anti-repetição e limites editoriais;
8. rodar suíte completa.

Não promover diretamente uma experiência visual nova para todas as músicas sem fallback e teste.

### Limitações atuais que o Hermes deve respeitar

- Scene Intelligence atual usa heurísticas visuais OpenCV offline. Um encoder visual profundo (CLIP/SigLIP) ainda é evolução futura/opcional; não tornar o pipeline dependente de download de modelo sem fallback local.
- Graphics Auto de produção atualmente injeta **takes full-scene**, substituindo aquele pequeno intervalo da timeline.
- **Overlay automático sobre a cena do anime NÃO é contrato de produção do Graphics Auto.** O protótipo `graphics_overlay_lab.py` foi testado visualmente e rejeitado para produção: mesmo com personagem recortado e tipografia atrás do corpo, o resultado ficou artificial/colado em comparação com os cards e takes gráficos full-scene. Não habilitar na esteira nem promover esse efeito sem uma solução visual claramente superior (segmentação/tracking/composição de nível profissional) e nova aprovação visual.
- `transcricao-canonica` atual ainda carrega vocabulário específico de Sasuke; generalizar antes de torná-lo etapa universal.
- Title Card e End Card são do `titulos_pipeline.py`. SFX sintético (`sfx_engine.py`) não entra no master: soa artificial sobre a mix da música.
- `render_dispatch` só grava `<saida>.encode.log` quando o encode falha; o Demucs não deixa mais a árvore `htdemucs/` duplicada.
- A intro oficial continua sendo acrescentada depois do corpo pela esteira.
- Publicação continua separada em `publicar.py`.

### Critério de sucesso de uma música nova

Antes de considerar um projeto pronto para revisão humana, confirmar:
- `projeto.json` coerente;
- letra autoral preservada;
- `auditar-letra` aprovado (toda voz transcrita, toda linha achada, nada cantado fora da letra);
- cenas mortas (tela preta, splash de streaming tipo Prime/Netflix) marcadas `dead_scene` no catálogo e fora da timeline;
- áudio normalizado presente;
- ASR word-level válido;
- legenda sincronizada e apontada no manifesto;
- timeline sem erros;
- Scene Intelligence catalogando apenas fontes narrativas elegíveis;
- `cenas-auto` escolhendo cenas pela letra/conteúdo visual antes do Graphics Auto;
- Graphics Auto usando letra/beat automaticamente;
- nenhum card duplicado após reexecução;
- plano com cards `graphics_locked`;
- preflight aprovado;
- suíte de testes verde;
- candidato final gerado pela esteira e aprovado no QA automático;
- master aprovado anterior não foi sobrescrito.

### Regra final para o Hermes

**O Hermes deve melhorar o sistema, não “resolver a música” com exceções locais.**

Ao receber uma música nova:
- configurar dados do projeto;
- alimentar letra, áudio e material;
- usar as portas oficiais;
- observar QA;
- corrigir módulos genéricos quando houver falha;
- documentar mudanças relevantes aqui;
- preservar idempotência, NVENC, fonte autoral e segurança do master.

---

## 🚀 Novos Módulos Visuais e de Impacto (v3 Pro)

O `AgentYT_Pro` conta com os seguintes módulos de vanguarda:

### 1. `impact_frames.py` (`estudio.py impacto <PALAVRA>`)
- Tipografia brutalista de mangá/anime no centro da tela para clímax (ex: "TATAKAE", "EXPANSÃO", "ARISE").
- Gera sequências animadas PNG RGBA com Snap Zoom de entrada (1.35x -> 1.0x), contorno preto, kanji decorativo de fundo e auras neon personalizadas.

### 2. `transicoes_vfx.py`
- Transições de flow anime com aceleração de câmera:
  - `whip_pan`: Puxada lateral com directional blur.
  - `zoom_in_punch`: Snap zoom na batida.
  - `glitch_rgb`: Aberração cromática em 3 frames no compasso.
  - `flash_cut`: Flash branco com decaimento exponencial.

### 3. `bass_shake.py` (`estudio.py subgrave <audio.wav>`)
- Isola frequências < 120Hz via Librosa e extrai os picos exatos de 808/kick.
- Dispara tremores de câmera com aberração cromática (RGB split) perfeitamente síncronos com o sub-grave.

### 4. `analisador_movimento.py` (`estudio.py movimento <video.mp4>`)
- Mede vetores de **Optical Flow (Farneback)** via OpenCV.
- Identifica os "Hit Frames" (o frame exato do soco, corte de lâmina ou explosão) para ancorar os cortes no milissegundo do drop.

### 5. `curadoria_ia.py` (`estudio.py curadoria <video.mp4>`)
- Escaneia clipes brutos (twixtor / scene packs) e rejeita logos estáticos de streaming (Crunchyroll, VIZ) nos 4 cantos.
- Corta automaticamente os cartões finais de CapCut dos últimos 5 segundos.

### 7. `color_grade_pro.py` (`estudio.py colorgrade <estilo>`)
- Color grading cinemático dinâmico calibrado por arquétipo de anime:
  - `titan_fire` (Attack on Titan / Eren): tons âmbar e fogo, alto contraste.
  - `cursed_energy` (Jujutsu Kaisen / Sukuna): azul profundo e sangue vívido.
  - `dark_shadow` (Solo Leveling / Jin-Woo): tons frios monarca e ciano brilhante.
  - `demon_blood` (Demon Slayer / Akaza): magenta dramático e sombras escuras.

### 8. `cinemascope_fx.py` (`estudio.py cinemascope`)
- Barras pretas anamórficas 2.39:1 com abertura suave de cortina na introdução.

### 9. `speedlines_manga.py` (`estudio.py speedlines`)
- Geração procedural de linhas de ação/velocidade shonen convergindo para o centro com o rosto protegido.

### 11. `stems_ia_gpu.py` (`estudio.py stems <audio>`)
- Separação de stems em 4 faixas (vocal, drums, bass, other) usando Demucs via CUDA na RTX 3090.
- Permite que o Whisper transcreva apenas a voz isolada e que os efeitos de shake reajam apenas ao 808 puro.

### 13. `motion_blur_pro.py` (`estudio.py motionblur <in.mp4> <out.mp4>`)
- Simulação de RSMB (ReelSmart Motion Blur) calculando vetores de Optical Flow.
- Transforma animações de anime de 12/24fps em movimentos cinematográficos fluidos.

### 14. `gerador_tumbas_ab.py` (`estudio.py tumbas-ab <frame> <slug>`)
- Criação automática de miniaturas A/B de alto CTR (Variação A: foco no olhar com vinheta; Variação B: impacto de corte com tarja e tipografia agressiva).

### 15. `gerador_artes_ia.py` (`estudio.py capa-ia <slug> [--motor local|remoto] [--prompt "tags"] [--seed N] [--ref frame.jpg] [--variacoes 4]`)
- Pacote de lançamento completo: `estudio.py artes-ia <slug>` → thumb YouTube + banner do canal 2560x1440 (safe area) + capa de streaming 3000x3000, todas com base IA escolhida pelo VX Image Critic, em `saidas/`.
- Miniatura YouTube 1280x720 (<2MB, pronta para `publicar.py miniatura`) em `projetos/<slug>/saidas/<slug>_capa_ia.jpg`.
- **Motor padrão `local`**: VX Image Local (ComfyUI + SDXL na RTX 3090). Ver seção VX Image Local.
- **Motor `remoto`**: API compatível com OpenAI Images, configurada SOMENTE por ambiente (`VX_IMAGE_API_URL`, `VX_IMAGE_API_KEY`, `VX_IMAGE_API_MODEL`). **Nunca gravar chave de API em código.**
- Kanji, tags e descrição vêm de `projeto.json -> imagem_ia`; sem `if personagem` no código.
- Pós-processamento: contraste/cor, scrim do texto, kanji vertical, partículas na `cor.destaque_claro` (seed fixa), tipografia 3D.

### VX Image Local — geração de imagens na GPU (ComfyUI + SDXL)
- Módulo: `ferramentas/gerador_imagem_local.py`. Config: `assets/design/imagem_local.json` (checkpoint, sampler, steps, cfg, formatos, estilos, negativos).
- Checkpoint padrão: `animagine-xl-3.1.safetensors` (SDXL anime). ~17s por imagem 1344x768 na 3090.
- **Autoconfigurável:** se o ComfyUI estiver offline, o estúdio o localiza (`comfy_dir` no config, `VX_COMFY_DIR` ou pastas comuns como `~/Documents/comfy/ComfyUI`), sobe com `--disable-pinned-memory` (log em `logs/comfyui.log`, pid em `logs/comfyui.pid`) e espera ficar online. Só auto-inicia em localhost. `auto_iniciar: false` desliga. Se o checkpoint configurado sumir, usa o primeiro SDXL disponível e avisa.
  ```powershell
  python ferramentas\estudio.py comfy-status --iniciar
  python ferramentas\estudio.py comfy-parar      # só mata o ComfyUI que o estúdio subiu
  ```
  Overrides por ambiente: `VX_COMFY_URL`, `VX_COMFY_CHECKPOINT`, `VX_COMFY_DIR`.
- Portas:
  ```powershell
  python ferramentas\estudio.py comfy-status
  python ferramentas\estudio.py gerar-imagem <slug> --tipo capa|fundo|vertical|quadrado [--cena "tags"] [--variacoes N] [--seed N]
  python ferramentas\estudio.py gerar-imagem <slug> --tipo capa --ref frames_capa\hd\t_20.0.jpg --denoise 0.55   # img2img a partir de frame real
  ```
- Identidade no manifesto (tags estilo danbooru, em inglês):
  ```json
  "imagem_ia": {
    "tags_personagem": "1boy, solo, <nome danbooru>, <obra>, <cabelo>, <olhos>, <roupa>",
    "tags_cenario": "<cenário para --tipo fundo>",
    "tags_estilo": "<efeitos de poder>",
    "descricao": "<frase natural p/ motor remoto>",
    "negativo": "<tags a evitar>",
    "kanji": ["<coluna>", "<nome>"]
  }
  ```
  Sem `imagem_ia`, cai no fallback `personagem, anime`.
- Saída: `projetos/<slug>/artes_ia/<tipo>_<seed>_<hash>.png` + `.json` (prompt, seed, modelo). Seed determinística por (slug, tipo, cena); cache por hash do workflow — rerodar não gera de novo (`--forcar` para regenerar).
- Toda imagem é validada (rejeita preta/chapada). ComfyUI offline = erro explícito com o comando de subida; nunca fallback silencioso.
- No corpo do AMV, imagem IA só entra via VX Cenas IA (PASSO 9.7), nunca no lugar de uma cena real que responde bem à letra.

### 16. `card_apresentacao_saber.py` (`estudio.py card-saber <frame> "<NOME>" <out.mp4>`)
- Take de apresentação de personagem (estilo Jiraiya aos 18s):
  - Segmentação do personagem via IA.
  - Nome monumental posicionado atrás do corpo.
  - Contorno de neon brilhante (*Saber / Neon Edge*) na silhueta do personagem com zoom punch de entrada.

### 17. `legendas_mugen_pro.py` (`estudio.py legendas-mugen <slug>`)
- Legendas Cinzel com detecção automática de palavras de impacto:
  - Nomes de clãs/vilas/técnicas acendem em **ciano luminoso** (`\c&H00E0F000&`).
  - Palavras de sangue/combate acendem em **vermelho vivo** (`\c&H002020FF&`).
  - Fade-in/out suave (`\fad(120,90)`).

### 18. `snap_impact_transition.py` (`estudio.py snap-impact <tempo>`)
- Transição de drop com Flash Pop de 3 frames + Snap Zoom desacelerado (1.16x -> 1.0x).

### 19. `ghosting_fx.py` (`estudio.py ghosting <tempo>`)
- Efeito de eco visual cinematográfico (frames defasados com blend screen e decay temporal).

### 20. `smart_crop_916.py` (`estudio.py smartcrop <in.mp4> <out_916.mp4>`)
- Auto-Reframing 9:16 Inteligente com rastreamento contínuo da ação via OpenCV:
  - Rastreia o centróide de movimento e aplica filtro passa-baixa (moving average) para suavizar a câmera.
  - Mantém o personagem sempre centralizado no enquadramento vertical de Shorts/TikTok, sem cortar golpes nas bordas.

### 21. `sfx_engine.py` (Biblioteca de Foley e Sound Design Automático)
- Síntese e posicionamento preciso de camadas sonoras auxiliares:
  - `whoosh`: Transições de chicote de ar nas trocas de cena.
  - `impact_hit`: Soco pesado e corte de espada nos hit-frames.
  - `sub_boom`: Trovão e impacto grave sub-bass nos drops de 808.

### 22. `compositor_master_gpu.py` (1-Pass GPU Engine)
- Compilador de árvore unificada do FFmpeg: monta color grading + cinemascope + legendas Cinzel + mixagem de áudio com SFX (-12dB) em um único encode NVENC na RTX 3090, sem arquivos temporários intermediários.

### 23. `auditor_ritmo.py` (`estudio.py auditar-ritmo <slug>`)
- Mede Cuts Per Minute (CPM), duração média por corte e pontuação de retenção estimada do YouTube, alertando sobre planos excessivamente longos ou risco de fadiga visual.

### 24. `legendas_word_by_word.py` (`estudio.py legenda-palavra <slug>`)
- Legenda dinâmica palavra-a-palavra: cada palavra aparece conforme é cantada; as anteriores ficam em cinza, a atual acende em ciano vibrante. Estilo TikTok/karaokê.

### 25. `legendas_neon_motion.py` (`estudio.py legenda-neon <slug>`) 🔥 MOTION GRAPHICS
- Legenda word-by-word COM motion graphics de neon nativo (ASS puro renderizado na GPU pelo libass):
  - Palavra ativa: pop de escala (1.0→1.18→1.0 via `\t`) + glow neon emissivo (`\blur4` + `\3c`).
  - **Traço de neon glow que se DESENHA por baixo do texto** (revelação esq→dir via `\clip` animado com `\t`), centralizado e casando a largura com o número de caracteres.
  - Cor adaptativa: ciano (padrão), dourado (técnicas/poderes: chidori, kirin, susanoo, sharingan) e vermelho (combate: chamas, sangue, fúria).
  - **Pitfall CRÍTICO**: o porteiro de sincronia (`legenda.py:_onset_para`) precisa achar a palavra ATIVA (dentro do bloco `\b1`) — regex `\{[^}]*\\b1[^}]*\}([^{]+)`. Sem isso mede 0/N e reprova.
  - **Pitfall**: aplicar o neon sobre RAW sem legenda queimada (`render-clipe` SEM `--legenda`), senão duplica o texto (fantasma).
  - **Pitfall**: elevar gamma (~1.35) + brightness (~0.08) no color grade dark_shadow para as silhuetas escuras do anime não reprovarem no porteiro de imagem (tela morta).

### `neon_overlay_fx.py` (biblioteca de overlays PNG RGBA)
- Gera sequências de frames neon (underline, streak, corner_frame, particles, pulse) para composição em modo screen/add quando se quer motion graphics ainda mais elaborado que o ASS puro.

### 26. `font_manager.py` (Gerenciador de Fontes & Font Pairing)
- Sistema centralizado de fontes locais (Windows + cache do projeto) com seleção por papel visual:
  - `dominant`: palavra de impacto de 30% a 70% da tela (Impact, Arial Black, Cinzel Bold).
  - `secondary`: frase de apoio limpa e legível (Bebas Neue).
  - `support`: tags de lore, kanjis japoneses e estilo mangá (MS Gothic).
- Verificação de licença e prevenção de conflitos de uso comercial.

### 28. `creative_impact_director.py` (Diretor Criativo Autônomo)
- Planeja a intercalação orgânica de cenas de impacto (0.5s a 3.0s) analisando:
  - Letra, transcrição Whisper, energia de graves e punchlines de lore.
  - Hierarquia de palavras: `PRIMARY WORD` (dominante monumental) vs `SECONDARY WORDS` vs `SUPPORT`.
  - **Memória Temporal Anti-Repetição**: penaliza o reúso recente dos mesmos estilos visuais e backgrounds para garantir que o espectador nunca preveja a próxima cena.

### VX Scene Intelligence — Diretor Visual Universal
- Porta de catálogo: `estudio.py catalogar-cenas <slug>`.
- Porta de produção: `estudio.py cenas-auto <slug>`; a `esteira` executa esse estágio antes do Graphics Auto.
- `scene_intelligence.py` analisa conteúdo visual real e gera `scene_intelligence.json`; não depende do nome do arquivo.
- `semantic_scene_matcher.py` cruza letra canônica/autoral com tags/intensidade/qualidade das cenas e grava `scene_match` em cada segmento selecionado.
- Cache obrigatório por fingerprint; reanálise somente para clipe alterado ou `--force`.
- Assets gerados pelo sistema não entram no pool narrativo normal.
- `selecao_cenas.py`/mapas de nomes antigos são legado e não devem receber novas regras por anime.
- O encoder semântico visual atual é offline/OpenCV heurístico; a arquitetura permite adicionar CLIP/SigLIP depois sem mudar o contrato do catálogo.

### VX Graphics Pro — Motor de Motion Design
- Porta de producao automatica: `estudio.py graficos-auto <slug>`; a `esteira` chama
  esse estagio automaticamente antes de `planejar` e `render-clipe`.
- `estudio.py impacto-pro <slug>` fica como laboratorio/manual para testar estilos,
  nao como requisito do fluxo de producao.
- Presets, temas e mapa semantico ficam em `assets/design/`.
- `style_preset_engine.py` resolve tema/preset/layout e penaliza repeticao.
- `kinetic_typography.py` anima escala, slam, flicker, glitch, glow e underline;
  para nomes/titulos oferece `write_on`, `letter_reveal`, `outline_fill` e
  `trace_write`, incluindo rastreamento real do contorno do glifo via OpenCV.
- `background_fx_engine.py` gera fundos/particulas/aneis/raios procedurais.
- `audio_reactive_fx.py` reutiliza o detector de subgrave, faz cache por fingerprint e
  entrega eventos locais de 808 para scale/glow/flash.
- `impact_scene_orchestrator.py` conecta o Creative Director ao render isolado.
- `graphic_auto_pipeline.py` e o diretor de producao: prioriza letra canonica/autoral,
  cruza significado + timestamps + 808, aplica limite de frequencia/espacamento,
  renderiza em `clips_raw/vx_graphics_auto/` e injeta na timeline sem lacunas.
- Render final passa obrigatoriamente por `render_dispatch.py`; nunca criar encode
  CPU paralelo para estes takes.
- Regra editorial: sem palavra manual, selecionar punchlines por semantica; nunca
  considerar artigos/preposicoes como impacto por casamento parcial de string.
- Regra de variedade: evitar preset/layout repetido recentemente e manter a paleta
  coerente com o personagem. Para nomes reconhecidos do personagem, rotacionar
  `neon_write_on`, `neon_letter_reveal`, `neon_outline_fill` e `neon_trace` antes
  de repetir uma linguagem de escrita, salvo preset manual mais especifico.
- A injecao na timeline e automatica e idempotente. O estado em
  `qa/vx_graphics_auto/state.json` preserva a timeline-base; nunca duplicar segmentos
  numa reexecucao. Se uma timeline auto aplicada for alterada externamente, falhar
  fechado em vez de sobrescrever edicoes desconhecidas.
- Segmentos `vx_graphics_auto` devem permanecer `graphics_locked` no plano de camera:
  zoom 1.0 -> 1.0 e sem flash adicional, pois o take ja contem seu proprio motion.
- Se `legenda_ass` estiver ativa, nao duplicar a linha inteira dentro do card automatico;
  a tipografia principal reforca a palavra e a legenda oficial carrega a frase.

### 29. `render_impact_scene.py` (Renderizador de Cenas de Impacto)
- Compila takes de impacto completos em MP4 na GPU NVENC com:
  - Backgrounds gráficos temáticos (dark radial, manga speedlines, grunge noise).
  - Animações cinéticas: `scale_punch` (Snap Zoom 1.35x com decay exponencial), `slam_hit`, `rgb_glitch_pop`.
  - Flash de impacto nos primeiros frames para transição limpa.
  - Composição isolada garantindo que a barra de cinemascope permaneça 100% preta e sem vazamento de texto.
- Criação de loop invisível e infinito para Shorts e TikTok via crossfade de áudio e vídeo nos últimos 0.45s, garantindo retenção > 100% no algoritmo.

### 25. `paineis_manga.py` (`estudio.py paineis [--modo 2_paineis_h|2_paineis_v]`)
- Split-screen dinâmico em estilo página de mangá com bordas pretas espessas (divisão vertical ou horizontal de planos).

### 26. `color_splash.py` (`estudio.py color-splash <cor> [--inicio S] [--dur D]`)
- Desaturação seletiva: converte a cena para PB de alto contraste, preservando apenas uma cor específica (vermelho sangue, ciano, verde ou dourado).

### 27. `hook_retencao_shorts.py` (`estudio.py hook-retencao "<TEXTO>" <out.png>`)
- Gera overlays hipnóticos de retenção para os primeiros 2.5s do Short com micro-barra de progresso e curiosity gap.

### 28. `pixel_sort_glitch.py` (`estudio.py pixel-sort <tempo>`)
- Transição de Datamosh / Pixel Sorting nos cortes de impacto com deslocamento de linhas.
