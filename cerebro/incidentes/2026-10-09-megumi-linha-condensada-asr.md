# Incidente: Megumi "Dez Sombras" — linha condensada pelo ASR (09/10/2026)

Primeira faixa gerada pelo Mureka (não Suno) no projeto `megumi_shadows`. A letra autoral veio
com **timing de linha do próprio gerador**, então a sincronia foi montada por
`transcricao_canonica.json` (caminho que pula o alinhamento estatístico). Isso expôs um buraco
no motor que o Suno nunca tinha mostrado.

| Sintoma | Causa real | Correção permanente |
|---|---|---|
| `auditar-letra` REPROVADO com 1 linha a **33 %** ("Cada shikigami meu sabe onde atacar") | O Whisper ouviu só `shikigami` (p 0,33/0,60) e `atacar` (p 0,94) e **condensou** as 6 palavras em 2. A voz TEM transcrição, então **não existe lacuna de energia** — e a 3ª passada (`passada_guiada`) só dispara em lacuna | **4ª passada `passada_por_linha_fraca`**: gatilho é *linha com cobertura baixa*, não lacuna |
| A 3ª passada nunca rodava neste caso | `lacunas_vocais` acha trecho **sem nenhuma palavra**. Aqui há 2 palavras: não forma lacuna | `linhas_fracas()` (nova, pura) detecta cobertura em `(0, 45 %)` e devolve a janela |
| A tentativa com prompt piorava o resultado | Com o prompt, o Whisper "copia" a frase e casa **menos** (casou `shikigami`/`meu`; sem prompt casou `sabe`/`onde`/`atacar`) | Tenta **primeiro sem prompt**; guarda a tentativa **ACEITA**, nunca a última |
| `esperados` vinha com 4 tokens em vez de 6 | Filtrar só os "buracos" embaralhava o alinhamento monotônico e `atacar` **desaparecia** da lista | `esperados` = **linha inteira**; a passada retranscreve a frase completa |

Resultado: `253 → 255 palavras`, `auditar-letra` **APROVADO** (271 letra / 255 áudio / 243 casadas),
sem exceção registrada e sem afrouxar limiar. Testes:
`tests/test_transcrever_linha_fraca.py` (9 testes, inclui o caso em que a tentativa aceita
sobrevive à rejeitada).

## Nota sobre o Mureka
O Mureka **entrega os tempos de linha**, o que é melhor evidência que o ASR: dois relógios
independentes (gerador e Whisper) concordaram com diferença mediana de **0,16 s**. Usar
`transcricao_canonica.json` não é atalho — é a fonte mais forte disponível. O Whisper continua
necessário para `palavras_vocal` (o karaokê POV e vários módulos leem), mas deixa de decidir o tempo.

## Lição
"Cobertura zero" e "cobertura baixa" são **dois modos de falha diferentes** do ASR e precisam de
gatilhos diferentes. Zero = lacuna de voz (`lacunas_vocais`); baixa = linha condensada
(`linhas_fracas`). Manter os dois disjuntos evita retranscrever duas vezes o mesmo trecho.
Repete a lição do Douma: **a letra autoral diz o que falta; o áudio diz se foi cantado.**
