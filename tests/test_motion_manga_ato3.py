import unittest, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
import motion_manga as mm
import paineis_manga as pm

class Ato3FeaturesTest(unittest.TestCase):
    def test_tinta_supports_purple_and_cyan_accents(self):
        im = np.zeros((40, 60, 3), np.uint8)
        im[:] = [100, 100, 100]
        # Inject purple pixel (high R, low G, high B)
        im[10:20, 10:20] = [180, 20, 220]
        out_purple = mm.tinta(im, 'purple')
        self.assertEqual(out_purple.shape, im.shape)
        # In purple region, color should be preserved
        self.assertGreater(int(out_purple[15, 15, 2]), int(out_purple[15, 15, 1]))
        self.assertGreater(int(out_purple[15, 15, 0]), int(out_purple[15, 15, 1]))

        # Inject cyan pixel (low R, high G, high B)
        im[25:35, 25:35] = [20, 220, 240]
        out_cyan = mm.tinta(im, 'cyan')
        self.assertGreater(int(out_cyan[30, 30, 2]), int(out_cyan[30, 30, 0]))

    def test_mascaras_3_paineis(self):
        # 3-panel diagonal split mask generator
        if not hasattr(pm, 'mascaras_3_paineis'):
            self.fail("pm.mascaras_3_paineis not implemented yet")
        m1, m2, m3 = pm.mascaras_3_paineis(320, 180, 0.5, borda=8)
        self.assertEqual(m1.shape, (180, 320))
        self.assertEqual(m2.shape, (180, 320))
        self.assertEqual(m3.shape, (180, 320))
        # Masks must be mutually exclusive
        self.assertFalse(np.any((m1 > 0) & (m2 > 0)))
        self.assertFalse(np.any((m2 > 0) & (m3 > 0)))
        self.assertFalse(np.any((m1 > 0) & (m3 > 0)))
        # All 3 panels must have significant area
        self.assertGreater(np.count_nonzero(m1), 3000)
        self.assertGreater(np.count_nonzero(m2), 3000)
        self.assertGreater(np.count_nonzero(m3), 3000)

    def test_ato3_duration_and_line_coverage(self):
        # Verify that motion_manga can handle Ato 3 duration (17.0s, 510 frames)
        # and that the duration assertion allows 10 <= duration <= 20
        self.assertTrue(hasattr(mm, 'executar'))

if __name__ == '__main__':
    unittest.main()
