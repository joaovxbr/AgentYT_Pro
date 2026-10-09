"""Regressao: POV com palavras acendendo fora de ordem (Douma, 01/10/2026).

Incidente: cerebro/incidentes/2026-10-01-douma-pov-fora-de-ordem.md
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import json  # noqa: E402
import pov_lyrics_official as pov  # noqa: E402
import sincronizar_letra as sl  # noqa: E402


def _w(word, a):
    return {"word": word, "start": a, "end": a + 0.3}


class PalavraNoTempoDelaTests(unittest.TestCase):
    def test_skipped_token_does_not_shift_the_rest(self):
        # ASR engoliu o "o": "Eu escuto seu choro" -> antes "o" acendia em "seu", "seu" em "choro"...
        asr = [_w("Eu", 1.0), _w("escuto", 1.4), _w("seu", 2.0), _w("choro", 2.4)]
        sync = sl.alinhar(["Eu escuto o seu choro"], asr)
        ws = {p["text"]: p for p in sync[0]["words"]}
        self.assertEqual(ws["seu"]["start"], 2.0)
        self.assertEqual(ws["choro"]["start"], 2.4)
        self.assertEqual(ws["o"]["origem"], "estimada")
        self.assertTrue(1.4 <= ws["o"]["start"] <= 2.0)
        self.assertEqual(sl.validar_palavras(sync, asr), [])

    def test_dash_sticks_to_previous_word(self):
        asr = [_w("Paraíso", 1.0), _w("eterno", 1.5), _w("o", 2.0), _w("gelo", 2.3)]
        sync = sl.alinhar(["PARAÍSO ETERNO — o gelo"], asr)
        textos = [p["text"] for p in sync[0]["words"]]
        self.assertEqual(textos, ["PARAÍSO", "ETERNO —", "o", "gelo"])
        self.assertEqual(sync[0]["words"][2]["start"], 2.0)

    def test_collapsed_asr_words_are_interpolated(self):
        # Douma 44,16 s: varias palavras do ASR com duracao zero no mesmo instante
        asr = [_w("Paraíso", 42.4), {"word": "eterno", "start": 44.16, "end": 44.16},
               {"word": "eu", "start": 44.16, "end": 44.16}, {"word": "vim", "start": 44.16, "end": 44.48},
               _w("te", 44.5)]
        sync = sl.alinhar(["PARAÍSO ETERNO eu vim te"], asr)
        ws = sync[0]["words"]
        self.assertEqual([p["origem"] for p in ws], ["asr", "estimada", "estimada", "asr", "asr"])
        self.assertLess(ws[1]["start"], ws[2]["start"])
        self.assertLessEqual(ws[2]["end"], 44.16 + 1e-6)

    def test_words_are_monotonic(self):
        asr = [_w("a", 1.0), _w("b", 1.5), _w("c", 2.0)]
        sync = sl.alinhar(["a x b y c"], asr)
        st = [p["start"] for p in sync[0]["words"]]
        self.assertEqual(st, sorted(st))

    def test_gate_catches_old_shifted_timing(self):
        asr = [_w("Eu", 1.0), _w("escuto", 1.4), _w("seu", 2.0), _w("choro", 2.4)]
        velho = [{"text": "Eu escuto o seu choro", "start": 1.0, "end": 2.7, "words": [
            {"text": "Eu", "start": 1.0, "end": 1.3}, {"text": "escuto", "start": 1.4, "end": 1.7},
            {"text": "o", "start": 2.0, "end": 2.3}, {"text": "seu", "start": 2.4, "end": 2.7},
            {"text": "choro", "start": 2.7, "end": 2.9}]}]
        self.assertTrue(sl.validar_palavras(velho, asr))

    def test_misheard_name_is_not_flagged(self):
        asr = [_w("novo", 1.0), _w("no", 1.4), _w("meu", 1.8)]
        sync = [{"text": "Shinobu no meu", "start": 1.0, "end": 2.1, "words": [
            {"text": "Shinobu", "start": 1.0, "end": 1.3, "origem": "asr"},
            {"text": "no", "start": 1.4, "end": 1.7, "origem": "asr"},
            {"text": "meu", "start": 1.8, "end": 2.1, "origem": "asr"}]}]
        self.assertEqual(sl.validar_palavras(sync, asr), [])


class PovSemSobreposicaoTests(unittest.TestCase):
    def test_events_never_overlap(self):
        linhas = [{"text": "um dois tres", "start": 0.0, "end": 2.0, "words": [
            {"text": "um", "start": 0.0, "end": 0.9}, {"text": "dois", "start": 0.5, "end": 1.2},
            {"text": "tres", "start": 1.0, "end": 2.5}]}]
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "s.json"
            src.write_text(json.dumps(linhas), encoding="utf-8")
            ass = pov.build_ass(src, Path(td) / "a.ass", 0.0, 10.0)
            ev = []
            for x in ass.read_text(encoding="utf-8-sig").splitlines():
                if x.startswith("Dialogue:"):
                    p = x.split(",", 9)
                    s = lambda t: sum(float(v) * m for v, m in zip(t.split(":"), (3600, 60, 1)))
                    ev.append((s(p[1]), s(p[2])))
        self.assertEqual(len(ev), 3)
        for a, b in zip(ev, ev[1:]):
            self.assertLessEqual(a[1], b[0] + 1e-6)


if __name__ == "__main__":
    unittest.main()
