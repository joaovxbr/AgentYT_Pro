from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import legenda
import montar_timeline
from scene_intelligence import is_generated_asset


class CleanRebuildContractTests(unittest.TestCase):
    def test_generated_legacy_assets_are_never_narrative_sources(self):
        generated = [
            "impact_01_sangue.mp4",
            "take_saber_18s.mp4",
            "take_chroma_chidori.mp4",
            "demo_overlay.mp4",
            "overlay_uchiha_v2.mp4",
            "vx_graphics_sangue.mp4",
        ]
        for name in generated:
            self.assertTrue(is_generated_asset(Path(name)), name)
        self.assertFalse(is_generated_asset(Path("sasuke_twixtor_01.mp4")))

    def test_base_timeline_filters_generated_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for name in (
                "sasuke_twixtor_01.mp4",
                "impact_01_sangue.mp4",
                "take_saber_18s.mp4",
            ):
                (p / name).write_bytes(b"x")

            with patch.object(montar_timeline, "duracao", return_value=120.0):
                clips = montar_timeline._clipes_disponiveis(p)

            self.assertEqual(
                [x["nome"] for x in clips],
                ["sasuke_twixtor_01.mp4"],
            )

    def test_sync_gate_extracts_text_from_full_ass_dialogue(self):
        line = (
            r"Dialogue: 0,0:00:12.12,0:00:17.00,Verso,,0,0,0,,"
            r"{\fad(140,120)}OLHOS VERMELHOS NA ESCURIDÃO"
        )
        onsets = [(12.12, "olhos"), (13.28, "vermelhos")]
        self.assertEqual(legenda._onset_para(line, 12.12, onsets), 12.12)

    def test_sync_gate_strips_ass_tags_before_first_word(self):
        payload = r"{\move(0,20,0,0,0,200)\fad(100,100)}VOCÊ NÃO CONHECE"
        onsets = [(17.90, "você")]
        self.assertEqual(legenda._onset_para(payload, 17.90, onsets), 17.90)


if __name__ == "__main__":
    unittest.main()
