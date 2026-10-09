from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import legenda


class LegendaSlideVisibilityTests(unittest.TestCase):
    def test_slide_stays_inside_master_frame(self):
        sync = [
            {"start": 1.0, "end": 2.0, "text": "linha um"},
            {"start": 2.0, "end": 3.0, "text": "linha dois"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "teste.ass"
            legenda.gerar_ass_de_sync(sync, out, "#7B1FA2", estilo_animacao="auto")
            text = out.read_text(encoding="utf-8")
        self.assertIn(r"\move(960,1010,960,990,0,200)", text)
        self.assertNotIn(r"\move(0,20,0,0,0,200)", text)


if __name__ == "__main__":
    unittest.main()
