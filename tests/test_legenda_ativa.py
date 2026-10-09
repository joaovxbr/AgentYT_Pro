"""Todo comando que gera a legenda do master grava no legenda_ass do manifesto.

Regressao: `karaoke` e `legenda` gravavam em legendas/<slug>.ass fixo; com um
legenda_ass diferente no projeto.json o render queimava a legenda antiga.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import estudio  # noqa: E402

SYNC = [{"start": 1.0, "end": 2.5, "text": "linha de teste",
         "words": [{"word": "linha", "start": 1.0, "end": 1.4},
                   {"word": "de", "start": 1.4, "end": 1.6},
                   {"word": "teste", "start": 1.6, "end": 2.5}]}]


class LegendaAtivaTests(unittest.TestCase):
    def _projeto(self, tmp: str) -> tuple[Path, dict]:
        d = Path(tmp) / "proj"
        (d / "legendas").mkdir(parents=True)
        return d, {"legenda_ass": "legendas/proj_ativa.ass", "cor": {"destaque": "#FF0000"}}

    def test_ass_ativo_follows_manifest_and_falls_back(self):
        d = Path("x")
        self.assertEqual(estudio._ass_ativo(d, {"legenda_ass": "legendas/a.ass"}, "s"), d / "legendas/a.ass")
        self.assertEqual(estudio._ass_ativo(d, {}, "s"), d / "legendas/s.ass")
        self.assertEqual(estudio._ass_ativo(d, {"legenda_ass": ""}, "s"), d / "legendas/s.ass")

    def test_karaoke_writes_active_subtitle(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, m = self._projeto(tmp)
            with patch.object(estudio, "dir_projeto", return_value=d), \
                 patch.object(estudio, "carregar_manifesto", return_value=m), \
                 patch.object(estudio, "_gerar_sync_word_level", return_value=(SYNC, [], None)):
                self.assertEqual(estudio.cmd_karaoke("proj"), 0)
            self.assertTrue((d / "legendas" / "proj_ativa.ass").is_file())
            self.assertFalse((d / "legendas" / "proj.ass").exists())


if __name__ == "__main__":
    unittest.main()
