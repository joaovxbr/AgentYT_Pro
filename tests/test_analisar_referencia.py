"""Raio-x de referencia: medidas puras (sem video, rede ou GPU)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import analisar_referencia as ar  # noqa: E402


class MedidasTests(unittest.TestCase):
    def test_cut_detection_takes_peaks_and_ignores_close_duplicates(self):
        d = [0, 0.05, 0.9, 0.1, 0.05, 0.6, 0.7, 0.1, 0, 0]
        self.assertEqual(ar.detectar_cortes(d, 10, limiar=0.42, min_intervalo=0.12), [0.2, 0.6])

    def test_flash_needs_to_come_back(self):
        luma = [40, 40, 120, 45, 40, 40, 130, 130, 130, 130, 130, 130, 130, 130]
        self.assertEqual(ar.detectar_flashes(luma, 24, salto=55, max_dur=0.25), [0.083])

    def test_beat_sync(self):
        s = ar.sincronia_com_batida([1.0, 2.04, 3.2], [1.0, 2.0, 3.0])
        self.assertAlmostEqual(s["ate_50ms"], 2 / 3, places=3)
        self.assertEqual(s["cortes"], 3)
        self.assertEqual(ar.sincronia_com_batida([], [1.0])["ate_50ms"], 0.0)

    def test_shot_stats(self):
        st = ar.estatisticas_planos([1.0, 1.4, 3.0], 4.0)
        self.assertEqual(st["planos"], 4)
        self.assertEqual(st["cortes_por_minuto"], 45.0)
        self.assertEqual(st["planos_menores_0_5s"], 0.25)

    def test_video_id(self):
        self.assertEqual(ar.id_de("https://youtu.be/Vd0dlRTnWKw"), "Vd0dlRTnWKw")
        self.assertEqual(ar.id_de("https://www.youtube.com/watch?v=Vd0dlRTnWKw&t=3"), "Vd0dlRTnWKw")
        self.assertEqual(ar.id_de("C:/x/meu_video.mp4"), "meu_video")

    def test_graphic_moments_merge_and_filter(self):
        def q(**kw):
            base = {k: 0.0 for k, _ in ar.ROTULOS}
            base.update(kw)
            return base
        tipos = [q(anime_limpo=.9)] * 2 + [q(texto_grande=.6)] * 3 + [q(anime_limpo=.9)] + \
                [q(logo_card=.5)] * 2 + [q(anime_limpo=.9)] * 4 + [q(kanji=.7)]
        m = ar.momentos_graficos(tipos, fps=2, limiar=0.35, juntar=0.6)   # min_dur padrao = 2 quadros
        self.assertEqual(len(m), 1)                      # texto+card juntos (gap 0,5 s); kanji isolado < 0,5 s
        self.assertEqual((m[0]["de"], m[0]["tipo"]), (1.0, "texto_grande"))

    def test_palette_and_layout(self):
        import numpy as np
        img = np.zeros((90, 160, 3), np.uint8)
        img[:, :100] = (200, 40, 20)
        img[:, 100:] = (10, 10, 10)
        pal = ar.paleta(img, k=2)
        self.assertEqual(pal[0]["hex"], "#C82814")
        self.assertAlmostEqual(pal[0]["fracao"], 0.625, places=2)
        img[60:80, 40:120] = 255                          # "texto" embaixo
        img[62:78:3, 40:120] = 0
        self.assertEqual(ar.layout_texto(img)["vertical"], "base")

    def test_color_names(self):
        self.assertEqual(ar.nome_cor(0.62, 0.8, 0.8), "azul")
        self.assertEqual(ar.nome_cor(0.0, 0.8, 0.1), "escuro")
        self.assertEqual(ar.nome_cor(0.78, 0.8, 0.8), "roxo")


if __name__ == "__main__":
    unittest.main()
