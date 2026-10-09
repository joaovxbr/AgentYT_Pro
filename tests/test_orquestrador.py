"""Fase 2: registro de etapas, cerebro gerado, imports preguicosos e etapas informativas."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ferramentas"))

from vx import etapas as vx_etapas, lazy
import pipeline_autonomo_pro as pipeline
import render_dispatch as rd

INTERNAS = {"intro", "qa-master"}  # executadas dentro do orquestrador, sem subcomando


class RegistroTests(unittest.TestCase):
    def test_every_stage_has_an_estudio_subcommand(self):
        fonte = (ROOT / "ferramentas" / "estudio.py").read_text(encoding="utf-8")
        parsers = set(re.findall(r'add_parser\(\s*"([^"]+)"', fonte))
        faltam = [n for n in vx_etapas.nomes() if n not in INTERNAS and n not in parsers]
        self.assertEqual(faltam, [])

    def test_stage_contracts_are_complete(self):
        for e in vx_etapas.TODAS:
            self.assertTrue(e.descricao, e.nome)
            self.assertTrue(e.le, f"{e.nome} sem entradas declaradas")
            self.assertIn(e.fase, {"bootstrap", "producao", "master"})
        self.assertEqual(len(vx_etapas.POR_NOME), len(vx_etapas.TODAS), "nome de etapa repetido")

    def test_order_is_the_production_contract(self):
        ordem = vx_etapas.nomes()
        for antes, depois in [("fonte-limpa", "cenas-auto"), ("transcrever", "auditar-letra"),
                              ("auditar-letra", "cenas-auto"),
                              ("cenas-auto", "cenas-ia"), ("cenas-ia", "titulos"),
                              ("cenas-auto", "chroma-auto"), ("chroma-auto", "cenas-ia"),
                              ("titulos", "manga-auto"), ("manga-auto", "graficos-auto"),
                              ("graficos-auto", "planejar"), ("sincronia", "render-clipe"),
                              ("render-clipe", "intro"), ("intro", "qa-master")]:
            self.assertLess(ordem.index(antes), ordem.index(depois), f"{antes} antes de {depois}")

    def test_cerebro_doc_is_in_sync_with_registry(self):
        doc = (ROOT / "cerebro" / "etapas.md").read_text(encoding="utf-8")
        self.assertEqual(doc.strip(), vx_etapas.documentacao().strip(),
                         "cerebro/etapas.md defasado: rode `estudio.py cerebro`")


class LazyTests(unittest.TestCase):
    def test_broken_module_only_fails_when_used(self):
        quebrado = lazy.modulo("modulo_que_nao_existe_vx")
        with self.assertRaises(ModuleNotFoundError):
            quebrado.qualquer_coisa

    def test_patch_through_proxy_reaches_real_module(self):
        proxy = lazy.modulo("json")
        with patch.object(proxy, "dumps", return_value="patched"):
            import json as real
            self.assertEqual(real.dumps({}), "patched")
        self.assertEqual(proxy.dumps({}), "{}")

    def test_optional_missing_dependency_is_falsy(self):
        self.assertFalse(lazy.modulo_opcional("dependencia_opcional_inexistente_vx"))
        self.assertTrue(lazy.modulo_opcional("json"))

    def test_estudio_help_does_not_import_heavy_modules(self):
        # carrega o estudio.py sem executar main(): nenhum modulo pesado pode vir junto
        codigo = ("import sys, runpy;"
                  f"runpy.run_path(r'{ROOT / 'ferramentas' / 'estudio.py'}', run_name='vx_teste');"
                  "print('cv2' in sys.modules, 'librosa' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False False")


class EtapaInformativaTests(unittest.TestCase):
    def test_non_blocking_stage_failure_is_recorded_and_pipeline_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            from vx import projeto as vx_projeto
            vx_projeto.stems_dir(p).mkdir(parents=True)
            for s in vx_projeto.stems(p):  # nome canonico derivado do manifesto/pasta
                s.write_bytes(b"x")
            (p / "entradas" / "transcricao.json").write_text("{}")
            chamadas = []

            def fake(etapa, args, log_path=None, **kw):
                chamadas.append(etapa)
                if etapa == "auditar-ritmo":
                    raise pipeline.vx_runner.ErroDeEtapa("exit 1", codigo=1, etapa=etapa)
                if etapa == "cenas-auto":
                    raise RuntimeError("parar aqui")

            report = {"aprovado": True, "erros": [], "saida": str(p / "o.mp4")}
            with patch.object(pipeline, "preflight", return_value=report), \
                 patch.object(pipeline, "projeto", return_value=p), \
                 patch.object(rd, "video_args", return_value=[]), \
                 patch.object(pipeline.vx_runner, "executar", side_effect=fake):
                with self.assertRaisesRegex(RuntimeError, "parar aqui"):
                    pipeline.executar_esteira_completa("demo")
            estado = json.loads(next((p / "qa" / "esteira").glob("*/execucao.json")).read_text(encoding="utf-8"))
            status = {x["nome"]: x["status"] for x in estado["etapas"]}
            self.assertEqual(status["auditar-ritmo"], "aviso")
            self.assertEqual(status["cenas-auto"], "falhou")
            # fonte-limpa (marca d'agua/legenda nos clipes) vem antes de tudo desde o incidente Douma
            self.assertEqual(chamadas[:4], ["fonte-limpa", "auditar-letra", "auditar-ritmo", "cenas-auto"])
            self.assertFalse((p / ".esteira.lock").exists())


if __name__ == "__main__":
    unittest.main()
