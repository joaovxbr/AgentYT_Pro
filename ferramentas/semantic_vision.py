#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Semantic vision layer for VX Scene Intelligence.

Uses OpenCLIP zero-shot image/text similarity to identify project-specific
characters, techniques and narrative contexts from actual pixels. Labels live
in projeto.json; the engine contains no anime-specific rules.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2

DEFAULT_MODEL = "ViT-B-32"
DEFAULT_PRETRAINED = "laion2b_s34b_b79k"


def normalizar(text: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.lower().replace("_", " ").split())


def scene_semantics_cfg(manifesto: dict) -> dict:
    """Normaliza `projeto.json -> scene_semantics` para o formato canonico.

    Formato canonico (todos os consumidores esperam ele)::

        {"enabled": bool, "labels": [{"id":..., "kind":..., "name":...,
                                      "prompt":..., "aliases":[...], "required":bool}],
         "strict": bool, "model": str, "pretrained": str, "min_score": float,
         "required_score": float, ...}

    O manifesto tambem aceita a forma CURTA, uma lista de ids::

        "scene_semantics": ["megumi_fushiguro", "shikigami", ...]

    que significa "rotulos sem prompt explicito". Nesse caso derivamos
    `id = name = prompt = texto` com `kind = "concept"`. Sem isso qualquer
    consumidor que faca `cfg.get(...)` estoura com
    `AttributeError: 'list' object has no attribute 'get'` (cenas-auto).
    """
    raw = manifesto.get("scene_semantics")
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        labels = []
        for item in raw:
            if isinstance(item, dict):
                labels.append(item)
                continue
            texto = str(item or "").strip()
            if not texto:
                continue
            labels.append({"id": texto, "kind": "concept", "name": texto,
                           "prompt": texto.replace("_", " ")})
        return {"enabled": True, "labels": labels}
    if isinstance(raw, dict):
        return raw
    return {}


def imagem_ia_cfg(manifesto: dict) -> dict:
    """Normaliza `projeto.json -> imagem_ia` para o formato canonico.

    Formato canonico (contrato documentado em `cerebro/historico/AGENTS_v3_legado.md`)::

        {"tags_personagem": "1boy, solo, ...", "tags_cenario": ...,
         "tags_estilo": ..., "descricao": ..., "negativo": ...,
         "kanji": ["<coluna>", "<nome>"], "tags_alvos": {...},
         "clip_identidade": ...}

    O manifesto tambem aceita a forma CURTA, uma lista de tags soltas::

        "imagem_ia": ["jujutsu kaisen anime style", "dark blue shadow energy"]

    que e o atalho para uma identidade simples, sem bloco por campo. Nesse caso
    juntamos tudo em `tags_estilo` — o campo que os geradores concatenam no
    prompt sem exigir estrutura. Sem isso qualquer consumidor que faca
    `bloco.get(...)` estoura com
    `AttributeError: 'list' object has no attribute 'get'` (titulos, cenas-ia,
    geradores de imagem).
    """
    raw = manifesto.get("imagem_ia")
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        tags = [str(t).strip() for t in raw if str(t or "").strip()]
        cfg: dict = {}
        if tags:
            cfg["tags_estilo"] = ", ".join(tags)
        return cfg
    if isinstance(raw, dict):
        return raw
    return {}


def profile_from_manifest(manifesto: dict) -> dict:
    cfg = scene_semantics_cfg(manifesto)
    labels = cfg.get("labels") or []
    clean = []
    for row in labels:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id") or "").strip()
        prompt = str(row.get("prompt") or row.get("name") or "").strip()
        kind = str(row.get("kind") or "concept").strip().lower()
        if not ident or not prompt:
            continue
        clean.append({
            "id": ident,
            "kind": kind,
            "name": str(row.get("name") or ident),
            "prompt": prompt,
            "aliases": [normalizar(x) for x in (row.get("aliases") or []) if str(x).strip()],
            "required": bool(row.get("required", False)),
        })
    enabled = bool(cfg.get("enabled", True) and clean)
    return {
        "enabled": enabled,
        "model": str(cfg.get("model") or DEFAULT_MODEL),
        "pretrained": str(cfg.get("pretrained") or DEFAULT_PRETRAINED),
        "labels": clean,
        "frames_per_scene": max(1, min(5, int(cfg.get("frames_per_scene", 3)))),
        "top_k_per_kind": max(1, min(4, int(cfg.get("top_k_per_kind", 2)))),
        "min_score": float(cfg.get("min_score", 0.08)),
        "required_score": float(cfg.get("required_score", 0.16)),
    }


def profile_hash(profile: dict) -> str:
    raw = json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def pick_sample_indices(count: int, nframes: int) -> list[int]:
    """Indices espaçados das amostras de uma cena (mesmo espírito de (i+1)/(n+1))."""
    count, nframes = int(count), max(1, int(nframes))
    if count <= nframes:
        return list(range(max(0, count)))
    return sorted({min(count - 1, int((i + 1) * count / (nframes + 1))) for i in range(nframes)})


class SemanticVisionEncoder:
    def __init__(self, profile: dict):
        self.profile = profile
        self.enabled = bool(profile.get("enabled"))
        self.device = "cpu"
        self.error = None
        self.model = self.preprocess = self.tokenizer = None
        self.labels = list(profile.get("labels") or [])
        self.kind_indices: dict[str, list[int]] = {}
        if not self.enabled:
            return
        try:
            import torch
            import open_clip
            self.torch = torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                profile["model"], pretrained=profile["pretrained"], device=self.device)
            self.model.eval()
            self.tokenizer = open_clip.get_tokenizer(profile["model"])
            prompts = [row["prompt"] for row in self.labels]
            with torch.no_grad():
                text = self.model.encode_text(self.tokenizer(prompts).to(self.device))
                self.text_features = text / text.norm(dim=-1, keepdim=True)
            for idx, row in enumerate(self.labels):
                self.kind_indices.setdefault(row["kind"], []).append(idx)
        except Exception as exc:  # optional accelerator; fail soft
            self.error = str(exc)
            self.enabled = False

    def info(self) -> dict:
        return {
            "enabled": self.enabled,
            "device": self.device,
            "model": self.profile.get("model"),
            "pretrained": self.profile.get("pretrained"),
            "profile_hash": profile_hash(self.profile),
            "label_count": len(self.labels),
            "error": self.error,
        }

    def _read_frame(self, cap, second: float):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, second) * 1000.0)
        ok, frame = cap.read()
        return frame if ok else None

    def _frame_scores(self, frame) -> dict[str, float]:
        from PIL import Image
        torch = self.torch
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self.preprocess(Image.fromarray(rgb)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            feat = self.model.encode_image(image)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            cosine = (feat @ self.text_features.T)[0]
        scores: dict[str, float] = {}
        for kind, indices in self.kind_indices.items():
            values = torch.softmax(cosine[indices] * 70.0, dim=-1)
            for local_idx, global_idx in enumerate(indices):
                ident = self.labels[global_idx]["id"]
                scores[ident] = float(values[local_idx])
        return scores

    def frame_scores(self, frame) -> dict[str, float] | None:
        """Scores zero-shot de um frame ja decodificado (sem seek no video)."""
        if not self.enabled or frame is None:
            return None
        return self._frame_scores(frame)

    def attach_scene_scores(self, scene: dict, frame_scores: list[dict]) -> bool:
        """Media os scores dos frames escolhidos e grava semantic_* na cena."""
        frame_scores = [x for x in frame_scores if x]
        if not self.enabled or not frame_scores:
            return False
        averaged = {}
        for row in self.labels:
            ident = row["id"]
            total = sum(x.get(ident, 0.0) for x in frame_scores)
            averaged[ident] = total / len(frame_scores)
        scene["semantic_scores"] = {
            key: round(value, 5) for key, value in averaged.items()
        }
        scene["semantic_frames"] = len(frame_scores)
        self._attach_top_labels(scene, averaged)
        return True

    def enrich_scenes(self, video_path: Path, scenes: list[dict]) -> dict:
        """Caminho com seek por frame. O catalogo usa as amostras sequenciais
        (scene_intelligence.analisar_clipe); seek em AV1/long-GOP custa ~0.6 s."""
        if not self.enabled:
            return self.info()
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {**self.info(), "error": f"cannot open {video_path}"}
        nframes = int(self.profile.get("frames_per_scene", 3))
        for scene in scenes:
            start = float(scene.get("start", 0.0))
            end = float(scene.get("end", start))
            if end <= start:
                continue
            times = [start + (end-start)*(i+1)/(nframes+1) for i in range(nframes)]
            frame_scores = []
            for t in times:
                frame = self._read_frame(cap, t)
                if frame is not None:
                    frame_scores.append(self._frame_scores(frame))
            self.attach_scene_scores(scene, frame_scores)
        cap.release()
        return self.info()

    def _attach_top_labels(self, scene: dict, scores: dict[str, float]):
        min_score = float(self.profile.get("min_score", 0.08))
        top_k = int(self.profile.get("top_k_per_kind", 2))
        semantic = []
        for kind, indices in self.kind_indices.items():
            ranked = sorted(
                ((scores.get(self.labels[i]["id"], 0.0), self.labels[i]) for i in indices),
                key=lambda item: (-item[0], item[1]["id"]),
            )[:top_k]
            for score, row in ranked:
                if score < min_score:
                    continue
                semantic.append({
                    "id": row["id"], "kind": kind, "name": row["name"],
                    "score": round(float(score), 5),
                })
        semantic.sort(key=lambda item: (-item["score"], item["id"]))
        scene["semantic_labels"] = semantic
        scene["entities"] = [x["id"] for x in semantic if x["kind"] == "entity"]
        scene["actions"] = [x["id"] for x in semantic if x["kind"] == "action"]
        scene["contexts"] = [x["id"] for x in semantic if x["kind"] == "context"]


def semantic_targets(text: str, profile: dict) -> list[dict]:
    normalized = normalizar(text)
    targets = []
    for row in profile.get("labels") or []:
        hits = [a for a in row.get("aliases", []) if a and a in normalized]
        if hits:
            targets.append({
                "id": row["id"], "kind": row["kind"], "name": row["name"],
                "aliases": hits, "required": bool(row.get("required", False)),
            })
    return targets
