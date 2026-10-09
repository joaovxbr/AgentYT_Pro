# Incidente: Gojo "INFINITO" (set/2026)

Várias falhas encadeadas numa mesma produção. Cada uma virou regra ou teste.

| Sintoma | Causa real | Correção permanente |
|---|---|---|
| Esteira "travava" em `cenas-auto` | Catálogo com OpenCLIP é lento (~2,5 min); execuções anteriores foram interrompidas | Nenhuma no código; aguardar. Cache por fingerprint evita repetir |
| `cenas-auto` reprovava alvos obrigatórios com score 0.000 | Cobertura lia só o subconjunto de alvos do intent do segmento; matcher greedy não sabia dos alvos das linhas vizinhas | `scene_semantic_scores` persistido; alvos obrigatórios ancorados no segmento de maior sobreposição |
| Logo Amazon Prime aos ~10 s | Clipe `gojo_hollow_purple_toji.mp4` tem splash preto do Prime em 226–230 s; o matcher escolheu essa janela | `dead_scene` no catálogo; cenas mortas fora do inventário |
| Gate de imagem 5,5% quase-morto | Silhuetas escuras de anime | Lift leve de sombras só em footage de anime (`render_clipe._lift_sombra`) |
| LUFS −16,1 | Limitador só cortava pico, sem normalizar | `loudnorm I=-14` no master final |
| `[Intro]`, `[Refrão]` na legenda | Marcadores do Suno lidos como versos | `extrair_linhas_suno` em todos os leitores de letra |
| Legenda sumia em trechos cantados | Whisper em passada única pulou 31–58 s; eu removi um refrão da letra achando que o Suno não cantou (**erro**) | Transcrição em blocos + 2ª passada sem prompt nas lacunas; porteiro `auditar-letra`; alinhador monótono |
| "Inscreva-se no canal… sininho" no fim | Alucinação clássica do Whisper em instrumental | Filtro `limpar_alucinacoes` + palavras degeneradas |

| 2 testes de ComfyUI falhando com "HTTP 503 Charles Error Report" | Proxy Charles do sistema interceptava chamadas para 127.0.0.1 | Cliente ComfyUI local usa opener sem proxy |
| Mudança de letra não entrava no vídeo sem `rebuild-total` | Etapas editavam `timeline.json` no lugar e se recusavam a recompor ("preserved_after_downstream_visuals") | `vx/composicao.py`: toda esteira recompõe da `timeline_base.json` |

## Lição principal
Nunca editar a letra autoral "no chute" com base em um ASR suspeito. Primeiro provar
com evidência do áudio (`auditar-letra`, energia do stem vocal); depois decidir.
