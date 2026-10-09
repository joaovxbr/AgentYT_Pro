from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import graphic_auto_pipeline as gap
import direcao_clipe as dir_clipe


class GraphicAutoUnitTests(unittest.TestCase):
    def test_dominant_prefers_stronger_semantic_word(self):
        line = {
            "start": 10.0, "end": 12.0, "text": "clã sangue",
            "words": [
                {"word": "clã", "start": 10.1, "end": 10.5},
                {"word": "sangue", "start": 11.0, "end": 11.4},
            ],
        }
        dom = gap._dominant(line, {"sasuke", "uchiha"})
        self.assertEqual(dom["norm"], "sangue")
        self.assertGreater(dom["strength"], 0.95)

    def test_character_identity_is_name_hit(self):
        line = {
            "start": 20.0, "end": 22.0, "text": "o último Uchiha",
            "words": [
                {"word": "último", "start": 20.4, "end": 20.8},
                {"word": "Uchiha", "start": 21.0, "end": 21.5},
            ],
        }
        dom = gap._dominant(line, {"sasuke", "uchiha"})
        self.assertEqual(dom["norm"], "uchiha")
        self.assertTrue(dom["name_hit"])

    def test_replace_interval_splits_and_advances_source(self):
        segments = [{
            "start": 0.0, "end": 10.0, "duration": 10.0,
            "clip": "base.mp4", "src": 5.0, "type": "narrativo",
        }]
        gfx = {
            "start": 3.0, "end": 5.0, "duration": 2.0,
            "clip": "gfx.mp4", "src": 0.0, "type": "vx_graphics_auto",
        }
        out = gap._replace_interval(segments, 3.0, 5.0, gfx)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["end"], 3.0)
        self.assertEqual(out[1]["clip"], "gfx.mp4")
        self.assertEqual(out[2]["start"], 5.0)
        self.assertAlmostEqual(out[2]["src"], 10.0)

    def test_graphics_segment_is_locked_against_extra_camera_motion(self):
        timeline = {"audio_duration": 2.0, "segments": [{
            "start": 0.0, "end": 2.0, "duration": 2.0,
            "clip": "gfx.mp4", "src": 0.0, "type": "vx_graphics_auto",
        }]}
        shot = dir_clipe.criar(timeline)["shots"][0]
        self.assertEqual(shot["preset"], "graphics_locked")
        self.assertEqual(shot["camera"]["zoom_inicio"], 1.0)
        self.assertEqual(shot["camera"]["zoom_fim"], 1.0)
        self.assertEqual(shot["efeitos"], [])

    def test_selection_respects_special_ranges_and_gap(self):
        timeline = {
            "segments": [
                {"start": 0, "end": 30, "type": "narrativo"},
                {"start": 30, "end": 32, "type": "impact_typography"},
                {"start": 32, "end": 90, "type": "narrativo"},
            ]
        }
        cfg = dict(gap.DEFAULT_CONFIG, max_scenes=5, min_gap_seconds=9)
        candidates = [
            {"start": 30.3, "end": 31.5, "word_norm": "sangue", "score": .99},
            {"start": 40.0, "end": 41.2, "word_norm": "odio", "score": .95},
            {"start": 45.0, "end": 46.2, "word_norm": "kirin", "score": .94},
            {"start": 60.0, "end": 61.2, "word_norm": "fogo", "score": .90},
        ]
        selected = gap._select(candidates, timeline, cfg, 90.0)
        words = [x["word_norm"] for x in selected]
        self.assertNotIn("sangue", words)
        self.assertIn("odio", words)
        self.assertNotIn("kirin", words)
        self.assertIn("fogo", words)


class GraphicAutoLyricsTests(unittest.TestCase):
    def test_plan_uses_authored_lyrics_when_canonical_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "demo"
            (project / "entradas").mkdir(parents=True)
            (project / "LETRA_LINHAS.txt").write_text(
                "Sangue no olhar\nKirin corta o céu\n", encoding="utf-8"
            )
            words = [
                {"word": "Sangue", "start": 10.0, "end": 10.5},
                {"word": "no", "start": 10.5, "end": 10.7},
                {"word": "olhar", "start": 10.7, "end": 11.2},
                {"word": "Kirin", "start": 25.0, "end": 25.5},
                {"word": "corta", "start": 25.5, "end": 25.8},
                {"word": "o", "start": 25.8, "end": 25.9},
                {"word": "céu", "start": 25.9, "end": 26.3},
            ]
            (project / "entradas" / "transcricao.json").write_text(
                json.dumps({"words": words}), encoding="utf-8"
            )
            (project / "projeto.json").write_text(json.dumps({
                "personagem": "Demo Hero",
                "faixa": "DEMO",
                "audio_fonte": "entradas/demo.wav",
                "letra": {"linhas": "LETRA_LINHAS.txt"},
            }), encoding="utf-8")
            (project / "timeline.json").write_text(json.dumps({
                "audio_duration": 40.0,
                "segments": [{
                    "start": 0.0, "end": 40.0, "duration": 40.0,
                    "clip": "base.mp4", "src": 0.0, "type": "narrativo",
                }],
            }), encoding="utf-8")

            with patch.object(gap, "PROJETOS", root),                  patch.object(gap, "carregar_picos", return_value=[]):
                result = gap.planejar("demo")

            self.assertEqual(result["source_lines"], 2)
            self.assertTrue(result["selected"])
            self.assertTrue(all(
                x["source"] == "author_lyrics_aligned"
                for x in result["selected"]
            ))


if __name__ == "__main__":
    unittest.main()
