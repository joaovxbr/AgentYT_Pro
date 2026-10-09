"""Registro das etapas de producao — fonte UNICA da ordem e dos contratos.

Cada etapa declara o que le, o que grava e se reprova a esteira. O orquestrador
(`pipeline_autonomo_pro`) executa por este registro; `cerebro/etapas.md` e gerado
a partir dele (`estudio.py cerebro`) e um teste falha se o doc ficar defasado.

Para criar uma etapa nova: adicionar um `Etapa(...)` aqui na posicao certa, com o
comando correspondente em `estudio.py`, e rodar `estudio.py cerebro`.
Caminhos sao relativos a `projetos/<slug>/`; `{slug}` e substituido.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Etapa:
    nome: str                      # tambem e o subcomando do estudio.py
    descricao: str
    le: tuple[str, ...]
    escreve: tuple[str, ...]
    bloqueante: bool = True        # exit != 0 reprova a esteira
    fase: str = "producao"         # bootstrap | producao | master
    quando: str = "sempre"         # sempre | se_ausente (so roda se alguma saida falta)
    args: tuple[str, ...] = field(default_factory=tuple)  # args extras alem do slug
    notas: str = ""
    #: Pode ser reaproveitada entre execucoes pelo cache por hash (vx/cache.py).
    #: `False` nas etapas de composicao: elas EDITAM `timeline.json` sobre a base
    #: limpa a cada esteira (vx/composicao.py) e ja tem idempotencia interna via
    #: `qa/<etapa>/state.json`. Cachear por fora brigaria com esse desenho.
    cacheavel: bool = True


BOOTSTRAP = (
    Etapa("stems", "Separa voz/bateria/baixo/outros com Demucs (GPU).",
          le=("entradas/{slug}_normalizado.wav",),
          escreve=("entradas/stems/{slug}_normalizado_vocals.wav",
                   "entradas/stems/{slug}_normalizado_drums.wav",
                   "entradas/stems/{slug}_normalizado_bass.wav",
                   "entradas/stems/{slug}_normalizado_other.wav"),
          fase="bootstrap", quando="se_ausente"),
    Etapa("transcrever", "Whisper large-v3 no stem vocal, em blocos, com 2a passada nas lacunas de voz.",
          le=("entradas/stems/{slug}_normalizado_vocals.wav", "LETRA_LINHAS.txt"),
          escreve=("entradas/transcricao.json",),
          fase="bootstrap", quando="se_ausente", args=("--modelo", "large-v3"),
          notas="Reprova se sobrar voz sem palavras depois do 1o verso."),
    Etapa("sincronizar", "Alinha a letra autoral (monotono) aos tempos do ASR e gera a legenda ativa.",
          le=("entradas/transcricao.json", "LETRA_LINHAS.txt", "transcricao_canonica.json"),
          escreve=("letra_sincronizada.json", "<projeto.json:legenda_ass>", "legendas/{slug}_pov.ass"),
          fase="bootstrap", quando="se_ausente"),
    Etapa("timeline", "Timeline-base 0..fim sem lacunas, planos quebrados nos picos de 808.",
          le=("letra_sincronizada.json", "clips_raw/*.mp4", "qa/vx_graphics_bass_peaks.json"),
          escreve=("timeline.json", "timeline_base.json", "qa/composicao.json"),
          fase="bootstrap", quando="se_ausente",
          notas="Tambem roda sozinha se a letra sincronizada mudou desde a base (vx/composicao.py)."),
)

# Antes de PRODUCAO o orquestrador restaura timeline.json a partir de timeline_base.json
# e arquiva os state.json das etapas de composicao (vx/composicao.py): cenas-auto,
# cenas-ia, titulos, manga-auto e graficos-auto sempre reaplicam sobre a base limpa.
PRODUCAO = (
    Etapa("fonte-limpa", "Porteiro de fonte: marca d'agua/logo (limpa com recorte ou delogo) e legenda queimada (cena vira poluida).",
          le=("clips_raw/*.mp4",),
          escreve=("qa/fonte_limpa.json", "qa/fonte_limpa.md", "clips_raw/_originais/*"),
          args=("--corrigir",),
          notas="Reprova se sobrar marca d'agua depois da limpeza. Incidente Douma (clipes oficiais com legenda em ingles)."),
    Etapa("auditar-letra", "Porteiro letra x audio: voz sem transcricao, verso nao cantado, trecho cantado fora da letra.",
          le=("LETRA_LINHAS.txt", "entradas/transcricao.json", "entradas/stems/{slug}_normalizado_vocals.wav"),
          escreve=("qa/auditoria_letra.json", "qa/auditoria_letra.md")),
    Etapa("auditar-ritmo", "Mede cortes por minuto e retencao estimada.",
          le=("timeline.json",), escreve=(), bloqueante=False, notas="Informativo; nunca reprova."),
    Etapa("cenas-auto", "Scene Intelligence + matcher: escolhe a cena real do anime para cada trecho da letra.",
          le=("timeline.json", "letra_sincronizada.json", "clips_raw/*.mp4", "projeto.json"),
          escreve=("timeline.json", "scene_intelligence.json", "qa/scene_matcher/plano.json",
                   "qa/scene_matcher/state.json"),
          notas="Cenas mortas (tela preta, splash de streaming) sao excluidas (dead_scene).",
          cacheavel=False),
    Etapa("chroma-auto", "Cena de tela verde (chroma key) vira cena composta: fundo do projeto + personagem recortado + aura pulsando no 808.",
          le=("timeline.json", "qa/fonte_limpa.json", "artes_ia/fundo_*.png"),
          escreve=("timeline.json", "clips_raw/vx_chroma/*", "qa/vx_chroma/state.json"),
          notas="Pedido do usuario (Douma): nunca mostrar a tela verde crua.",
          cacheavel=False),
    Etapa("cenas-ia", "Gera cena nova no ComfyUI so onde a cena real ficou fraca.",
          le=("timeline.json", "projeto.json", "assets/design/cenas_ia_map.json"),
          escreve=("timeline.json", "artes_ia/*", "clips_raw/vx_cenas_ia/*.mp4",
                   "qa/vx_cenas_ia/plano.json", "qa/vx_cenas_ia/state.json"),
          notas="ComfyUI offline = pula com aviso (cenas_ia.strict=true torna obrigatorio).",
          cacheavel=False),
    Etapa("titulos", "Title Card (abertura) e End Card (encerramento).",
          le=("timeline.json", "projeto.json", "artes_ia/*"),
          escreve=("timeline.json", "clips_raw/vx_titulos/*", "qa/vx_titulos/state.json"),
          cacheavel=False),
    Etapa("manga-auto", "Insere 1-2 takes raros de manga em climax fortes.",
          le=("timeline.json", "letra_sincronizada.json"),
          escreve=("timeline.json", "clips_raw/vx_manga_auto/*", "qa/vx_manga_auto/state.json"),
          cacheavel=False),
    Etapa("graficos-auto", "Takes tipograficos pela letra + picos de 808, em motion sobre a cena real do anime.",
          le=("timeline.json", "letra_sincronizada.json", "assets/design/semantic_style_map.json",
              "assets/design/motion_lab.json"),
          escreve=("timeline.json", "clips_raw/vx_graphics_auto/*", "qa/vx_graphics_auto/state.json"),
          notas="Estilos de linha ocultam a legenda so no trecho do take (decisao 003).",
          cacheavel=False),
    Etapa("planejar", "Plano de camera por shot (respeita graphics_locked).",
          le=("timeline.json", "entradas/transcricao.json"), escreve=("plano_visual.json",)),
    Etapa("sincronia", "Porteiro de legenda: ASR + linhas exibidas com a voz em silencio.",
          le=("<projeto.json:legenda_ass>", "entradas/transcricao.json",
              "entradas/stems/{slug}_normalizado_vocals.wav"),
          escreve=()),
)

MASTER = (
    Etapa("render-clipe", "Render do corpo em NVENC com legenda ASS queimada.",
          le=("timeline.json", "plano_visual.json", "<projeto.json:legenda_ass>", "entradas/{slug}_normalizado.wav"),
          escreve=("saidas/esteira/<run_id>/{slug}_corpo.mp4",), fase="master",
          args=("--legenda",),
          notas="Nao cacheavel: escreve em saidas/esteira/<run_id>/, que e da execucao atual.",
          cacheavel=False),
    Etapa("intro", "Concatena a intro oficial + loudnorm -14 LUFS + limitador de true peak.",
          le=("saidas/esteira/<run_id>/{slug}_corpo.mp4", "assets/intro/Eu_preciso_criar_INTRO_para_o.mp4"),
          escreve=("saidas/esteira/<run_id>/{slug}_master_final_com_intro.mp4",), fase="master",
          notas="Interna ao orquestrador (compositor_master_gpu.concatenar_intro).",
          cacheavel=False),
    Etapa("qa-master", "Decode completo + porteiro de imagem + porteiro de TEXTO (OCR no corpo) + porteiro de audio no master final.",
          le=("saidas/esteira/<run_id>/{slug}_master_final_com_intro.mp4", "saidas/esteira/<run_id>/{slug}_corpo.mp4"),
          escreve=("qa/esteira/<run_id>/decode.log", "qa/esteira/<run_id>/imagem.json",
                   "qa/esteira/<run_id>/texto_render.json", "qa/esteira/<run_id>/audio.json"), fase="master",
          notas="Interna ao orquestrador. Clareza vocal e so aviso. Texto que nao e da letra/titulos "
                "(logo de streaming, legenda em ingles, cartela) reprova (fonte_limpa.auditar_texto_render).",
          cacheavel=False),
)

TODAS = BOOTSTRAP + PRODUCAO + MASTER
POR_NOME = {e.nome: e for e in TODAS}


def nomes(fase: str | None = None) -> list[str]:
    return [e.nome for e in TODAS if fase is None or e.fase == fase]


def documentacao() -> str:
    """Markdown de `cerebro/etapas.md` (gerado; nao editar a mao)."""
    out = ["# Etapas da esteira (gerado de `vx/etapas.py`)", "",
           "> Não edite à mão: rode `estudio.py cerebro`. Um teste falha se este arquivo ficar defasado.", "",
           "Ordem: " + " → ".join(nomes()), "",
           "**Composição:** antes da fase `producao`, a esteira restaura `timeline.json` a partir de "
           "`timeline_base.json` e arquiva os `state.json` de cenas-auto, cenas-ia, titulos, manga-auto e "
           "graficos-auto (backup em `qa/esteira/<run_id>/recomposicao/`). Cada etapa reaplica sobre a base; "
           "renders e imagens IA vêm do cache. Ver `vx/composicao.py`.", ""]
    for fase in ("bootstrap", "producao", "master"):
        out += [f"## Fase: {fase}", ""]
        for e in TODAS:
            if e.fase != fase:
                continue
            flags = ["bloqueia" if e.bloqueante else "informativa"]
            if e.quando == "se_ausente":
                flags.append("só se a saída faltar")
            flags.append("cacheável" if e.cacheavel else "sempre refeita")
            out += [f"### `{e.nome}` ({', '.join(flags)})", "", e.descricao, ""]
            out.append("- **Lê:** " + (", ".join(f"`{x}`" for x in e.le) or "—"))
            out.append("- **Grava:** " + (", ".join(f"`{x}`" for x in e.escreve) or "—"))
            if e.notas:
                out.append(f"- **Nota:** {e.notas}")
            out.append("")
    return "\n".join(out)
