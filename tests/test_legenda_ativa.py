"""Todo comando que gera a legenda do master grava no legenda_ass do manifesto.

Regressao: `karaoke` e `legenda` gravavam em legendas/<slug>.ass fixo; com um
legenda_ass diferente no projeto.json o render queimava a legenda antiga.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import estudio  # noqa: E402
import legenda as leg  # noqa: E402

SYNC = [{"start": 1.0, "end": 2.5, "text": "linha de teste",
         "words": [{"word": "linha", "start": 1.0, "end": 1.4},
                   {"word": "de", "start": 1.4, "end": 1.6},
                   {"word": "teste", "start": 1.6, "end": 2.5}]}]


class LegendaAtivaTests(unittest.TestCase):
    def _projeto(self, tmp: str) -> tuple[Path, dict]:
        d = Path(tmp) / "proj"
        (d / "legendas").mkdir(parents=True)
        return d, {"legenda_ass": "legendas/proj_ativa.ass", "cor": {"destaque": "#FF0000"}}

    def test_ass_ativo_follows_manifest_and_falls_back(self):
        d = Path("x")
        self.assertEqual(estudio._ass_ativo(d, {"legenda_ass": "legendas/a.ass"}, "s"), d / "legendas/a.ass")
        self.assertEqual(estudio._ass_ativo(d, {}, "s"), d / "legendas/s.ass")
        self.assertEqual(estudio._ass_ativo(d, {"legenda_ass": ""}, "s"), d / "legendas/s.ass")

    def test_karaoke_writes_active_subtitle(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, m = self._projeto(tmp)
            with patch.object(estudio, "dir_projeto", return_value=d), \
                 patch.object(estudio, "carregar_manifesto", return_value=m), \
                 patch.object(estudio, "_gerar_sync_word_level", return_value=(SYNC, [], None)):
                self.assertEqual(estudio.cmd_karaoke("proj"), 0)
            self.assertTrue((d / "legendas" / "proj_ativa.ass").is_file())
            self.assertFalse((d / "legendas" / "proj.ass").exists())


class OnsetsCanonicaTests(unittest.TestCase):
    """Regressao do incidente 2026-10-09: `transcricao_canonica.json` nao era lida.

    A canonica guarda as palavras ANINHADAS em `lines[].words`. `carregar_onsets`
    so conhecia `{"words": [...]}` e a lista plana, entao lia 0 onsets e o gate
    `sincronia` reprovava com "sem onsets casados — relogio errado?" mesmo com o
    arquivo perfeito (38 linhas, 271 palavras, alinhadas ao .ass).
    """

    def _escrever(self, d: Path, dados) -> Path:
        p = d / "canonica.json"
        p.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return p

    def test_canonica_com_lines_e_words(self):
        """O formato real da canonica: palavras dentro de `lines`."""
        dados = {"lines": [
            {"text": "Sombras se abrem", "start": 15.72, "end": 17.32,
             "words": [{"word": "Sombras", "start": 15.72, "end": 16.28},
                       {"word": "se", "start": 16.28, "end": 16.44},
                       {"word": "abrem", "start": 16.44, "end": 17.32}]},
            {"text": "no chao", "start": 18.0, "end": 19.0,
             "words": [{"word": "no", "start": 18.0, "end": 18.5},
                       {"word": "chao", "start": 18.5, "end": 19.0}]},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            ons = leg.carregar_onsets(self._escrever(Path(tmp), dados))
        self.assertEqual(len(ons), 5)
        self.assertEqual(ons[0], (15.72, "sombras"))
        self.assertEqual(ons[-1], (18.5, "chao"))
        self.assertEqual([t for t, _ in ons], sorted(t for t, _ in ons))

    def test_canonica_com_varias_linhas_e_ordenada(self):
        dados = {"lines": [
            {"text": "b", "start": 5.0, "words": [{"word": "b", "start": 5.0}]},
            {"text": "a", "start": 1.0, "words": [{"word": "a", "start": 1.0}]},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            ons = leg.carregar_onsets(self._escrever(Path(tmp), dados))
        self.assertEqual([t for t, _ in ons], [1.0, 5.0])

    def test_canonica_sem_words_usa_a_linha_como_onset(self):
        """Sem word-level a linha inteira ancora o evento (nunca 0 onsets)."""
        dados = {"lines": [{"text": "linha inteira", "start": 3.5, "end": 6.0}]}
        with tempfile.TemporaryDirectory() as tmp:
            ons = leg.carregar_onsets(self._escrever(Path(tmp), dados))
        self.assertEqual(len(ons), 1)
        self.assertEqual(ons[0][0], 3.5)

    def test_formatos_antigos_continuam_funcionando(self):
        """Regressao: {"words": [...]} e a lista plana nao podem quebrar."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            p = self._escrever(d, {"words": [{"word": "um", "start": 1.0}]})
            self.assertEqual(leg.carregar_onsets(p), [(1.0, "um")])
            p2 = self._escrever(d, [{"word": "dois", "start": 2.0}])
            self.assertEqual(leg.carregar_onsets(p2), [(2.0, "dois")])
            p3 = self._escrever(d, [{"words": [{"word": "tres", "start": 3.0}]}])
            self.assertEqual(leg.carregar_onsets(p3), [(3.0, "tres")])

    def test_gate_de_sincronia_mede_a_canonica(self):
        """O fim do incidente: com a canonica o gate MEDE (nao reprova por zero)."""
        ass = Path(self.tmp.name) / "l.ass"
        ass.write_text(
            "[Events]\n"
            "Dialogue: 0,0:00:15.72,0:00:17.32,Verso,,0,0,0,,SOMBRAS SE ABREM\n",
            encoding="utf-8")
        dados = {"lines": [{"text": "Sombras se abrem", "start": 15.72, "end": 17.32,
                            "words": [{"word": "sombras", "start": 15.72, "end": 16.28},
                                      {"word": "se", "start": 16.28, "end": 16.44},
                                      {"word": "abrem", "start": 16.44, "end": 17.32}]}]}
        canon = self._escrever(Path(self.tmp.name), dados)
        rel = leg.medir_sincronia(ass, canon)
        self.assertEqual(rel.n_medidos, 1)          # nao mais 0
        self.assertFalse(rel.motivo)                # sem "relogio errado?"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
