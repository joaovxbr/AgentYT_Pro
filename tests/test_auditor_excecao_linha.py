"""Excecao humana por linha de fala (projetos/<slug>/qa/excecao_letra.json). Caso Zeref 09/10/2026:
'Natsu...' (uma palavra falada) nao casa com o ASR. So a linha registrada sai de 'sem audio'."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import auditor_letra as al  # noqa: E402


def _words(*pares):
    return [{"word": w, "start": s, "end": e, "probability": 0.95} for w, s, e in pares]


class ExcecaoLinhaTest(unittest.TestCase):
    def setUp(self):
        self.linhas = ["Eu cansei de ser eterno.", "Natsu...", "Mavis..."]
        self.words = _words(("Eu", 1.0, 1.2), ("cansei", 1.2, 1.6), ("de", 1.6, 1.7),
                            ("ser", 1.7, 1.9), ("eterno", 1.9, 2.4),
                            ("Mavis", 5.0, 5.5))

    def test_sem_excecao_linha_nao_casada_reprova(self):
        rel = al.auditar(self.linhas, self.words)
        self.assertFalse(rel["aprovado"])
        self.assertEqual([l["texto"] for l in rel["linhas_sem_audio"]], ["Natsu..."])

    def test_excecao_registrada_libera_so_a_linha_exata(self):
        exc = {"linhas_fala": [{"texto": "Natsu..."}]}
        rel = al.auditar(self.linhas, self.words, excecoes=exc)
        self.assertEqual(rel["linhas_sem_audio"], [])
        self.assertTrue(rel["aprovado"])

    def test_excecao_nao_libera_outra_linha_sem_audio(self):
        exc = {"linhas_fala": [{"texto": "Natsu..."}]}
        linhas = self.linhas + ["Outra linha que nao existe no audio"]
        rel = al.auditar(linhas, self.words, excecoes=exc)
        self.assertEqual([l["texto"] for l in rel["linhas_sem_audio"]],
                         ["Outra linha que nao existe no audio"])
        self.assertFalse(rel["aprovado"])

    def test_normalizacao_ignora_pontuacao_e_caixa(self):
        exc = {"linhas_fala": [{"texto": "NATSU"}]}
        rel = al.auditar(self.linhas, self.words, excecoes=exc)
        self.assertEqual(rel["linhas_sem_audio"], [])

    def test_leitura_so_vale_para_o_slug_do_projeto(self):
        import json
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "qa").mkdir()
        (d / "qa" / "excecao_letra.json").write_text(
            json.dumps({"projeto": "outro", "linhas_fala": [{"texto": "Natsu..."}]}), encoding="utf-8")
        self.assertIsNone(al._ler_excecoes_letra(d, "zeref"))
        (d / "qa" / "excecao_letra.json").write_text(
            json.dumps({"projeto": "zeref", "linhas_fala": [{"texto": "Natsu..."}]}), encoding="utf-8")
        self.assertIsNotNone(al._ler_excecoes_letra(d, "zeref"))


if __name__ == "__main__":
    unittest.main()
