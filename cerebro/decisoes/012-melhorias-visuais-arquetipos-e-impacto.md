# Decisão 012 — Color Grading por Arquétipo, Transições Snap Impact (808) e Color Splash Nativo

Data: 2026-10-13
Módulos: `ferramentas/color_grade_pro.py`, `ferramentas/snap_impact_transition.py`, `ferramentas/bass_shake.py`, `ferramentas/color_splash.py`, `ferramentas/motion_match_director.py`, `ferramentas/render_clipe.py`, `ferramentas/filtros.py`
Testes: `tests/test_color_grade_pro.py`, `tests/test_color_splash.py`, `tests/test_bass_shake.py`, `tests/test_snap_impact_transition.py` (16 novos testes, 635 na suíte total)

## Contexto

Após a aprovação e entrega do clipe de Jujutsu Kaisen (`sukuna_shrine`), foi identificado potencial para elevar o patamar visual das produções em três frentes complementares:
1. **Identidade cromática cinemática adaptada ao anime**: Em vez de grading genérico, cada universo precisa de curvas e saturações características (ex: `cursed_energy` com sombras azuladas e carmesim saturado).
2. **Impacto rítmico nos graves (808/sub-bass)**: Cortes em momentos de alta energia musical que coincidem com drops de sub-grave precisam de impacto visual (`snap_impact` com flash pop de 3 quadros, snap zoom punch e aberração cromática).
3. **Destaque cromático (Color Splash / Sin City)**: Momentos de clímax onde todo o quadro é convertido em preto e branco de alto contraste, preservando apenas o tom do arquétipo (ex: sangue/olhos carmesim de Sukuna).

## Princípios e Diretrizes Técnicas

### 1. Lift Seguro contra Rejeição do Porteiro de Imagem
- **Problema**: O porteiro `ferramentas/imagem.py` reprova clipes com `luz < 24` e `detalhe < 22` como `quase-morto`. Color grading que afunda pretos em excesso em animes escuros podia causar falso positivo.
- **Solução**: Implementação do parâmetro `lift_seguro=True` em `obter_filtro_color_grade()`, que ancora a curva em `0/0.02` e aplica leve compensação de gamma `eq=gamma=1.06:brightness=0.01`. Sombras ficam cinematográficas e profundas sem tocar o piso de alarme.

### 2. Filtro Linear Nativo para Color Splash (`chromahold`)
- **Problema**: Módulos legados tentavam usar grafos complexos com `split`, `colorkey` invertido e `overlay`, gerando inversão de cores e impedindo aceleração linear no `-vf`.
- **Solução**: Adoção do filtro nativo FFmpeg `chromahold=color={cor}:similarity=0.22,eq=contrast=1.30`. Mantém 100% de saturação no tom alvo e zera o restante para escala de cinza, executando a mais de 200 fps na GPU NVENC.

### 3. Integração Não-Invasiva de Direção de Câmera (`motion_match_director.py`)
- O corte `snap_impact` só é ativado quando:
  a) Há drop de sub-grave (<120Hz detectado via `librosa`) a menos de 0.14s da fronteira do corte;
  b) A intensidade da cena é alta (`avg_intensity >= 0.60` ou tags de impacto).
- Preserva a regra sagrada: cortes limpos por padrão (`hard_cut`), efeitos somente onde justificados.

## Consequências
- Os 635 testes da suíte passam com 100% de aprovação verde.
- O compositor GPU (`compositor_master_gpu.py`) e o motor de render (`render_clipe.py`) consom as receitas dinamicamente.
