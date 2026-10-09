from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import compositor_master_gpu as comp  # noqa: E402
import pipeline_autonomo_pro as pap  # noqa: E402


class BootstrapTests(unittest.TestCase):
    def _novo(self, tmp, com_audio=True):
        proj = Path(tmp) / "projetos" / "novo"
        (proj / "entradas").mkdir(parents=True)
        (proj / "projeto.json").write_text(json.dumps({"legenda_ass": "legendas/novo.ass"}),
                                           encoding="utf-8")
        if com_audio:
            (proj / "entradas" / "novo_normalizado.wav").write_bytes(b"RIFF0000")
        return proj

    def test_projeto_novo_lista_etapas_na_ordem(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._novo(tmp)
            with patch.object(pap, "RAIZ", Path(tmp)):
                self.assertEqual(pap.pendencias_bootstrap("novo"),
                                 ["stems", "transcrever", "sincronizar", "timeline"])

    def test_sem_audio_nao_ha_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._novo(tmp, com_audio=False)
            with patch.object(pap, "RAIZ", Path(tmp)):
                self.assertEqual(pap.pendencias_bootstrap("novo"), [])

    def test_preflight_tolera_so_o_que_o_bootstrap_gera(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._novo(tmp)
            with patch.object(pap, "RAIZ", Path(tmp)):
                estrito = pap.preflight("novo")
                tolerante = pap.preflight("novo", permitir_bootstrap=True)
            texto_estrito = "\n".join(estrito["erros"])
            texto_tol = "\n".join(tolerante["erros"])
            self.assertIn("novo.ass", texto_estrito)
            self.assertIn("Timeline", texto_estrito)
            self.assertNotIn("novo.ass", texto_tol)
            self.assertNotIn("Timeline", texto_tol)
            # a intro oficial nao e gerada pelo bootstrap: continua obrigatoria
            self.assertIn("INTRO", texto_tol)

    def test_executa_so_as_pendencias(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._novo(tmp)
            chamados = []
            with patch.object(pap, "RAIZ", Path(tmp)), \
                    patch.object(pap.vx_runner, "executar",
                                 lambda etapa, args, **kw: chamados.append(etapa)):
                pap.executar_bootstrap("novo", ["transcrever", "timeline"])
            self.assertEqual(chamados, ["transcrever", "timeline"])


class LimitadorTests(unittest.TestCase):
    def test_master_final_tem_limitador_true_peak(self):
        self.assertIn("alimiter", comp.LIMITADOR_TRUE_PEAK)
        self.assertIn("aresample=192000", comp.LIMITADOR_TRUE_PEAK)
        fonte = (ROOT / "ferramentas" / "compositor_master_gpu.py").read_text(encoding="utf-8")
        corpo = fonte[fonte.index("def concatenar_intro"):]
        self.assertIn("LIMITADOR_TRUE_PEAK", corpo)

    def test_esteira_bloqueia_true_peak(self):
        fonte = (ROOT / "ferramentas" / "pipeline_autonomo_pro.py").read_text(encoding="utf-8")
        self.assertIn("QA de audio do master reprovado", fonte)


if __name__ == "__main__":
    unittest.main()
