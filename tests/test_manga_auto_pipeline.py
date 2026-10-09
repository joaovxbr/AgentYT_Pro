from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import direcao_clipe
import manga_auto_pipeline as ma
import semantic_scene_matcher as sm


class MangaAutoSelectionTests(unittest.TestCase):
    def test_same_concept_is_not_repeated(self):
        timeline = {
            "segments": [{
                "start": 0.0, "end": 120.0, "duration": 120.0,
                "clip": "base.mp4", "src": 0.0, "type": "lyric",
            }]
        }
        cfg = dict(ma.DEFAULTS, max_scenes=2, min_gap_seconds=20)
        candidates = [
            {"start": 20.0, "end": 21.5, "score": .95, "concepts": ["electric"]},
            {"start": 60.0, "end": 61.5, "score": .92, "concepts": ["electric"]},
            {"start": 90.0, "end": 91.5, "score": .88, "concepts": ["fire"]},
        ]
        out = ma._select(candidates, timeline, cfg)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["concepts"], ["electric"])
        self.assertEqual(out[1]["concepts"], ["fire"])

    def test_special_range_is_protected(self):
        timeline = {
            "segments": [
                {
                    "start": 0.0, "end": 30.0, "duration": 30.0,
                    "clip": "base.mp4", "src": 0.0, "type": "lyric",
                },
                {
                    "start": 30.0, "end": 32.0, "duration": 2.0,
                    "clip": "special.mp4", "src": 0.0, "type": "impact_typography",
                },
                {
                    "start": 32.0, "end": 100.0, "duration": 68.0,
                    "clip": "base.mp4", "src": 32.0, "type": "lyric",
                },
            ]
        }
        cfg = dict(ma.DEFAULTS, max_scenes=2, min_gap_seconds=10)
        candidates = [
            {"start": 30.2, "end": 31.6, "score": .99, "concepts": ["rage"]},
            {"start": 60.0, "end": 61.5, "score": .90, "concepts": ["fire"]},
        ]
        out = ma._select(candidates, timeline, cfg)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["concepts"], ["fire"])

    def test_injection_splits_source_correctly(self):
        base = {
            "segments": [{
                "start": 0.0, "end": 10.0, "duration": 10.0,
                "clip": "anime.mp4", "src": 5.0, "type": "lyric",
            }]
        }
        selected = [{
            "start": 3.0, "end": 4.5, "duration": 1.5,
            "clip": "clips_raw/vx_manga_auto/demo.mp4",
            "text": "CLIMAX", "score": .9,
            "concepts": ["power"], "beat_score": .8, "visual_score": .9,
        }]
        out = ma._inject(base, selected)
        segs = out["segments"]
        self.assertEqual(len(segs), 3)
        self.assertEqual(segs[1]["type"], "vx_manga_auto")
        self.assertAlmostEqual(segs[2]["src"], 9.5)
        self.assertAlmostEqual(segs[2]["start"], 4.5)

    def test_manga_segment_is_camera_locked(self):
        timeline = {
            "audio_duration": 2.0,
            "segments": [{
                "start": 0.0, "end": 2.0, "duration": 2.0,
                "clip": "manga.mp4", "src": 0.0, "type": "vx_manga_auto",
            }],
        }
        shot = direcao_clipe.criar(timeline)["shots"][0]
        self.assertEqual(shot["preset"], "graphics_locked")
        self.assertEqual(shot["camera"]["zoom_inicio"], 1.0)
        self.assertEqual(shot["camera"]["zoom_fim"], 1.0)
        self.assertEqual(shot["efeitos"], [])


class RenderCacheTests(unittest.TestCase):
    """Douma 01/10/2026: take antigo (cartela Crunchyroll) ficou porque o cache era so pelo nome."""

    def test_spec_changes_when_sources_change_and_survives_json(self):
        a = {"text": "x", "duration": 1.5, "sources_preview": [{"clip": "c.mp4", "scene_id": "s1", "scene_start": 1.0}]}
        b = copy.deepcopy(a)
        b["sources_preview"][0]["scene_id"] = "s2"
        self.assertNotEqual(ma._spec_render(a), ma._spec_render(b))
        self.assertEqual(json.loads(json.dumps(ma._spec_render(a))), ma._spec_render(a))


class DownstreamRecoveryTests(unittest.TestCase):
    def test_scene_matcher_preserves_timeline_after_manga_stage(self):
        timeline = {
            "segments": [{
                "start": 0.0, "end": 2.0, "duration": 2.0,
                "clip": "manga.mp4", "src": 0.0,
                "type": "vx_manga_auto",
            }]
        }
        self.assertTrue(sm._has_downstream_visuals(timeline))

    def test_manga_execute_preserves_after_graphics_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "demo"
            (project / "qa" / "vx_manga_auto").mkdir(parents=True)
            timeline = {
                "segments": [
                    {
                        "start": 0.0, "end": 1.0, "duration": 1.0,
                        "clip": "manga.mp4", "src": 0.0, "type": "vx_manga_auto",
                    },
                    {
                        "start": 1.0, "end": 2.0, "duration": 1.0,
                        "clip": "gfx.mp4", "src": 0.0, "type": "vx_graphics_auto",
                    },
                ]
            }
            (project / "timeline.json").write_text(
                json.dumps(timeline), encoding="utf-8"
            )
            (project / "qa" / "vx_manga_auto" / "state.json").write_text(
                json.dumps({"plan": {"selected": [{"text": "X"}]}}),
                encoding="utf-8",
            )
            with patch.object(ma, "PROJECTS", root):
                result = ma.executar("demo")
            self.assertEqual(result["status"], "preserved_after_graphics_auto")
            self.assertFalse(result["applied"])


if __name__ == "__main__":
    unittest.main()
