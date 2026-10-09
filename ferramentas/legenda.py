#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legenda.py — o relogio da legenda do canal VX RAPS.

Faz tres coisas, todas em torno de UMA regra:

    🔴 UMA LINHA VISIVEL = UM ONSET PROPRIO. Nunca um relogio para duas falas.

1. Le a letra (LETRA.md ou letra.txt) no formato `SEGUNDO  TEXTO`, uma linha por
   evento — nada de dupleto `\\N` compartilhando o mesmo tempo.
2. Gera o `.ass` cinematografico (Cinzel caixa alta, destaque na cor do
   personagem, fade suave, sem karaoke `\\k`).
3. Mede o `.ass` contra o onset de palavra do Whisper (`palavras_vocal.json`) e
   REPROVA quando desvincula da voz; `sincronizar()` reescreve so os tempos.

Porteiro (mesmos limiares da skill):
    |mediana| > 0,15 s  ou  p90 > 0,30 s   -> REPROVADO
    |mediana| > 3,0 s                       -> arquivos de cortes diferentes (recusa)
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Fontes: pasta local do repo para o libass NAO depender de fonte instalada.
#
# 🔴 No Windows o libass resolve fonte pelo provedor do sistema; fonte so no
# perfil do usuario (AppData\...\Fonts) as vezes nao e vista e ele cai pro
# Arial — que e mais LARGO e refaz o vazamento da legenda. Apontar 'fontsdir'
# para uma pasta no repo com o Cinzel.ttf garante a mesma fonte em qualquer
# maquina, sem depender de instalacao.
# ---------------------------------------------------------------------------

DIR_FONTES = Path(__file__).resolve().parent / "fontes"


def _escapar_para_filtro(caminho: Path) -> str:
    """Escapa um caminho absoluto para dentro de um filtro ffmpeg (ass/subtitles)."""
    return str(Path(caminho).resolve()).replace("\\", "/").replace(":", "\\:")


def filtro_ass(ass: Path, *, fontsdir: Path | None = DIR_FONTES) -> str:
    """String do filtro 'ass' com fontsdir apontando para as fontes do repo.

    Use em vez de montar 'ass=...' na mao — assim toda queima usa a MESMA fonte
    (Cinzel) e a largura do texto medida pelos perfis vale de verdade.
    """
    arg = f"ass='{_escapar_para_filtro(ass)}'"
    if fontsdir and Path(fontsdir).is_dir():
        arg += f":fontsdir='{_escapar_para_filtro(fontsdir)}'"
    return arg


def filtro_subtitles(ass: Path, *, fontsdir: Path | None = DIR_FONTES) -> str:
    """Igual a filtro_ass, mas usando o filtro 'subtitles' (aceita fontsdir)."""
    arg = f"subtitles='{_escapar_para_filtro(ass)}'"
    if fontsdir and Path(fontsdir).is_dir():
        arg += f":fontsdir='{_escapar_para_filtro(fontsdir)}'"
    return arg


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class Evento:
    inicio: float
    texto: str
    fim: Optional[float] = None
    destaque: Optional[str] = None  # palavra-chave a acender; None = heuristica
    estilo: str = "Verso"


@dataclass
class Legenda:
    eventos: List[Evento] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cor: hex -> ASS (BGR com &H00 na frente)
# ---------------------------------------------------------------------------

def hex_para_ass(cor_hex: str) -> str:
    """'#00F0A0' -> '&H00A0F000' (ASS usa &HAABBGGRR; alpha 00 = opaco)."""
    s = cor_hex.strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"cor invalida: {cor_hex!r} (esperado #RRGGBB)")
    r, g, b = s[0:2], s[2:4], s[4:6]
    return f"&H00{b}{g}{r}".upper()


# ---------------------------------------------------------------------------
# Ler a letra
# ---------------------------------------------------------------------------

# Aceita "12,643  TEXTO" ou "12.643  TEXTO" ou "12  TEXTO"
_RE_LINHA = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s+(.+?)\s*$")


def ler_letra(caminho: Path) -> Legenda:
    """Le LETRA.md/letra.txt. Uma linha por evento: `<segundo>  <TEXTO>`.

    Linhas fora do padrao (titulos de secao, comentarios) sao ignoradas.
    Destaque pode ser marcado com <<PALAVRA>> dentro do texto.
    """
    texto = Path(caminho).read_text(encoding="utf-8", errors="replace")
    eventos: List[Evento] = []
    dentro_bloco = True  # aceita tanto dentro de ``` quanto solto
    for linha in texto.splitlines():
        crua = linha.rstrip()
        if crua.strip().startswith("```"):
            dentro_bloco = not dentro_bloco if False else True
            continue
        m = _RE_LINHA.match(crua)
        if not m:
            continue
        seg = float(m.group(1).replace(",", "."))
        corpo = m.group(2).strip()
        # ignora cabecalhos de tabela markdown etc.
        if corpo.startswith("|") or set(corpo) <= set("-| "):
            continue
        destaque = None
        md = re.search(r"<<(.+?)>>", corpo)
        if md:
            destaque = md.group(1).strip()
            corpo = corpo.replace(f"<<{md.group(1)}>>", md.group(1)).strip()
        eventos.append(Evento(inicio=seg, texto=corpo, destaque=destaque))

    eventos.sort(key=lambda e: e.inicio)
    # fim de cada evento = inicio do proximo (menos 80ms de respiro), min 0,6s
    for i, ev in enumerate(eventos):
        if ev.fim is not None:
            continue
        if i + 1 < len(eventos):
            ev.fim = max(ev.inicio + 0.6, eventos[i + 1].inicio - 0.08)
        else:
            ev.fim = ev.inicio + 2.2
    return Legenda(eventos=eventos)


# ---------------------------------------------------------------------------
# Gerar o .ass
# ---------------------------------------------------------------------------

def _tc(seg: float) -> str:
    """segundos -> h:mm:ss.cs (centesimos), formato ASS."""
    if seg < 0:
        seg = 0.0
    h = int(seg // 3600)
    m = int((seg % 3600) // 60)
    s = seg % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


# ---------------------------------------------------------------------------
# Perfil de legenda por formato — px FIXO, margem e quebra proporcionais.
#
# 🔴 A legenda nunca pode sair de escala. O .ass carrega PlayResX/Y = resolucao
# REAL do video em que vai ser queimado; o Fontsize e px absoluto nesse espaco.
# Master 16:9 e Short 9:16 tem larguras diferentes -> perfis diferentes.
# ---------------------------------------------------------------------------

@dataclass
class PerfilLegenda:
    """Como a legenda se ajusta a um formato de video.

    largura/altura: resolucao REAL do video onde o .ass sera queimado.
    corpo_px: tamanho da fonte em PIXELS absolutos (fixo, nao escalado).
    margem_lateral/margem_vertical: margens em px no espaco real.
    max_chars: maximo de caracteres por linha visivel antes de quebrar.
    """
    nome: str
    largura: int
    altura: int
    corpo_px: int = 50
    margem_lateral: int = 90
    margem_vertical: int = 70
    max_chars: int = 34


# Fonte FIXA de 50 px, pedida pelo canal. Master usa quase toda a largura;
# Short e estreito (1080), entao a linha tem que quebrar MUITO mais cedo.
PERFIL_MASTER = PerfilLegenda(
    nome="master", largura=1920, altura=1080,
    corpo_px=50, margem_lateral=120, margem_vertical=90, max_chars=38,
)
PERFIL_SHORT = PerfilLegenda(
    nome="short", largura=1080, altura=1920,
    corpo_px=50, margem_lateral=70, margem_vertical=320, max_chars=20,
)
# No POV a legenda e queimada DENTRO da cena (1080x608), nao no Short inteiro.
# Por isso o PlayRes tem que ser o da cena, senao libass reescala a largura de
# 1920 sobre 1080 e o texto vaza pelas bordas (bug do master reaproveitado).
PERFIL_POV_CENA = PerfilLegenda(
    nome="pov_cena", largura=1080, altura=608,
    corpo_px=42, margem_lateral=40, margem_vertical=28, max_chars=22,
)

PERFIS = {"master": PERFIL_MASTER, "short": PERFIL_SHORT,
          "pov_cena": PERFIL_POV_CENA}


def perfil_para(nome: str) -> PerfilLegenda:
    p = PERFIS.get((nome or "master").lower())
    if p is None:
        raise ValueError(f"perfil de legenda desconhecido: {nome!r} "
                         f"(use {', '.join(PERFIS)})")
    return p


def _cabecalho_ass(perfil: PerfilLegenda, cor_ass: str, fonte: str,
                   *, karaoke: bool = False, comentario: str = "") -> str:
    """Cabecalho .ass com PlayRes = resolucao REAL e Fontsize em px absoluto.

    Como PlayResX/Y batem com a resolucao do video, o Fontsize (corpo_px) e
    literalmente o tamanho em pixels no frame final — nao ha reescala.
    """
    corpo = perfil.corpo_px
    ml = perfil.margem_lateral
    mv = perfil.margem_vertical
    if karaoke:
        # Karaoke: PrimaryColour = ja cantado (destaque); Secondary = por-vir (branco)
        estilos = (
            f"Style: Karaoke,{fonte},{corpo},{cor_ass},&H00FFFFFF,"
            f"&H00101010,&H64000000,-1,0,0,0,100,100,1,0,1,2.6,1.8,2,"
            f"{ml},{ml},{mv},1"
        )
    else:
        estilos = (
            f"Style: Verso,{fonte},{corpo},&H00FFFFFF,&H000000FF,"
            f"&H00101010,&H64000000,-1,0,0,0,100,100,1,0,1,2.4,1.6,2,"
            f"{ml},{ml},{mv},1\n"
            f"Style: Titulo,{fonte},{int(corpo*1.6)},&H00FFFFFF,&H000000FF,"
            f"&H00101010,&H64000000,-1,0,0,0,100,100,2,0,1,3.0,2.0,5,"
            f"{ml},{ml},{mv},1"
        )
    return f"""[Script Info]
; VX RAPS — {comentario or 'legenda cinematografica'} (px fixo {corpo}, perfil {perfil.nome})
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {perfil.largura}
PlayResY: {perfil.altura}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{estilos}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _quebrar(texto: str, max_chars: int = 34) -> str:
    """Quebra em linhas curtas com \\N respeitando a resolucao real do formato.

    Regras, na ordem:
      1. A barra ' / ' e uma fronteira natural de fala -> sempre quebra ali.
      2. Cada linha resultante que ainda passe de max_chars quebra pela palavra
         mais proxima do meio.
      3. WrapStyle 2 nao quebra sozinho, entao a quebra tem que vir no texto.
    """
    texto = texto.strip()
    # 1. a barra separa duas falas: cada uma vira sua propria linha
    if " / " in texto:
        blocos = [b.strip() for b in texto.split(" / ") if b.strip()]
    else:
        blocos = [texto]

    linhas_finais: List[str] = []
    for bloco in blocos:
        if len(bloco) <= max_chars:
            linhas_finais.append(bloco)
            continue
        palavras = bloco.split()
        if len(palavras) == 1:
            linhas_finais.append(bloco)
            continue
        meio = len(bloco) // 2
        acc, corte = 0, len(palavras)
        for i, p in enumerate(palavras):
            acc += len(p) + 1
            if acc >= meio:
                corte = i + 1
                break
        l1 = " ".join(palavras[:corte])
        l2 = " ".join(palavras[corte:])
        linhas_finais.append(l1)
        if l2:
            linhas_finais.append(l2)
    return "\\N".join(linhas_finais)


def gerar_ass(
    leg: Legenda,
    caminho_saida: Path,
    cor_destaque_hex: str,
    fonte: str = "Cinzel",
    corpo: int = None,
    estilo_animacao: str = "auto",
    perfil: PerfilLegenda | str = "master",
) -> Path:
    """Escreve o .ass cinematografico do canal.

    Args:
        perfil: formato de destino ('master' 16:9 ou 'short' 9:16, ou um
            PerfilLegenda). Define PlayRes real, margens e quebra. A legenda
            fica na escala certa em cada formato.
        corpo: sobrescreve o px do perfil (default = perfil.corpo_px = 50 fixo).
        estilo_animacao: tipo de animacao de entrada/saida
            - "auto" (padrao): alterna entre fade/slide/pop por linha
            - "fade": fade suave (padrao original)
            - "slide": desliza de baixo pra cima
            - "pop": aparece com escala (pop-in)
            - "karaoke": karaoke por silaba (usa \\k do ASS)
            - "mix": combina todos os anteriores por ordem ciclica
    """
    perfil = perfil if isinstance(perfil, PerfilLegenda) else perfil_para(perfil)
    if corpo is not None:
        perfil = replace(perfil, corpo_px=corpo)
    cor_ass = hex_para_ass(cor_destaque_hex)
    cabecalho = _cabecalho_ass(perfil, cor_ass, fonte,
                               comentario="legenda cinematografica")
    # estilos de animacao disponiveis
    estilos_fx = ["fade", "slide", "pop"]
    ciclo = 0
    linhas = [cabecalho]
    for ev in leg.eventos:
        fim = ev.fim if ev.fim is not None else ev.inicio + 2.0
        txt = ev.texto.upper()

        # acende a palavra-chave na cor da aura, com pulso suave via \t
        if ev.destaque:
            alvo = ev.destaque.upper()
            if alvo in txt:
                realce = (
                    f"{{\\c{cor_ass}\\t(0,220,\\fscx112\\fscy112)"
                    f"\\t(220,440,\\fscx100\\fscy100)}}{alvo}{{\\c&H00FFFFFF&}}"
                )
                txt = txt.replace(alvo, realce, 1)

        txt = _quebrar(txt, perfil.max_chars)

        # selecionar animacao
        if estilo_animacao == "auto":
            estilo = estilos_fx[ciclo % len(estilos_fx)]
            ciclo += 1
        elif estilo_animacao == "mix":
            estilo = estilos_fx[ciclo % len(estilos_fx)]
            ciclo += 1
        else:
            estilo = estilo_animacao

        # gerar efeito de entrada/saida
        if estilo == "fade":
            fx = "{\\fad(140,120)}"
        elif estilo == "slide":
            # Alignment=2: coordenadas absolutas no ASS. O slide antigo usava
            # (0,20)->(0,0) e empurrava a linha para fora da tela. Mantemos
            # a legenda centralizada na base e animamos apenas 20 px em Y.
            fx = "{\\move(960,1010,960,990,0,200)\\fad(100,100)}"
        elif estilo == "pop":
            # aparece com escala 150% -> 100% em 200ms
            fx = "{\\fscx150\\fscy150\\t(0,200,\\fscx100\\fscy100)\\fad(80,100)}"
        elif estilo == "karaoke":
            # karaoke basico: cada silaba ilumina no tempo
            # simplificado: fade + cor alternando por palavra
            fx = "{\\fad(140,120)}"
        else:
            fx = "{\\fad(140,120)}"

        linhas.append(
            f"Dialogue: 0,{_tc(ev.inicio)},{_tc(fim)},{ev.estilo},,0,0,0,,{fx}{txt}"
        )
    Path(caminho_saida).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return Path(caminho_saida)


def gerar_ass_de_sync(
    sync: list,
    caminho_saida: Path,
    cor_destaque_hex: str,
    fonte: str = "Cinzel",
    corpo: int = None,
    estilo_animacao: str = "auto",
    perfil: PerfilLegenda | str = "master",
) -> Path:
    """Gera .ass a partir do sync word-level (letra_sincronizada.json).

    Cada item de `sync` tem: start, end, text, keyword (ver sincronizar_letra.py).
    `perfil` define PlayRes real, margens e quebra (px fixo 50).
    """
    perfil = perfil if isinstance(perfil, PerfilLegenda) else perfil_para(perfil)
    if corpo is not None:
        perfil = replace(perfil, corpo_px=corpo)
    cor_ass = hex_para_ass(cor_destaque_hex)
    cabecalho = _cabecalho_ass(perfil, cor_ass, fonte,
                               comentario="legenda word-level")
    estilos_fx = ["fade", "slide", "pop"]
    ciclo = 0
    linhas = [cabecalho]
    for item in sync:
        ini = item["start"]
        fim = item["end"]
        txt = item["text"].upper()
        kw = item.get("keyword")

        if kw:
            alvo = kw.upper()
            if alvo in txt:
                realce = (
                    f"{{\\c{cor_ass}\\t(0,220,\\fscx112\\fscy112)"
                    f"\\t(220,440,\\fscx100\\fscy100)}}{alvo}{{\\c&H00FFFFFF&}}"
                )
                txt = txt.replace(alvo, realce, 1)

        txt = _quebrar(txt, perfil.max_chars)

        if estilo_animacao in ("auto", "mix"):
            estilo = estilos_fx[ciclo % len(estilos_fx)]
            ciclo += 1
        else:
            estilo = estilo_animacao

        if estilo == "slide":
            # Mantem o texto visivel no rodape (Alignment=2); \move usa
            # coordenadas absolutas no PlayRes 1920x1080.
            fx = "{\\move(960,1010,960,990,0,200)\\fad(100,100)}"
        elif estilo == "pop":
            fx = "{\\fscx150\\fscy150\\t(0,200,\\fscx100\\fscy100)\\fad(80,100)}"
        else:
            fx = "{\\fad(140,120)}"

        linhas.append(
            f"Dialogue: 0,{_tc(ini)},{_tc(fim)},Verso,,0,0,0,,{fx}{txt}"
        )
    Path(caminho_saida).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return Path(caminho_saida)


def _clonar_words(words: list, ini_linha: float) -> list:
    """Words validas, ordenadas, sem sobrepor. Preenche buracos entre palavras.

    O \\kf soma duracoes: nao pode haver vao nem sobreposicao entre palavras da
    mesma linha, senao a varredura descola da voz.
    """
    limpos = []
    prev = ini_linha
    for w in words:
        t = w.get("text", "").strip()
        if not t:
            continue
        s = max(float(w.get("start", prev)), prev)
        e = max(float(w.get("end", s)), s + 0.05)
        limpos.append({"text": t, "start": s, "end": e})
        prev = e
    return limpos


def gerar_ass_karaoke(
    sync: list,
    caminho_saida: Path,
    cor_destaque_hex: str,
    fonte: str = "Cinzel",
    corpo: int = None,
    perfil: PerfilLegenda | str = "master",
) -> Path:
    """Gera .ass KARAOKE fill-sweep (\\kf) — cada palavra varre a cor no seu tempo.

    Precisa de `words` (start/end por palavra) em cada item de `sync`; use o
    sincronizar_letra.alinhar novo, que grava esse campo. A palavra ja cantada
    fica na cor de destaque; a que esta sendo cantada varre branco->destaque; a
    por-vir fica branca.

    PrimaryColour = cor JA preenchida (destaque); SecondaryColour = cor ainda
    NAO preenchida (branco). O \\kf anima da secundaria para a primaria.

    `perfil` define PlayRes real, margens e quebra por linha (px fixo 50). A
    quebra respeita a largura do formato — no Short a linha e curta, entao
    quebra cedo e NAO vaza pelas bordas.
    """
    perfil = perfil if isinstance(perfil, PerfilLegenda) else perfil_para(perfil)
    if corpo is not None:
        perfil = replace(perfil, corpo_px=corpo)
    cor_ass = hex_para_ass(cor_destaque_hex)   # &H00BBGGRR
    cabecalho = _cabecalho_ass(perfil, cor_ass, fonte, karaoke=True,
                               comentario="legenda KARAOKE fill-sweep")
    linhas = [cabecalho]
    n = len(sync)
    for i, item in enumerate(sync):
        words = _clonar_words(item.get("words") or [], float(item["start"]))
        if not words:
            # sem palavras: cai no comportamento simples (linha inteira, fade)
            ini, fim = float(item["start"]), float(item["end"])
            txt = _quebrar(item["text"].upper(), perfil.max_chars)
            linhas.append(
                f"Dialogue: 0,{_tc(ini)},{_tc(fim)},Karaoke,,0,0,0,,"
                f"{{\\fad(120,100)}}{txt}")
            continue

        ini = words[0]["start"]
        # Teto duro: a linha NUNCA pode passar do inicio da proxima (menos um
        # respiro de 0,04s). O Whisper as vezes deixa a ultima palavra terminar
        # depois do inicio da linha seguinte; cortamos a palavra E a linha nesse
        # teto para nao haver sobreposicao (o porteiro reprova qualquer invasao).
        teto = float(item["end"])
        if i + 1 < n:
            prox_ini = float(sync[i + 1].get("start", teto))
            teto = min(teto, prox_ini - 0.04)
        # a ultima palavra nao pode passar do teto
        if words[-1]["end"] > teto > words[-1]["start"] + 0.03:
            words[-1]["end"] = teto
        fim = max(words[-1]["end"], ini + 0.10)
        if fim > teto:
            fim = words[-1]["end"] = teto

        # Constroi a varredura cobrindo TODA a linha (ini..fim):
        #  - o vao ANTES de cada palavra soma ao \kf da palavra anterior (ela
        #    fica acesa durante o silencio), ou vira um \kf invisivel no comeco;
        #  - a sobra depois da ultima palavra estica o \kf dela ate 'fim'.
        # Assim soma(\kf) == (fim - ini) e a varredura nao trava nem estoura.
        alvo_cs = max(1, int(round((fim - ini) * 100)))
        partes = []
        chars_linha = 0
        soma_cs = 0
        for idx, w in enumerate(words):
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            # vao ate a proxima palavra (ou ate o fim, na ultima) acresce nesta
            prox = words[idx + 1]["start"] if idx + 1 < len(words) else fim
            gap_cs = max(0, int(round((prox - w["end"]) * 100)))
            cs = dur_cs + gap_cs
            palavra = w["text"].upper()
            if chars_linha > 0 and chars_linha + len(palavra) + 1 > perfil.max_chars:
                if partes and partes[-1].endswith(" "):
                    partes[-1] = partes[-1][:-1] + "\\N"
                chars_linha = 0
            partes.append(f"{{\\kf{cs}}}{palavra} ")
            soma_cs += cs
            chars_linha += len(palavra) + 1
        # Casa a soma dos \kf com a duracao da linha EXATAMENTE.
        # O piso de cada \kf e 1cs, entao a soma minima possivel = nº de palavras;
        # se 'alvo_cs' e menor que isso (linha degenerada, ex.: 0,02s de duas
        # palavras repetidas), estende a linha ate caber o minimo — uma legenda
        # de 2cs nao existe na tela de qualquer forma.
        n_kf = len(re.findall(r"\\kf(\d+)", "".join(partes)))
        if alvo_cs < n_kf:
            alvo_cs = n_kf
            fim = ini + alvo_cs / 100.0
            # respeita o teto (nao invade a proxima); se nao couber, mantem o teto
            if i + 1 < n:
                fim = min(fim, float(sync[i + 1].get("start", fim)) - 0.01)
        if partes and soma_cs != alvo_cs:
            diff = alvo_cs - soma_cs
            kfs = [int(x) for x in re.findall(r"\\kf(\d+)", "".join(partes))]
            # distribui a diferenca proporcionalmente, mantendo cada \kf >= 1
            if diff > 0:
                # sobra: joga tudo na ultima palavra (ela fica acesa mais tempo)
                m_kf = list(re.finditer(r"\\kf(\d+)", partes[-1]))
                if m_kf:
                    novo = int(m_kf[-1].group(1)) + diff
                    partes[-1] = re.sub(r"\\kf\d+", f"\\\\kf{novo}", partes[-1], count=1)
            else:
                # falta (soma > alvo): tira dos maiores \kf, sem descer de 1
                falta = -diff
                idxs = sorted(range(len(kfs)), key=lambda k: -kfs[k])
                cortes = {}
                j = 0
                while falta > 0 and any(kfs[k] > 1 for k in idxs):
                    k = idxs[j % len(idxs)]
                    if kfs[k] > 1:
                        kfs[k] -= 1
                        cortes[k] = kfs[k]
                        falta -= 1
                    j += 1
                # reaplica os \kf ajustados na ordem
                it = iter(kfs)
                partes = [re.sub(r"\\kf\d+", lambda mm: f"\\kf{next(it)}", p, count=1)
                          for p in partes]
        corpo_txt = "".join(partes).rstrip()
        linhas.append(
            f"Dialogue: 0,{_tc(ini)},{_tc(fim)},Karaoke,,0,0,0,,"
            f"{{\\fad(120,80)}}{corpo_txt}")
    Path(caminho_saida).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return Path(caminho_saida)


# ---------------------------------------------------------------------------
# Ler o .ass de volta (para o porteiro e o sincronizar)
# ---------------------------------------------------------------------------

_RE_DIALOG = re.compile(
    r"^Dialogue:\s*\d+,(\d+:\d\d:\d\d\.\d\d),(\d+:\d\d:\d\d\.\d\d),([^,]*),",
    re.IGNORECASE,
)


def _tc_para_seg(tc: str) -> float:
    h, m, s = tc.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _texto_limpo_evento(linha: str) -> str:
    # tudo depois do 9o campo e o texto; remove tags {\...} e \N
    partes = linha.split(",", 9)
    txt = partes[9] if len(partes) >= 10 else ""
    txt = re.sub(r"\{[^}]*\}", "", txt)
    txt = txt.replace("\\N", " ")
    return txt.strip()


def eventos_sobre_silencio(eventos, energia, *, janela: float = 0.5,
                           limiar_db: float | None = None,
                           max_frac_silencio: float = 0.8) -> list[dict]:
    """Eventos de legenda exibidos enquanto o STEM VOCAL esta em silencio.

    Evidencia independente do ASR: `medir_sincronia` compara o ASS com os mesmos
    onsets que o geraram (circular). Aqui a prova e a energia real da voz. Uma
    linha cuja duracao cai >80% em silencio vocal esta fora do lugar.

    eventos: [(ini, fim, texto, ...)]; energia: [(t, dB)] de transcrever.energia_vocal.
    """
    import statistics
    if not eventos or not energia:
        return []
    dbs = sorted(d for _, d in energia)
    limiar = limiar_db if limiar_db is not None else dbs[int(len(dbs) * 0.9) - 1] - 12.0
    ruins = []
    for ev in eventos:
        ini, fim, texto = float(ev[0]), float(ev[1]), ev[2]
        jan = [d for t, d in energia if ini - janela / 2 <= t < fim]
        if not jan:
            continue
        frac = sum(1 for d in jan if d < limiar) / len(jan)
        if frac > max_frac_silencio:
            ruins.append({"inicio": round(ini, 2), "fim": round(fim, 2),
                          "texto": texto, "silencio": round(frac, 2),
                          "voz_media_db": round(statistics.mean(jan), 1)})
    return ruins


def _eventos_do_ass(caminho: Path):
    saida = []
    for linha in Path(caminho).read_text(encoding="utf-8", errors="replace").splitlines():
        m = _RE_DIALOG.match(linha)
        if not m:
            continue
        # ignora desenhos vetoriais (\p1) — nao sao letra, sao seguidores
        if "\\p1" in linha or re.search(r"\bm\s+\d+\s+\d+\s+l\s", linha):
            continue
        ini = _tc_para_seg(m.group(1))
        fim = _tc_para_seg(m.group(2))
        saida.append((ini, fim, _texto_limpo_evento(linha), linha))
    return saida


# ---------------------------------------------------------------------------
# Onset da voz (palavras_vocal.json / transcricao.json)
# ---------------------------------------------------------------------------

def carregar_onsets(caminho: Path) -> List[Tuple[float, str]]:
    """Le a saida do Whisper com word_timestamps. Aceita dois formatos:

    - lista de segmentos com 'words': [{word,start,end}, ...]  (transcricao.json)
    - lista de palavras direto: [{word,start,end}, ...]        (palavras_vocal.json)

    Retorna [(start, palavra_normalizada), ...] ordenada por tempo.
    """
    dados = json.loads(Path(caminho).read_text(encoding="utf-8", errors="replace"))
    palavras: List[Tuple[float, str]] = []

    def add(w):
        try:
            t = float(w.get("start"))
        except (TypeError, ValueError):
            return
        token = _norm(str(w.get("word", "")))
        if token:
            palavras.append((t, token))

    if isinstance(dados, dict) and "words" in dados:
        for w in dados["words"]:
            add(w)
    elif isinstance(dados, list):
        for item in dados:
            if isinstance(item, dict) and "words" in item and isinstance(item["words"], list):
                for w in item["words"]:
                    add(w)
            elif isinstance(item, dict) and "word" in item:
                add(item)
    palavras.sort(key=lambda x: x[0])
    return palavras


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\wàáâãéêíóôõúüç]", "", s, flags=re.UNICODE)
    return s


def _primeira_palavra(texto: str) -> str:
    for tok in texto.split():
        n = _norm(tok)
        if n:
            return n
    return ""


def _onset_para(texto: str, tempo_ass: float,
                onsets: List[Tuple[float, str]]) -> Optional[float]:
    """Acha o onset da palavra ativa do evento, ancorado perto do tempo do .ass."""
    payload = texto
    if texto.lstrip().startswith("Dialogue:"):
        partes = texto.split(",", 9)
        if len(partes) == 10:
            payload = partes[9]

    # Se houver tag de destaque (\b1), a palavra ativa vem apos esse bloco.
    m_destaque = re.search(r"\{[^}]*\\b1[^}]*\}([^{]+)", payload)
    if m_destaque:
        alvo = _primeira_palavra(m_destaque.group(1))
    else:
        limpo = re.sub(r"\{[^}]*\}", "", payload)
        alvo = _primeira_palavra(limpo)

    if not alvo:
        return None
    melhor, melhor_d = None, 6.0
    for t, palavra in onsets:
        if palavra == alvo or (len(alvo) >= 4 and palavra.startswith(alvo[:4])):
            d = abs(t - tempo_ass)
            if d < melhor_d:
                melhor, melhor_d = t, d
    return melhor


# ---------------------------------------------------------------------------
# Porteiro de sincronia
# ---------------------------------------------------------------------------

@dataclass
class RelatorioSincronia:
    aprovado: bool
    mediana: float
    p90: float
    n_medidos: int
    n_total: int
    fora: List[Tuple[float, str, float]]  # (tempo_ass, texto, desvio)
    motivo: str = ""


def medir_sincronia(caminho_ass: Path,
                    caminho_onsets: Path) -> RelatorioSincronia:
    eventos = _eventos_do_ass(caminho_ass)
    onsets = carregar_onsets(caminho_onsets)
    desvios: List[float] = []
    fora: List[Tuple[float, str, float]] = []
    for ini, _fim, texto, linha_bruta in eventos:
        if not texto:
            continue
        onset = _onset_para(linha_bruta, ini, onsets)
        if onset is None:
            continue
        d = ini - onset  # positivo = legenda ADIANTADA (entra antes da voz)
        desvios.append(d)
        if abs(d) > 0.30:
            fora.append((ini, texto, round(d, 3)))

    if not desvios:
        return RelatorioSincronia(False, 0, 0, 0, len(eventos), [],
                                  "sem onsets casados — relogio errado?")
    mediana = statistics.median(desvios)
    p90 = sorted(abs(x) for x in desvios)[max(0, int(len(desvios) * 0.9) - 1)]

    if abs(mediana) > 3.0:
        return RelatorioSincronia(
            False, round(mediana, 3), round(p90, 3), len(desvios),
            len(eventos), fora,
            "desvio mediano > 3 s: sao arquivos de CORTES DIFERENTES, nao dessincronia.",
        )
    aprovado = abs(mediana) <= 0.15 and p90 <= 0.30
    return RelatorioSincronia(aprovado, round(mediana, 3), round(p90, 3),
                              len(desvios), len(eventos), fora)


def sincronizar(caminho_ass: Path, caminho_onsets: Path) -> int:
    """Reescreve SO os tempos do .ass pela voz. Guarda .bak. Retorna nº ajustado."""
    from datetime import date
    caminho_ass = Path(caminho_ass)
    original = caminho_ass.read_text(encoding="utf-8", errors="replace")
    bak = caminho_ass.with_suffix(
        caminho_ass.suffix + f".bak-dessincronizado-{date.today():%Y%m%d}")
    if not bak.exists():
        bak.write_text(original, encoding="utf-8")

    onsets = carregar_onsets(caminho_onsets)
    saida_linhas: List[str] = []
    ajustados = 0
    eventos = _eventos_do_ass(caminho_ass)
    idx_evento = 0

    for linha in original.splitlines():
        m = _RE_DIALOG.match(linha)
        if not m or "\\p1" in linha:
            saida_linhas.append(linha)
            continue
        # localiza o evento correspondente (mesma ordem)
        if idx_evento >= len(eventos):
            saida_linhas.append(linha)
            continue
        ini, fim, texto, _ = eventos[idx_evento]
        idx_evento += 1
        onset = _onset_para(texto, ini, onsets)
        if onset is None:
            saida_linhas.append(linha)
            continue
        delta = onset - ini
        if abs(delta) < 0.02:
            saida_linhas.append(linha)
            continue
        novo_ini, novo_fim = ini + delta, fim + delta
        nova = re.sub(
            _RE_DIALOG,
            lambda mm: f"Dialogue: 0,{_tc(novo_ini)},{_tc(novo_fim)},{mm.group(3)},",
            linha, count=1,
        )
        saida_linhas.append(nova)
        ajustados += 1

    caminho_ass.write_text("\n".join(saida_linhas) + "\n", encoding="utf-8")
    return ajustados
