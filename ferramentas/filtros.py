#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""filtros.py — a caixa de efeitos do canal VX RAPS.

Uma biblioteca so de filtros ffmpeg, nomeados, componiveis e — o que importa —
encaixados no BEAT. O `ritmo.py` mede a grade musical; aqui os efeitos pulsam
nela em vez de pulsar em tempos aleatorios.

    🔴 Efeito fora do beat e ruido visual. Efeito no beat e edicao.

Uso como biblioteca:

    import filtros as flt

    # cadeia simples, sem ritmo
    vf = flt.montar(["bloom", "grao", "vinheta"])

    # cadeia com pulso no beat (precisa da grade do ritmo.py)
    grade = ritmo.medir_grade(master)
    vf = flt.montar(["grade_cor", "zoom_pulse", "bloom"],
                    grade=grade, cor="#00F0A0", duracao=34.5)

    # aplicar num arquivo (passa por render_dispatch -> GPU)
    flt.aplicar(entrada, saida, ["bloom", "shake"], grade=grade)

Uso como CLI:

    python filtros.py listar
    python filtros.py aplicar in.mp4 out.mp4 --efeitos bloom,grao,vinheta
    python filtros.py aplicar in.mp4 out.mp4 --efeitos zoom_pulse --bpm 140
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_dispatch as rd  # noqa: E402

try:
    import ritmo as ritmo_mod  # noqa: E402
except Exception:  # pragma: no cover - ritmo depende de numpy
    ritmo_mod = None


# ---------------------------------------------------------------------------
# Constantes de intensidade
#
# Todo efeito tem uma intensidade 0..1 que mapeia para os parametros reais.
# Os limites abaixo foram escolhidos para ficarem no ponto do canal: visiveis
# num Short de celular, sem virar poluicao no video longo em tela grande.
# ---------------------------------------------------------------------------

INTENSIDADE_PADRAO = 0.6

BLOOM_MIN, BLOOM_MAX = 0.10, 0.45          # peso da camada de glow
ABERRACAO_MIN, BERRACAO_MAX = 1.0, 6.0     # deslocamento RGB em pixels
GRAO_MIN, GRAO_MAX = 4.0, 22.0             # forca do noise
VINHETA_MIN, VINHETA_MAX = 0.55, 1.25      # angulo (menor = mais escuro nos cantos)
SHAKE_MIN, SHAKE_MAX = 2.0, 14.0           # amplitude do tremor em pixels
ZOOM_MIN, ZOOM_MAX = 0.01, 0.08            # amplitude do pulso de zoom
SATURACAO_MIN, SATURACAO_MAX = 1.0, 1.6
CONTRASTE_MIN, CONTRASTE_MAX = 1.0, 1.35

# Um flash dura 2 frames a 30fps. Curto de proposito: mais que isso cega.
FLASH_FRAMES = 2
FPS_REFERENCIA = 30.0

# Piso de confianca da grade para deixar um efeito ritmico entrar.
# Espelha o piso do ritmo.py: grade errada e pior que grade nenhuma.
CONFIANCA_MINIMA_RITMO = 0.25


def _lerp(minimo: float, maximo: float, t: float) -> float:
    t = max(0.0, min(1.0, t))
    return minimo + (maximo - minimo) * t


def _hex_para_rgb(cor_hex: str) -> tuple[float, float, float]:
    """'#00F0A0' -> (0.0, 0.94, 0.63). Aceita com ou sem '#'."""
    s = (cor_hex or "").lstrip("#").strip()
    if len(s) != 6:
        return (1.0, 1.0, 1.0)
    try:
        return (int(s[0:2], 16) / 255.0,
                int(s[2:4], 16) / 255.0,
                int(s[4:6], 16) / 255.0)
    except ValueError:
        return (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Contexto de um filtro
# ---------------------------------------------------------------------------

@dataclass
class Contexto:
    """Tudo que um filtro pode precisar saber para se montar."""
    intensidade: float = INTENSIDADE_PADRAO
    cor: str = "#FFFFFF"
    duracao: float = 0.0
    bpm: float = 0.0
    periodo: float = 0.0        # segundos por beat
    fase: float = 0.0           # offset do primeiro downbeat
    confianca: float = 0.0
    largura: int = 0
    altura: int = 0
    fps: float = 0.0

    @property
    def tem_ritmo(self) -> bool:
        return self.periodo > 0 and self.confianca >= CONFIANCA_MINIMA_RITMO

    @classmethod
    def de_grade(cls, grade, **kwargs) -> "Contexto":
        """Constroi um contexto a partir de uma Grade do ritmo.py."""
        if grade is None:
            return cls(**kwargs)
        return cls(
            bpm=getattr(grade, "bpm", 0.0),
            periodo=getattr(grade, "periodo", 0.0),
            fase=getattr(grade, "fase", 0.0),
            confianca=getattr(grade, "confianca", 0.0),
            duracao=kwargs.pop("duracao", None) or getattr(grade, "duracao", 0.0),
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Efeitos
#
# Cada efeito e uma funcao Contexto -> string de filtro ffmpeg (ou "" para
# desistir em silencio, quando falta informacao: por exemplo um efeito ritmico
# sem grade confiavel).
# ---------------------------------------------------------------------------

def _bloom(ctx: Contexto) -> str:
    """Glow nas altas luzes. O brilho de AMV vem daqui."""
    peso = _lerp(BLOOM_MIN, BLOOM_MAX, ctx.intensidade)
    raio = 8 + int(12 * ctx.intensidade)
    return (
        f"split=2[bl_a][bl_b];"
        f"[bl_b]curves=all='0/0 0.6/0.35 1/1',gblur=sigma={raio}[bl_glow];"
        f"[bl_a][bl_glow]blend=all_mode=screen:all_opacity={peso:.3f}"
    )


def _aberracao(ctx: Contexto) -> str:
    """Separacao cromatica RGB. Sensacao de lente e de energia."""
    d = _lerp(ABERRACAO_MIN, BERRACAO_MAX, ctx.intensidade)
    return f"rgbashift=rh=-{d:.1f}:bh={d:.1f}:rv={d / 2:.1f}:bv=-{d / 2:.1f}"


def _grao(ctx: Contexto) -> str:
    """Film grain. Tira o aspecto digital limpo demais."""
    forca = _lerp(GRAO_MIN, GRAO_MAX, ctx.intensidade)
    return f"noise=alls={forca:.0f}:allf=t+u"


def _vinheta(ctx: Contexto) -> str:
    """Escurece os cantos e joga o olho no centro do quadro."""
    ang = _lerp(VINHETA_MAX, VINHETA_MIN, ctx.intensidade)  # invertido: menor = mais forte
    return f"vignette=angle={ang:.3f}"


def _grade_cor(ctx: Contexto) -> str:
    """Color grading puxando a cor do personagem (projeto.json cor.destaque)."""
    r, g, b = _hex_para_rgb(ctx.cor)
    # Puxa cada canal na direcao da cor de destaque, proporcional a intensidade.
    forca = 0.25 * ctx.intensidade
    sat = _lerp(SATURACAO_MIN, SATURACAO_MAX, ctx.intensidade)
    con = _lerp(CONTRASTE_MIN, CONTRASTE_MAX, ctx.intensidade)
    return (
        f"colorbalance="
        f"rs={(r - 0.5) * forca:.3f}:gs={(g - 0.5) * forca:.3f}:bs={(b - 0.5) * forca:.3f}:"
        f"rm={(r - 0.5) * forca * 0.6:.3f}:gm={(g - 0.5) * forca * 0.6:.3f}:bm={(b - 0.5) * forca * 0.6:.3f},"
        f"eq=saturation={sat:.3f}:contrast={con:.3f}"
    )


def _nitidez(ctx: Contexto) -> str:
    """Unsharp leve. Recupera detalhe perdido no upscale do anime."""
    forca = 0.4 + 0.8 * ctx.intensidade
    return f"unsharp=5:5:{forca:.2f}:5:5:0.0"


# --- efeitos ritmicos (precisam da grade) ----------------------------------

def _expr_fase_beat(ctx: Contexto, var_tempo: str = "t") -> str:
    """Expressao ffmpeg: posicao dentro do beat atual, 0..1.

    mod(t - fase, periodo) / periodo — anda de 0 a 1 a cada batida.
    O `zoompan` nao expõe `t`; lá a variavel de tempo chama `time`.
    """
    return (f"(mod({var_tempo}-{ctx.fase:.4f}\\,{ctx.periodo:.4f})"
            f"/{ctx.periodo:.4f})")


def _zoom_pulse(ctx: Contexto) -> str:
    """Pulso de zoom NA BATIDA. O efeito que mais entrega ritmo.

    O zoom estoura no downbeat e relaxa ate o proximo. Sem grade confiavel,
    nao entra: zoom fora do beat parece defeito, nao edicao.

    Usa `zoompan`, nao `crop`: o crop avalia largura/altura UMA vez na
    inicializacao, entao um w/h que depende de `t` falha com
    "Error when evaluating the expression". O zoompan reavalia por quadro.
    """
    if not ctx.tem_ritmo:
        return ""
    if not (ctx.largura and ctx.altura):
        # zoompan precisa de um tamanho de saida explicito; sem as dimensoes
        # reais ele cai no padrao hd720 e destroi o enquadramento vertical.
        return ""
    amp = _lerp(ZOOM_MIN, ZOOM_MAX, ctx.intensidade)
    fase = _expr_fase_beat(ctx, var_tempo="time")
    # decaimento exponencial dentro do beat: forte no ataque, suave no fim
    z = f"1+{amp:.4f}*exp(-3*{fase})"
    fps = ctx.fps or FPS_REFERENCIA
    return (
        f"zoompan=z='{z}'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={ctx.largura}x{ctx.altura}:fps={fps:g}"
    )


def _shake(ctx: Contexto) -> str:
    """Tremor de impacto no downbeat. Camera reagindo ao golpe."""
    if not ctx.tem_ritmo:
        return ""
    amp = _lerp(SHAKE_MIN, SHAKE_MAX, ctx.intensidade)
    fase = _expr_fase_beat(ctx)
    decai = f"exp(-6*{fase})"
    dx = f"{amp:.2f}*{decai}*sin(t*97)"
    dy = f"{amp:.2f}*{decai}*cos(t*131)"
    pad = int(amp) + 2
    return (
        f"pad=iw+{pad * 2}:ih+{pad * 2}:{pad}:{pad}:black,"
        f"crop=w=iw-{pad * 2}:h=ih-{pad * 2}:x={pad}+({dx}):y={pad}+({dy})"
    )


def _flash(ctx: Contexto) -> str:
    """Clarao branco curto no downbeat. Marca a virada."""
    if not ctx.tem_ritmo:
        return ""
    janela = FLASH_FRAMES / FPS_REFERENCIA
    limite = janela / ctx.periodo
    fase = _expr_fase_beat(ctx)
    pico = 0.35 + 0.35 * ctx.intensidade
    # brilho extra somente nos primeiros frames do beat
    return f"eq=brightness='if(lt({fase}\\,{limite:.4f})\\,{pico:.3f}\\,0)'"


def _pulso_cor(ctx: Contexto) -> str:
    """Saturacao pulsando no beat. Sutil, mas o olho sente."""
    if not ctx.tem_ritmo:
        return ""
    amp = 0.15 + 0.35 * ctx.intensidade
    fase = _expr_fase_beat(ctx)
    return f"eq=saturation='1+{amp:.3f}*exp(-4*{fase})'"


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

@dataclass
class Efeito:
    nome: str
    descricao: str
    montar: Callable[[Contexto], str]
    ritmico: bool = False
    usa_split: bool = False     # usa filtros de grafo (split/blend), nao cabe em -vf simples


CATALOGO: Dict[str, Efeito] = {
    "bloom": Efeito("bloom", "glow nas altas luzes (brilho de AMV)", _bloom, usa_split=True),
    "aberracao": Efeito("aberracao", "separacao cromatica RGB nas bordas", _aberracao),
    "grao": Efeito("grao", "film grain, tira o aspecto digital", _grao),
    "vinheta": Efeito("vinheta", "escurece os cantos, foca o centro", _vinheta),
    "grade_cor": Efeito("grade_cor", "grading na cor do personagem", _grade_cor),
    "nitidez": Efeito("nitidez", "unsharp leve, recupera detalhe", _nitidez),
    "zoom_pulse": Efeito("zoom_pulse", "pulso de zoom NA BATIDA", _zoom_pulse, ritmico=True),
    "shake": Efeito("shake", "tremor de impacto no downbeat", _shake, ritmico=True),
    "flash": Efeito("flash", "clarao branco curto no downbeat", _flash, ritmico=True),
    "pulso_cor": Efeito("pulso_cor", "saturacao pulsando no beat", _pulso_cor, ritmico=True),
}

# Receitas prontas: combinacoes que funcionam juntas, testadas no canal.
RECEITAS: Dict[str, List[str]] = {
    "amv": ["grade_cor", "bloom", "zoom_pulse", "vinheta"],
    "impacto": ["grade_cor", "shake", "flash", "aberracao", "vinheta"],
    "suave": ["grade_cor", "bloom", "pulso_cor"],
    "cru": ["nitidez", "grao", "vinheta"],
    "short": ["grade_cor", "bloom", "zoom_pulse", "nitidez", "vinheta"],
}


def listar() -> None:
    print("== efeitos ==")
    for e in CATALOGO.values():
        marca = " [beat]" if e.ritmico else ""
        print(f"  {e.nome:<12} {e.descricao}{marca}")
    print()
    print("== receitas ==")
    for nome, efeitos in RECEITAS.items():
        print(f"  {nome:<10} {', '.join(efeitos)}")
    print()
    print("[beat] = precisa da grade do ritmo.py (confianca >= "
          f"{CONFIANCA_MINIMA_RITMO}); sem ela o efeito nao entra.")


# ---------------------------------------------------------------------------
# Montagem da cadeia
# ---------------------------------------------------------------------------

@dataclass
class Cadeia:
    filtro: str
    aplicados: List[str] = field(default_factory=list)
    ignorados: List[str] = field(default_factory=list)
    complexo: bool = False

    def __bool__(self) -> bool:
        return bool(self.filtro)


def resolver_nomes(efeitos: Sequence[str]) -> List[str]:
    """Expande receitas e valida nomes. 'amv' -> ['grade_cor','bloom',...]."""
    saida: List[str] = []
    for nome in efeitos:
        n = (nome or "").strip().lower()
        if not n:
            continue
        if n in RECEITAS:
            saida.extend(RECEITAS[n])
        elif n in CATALOGO:
            saida.append(n)
        else:
            conhecidos = ", ".join(sorted(list(CATALOGO) + list(RECEITAS)))
            raise ValueError(f"efeito desconhecido: '{n}'. Conhecidos: {conhecidos}")
    # remove duplicatas preservando a ordem
    vistos: set[str] = set()
    return [n for n in saida if not (n in vistos or vistos.add(n))]


def montar(efeitos: Sequence[str], grade=None, cor: str = "#FFFFFF",
           intensidade: float = INTENSIDADE_PADRAO, duracao: float = 0.0,
           largura: int = 0, altura: int = 0, fps: float = 0.0,
           ctx: Optional[Contexto] = None) -> Cadeia:
    """Monta a cadeia de filtros ffmpeg para os efeitos pedidos.

    Efeitos ritmicos sem grade confiavel sao ignorados em silencio e listados
    em `Cadeia.ignorados` — a chamada nao falha por isso.
    """
    nomes = resolver_nomes(efeitos)
    if ctx is None:
        ctx = Contexto.de_grade(grade, cor=cor, intensidade=intensidade,
                               duracao=duracao, largura=largura,
                               altura=altura, fps=fps)

    partes: List[str] = []
    aplicados: List[str] = []
    ignorados: List[str] = []
    complexo = False

    for nome in nomes:
        efeito = CATALOGO[nome]
        trecho = efeito.montar(ctx)
        if not trecho:
            ignorados.append(nome)
            continue
        partes.append(trecho)
        aplicados.append(nome)
        if efeito.usa_split:
            complexo = True

    return Cadeia(filtro=",".join(partes), aplicados=aplicados,
                  ignorados=ignorados, complexo=complexo)


# ---------------------------------------------------------------------------
# Aplicacao
# ---------------------------------------------------------------------------

def sondar_video(caminho: Path) -> tuple[int, int, float]:
    """Le largura, altura e fps do arquivo. (0, 0, 0.0) se o ffprobe falhar.

    O `zoom_pulse` depende disso: sem o tamanho real, o zoompan cai no padrao
    hd720 e arruina o enquadramento 9:16 dos cortes.
    """
    import subprocess
    try:
        r = subprocess.run(
            [rd.ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate",
             "-of", "default=nw=1:nk=1", str(caminho)],
            capture_output=True, text=True, timeout=30,
        )
        linhas = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        if len(linhas) < 3:
            return (0, 0, 0.0)
        largura, altura = int(linhas[0]), int(linhas[1])
        num, _, den = linhas[2].partition("/")
        fps = float(num) / float(den or 1)
        return (largura, altura, round(fps, 3))
    except Exception:
        return (0, 0, 0.0)


def medir_grade(caminho: Path):
    """Mede a grade musical do arquivo. None se o ritmo.py nao estiver util."""
    if ritmo_mod is None:
        return None
    try:
        return ritmo_mod.medir_grade(Path(caminho))
    except Exception as exc:
        print(f"  [filtros] nao foi possivel medir a grade: {exc}")
        return None


def aplicar(entrada: Path, saida: Path, efeitos: Sequence[str],
            grade=None, cor: str = "#FFFFFF",
            intensidade: float = INTENSIDADE_PADRAO,
            medir_ritmo: bool = True, silencioso: bool = False) -> Path:
    """Aplica os efeitos em `entrada` e grava em `saida`. Encode via GPU.

    Se algum efeito pedido for ritmico e nenhuma grade foi passada, mede a
    grade do proprio arquivo de entrada.
    """
    entrada, saida = Path(entrada), Path(saida)
    if not entrada.exists():
        raise FileNotFoundError(f"entrada ausente: {entrada}")
    if entrada.resolve() == saida.resolve():
        raise ValueError("entrada e saida sao o mesmo arquivo")

    nomes = resolver_nomes(efeitos)
    precisa_ritmo = any(CATALOGO[n].ritmico for n in nomes)
    if precisa_ritmo and grade is None and medir_ritmo:
        if not silencioso:
            print("  [filtros] medindo a grade musical...")
        grade = medir_grade(entrada)

    largura, altura, fps = sondar_video(entrada)
    cadeia = montar(nomes, grade=grade, cor=cor, intensidade=intensidade,
                    largura=largura, altura=altura, fps=fps)
    if not cadeia:
        raise ValueError("nenhum efeito aplicavel na cadeia")

    if not silencioso:
        if grade is not None and getattr(grade, "bpm", 0):
            print(f"  [filtros] grade: {grade.bpm} bpm  "
                  f"confianca={grade.confianca}")
        print(f"  [filtros] aplicando: {', '.join(cadeia.aplicados)}")
        if cadeia.ignorados:
            print(f"  [filtros] ignorados (sem grade confiavel): "
                  f"{', '.join(cadeia.ignorados)}")

    saida.parent.mkdir(parents=True, exist_ok=True)

    if cadeia.complexo:
        # filtros com split/blend precisam de -filter_complex e mapa explicito
        rd.encode(
            saida=str(saida),
            entradas=["-i", str(entrada)],
            filtro_complexo=f"[0:v]{cadeia.filtro}[v]",
            mapa=["-map", "[v]", "-map", "0:a?"],
            silencioso=silencioso,
        )
    else:
        rd.encode(
            saida=str(saida),
            entradas=["-i", str(entrada)],
            filtro_v=cadeia.filtro,
            mapa=["-map", "0:v", "-map", "0:a?"],
            silencioso=silencioso,
        )
    return saida


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _grade_falsa(bpm: float, duracao: float = 0.0):
    """Grade sintetica a partir de um BPM informado a mao (--bpm)."""
    @dataclass
    class _G:
        bpm: float
        periodo: float
        fase: float
        confianca: float
        duracao: float
    periodo = 60.0 / bpm if bpm > 0 else 0.0
    return _G(bpm=bpm, periodo=periodo, fase=0.0, confianca=1.0, duracao=duracao)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="filtros e VFX do VX RAPS")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("listar", help="lista efeitos e receitas")

    ap = sub.add_parser("aplicar", help="aplica efeitos num arquivo")
    ap.add_argument("entrada")
    ap.add_argument("saida")
    ap.add_argument("--efeitos", required=True,
                    help="nomes separados por virgula, ou uma receita")
    ap.add_argument("--cor", default="#FFFFFF", help="cor de destaque do personagem")
    ap.add_argument("--intensidade", type=float, default=INTENSIDADE_PADRAO)
    ap.add_argument("--bpm", type=float, default=0.0,
                    help="informa o BPM a mao em vez de medir")
    ap.add_argument("--sem-ritmo", action="store_true",
                    help="nao mede a grade; efeitos ritmicos sao ignorados")

    pv = sub.add_parser("previa", help="mostra a cadeia sem renderizar")
    pv.add_argument("--efeitos", required=True)
    pv.add_argument("--cor", default="#FFFFFF")
    pv.add_argument("--intensidade", type=float, default=INTENSIDADE_PADRAO)
    pv.add_argument("--bpm", type=float, default=140.0)
    pv.add_argument("--largura", type=int, default=1080)
    pv.add_argument("--altura", type=int, default=1920)
    pv.add_argument("--fps", type=float, default=FPS_REFERENCIA)

    a = p.parse_args(argv)

    if a.cmd == "listar":
        listar()
        return 0

    efeitos = [s for s in a.efeitos.split(",") if s.strip()]

    if a.cmd == "previa":
        cadeia = montar(efeitos, grade=_grade_falsa(a.bpm), cor=a.cor,
                        intensidade=a.intensidade, largura=a.largura,
                        altura=a.altura, fps=a.fps)
        print(f"aplicados: {', '.join(cadeia.aplicados) or '(nenhum)'}")
        if cadeia.ignorados:
            print(f"ignorados: {', '.join(cadeia.ignorados)}")
        print(f"complexo:  {'sim (-filter_complex)' if cadeia.complexo else 'nao (-vf)'}")
        print()
        print(cadeia.filtro)
        return 0

    grade = _grade_falsa(a.bpm) if a.bpm > 0 else None
    aplicar(Path(a.entrada), Path(a.saida), efeitos, grade=grade, cor=a.cor,
            intensidade=a.intensidade, medir_ritmo=not a.sem_ritmo)
    print(f"pronto: {a.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
