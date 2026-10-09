import unittest, sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import motion_manga as mm
from _fixtures import projeto_sasuke_canonico

class Ato2VisualEffectsTest(unittest.TestCase):
    def test_rinnegan_overlay_draws_orbiting_tomoes_and_purple_glow(self):
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        out = mm.desenhar_rinnegan_fx(img.copy(), (150, 150), radius=60, u=0.5, tomoe_count=6)
        self.assertEqual(out.shape, img.shape)
        center_color = out[150, 150]
        self.assertGreater(int(center_color[0]) + int(center_color[2]), 20)
        ring_pixels = out[150, 150 + 40]
        self.assertGreater(int(ring_pixels.sum()), 0)

    def test_amenotejikara_shatter_glitch_displacement(self):
        img = np.full((180, 320, 3), 100, dtype=np.uint8)
        img[60:120, 100:220] = [200, 50, 50]
        shattered = mm.efeito_amenotejikara_shatter(img.copy(), u=0.5, seed=42)
        self.assertEqual(shattered.shape, img.shape)
        diff = np.abs(shattered.astype(float) - img.astype(float)).mean()
        self.assertGreater(diff, 1.0)

    def test_susanoo_arrow_break_frame_zoom(self):
        img = np.zeros((180, 320, 3), dtype=np.uint8)
        out = mm.efeito_flecha_susanoo(img.copy(), u=0.7)
        self.assertEqual(out.shape, img.shape)
        self.assertGreater(out.sum(), 1000)

class Ato2ConfigTest(unittest.TestCase):
    def test_ato2_config_structure_and_coverage(self):
        # Fixture hermetica: nao le projetos/ real (suite verde num clone limpo).
        with projeto_sasuke_canonico() as (_raiz, projeto):
            cfg_path = projeto / 'motion_manga_ato2_rinnegan.json'
            self.assertTrue(cfg_path.exists())
            cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        
        # Check start and duration
        self.assertEqual(cfg['start'], 78.8)
        self.assertEqual(cfg['frames'], 588)
        duration = cfg['frames'] / 30.0
        self.assertAlmostEqual(duration, 19.6, places=1)
        
        # Check canonical lines (22 to 29)
        self.assertEqual(cfg['lines'], [22, 23, 24, 25, 26, 27, 28, 29])
        
        # Check shots coverage
        shots = cfg['shots']
        self.assertGreater(len(shots), 6) # high density of shots
        self.assertEqual(shots[0]['start'], 0.0)
        self.assertAlmostEqual(shots[-1]['end'], duration, places=1)
        for i in range(len(shots) - 1):
            self.assertAlmostEqual(shots[i]['end'], shots[i+1]['start'], places=2)
            
        # Check presence of new visual features
        has_rinnegan = any(s.get('rinnegan_fx') for s in shots)
        has_amenotejikara = any(s.get('amenotejikara') for s in shots)
        has_susanoo_arrow = any(s.get('susanoo_arrow') for s in shots)
        has_panels_3 = any('panels_3' in s for s in shots)
        
        self.assertTrue(has_rinnegan, "Shots must contain rinnegan_fx")
        self.assertTrue(has_amenotejikara, "Shots must contain amenotejikara")
        self.assertTrue(has_susanoo_arrow, "Shots must contain susanoo_arrow")
        self.assertTrue(has_panels_3, "Shots must contain panels_3")

if __name__ == '__main__':
    unittest.main()
