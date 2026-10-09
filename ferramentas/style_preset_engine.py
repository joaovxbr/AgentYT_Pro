#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Graphics Pro: resolve tema, preset e layout de cenas de impacto."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESIGN_DIR = RAIZ / "assets" / "design"
PRESETS_PATH = DESIGN_DIR / "presets_impacto.json"
THEMES_PATH = DESIGN_DIR / "themes_personagens.json"
SEMANTIC_PATH = DESIGN_DIR / "semantic_style_map.json"

LAYOUTS = ("hero_center", "lyric_punchline", "energy_ring", "impact_fullscreen")


def _load(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"configuracao VX Graphics ausente: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def carregar_presets() -> dict:
    return _load(PRESETS_PATH)


def carregar_temas() -> dict:
    return _load(THEMES_PATH)


def carregar_semantica() -> dict:
    return _load(SEMANTIC_PATH)


def resolver_tema(slug: str, manifesto: dict | None = None) -> tuple[str, dict]:
    temas = carregar_temas()
    alvo = " ".join([
        slug or "",
        (manifesto or {}).get("personagem", ""),
        (manifesto or {}).get("faixa", ""),
    ])
    alvo_n = normalizar(alvo)
    for nome, tema in temas.items():
        if nome == "default":
            continue
        aliases = [nome, *tema.get("aliases", [])]
        if any(normalizar(alias) in alvo_n for alias in aliases if alias):
            return nome, dict(tema)

    tema = dict(temas["default"])
    cor = (manifesto or {}).get("cor", {})
    if cor.get("destaque"):
        tema["primary"] = cor["destaque"]
    if cor.get("destaque_claro"):
        tema["secondary"] = cor["destaque_claro"]
    return "default", tema


def candidatos_semanticos(palavra: str) -> list[str]:
    mapa = carregar_semantica()
    chave = normalizar(palavra)
    if not chave:
        return []
    diretos = mapa.get(chave, [])
    if diretos:
        return list(diretos)
    tokens = set(chave.split())
    for termo, presets in mapa.items():
        termo_n = normalizar(termo)
        if termo_n in tokens:
            return list(presets)
        if len(termo_n) >= 5 and len(chave) >= 5 and termo_n in chave:
            return list(presets)
    return []


def escolher_preset(
    palavra: str,
    tema: dict,
    preferido: str = "auto",
    recentes: list[str] | tuple[str, ...] = (),
) -> str:
    presets = carregar_presets()
    if preferido and preferido != "auto":
        if preferido not in presets:
            raise ValueError(f"preset desconhecido: {preferido}")
        return preferido

    palavra_n = normalizar(palavra)
    alias_tokens = set()
    for alias in tema.get("aliases", []):
        alias_n = normalizar(alias)
        if alias_n:
            alias_tokens.add(alias_n)
            alias_tokens.update(t for t in alias_n.split() if len(t) >= 3)

    candidatos = []
    if palavra_n in alias_tokens:
        candidatos += [
            nome for nome in (
                "neon_write_on", "neon_letter_reveal",
                "neon_outline_fill", "neon_trace")
            if nome in presets
        ]
    candidatos += candidatos_semanticos(palavra)
    candidatos += list(tema.get("preferred_presets", []))
    candidatos += list(presets)
    vistos = set()
    candidatos = [x for x in candidatos if not (x in vistos or vistos.add(x))]
    for nome in candidatos:
        if nome in presets and nome not in recentes:
            return nome
    return candidatos[0] if candidatos else "neon_royal"


def escolher_layout(preset: dict, preferido: str = "auto", recentes=()) -> str:
    if preferido and preferido != "auto":
        if preferido not in LAYOUTS:
            raise ValueError(f"layout desconhecido: {preferido}")
        return preferido
    candidatos = preset.get("layouts", ["hero_center"])
    for layout in candidatos:
        if layout not in recentes:
            return layout
    return candidatos[0]


def montar_spec_design(
    palavra: str,
    slug: str,
    manifesto: dict | None = None,
    texto_secundario: str = "",
    duracao: float = 1.8,
    energia: float = 0.85,
    preset: str = "auto",
    layout: str = "auto",
    presets_recentes=(),
    layouts_recentes=(),
) -> dict:
    todos = carregar_presets()
    tema_nome, tema = resolver_tema(slug, manifesto)
    preset_nome = escolher_preset(palavra, tema, preset, presets_recentes)
    cfg = dict(todos[preset_nome])
    layout_nome = escolher_layout(cfg, layout, layouts_recentes)
    energia = max(0.0, min(1.0, float(energia)))
    return {
        "version": 1,
        "engine": "vx_graphics_pro",
        "slug": slug,
        "keyword_dominante": palavra.upper().strip(),
        "texto_secundario": texto_secundario.upper().strip(),
        "duracao": round(max(0.5, min(4.0, float(duracao))), 3),
        "energia": energia,
        "theme": tema_nome,
        "theme_config": tema,
        "preset": preset_nome,
        "style": cfg,
        "layout": layout_nome,
        "background": cfg.get("background", "void_eclipse"),
        "animacao": cfg.get("animation", "scale_punch"),
        "audio_reactive": {
            "glow": True,
            "scale": energia >= 0.55,
            "flash": energia >= 0.78,
        },
    }


def listar_catalogo() -> dict:
    return {
        "presets": list(carregar_presets()),
        "themes": list(carregar_temas()),
        "layouts": list(LAYOUTS),
    }


if __name__ == "__main__":
    print(json.dumps(listar_catalogo(), ensure_ascii=False, indent=2))
