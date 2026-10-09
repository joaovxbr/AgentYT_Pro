"""POV --karaoke com master que tem a intro: o corte e no MASTER, o .ass e no CORPO.

Regressao (Asta 05/10/2026): `_rebase_ass` recebia o `de` do corte (tempo do master,
intro de 10 s na frente) e descartava as primeiras linhas do trecho, acendendo o resto
10 s adiantado. Agora `_de_ass_corpo` traduz o tempo do corte para o tempo do corpo e
só quando o master realmente comeca com a intro oficial.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import estudio  # noqa: E402

INTRO_S = 10.005


def _frame(valor: int) -> np.ndarray:
    return np.full((36, 64, 3), valor, dtype=np.int16)


class ComecaComIntroTests(unittest.TestCase):
    def test_frames_iguais_contam(self):
        self.assertTrue(estudio._comeca_com_intro(_frame(40), _frame(40)))

    def test_frames_diferentes_nao_contam(self):
        self.assertFalse(estudio._comeca_com_intro(_frame(10), _frame(200)))

    def test_frame_indisponivel_nao_conta(self):
        self.assertFalse(estudio._comeca_com_intro(None, _frame(40)))
        self.assertFalse(estudio._comeca_com_intro(_frame(40), None))
        self.assertFalse(estudio._comeca_com_intro(_frame(40), _frame(40)[:20]))


class DurIntroTests(unittest.TestCase):
    def _dur(self, quadro_master, quadro_intro):
        with patch.object(estudio, "_quadro_rgb", side_effect=[quadro_master, quadro_intro]), \
             patch("compositor_master_gpu.inspecionar_midia", return_value=({"video", "audio"}, INTRO_S)):
            return estudio._dur_intro(Path("master.mp4"))

    def test_master_que_comeca_com_intro_devolve_a_duracao(self):
        self.assertAlmostEqual(self._dur(_frame(40), _frame(40)), INTRO_S)

    def test_master_sem_intro_devolve_zero(self):
        # masters antigos (ex.: eren) nao tem a intro colada: comportamento antigo
        self.assertEqual(self._dur(_frame(10), _frame(200)), 0.0)

    def test_master_ilegivel_devolve_zero(self):
        self.assertEqual(self._dur(None, _frame(40)), 0.0)


class DeAssCorpoTests(unittest.TestCase):
    def test_subtrai_a_intro_do_tempo_do_corte(self):
        with patch.object(estudio, "_dur_intro", return_value=INTRO_S):
            self.assertAlmostEqual(estudio._de_ass_corpo(21.66, Path("m.mp4")), 21.66 - INTRO_S)

    def test_nao_fica_negativo(self):
        with patch.object(estudio, "_dur_intro", return_value=INTRO_S):
            self.assertEqual(estudio._de_ass_corpo(5.0, Path("m.mp4")), 0.0)


class RebaseNoTempoDoCorpoTests(unittest.TestCase):
    ASS = (
        "[Script Info]\n"
        "PlayResX: 1920\nPlayResY: 1080\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:11.66,0:00:14.62,Verso,,0,0,0,,NASCI NO VALE DE HAGE\n"
        "Dialogue: 0,0:00:47.98,0:00:51.22,Refrão,,0,0,0,,REI MAGI SEM MAGIA\n"
    )

    def test_primeira_linha_do_trecho_sobrevive(self):
        # corte no master em 21.66 s = 11.66 s de corpo (intro de 10 s)
        with patch.object(estudio, "_dur_intro", return_value=10.0):
            de_corpo = estudio._de_ass_corpo(21.66, Path("m.mp4"))
        with tempfile.TemporaryDirectory() as tmp:
            origem = Path(tmp) / "pov.ass"
            destino = Path(tmp) / "pov_21s.ass"
            origem.write_text(self.ASS, encoding="utf-8")
            estudio._rebase_ass(origem, de_corpo, 30.0, destino)
            linhas = [l for l in destino.read_text(encoding="utf-8").splitlines()
                      if l.startswith("Dialogue:")]
        self.assertEqual(len(linhas), 1, "a primeira linha do trecho nao pode ser descartada")
        self.assertIn("NASCI NO VALE DE HAGE", linhas[0])
        inicio = linhas[0].split(",")[1]          # 0:00:0X.XX no comeco do corte
        self.assertTrue(inicio.startswith("0:00:00.0"), inicio)

    def test_sem_intro_o_comportamento_antigo_continua(self):
        with patch.object(estudio, "_dur_intro", return_value=0.0):
            de_corpo = estudio._de_ass_corpo(21.66, Path("m.mp4"))
        self.assertEqual(de_corpo, 21.66)


if __name__ == "__main__":
    unittest.main()
