#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Graphics Pro: orquestracao de planejamento e render das cenas premium."""
from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path

from audio_reactive_fx import carregar_picos, relativos
from creative_impact_director import CreativeDirector
from render_impact_scene import renderizar_cena_impacto
from style_preset_engine import montar_spec_design, listar_catalogo

RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"


def _manifesto(projeto: Path) -> dict:
    p = projeto / "projeto.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _slugify(texto: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", texto.strip().lower()).strip("_")
    return s[:48] or "impacto"


def _enriquecer_planos(slug: str, manifesto: dict, planos: list[dict],
                       preset: str, layout: str, energia: float) -> list[dict]:
    recentes_presets = deque(maxlen=3)
    recentes_layouts = deque(maxlen=2)
    saida = []
    for i, plano in enumerate(planos):
        spec = montar_spec_design(
            palavra=plano["keyword_dominante"],
            slug=slug,
            manifesto=manifesto,
            texto_secundario=plano.get("texto_secundario", ""),
            duracao=plano.get("duracao", 1.8),
            energia=max(0.0, min(1.0, energia + ((i % 3) - 1) * 0.04)),
            preset=preset,
            layout=layout,
            presets_recentes=tuple(recentes_presets),
            layouts_recentes=tuple(recentes_layouts),
        )
        spec["id"] = plano.get("id", f"impact_{i+1:02d}")
        spec["tempo_inicio"] = plano.get("tempo_inicio")
        spec["suporte"] = plano.get("suporte", "VX RAPS")
        spec["transicao_in"] = plano.get("transicao_in", "flash_zoom")
        spec["transicao_out"] = plano.get("transicao_out", "motion_blur")
        recentes_presets.append(spec["preset"])
        recentes_layouts.append(spec["layout"])
        saida.append(spec)
    return saida


def planejar(
    slug: str,
    palavra: str | None = None,
    subtexto: str = "",
    preset: str = "auto",
    layout: str = "auto",
    duracao: float = 1.8,
    energia: float = 0.88,
    max_cenas: int = 6,
    tempo_inicio: float | None = None,
) -> list[dict]:
    projeto = PROJETOS / slug
    if not projeto.exists():
        raise FileNotFoundError(f"projeto nao encontrado: {projeto}")
    manifesto = _manifesto(projeto)

    if palavra:
        base = [{
            "id": "impact_manual_01",
            "keyword_dominante": palavra,
            "texto_secundario": subtexto,
            "duracao": duracao,
            "tempo_inicio": tempo_inicio,
            "suporte": manifesto.get("personagem", "VX RAPS"),
        }]
    else:
        base = CreativeDirector(projeto).planejar_cenas_impacto(max_cenas)
        if not base:
            raise RuntimeError(
                "nenhuma punchline de impacto encontrada na transcricao; "
                "use --word para criar uma cena manual")
    planos = _enriquecer_planos(slug, manifesto, base, preset, layout, energia)
    eventos = carregar_picos(projeto, manifesto)
    for spec in planos:
        beats = relativos(eventos, spec.get("tempo_inicio"), spec["duracao"])
        spec["beat_events"] = beats
        spec.setdefault("audio_reactive", {})["source"] = "subgrave_808" if beats else "curve_only"
        spec["audio_reactive"]["beat_count"] = len(beats)
    return planos


def executar(
    slug: str,
    palavra: str | None = None,
    subtexto: str = "",
    preset: str = "auto",
    layout: str = "auto",
    duracao: float = 1.8,
    energia: float = 0.88,
    max_cenas: int = 6,
    saida: str | None = None,
    somente_planejar: bool = False,
    tempo_inicio: float | None = None,
) -> dict:
    projeto = PROJETOS / slug
    planos = planejar(
        slug, palavra, subtexto, preset, layout, duracao, energia, max_cenas, tempo_inicio)
    out_dir = projeto / "saidas" / "impacto_pro"
    out_dir.mkdir(parents=True, exist_ok=True)
    plano_path = out_dir / "plano_vx_graphics.json"
    plano_path.write_text(
        json.dumps({"slug": slug, "cenas": planos}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    renderizados = []
    if not somente_planejar:
        for i, spec in enumerate(planos):
            if saida and len(planos) == 1:
                destino = Path(saida)
                if not destino.is_absolute():
                    destino = projeto / destino
            else:
                nome = f"{i+1:02d}_{_slugify(spec['keyword_dominante'])}_{spec['preset']}.mp4"
                destino = out_dir / nome
            renderizar_cena_impacto(spec, projeto, destino)
            renderizados.append(str(destino))

    return {
        "engine": "vx_graphics_pro",
        "slug": slug,
        "plano": str(plano_path),
        "cenas": planos,
        "renderizados": renderizados,
        "catalogo": listar_catalogo(),
    }
