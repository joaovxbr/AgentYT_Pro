import unittest, sys, json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import motion_manga as mm
import paineis_manga as pm
from _fixtures import projeto_sasuke_canonico

class Ato3FullSpecificationTest(unittest.TestCase):
    def test_mascaras_3_paineis_properties(self):
        m1, m2, m3 = pm.mascaras_3_paineis(1920, 1080, 0.5, borda=18)
        self.assertEqual(m1.shape, (1080, 1920))
        self.assertEqual(m2.shape, (1080, 1920))
        self.assertEqual(m3.shape, (1080, 1920))
        # Zero intersection
        self.assertFalse(np.any((m1 > 0) & (m2 > 0)))
        self.assertFalse(np.any((m2 > 0) & (m3 > 0)))
        self.assertFalse(np.any((m1 > 0) & (m3 > 0)))
        # Gutters (pixels where all masks are 0) must exist along the boundaries
        gutters = (m1 == 0) & (m2 == 0) & (m3 == 0)
        self.assertGreater(np.count_nonzero(gutters), 10000)

    def test_ato3_lyrics_generation(self):
        # Read canonical transcription and check Ato 3 lines (lines 17 to 21)
        # Fixture hermetica: nao le projetos/ real (suite verde num clone limpo).
        with projeto_sasuke_canonico(com_ato2=False) as (_raiz, projeto):
            canonical_path = projeto / 'transcricao_canonica.json'
            data = json.loads(canonical_path.read_text(encoding='utf-8'))
            lines = [l for l in data['lines'] if l.get('start') is not None and 62.0 <= l['start'] <= 78.0]
            self.assertEqual(len(lines), 5)
            self.assertIn("Amaterasu", lines[0]['text'])
            self.assertIn("Susanoo", lines[1]['text'])
            self.assertIn("Hokage", lines[2]['text'])
            self.assertIn("Kirin", lines[3]['text'])
            self.assertIn("Uchiha", lines[4]['text'])

            ass_text, audit = mm.legenda_manga(lines, 62.0, 16.84)
        self.assertIn("Cinzel", ass_text)
        self.assertIn("AMATERASU", ass_text)
        self.assertIn("SUSANOO", ass_text)
        self.assertIn("KIRIN", ass_text)
        self.assertGreater(audit['timed_words'], 25)

if __name__ == '__main__':
    unittest.main()
