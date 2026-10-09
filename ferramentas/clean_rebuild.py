#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX Clean Rebuild — remove heranca visual derivada antes de uma producao nova.

Nada autoral e perdido: timeline/planos/estados/assets derivados sao copiados
para backups/clean_rebuild_* antes de serem removidos da arvore de producao.
Audio, letra, transcricao, legendas e clipes narrativos brutos sao preservados.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from scene_intelligence import is_generated_asset

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projetos"


def _copy_file(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _copy_tree(src: Path, dst: Path) -> bool:
    if not src.is_dir():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return True


def preparar(slug: str) -> dict:
    project = PROJECTS / slug
    if not project.is_dir():
        raise FileNotFoundError(f"projeto nao encontrado: {project}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"clean_rebuild_{slug}_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)

    backed_up = []
    removed = []
    moved_legacy = []

    # Estado editorial/temporal que sera reconstruido.
    for name in (
        "timeline.json",
        "timeline.json.vxg.bak",
        "timeline_base.json",      # vx/composicao.py: recriada pela etapa timeline
        "qa/composicao.json",
        "plano_visual.json",
    ):
        src = project / name
        if _copy_file(src, backup / "project_state" / name):
            backed_up.append(str(src))
            src.unlink(missing_ok=True)
            removed.append(str(src))
    # scene_intelligence.json e cache por fingerprint de cada clipe bruto (e por perfil
    # semantico): continua valido no rebuild e poupa ~10 min de analise por projeto.
    # Use `catalogar-cenas --force` para invalidar de proposito.
    if _copy_file(project / "scene_intelligence.json", backup / "project_state" / "scene_intelligence.json"):
        backed_up.append(str(project / "scene_intelligence.json"))

    # Estados/cache que podem fazer a esteira preservar geracoes antigas.
    state_paths = [
        project / "qa" / "vx_graphics_auto",
        project / "qa" / "vx_manga_auto",
        project / "qa" / "vx_cenas_ia",
        project / "qa" / "vx_titulos",
        project / "qa" / "scene_matcher",
    ]
    for src in state_paths:
        if _copy_tree(src, backup / "qa_state" / src.name):
            backed_up.append(str(src))
            shutil.rmtree(src, ignore_errors=True)
            removed.append(str(src))

    for file_name in (
        "vx_graphics_bass_peaks.json",
        "manga_auto_audio_peaks.json",
    ):
        src = project / "qa" / file_name
        if _copy_file(src, backup / "qa_state" / file_name):
            backed_up.append(str(src))
            src.unlink(missing_ok=True)
            removed.append(str(src))

    clips_dir = project / "clips_raw"
    if not clips_dir.is_dir():
        raise FileNotFoundError(f"clips_raw ausente: {clips_dir}")

    # Takes gerados pelos pipelines novos tambem sao zerados para forcar render.
    # Imagens IA (projetos/<slug>/artes_ia) ficam: cache deterministico e caro de gerar.
    for dirname in ("vx_graphics_auto", "vx_manga_auto", "vx_cenas_ia", "vx_titulos"):
        src = clips_dir / dirname
        if _copy_tree(src, backup / "generated_pipeline" / dirname):
            backed_up.append(str(src))
            shutil.rmtree(src, ignore_errors=True)
            removed.append(str(src))

    # Assets antigos no root de clips_raw nao podem contaminar a timeline-base.
    legacy_dir = backup / "legacy_generated_root"
    for src in sorted(clips_dir.glob("*.mp4")):
        if not is_generated_asset(src):
            continue
        legacy_dir.mkdir(parents=True, exist_ok=True)
        target = legacy_dir / src.name
        shutil.move(str(src), str(target))
        moved_legacy.append({"from": str(src), "to": str(target)})

    narrative = [
        p.name for p in sorted(clips_dir.glob("*.mp4"))
        if not is_generated_asset(p)
    ]
    if not narrative:
        raise RuntimeError(
            "clean rebuild ficou sem clips narrativos; backup preservado em "
            + str(backup)
        )

    report = {
        "slug": slug,
        "backup": str(backup),
        "backed_up": backed_up,
        "removed_derivatives": removed,
        "moved_legacy_assets": moved_legacy,
        "narrative_clips_remaining": narrative,
        "policy": {
            "preserved": [
                "projeto.json", "audio", "letra/transcricoes",
                "legendas", "clips narrativos brutos", "masters anteriores",
            ],
            "rebuild": [
                "timeline", "scene intelligence", "scene matcher",
                "manga auto", "graphics auto/impacto_pro", "plano visual",
            ],
        },
    }
    (backup / "clean_rebuild_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
