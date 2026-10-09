"""Alucinacao do ASR sobre silencio do stem vocal (caso Zeref 08/10/2026).

Regra: palavra cai em silencio (RMS < -55 dBFS) e tem confianca baixa ou duracao zero -> sai.
Palavra com voz nunca sai, mesmo com confianca baixa.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import transcrever as tr  # noqa: E402


def _silencio(a, b):
    return -82.0


def _voz(a, b):
    return -20.0


class PalavraEmSilencioTest(unittest.TestCase):
    def test_alucinacao_de_fim_de_arquivo_sai(self):
        w = {"word": "NO", "start": 366.34, "end": 366.34, "probability": 0.99}
        self.assertTrue(tr.palavra_em_silencio(w, _silencio))   # duracao zero, mesmo com p alta

    def test_baixa_confianca_em_silencio_sai(self):
        w = {"word": "CIDADE", "start": 364.94, "end": 366.34, "probability": 0.77}
        self.assertTrue(tr.palavra_em_silencio(w, _silencio))

    def test_palavra_cantada_nunca_sai(self):
        w = {"word": "imortal", "start": 10.0, "end": 10.6, "probability": 0.10}
        self.assertFalse(tr.palavra_em_silencio(w, _voz))       # tem voz no stem

    def test_palavra_em_silencio_com_alta_confianca_e_duracao_real_fica(self):
        w = {"word": "descansar", "start": 350.0, "end": 351.0, "probability": 0.95}
        self.assertFalse(tr.palavra_em_silencio(w, _silencio))

    def test_sem_medidor_nao_remove(self):
        w = {"word": "NO", "start": 366.34, "end": 366.34, "probability": 0.99}
        self.assertFalse(tr.palavra_em_silencio(w, None))

    def test_limpar_remove_so_as_alucinadas(self):
        dados = {"words": [
            {"word": "descansar", "start": 350.0, "end": 351.0, "probability": 0.95},
            {"word": "CIDADE", "start": 364.94, "end": 366.34, "probability": 0.77},
            {"word": "NO", "start": 366.34, "end": 366.34, "probability": 0.99},
        ], "segments": []}

        def energia(a, b):
            return -82.0 if a >= 364.0 else -20.0

        n = tr.limpar_alucinacoes(dados, energia)
        self.assertEqual([w["word"] for w in dados["words"]], ["descansar"])
        self.assertEqual(n, 2)


if __name__ == "__main__":
    unittest.main()
