"""Composicao da timeline: base limpa + etapas reaplicadas a cada esteira.

Problema que resolve: cenas-auto, cenas-ia, titulos, manga-auto e graficos-auto
editavam `timeline.json` NO LUGAR, cada um com hash proprio em `qa/<etapa>/state.json`.
Consequencias:
- mudou a letra ou um parametro -> etapas respondiam "preserved_after_downstream_visuals"
  e mantinham a composicao velha (so `rebuild-total` resolvia);
- qualquer edicao fora da ordem -> "alterada externamente; falha fechada".

Agora:
- `estudio.py timeline` grava tambem `timeline_base.json` (so clipes narrativos) e o
  hash da `letra_sincronizada.json` que a gerou (`qa/composicao.json`);
- no inicio da esteira, `recompor()` restaura `timeline.json` a partir da base e arquiva
  os estados das 5 etapas; cada etapa reaplica sobre a base. Renders e imagens IA tem
  cache proprio (.design.json / artes_ia/escolhas.json), entao recompor e barato;
- se a letra sincronizada mudou, a base e regenerada antes (`base_desatualizada`);
- timeline editada por fora nao e perdida: vai para o backup da execucao.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ARQ_BASE = "timeline_base.json"
ARQ_META = "qa/composicao.json"
ARQ_SYNC = "letra_sincronizada.json"
ESTADOS = (
    "qa/scene_matcher/state.json",
    "qa/vx_chroma/state.json",
    "qa/vx_cenas_ia/state.json",
    "qa/vx_titulos/state.json",
    "qa/vx_manga_auto/state.json",
    "qa/vx_graphics_auto/state.json",
)
TIPOS_DERIVADOS = {"vx_cena_ia", "vx_title_card", "vx_end_card", "vx_manga_auto",
                   "vx_graphics_auto", "impact_typography", "vx_chroma"}


def _hash(path: Path) -> str | None:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _ler(path: Path, padrao=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar(path: Path, dados) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _e_base_limpa(timeline: dict) -> bool:
    segs = timeline.get("segments") or []
    return bool(segs) and not any(s.get("type") in TIPOS_DERIVADOS or "scene_match" in s for s in segs)


def registrar_base(projeto: Path, origem: str = "timeline") -> dict:
    """Chamado por `estudio.py timeline`: a timeline recem-montada vira a base."""
    projeto = Path(projeto)
    shutil.copy2(projeto / "timeline.json", projeto / ARQ_BASE)
    meta = {"base_hash": _hash(projeto / ARQ_BASE), "sync_hash": _hash(projeto / ARQ_SYNC),
            "composto_hash": None, "origem": origem,
            "registrado_em": datetime.now(timezone.utc).isoformat()}
    _gravar(projeto / ARQ_META, meta)
    return meta


def base_desatualizada(projeto: Path) -> bool:
    """True se a base foi montada de uma letra sincronizada diferente da atual."""
    projeto = Path(projeto)
    meta = _ler(projeto / ARQ_META, {}) or {}
    if not (projeto / ARQ_BASE).is_file() or not meta.get("sync_hash"):
        return False  # sem base registrada: nada a comparar (projeto legado)
    return meta["sync_hash"] != _hash(projeto / ARQ_SYNC)


def _adotar_base_legada(projeto: Path) -> str | None:
    """Projeto antigo sem timeline_base.json: tenta reconstruir a base sem perder nada."""
    estado_matcher = _ler(projeto / "qa/scene_matcher/state.json", {}) or {}
    base = estado_matcher.get("base_timeline")
    if isinstance(base, dict) and _e_base_limpa(base):
        _gravar(projeto / ARQ_BASE, base)
        origem = "scene_matcher.state.base_timeline"
    else:
        atual = _ler(projeto / "timeline.json", {}) or {}
        if not _e_base_limpa(atual):
            return None
        _gravar(projeto / ARQ_BASE, atual)
        origem = "timeline.json (ainda sem etapas aplicadas)"
    _gravar(projeto / ARQ_META, {"base_hash": _hash(projeto / ARQ_BASE), "sync_hash": None,
                                 "composto_hash": None, "origem": origem,
                                 "registrado_em": datetime.now(timezone.utc).isoformat()})
    return origem


def recompor(projeto: Path, backup_dir: Path) -> dict:
    """Restaura timeline.json da base e arquiva os estados das etapas de composicao."""
    projeto, backup_dir = Path(projeto), Path(backup_dir)
    info = {"modo": "recomposto", "base_adotada": None, "timeline_externa_arquivada": None,
            "estados_arquivados": []}
    if not (projeto / ARQ_BASE).is_file():
        info["base_adotada"] = _adotar_base_legada(projeto)
        if info["base_adotada"] is None:
            info["modo"] = "legado"  # sem base confiavel: mantem o comportamento antigo
            return info
    meta = _ler(projeto / ARQ_META, {}) or {}
    atual = projeto / "timeline.json"
    h_atual = _hash(atual)
    if h_atual and h_atual not in {meta.get("composto_hash"), meta.get("base_hash")}:
        # timeline mexida fora da esteira: nunca descartar sem copia
        destino = backup_dir / "timeline_antes_da_recomposicao.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(atual, destino)
        info["timeline_externa_arquivada"] = str(destino)
    shutil.copy2(projeto / ARQ_BASE, atual)
    for rel in ESTADOS:
        src = projeto / rel
        if src.is_file():
            dst = backup_dir / "estados_anteriores" / rel.replace("/", "__")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            info["estados_arquivados"].append(rel)
    return info


def registrar_composicao(projeto: Path) -> None:
    """Depois das etapas de composicao: guarda o hash da timeline final."""
    projeto = Path(projeto)
    meta = _ler(projeto / ARQ_META, {}) or {}
    meta["composto_hash"] = _hash(projeto / "timeline.json")
    meta["composto_em"] = datetime.now(timezone.utc).isoformat()
    _gravar(projeto / ARQ_META, meta)
