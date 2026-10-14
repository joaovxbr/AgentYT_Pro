"""Testes do detector de graves 808 e do filtro Bass Shake."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import scipy.io.wavfile as wavfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import bass_shake as bs
import filtros


class BassShakeTests(unittest.TestCase):
    def test_gerar_filtro_ffmpeg_bass_shake(self):
        eventos = [{"tempo": 1.25, "intensidade": 0.85, "duracao": 0.16}]
        filtro = bs.gerar_filtro_ffmpeg_bass_shake(eventos, duracao_total=5.0)
        self.assertIn("rgbashift", filtro)
        self.assertIn("crop=", filtro)
        self.assertIn("between(t,1.250,1.410)", filtro)

    def test_gerar_filtro_sem_eventos(self):
        filtro = bs.gerar_filtro_ffmpeg_bass_shake([], duracao_total=5.0)
        self.assertEqual(filtro, "null")

    def test_extrair_picos_subgrave_sintetico(self):
        sr = 22050
        dur = 2.0
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        # Pulso forte de sub-grave (60Hz) em 0.5s e 1.2s
        y = np.zeros_like(t)
        p1 = (t >= 0.5) & (t <= 0.7)
        y[p1] += 0.9 * np.sin(2 * np.pi * 60 * t[p1])
        p2 = (t >= 1.2) & (t <= 1.4)
        y[p2] += 0.9 * np.sin(2 * np.pi * 60 * t[p2])

        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "subgrave_teste.wav"
            wavfile.write(str(wav_path), sr, (y * 32767).astype(np.int16))
            picos = bs.extrair_picos_subgrave(str(wav_path), limite_hz=120.0)
            self.assertGreaterEqual(len(picos), 1)

    def test_catalogo_filtros_contem_bass_shake(self):
        self.assertIn("bass_shake", filtros.CATALOGO)
        self.assertTrue(filtros.CATALOGO["bass_shake"].ritmico)


if __name__ == "__main__":
    unittest.main()
