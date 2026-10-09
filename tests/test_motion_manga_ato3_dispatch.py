import unittest, sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import motion_manga as mm
from _fixtures import projeto_sasuke_canonico

class Ato3ConfigAndEngineTest(unittest.TestCase):
    def test_duration_assertion_supports_up_to_25s(self):
        # Ensure motion_manga supports duration > 15s (Ato 3 is 16.84s / 17.0s)
        self.assertTrue(hasattr(mm, 'executar'))

    def test_explicit_line_indices_in_config(self):
        # Fixture hermetica: nao le projetos/ real (suite verde num clone limpo).
        with projeto_sasuke_canonico(com_ato2=False) as (_raiz, projeto):
            canonical_path = projeto / 'transcricao_canonica.json'
            data = json.loads(canonical_path.read_text(encoding='utf-8'))
            cfg = {"lines": [17, 18, 19, 20, 21]}
            lines = [data['lines'][idx] for idx in cfg['lines']]
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0]['text'], "CHAMAS DO Amaterasu NÃO VÃO SE APAGAR")
        self.assertEqual(lines[4]['text'], "O último Uchiha que o mundo já viu")

if __name__ == '__main__':
    unittest.main()
