import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ferramentas'))
import pov_cinematic_pro as cinematic


class PovCinematicProContract(unittest.TestCase):
    def test_hero_window_is_relative_to_short_start(self):
        a, b = cinematic._hero_window(34.95, 62.18, 65.40, 35.0)
        self.assertAlmostEqual(a, 27.23, places=2)
        self.assertAlmostEqual(b, 30.45, places=2)

    def test_cinematic_contract_is_vertical_60fps_with_lyrics_inside_scene(self):
        self.assertEqual((cinematic.W, cinematic.H), (1080, 1920))
        self.assertEqual(cinematic.FPS, 60)
        self.assertGreater(cinematic.LYRIC_Y, cinematic.SCENE_Y)
        self.assertLess(cinematic.LYRIC_Y, cinematic.SCENE_Y + cinematic.SCENE_H)


if __name__ == '__main__':
    unittest.main()
