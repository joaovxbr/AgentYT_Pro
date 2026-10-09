"""Excecao humana restrita do porteiro de sincronia (projetos/<slug>/qa/excecao_sincronia.json).
Caso Zeref 09/10/2026: 1 linha fora de 0,30 s e 2 palavras 'volta no tempo'."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import estudio  # noqa: E402

REG = {
    "projeto": "zeref",
    "pontos": [
        {"tipo": "fora_de_0_30s", "t": 131.32, "texto": "EU CONSTRUÍ UM IMPÉRIO, FIZ O MUNDO ME T"},
        {"tipo": "palavra_volta_no_tempo", "palavra": "o",
         "texto": "Eu tenho o poder que faria um deus se ajoelhar,"},
        {"tipo": "palavra_volta_no_tempo", "palavra": "ensinou",
         "texto": "Igneel te criou, te ensinou a ser forte,"},
    ],
}


def _proj(reg, slug="zeref"):
    d = Path(tempfile.mkdtemp())
    (d / "qa").mkdir()
    (d / "qa" / "excecao_sincronia.json").write_text(json.dumps(reg), encoding="utf-8")
    return d


class ExcecaoSincroniaTest(unittest.TestCase):
    def test_ponto_registrado_e_perdoado(self):
        d = _proj(REG)
        fora = [(131.32, "EU CONSTRUÍ UM IMPÉRIO, FIZ O MUNDO ME T", -3.56)]
        pf, pp, sf, sp = estudio._excecoes_sincronia(d, "zeref", fora, [])
        self.assertEqual(sf, [])
        self.assertEqual(len(pf), 1)

    def test_palavra_volta_registrada_e_perdoada(self):
        d = _proj(REG)
        msg = "linha 22 'Eu tenho o poder que faria um deus se aj': 'o' volta no tempo"
        pf, pp, sf, sp = estudio._excecoes_sincronia(d, "zeref", [], [msg])
        self.assertEqual(sp, [])
        self.assertEqual(len(pp), 1)

    def test_fora_em_outro_tempo_nao_e_perdoado(self):
        d = _proj(REG)
        fora = [(200.0, "EU CONSTRUÍ UM IMPÉRIO, FIZ O MUNDO ME T", -3.56)]
        _, _, sf, _ = estudio._excecoes_sincronia(d, "zeref", fora, [])
        self.assertEqual(len(sf), 1)

    def test_palavra_volta_em_outra_linha_nao_e_perdoada(self):
        d = _proj(REG)
        msg = "linha 5 'Outra linha qualquer': 'o' volta no tempo"
        _, _, _, sp = estudio._excecoes_sincronia(d, "zeref", [], [msg])
        self.assertEqual(len(sp), 1)

    def test_outro_projeto_nao_usa_o_registro(self):
        d = _proj(REG)
        fora = [(131.32, "EU CONSTRUÍ UM IMPÉRIO, FIZ O MUNDO ME T", -3.56)]
        _, _, sf, _ = estudio._excecoes_sincronia(d, "asta", fora, [])
        self.assertEqual(len(sf), 1)

    def test_sem_arquivo_nada_e_perdoado(self):
        d = Path(tempfile.mkdtemp())
        (d / "qa").mkdir()
        fora = [(131.32, "EU CONSTRUÍ UM IMPÉRIO, FIZ O MUNDO ME T", -3.56)]
        _, _, sf, _ = estudio._excecoes_sincronia(d, "zeref", fora, [])
        self.assertEqual(len(sf), 1)


if __name__ == "__main__":
    unittest.main()
