#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa.py — QA UNIFICADO do canal VX RAPS.

Roda TODOS os porteiros em sequencia e gera um relatorio consolidado com
scores e severidades. O relatorio e a unica coisa que voce precisa ler.

Comandos:
    python qa.py <slug>                   # relatorio completo
    python qa.py <slug> --json            # saida JSON (para CI/automacao)
    python qa.py <slug> --porteiros-only  # so os porteiros (sem analise)
    python qa.py <slug> --rapido          # so os criticos (legenda + imagem)

Porteiros (por severidade):
    CRITICO  (bloqueia publicacao):
        - legenda sincronizada com a voz (mediana <0.15s, p90 <0.30s)
        - imagem sem tela preta/congelado/pagina
        - audio com loudness e true peak dentro doYouTube
    ALTO (deve corrigir antes):
        - encode com bitrate/resolucao adequados
        - legenda tem conteudo e formato valido
    MEDIO (melhoria recomendada):
        - ritmo com confianca > 0.25
        - projeto com todos os campos obrigatorios
    BAIXO (sugestao):
        - projeto avaliado vs tendencias
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"
sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class Porteiro:
    nome: str
    severidade: str   # "critico", "alto", "medio", "baixo"
    passou: bool
    detalhes: str
    metricas: dict = field(default_factory=dict)


@dataclass
class RelatorioQA:
    slug: str
    aprovado: bool     # True se nenhum CRITICO falhou
    porteiros: List[Porteiro]
    score_geral: int   # 0-100
    bloqueadores: int  # quantos criticos reprovaram


# ---------------------------------------------------------------------------
# Porteiro: legenda
# ---------------------------------------------------------------------------

def _cheque_legenda(slug: str, m: dict, d: Path) -> Porteiro:
    """Verifica se a legenda existe e esta sincronizada."""
    import legenda as leg_mod

    letra = d / m.get("letra", "LETRA.md")
    # legenda ativa = a que o render queima (projeto.json -> legenda_ass)
    ass = d / (m.get("legenda_ass") or f"legendas/{slug}.ass")
    onsets = d / m.get("palavras_vocal", "palavras_vocal.json")

    # etapa 1: existe .ass?
    if not ass.exists():
        return Porteiro("legenda", "critico", False,
                        f"arquivo .ass nao existe: {ass}")

    # etapa 2: tem onsets para medir sincronia?
    if not onsets.exists():
        return Porteiro("legenda", "alto", False,
                        f"palavras_vocal.json ausente — impossivel medir sincronia",
                        {"tem_ass": True})

    try:
        rel = leg_mod.medir_sincronia(ass, onsets)
    except Exception as e:
        return Porteiro("legenda", "critico", False,
                        f"erro ao medir sincronia: {e}")

    return Porteiro(
        nome="legenda",
        severidade="critico",
        passou=rel.aprovado,
        detalhes=(
            f"mediana={rel.mediana:+.3f}s  p90={rel.p90:.3f}s  "
            f"medidos={rel.n_medidos}/{rel.n_total}"
            + (f"  ! {rel.motivo}" if rel.motivo else "")
        ),
        metricas={
            "mediana": rel.mediana, "p90": rel.p90,
            "n_medidos": rel.n_medidos, "n_total": rel.n_total,
            "fora_count": len(rel.fora),
        },
    )


# ---------------------------------------------------------------------------
# Porteiro: imagem
# ---------------------------------------------------------------------------

def _cheque_imagem(slug: str, m: dict, d: Path) -> Porteiro:
    """Verifica se o master tem imagem (sem tela preta/congelado)."""
    import imagem as img_mod
    from estudio import _resolver

    master = _resolver(d, m.get("master", ""))
    if not master.exists():
        return Porteiro("imagem", "critico", False,
                        f"master ausente: {master}")

    try:
        rel = img_mod.analisar(master, pasta_qa=d / "qa")
    except Exception as e:
        return Porteiro("imagem", "critico", False,
                        f"erro ao analisar imagem: {e}")

    return Porteiro(
        nome="imagem",
        severidade="critico",
        passou=rel.aprovado,
        detalhes=(
            f"morto={rel.pct_morto}%  congelado={rel.pct_congelado}%  "
            f"pagina={rel.seg_pagina}s  maior_bloco={rel.maior_bloco_morto}s"
        ),
        metricas={
            "pct_morto": rel.pct_morto,
            "pct_congelado": rel.pct_congelado,
            "seg_pagina": rel.seg_pagina,
            "maior_bloco": rel.maior_bloco_morto,
            "folha": rel.folha,
        },
    )


# ---------------------------------------------------------------------------
# Porteiro: audio
# ---------------------------------------------------------------------------

def _cheque_audio(slug: str, m: dict, d: Path) -> Porteiro:
    """Verifica loudness, true peak e clareza vocal."""
    import audio as audio_mod
    from estudio import _resolver

    master = _resolver(d, m.get("master", ""))
    if not master.exists():
        return Porteiro("audio", "critico", False,
                        f"master ausente: {master}")

    try:
        rel = audio_mod.analisar(master)
    except Exception as e:
        return Porteiro("audio", "critico", False,
                        f"erro ao analisar audio: {e}")

    return Porteiro(
        nome="audio",
        severidade="critico",
        passou=rel.aprovado,
        detalhes=(
            f"lufs={rel.lufs:.1f}  peak={rel.true_peak_dbtp:.1f}dBTP  "
            f"clareza={rel.clareza_vocal:.2f}"
        ),
        metricas={
            "lufs": rel.lufs,
            "true_peak": rel.true_peak_dbtp,
            "clareza_vocal": rel.clareza_vocal,
        },
    )


# ---------------------------------------------------------------------------
# Porteiro: encode
# ---------------------------------------------------------------------------

def _cheque_encode(slug: str, m: dict, d: Path) -> Porteiro:
    """Verifica bitrate, resolucao e FPS do master."""
    import render_dispatch as rd
    from estudio import _resolver
    import subprocess

    master = _resolver(d, m.get("master", ""))
    if not master.exists():
        return Porteiro("encode", "alto", False,
                        f"master ausente: {master}")

    ffprobe = rd.ffprobe_bin()
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,bit_rate,codec_name",
        "-of", "json",
        str(master),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        dados = json.loads(r.stdout)
        stream = dados.get("streams", [{}])[0]
    except Exception as e:
        return Porteiro("encode", "alto", False,
                        f"erro ao ler metadados: {e}")

    width = stream.get("width", 0)
    height = stream.get("height", 0)
    codec = stream.get("codec_name", "?")
    r_frame_rate = stream.get("r_frame_rate", "0/1")
    bitrate = stream.get("bit_rate", "0")

    # calcular FPS
    try:
        num, den = r_frame_rate.split("/")
        fps = round(int(num) / int(den), 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    # calcular bitrate em Mbps
    try:
        bitrate_mbps = round(int(bitrate) / 1_000_000, 1)
    except (ValueError, TypeError):
        bitrate_mbps = 0.0

    motivos = []
    if width < 1920 or height < 1080:
        motivos.append(f"resolucao baixa: {width}x{height} (minimo 1920x1080)")
    if fps < 24:
        motivos.append(f"FPS baixo: {fps} (minimo 24)")
    if bitrate_mbps > 0 and bitrate_mbps < 3.0:
        motivos.append(f"bitrate baixo: {bitrate_mbps} Mbps (minimo 3.0 para 1080p)")

    aprovado = not motivos
    return Porteiro(
        nome="encode",
        severidade="alto",
        passou=aprovado,
        detalhes=f"{codec} {width}x{height} {fps}fps {bitrate_mbps}Mbps",
        metricas={
            "width": width, "height": height,
            "fps": fps, "bitrate_mbps": bitrate_mbps,
            "codec": codec,
        },
    )


# ---------------------------------------------------------------------------
# Porteiro: ritmo
# ---------------------------------------------------------------------------

def _cheque_ritmo(slug: str, m: dict, d: Path) -> Porteiro:
    """Verifica se a grade de BPM tem confianca suficiente."""
    import ritmo as ritmo_mod
    from estudio import _resolver

    master = _resolver(d, m.get("master", ""))
    if not master.exists():
        return Porteiro("ritmo", "medio", False,
                        "master ausente")

    try:
        g = ritmo_mod.medir_grade(master)
    except Exception as e:
        return Porteiro("ritmo", "medio", False,
                        f"erro ao medir ritmo: {e}")

    aprovado = g.confianca >= 0.25
    return Porteiro(
        nome="ritmo",
        severidade="medio",
        passou=aprovado,
        detalhes=f"BPM={g.bpm}  confianca={g.confianca}",
        metricas={"bpm": g.bpm, "confianca": g.confianca, "periodo": g.periodo},
    )


# ---------------------------------------------------------------------------
# Porteiro: manifesto
# ---------------------------------------------------------------------------

def _cheque_manifesto(slug: str, m: dict, d: Path) -> Porteiro:
    """Verifica campos obrigatorios do manifesto."""
    from estudio import CAMPOS_OBRIGATORIOS_CAPA

    faltando = [nome for nome, get in CAMPOS_OBRIGATORIOS_CAPA if not get(m)]

    # campos extras importantes
    extras = []
    if not m.get("master"):
        extras.append("master")
    if not m.get("cor", {}).get("destaque"):
        extras.append("cor.destaque")
    if not m.get("titulo_linhas"):
        extras.append("titulo_linhas")

    todos_faltando = faltando + extras
    aprovado = len(todos_faltando) == 0

    return Porteiro(
        nome="manifesto",
        severidade="medio",
        passou=aprovado,
        detalhes=f"{len(todos_faltando)} campos ausentes: {', '.join(todos_faltando)}" if todos_faltando else "manifesto completo",
        metricas={"campos_ausentes": todos_faltando},
    )


# ---------------------------------------------------------------------------
# Motor de QA
# ---------------------------------------------------------------------------

def rodar_qa(slug: str, porteiros_only: bool = False,
             rapido: bool = False, salvar: bool = True) -> RelatorioQA:
    """Roda todos os porteiros e gera o relatorio consolidado.

    Se salvar=True, grava o relatorio em JSON na pasta qa/ do projeto
    para historico e comparacao entre versoes.
    """
    from datetime import datetime
    from estudio import carregar_manifesto, dir_projeto

    try:
        m = carregar_manifesto(slug)
    except SystemExit as e:
        return RelatorioQA(
            slug=slug, aprovado=False, porteiros=[], score_geral=0, bloqueadores=1,
        )

    d = dir_projeto(slug)
    porteiros: List[Porteiro] = []

    # sempre rodar os criticos
    porteiros.append(_cheque_legenda(slug, m, d))
    porteiros.append(_cheque_imagem(slug, m, d))
    porteiros.append(_cheque_audio(slug, m, d))

    if not rapido:
        porteiros.append(_cheque_encode(slug, m, d))
        porteiros.append(_cheque_ritmo(slug, m, d))
        if not porteiros_only:
            porteiros.append(_cheque_manifesto(slug, m, d))

    # calcular score e bloqueadores
    bloqueadores = sum(1 for p in porteiros if p.severidade == "critico" and not p.passou)
    alto_falhas = sum(1 for p in porteiros if p.severidade == "alto" and not p.passou)
    medio_falhas = sum(1 for p in porteiros if p.severidade == "medio" and not p.passou)

    # score: 100 menos penalidades
    score = 100
    score -= bloqueadores * 25   # cada critico falha = -25
    score -= alto_falhas * 10    # cada alto = -10
    score -= medio_falhas * 5    # cada medio = -5
    score = max(0, min(100, score))

    aprovado = bloqueadores == 0

    rel = RelatorioQA(
        slug=slug, aprovado=aprovado,
        porteiros=porteiros, score_geral=score,
        bloqueadores=bloqueadores,
    )

    # salvar historico em JSON
    if salvar:
        qa_dir = d / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo = qa_dir / f"qa_{timestamp}.json"
        dados = {
            "slug": slug,
            "timestamp": timestamp,
            "aprovado": aprovado,
            "score_geral": score,
            "bloqueadores": bloqueadores,
            "porteiros": [
                {
                    "nome": p.nome,
                    "severidade": p.severidade,
                    "passou": p.passou,
                    "detalhes": p.detalhes,
                    "metricas": p.metricas,
                }
                for p in porteiros
            ],
        }
        arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        # tambem salvar como "ultimo.json" para consulta rapida
        ultimo = qa_dir / "ultimo.json"
        ultimo.write_text(json.dumps(dados, indent=2, ensure_ascii=False),
                          encoding="utf-8")

    return rel


# ---------------------------------------------------------------------------
# Relatorio formatado
# ---------------------------------------------------------------------------

def formatar_relatorio(rel: RelatorioQA) -> str:
    """Formata o relatorio em texto legivel."""
    linhas = [
        "=" * 60,
        f"  QA REPORT — {rel.slug}",
        "=" * 60,
        "",
    ]

    # resumo
    if rel.aprovado:
        linhas.append(f"  RESULTADO: APROVADO  (score {rel.score_geral}/100)")
    else:
        linhas.append(f"  RESULTADO: REPROVADO  (score {rel.score_geral}/100, "
                      f"{rel.bloqueadores} bloqueador(es))")
    linhas.append("")

    # cada porteiro
    for p in rel.porteiros:
        icone = "PASS" if p.passou else "FAIL"
        sev = {"critico": "CRIT", "alto": "HIGH", "medio": "MED ", "baixo": "LOW "}
        linhas.append(f"  [{icone}] [{sev.get(p.severidade, '?   ')}] {p.nome}")
        linhas.append(f"         {p.detalhes}")
        linhas.append("")

    # legenda de severidade
    linhas.append("-" * 60)
    linhas.append("  Severidade: CRIT=bloqueia publicacao  HIGH=corrigir antes")
    linhas.append("              MED=melhoria recomendada   LOW=sugestao")
    linhas.append("=" * 60)

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="qa.py")
    p.add_argument("slug")
    p.add_argument("--json", action="store_true")
    p.add_argument("--porteiros-only", dest="porteiros_only", action="store_true")
    p.add_argument("--rapido", action="store_true")
    a = p.parse_args(argv)

    rel = rodar_qa(a.slug, a.porteiros_only, a.rapido)

    if a.json:
        saida = {
            "slug": rel.slug,
            "aprovado": rel.aprovado,
            "score_geral": rel.score_geral,
            "bloqueadores": rel.bloqueadores,
            "porteiros": [
                {
                    "nome": p.nome,
                    "severidade": p.severidade,
                    "passou": p.passou,
                    "detalhes": p.detalhes,
                    "metricas": p.metricas,
                }
                for p in rel.porteiros
            ],
        }
        print(json.dumps(saida, indent=2, ensure_ascii=False))
    else:
        print(formatar_relatorio(rel))

    return 0 if rel.aprovado else 1


if __name__ == "__main__":
    sys.exit(main())
