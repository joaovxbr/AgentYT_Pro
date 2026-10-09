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


class ProducaoEmOndasTests(unittest.TestCase):
    """Fase 5: fases 1-4 em ondas (vx/dag.py) -- sem tocar no resto."""

    ORDEM = ["stems", "transcrever"] + [e.nome for e in vx_etapas.PRODUCAO]

    def _plano(self, nomes=None):
        nomes = nomes if nomes is not None else self.ORDEM
        return {n: ([n], None, vx_etapas.POR_NOME[n].bloqueante
                    if n in vx_etapas.POR_NOME else True) for n in nomes}

    def _step_falso(self):
        chamadas = []

        def step(nome, args, bloqueante=True):
            chamadas.append(nome)

        return chamadas, step

    def test_jobs_1_e_a_ordem_do_registro(self):
        chamadas, step = self._step_falso()
        pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=1)
        self.assertEqual(chamadas, self.ORDEM)

    def test_jobs_1_nao_consulta_o_grafo(self):
        """Serial nao pode depender do DAG: e a esteira de sempre."""
        chamadas, step = self._step_falso()
        with patch.object(pipeline.vx_dag, "construir",
                          side_effect=AssertionError("nao devia montar o grafo")):
            pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=1)
        self.assertEqual(chamadas, self.ORDEM)

    def test_jobs_maior_roda_todas_as_etapas_uma_vez(self):
        chamadas, step = self._step_falso()
        pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=4)
        self.assertEqual(sorted(chamadas), sorted(self.ORDEM))

    def test_etapa_ja_pronta_e_pulada(self):
        """Guarda 'se_ausente': stems/transcrever pulados quando a saida ja existe."""
        chamadas, step = self._step_falso()
        ja = {"stems": True, "transcrever": True}
        pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=1,
                                         ja_prontas=ja)
        self.assertNotIn("stems", chamadas)
        self.assertNotIn("transcrever", chamadas)
        self.assertEqual(chamadas, [e.nome for e in vx_etapas.PRODUCAO])

    def test_paralelismo_real_no_primeiro_par(self):
        """`stems` e `fonte-limpa` sao a primeira onda verdadeiramente paralela."""
        import threading
        import time as _t
        ativos = []
        pico = [0]
        lock = threading.Lock()

        def step(nome, args, bloqueante=True):
            with lock:
                ativos.append(nome)
                pico[0] = max(pico[0], len(ativos))
            _t.sleep(0.02)
            with lock:
                ativos.remove(nome)

        pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=4)
        self.assertGreater(pico[0], 1, "nenhuma etapa rodou em paralelo")

    def test_composicao_nunca_roda_em_paralelo(self):
        """A invariante que protege o timeline.json, agora no orquestrador."""
        import threading
        lock = threading.Lock()
        ativos: list[str] = []
        pares: list[tuple[str, str]] = []

        def step(nome, args, bloqueante=True):
            with lock:
                for x in ativos:
                    pares.append((x, nome))
                ativos.append(nome)
            import time as _t
            _t.sleep(0.002)
            with lock:
                ativos.remove(nome)

        pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=8)
        composicao = vx_dag_corrente()
        for a, b in pares:
            self.assertFalse(a in composicao and b in composicao,
                             f"duas etapas de composicao em paralelo: {a} + {b}")

    def test_fases_1_4_tem_onda_paralela_de_verdade(self):
        """`stems` || `fonte-limpa`: a onda util cruza bootstrap e producao."""
        from vx import dag as _d
        g = _d.construir()
        ondas = g.ondas(vx_etapas.nomes())
        primeira = ondas[0]
        self.assertEqual(set(primeira), {"stems", "fonte-limpa"})

    def test_grafo_invalido_cai_para_serial(self):
        chamadas, step = self._step_falso()
        with patch.object(pipeline.vx_dag, "validar",
                          return_value=["ciclo: a -> b -> a"]):
            pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=4)
        self.assertEqual(chamadas, self.ORDEM)

    def test_falha_bloqueante_propaga(self):
        def step(nome, args, bloqueante=True):
            if nome == "auditar-letra":
                raise pipeline.vx_runner.ErroDeEtapa("exit 1", codigo=1, etapa=nome)

        with self.assertRaises(pipeline.vx_runner.ErroDeEtapa):
            pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=4)

    def test_falha_informativa_nao_interrompe_a_onda(self):
        """Etapa nao bloqueante que falha: `step` registra aviso e volta."""
        vistos = []

        def step(nome, args, bloqueante=True):
            vistos.append(nome)
            if nome == "auditar-ritmo":
                self.assertFalse(bloqueante, "auditar-ritmo deveria ser informativa")
                return

        pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=4)
        self.assertIn("auditar-ritmo", vistos)
        self.assertEqual(sorted(vistos), sorted(self.ORDEM))

    def test_etapa_informativa_nao_aborta_a_onda_mesmo_se_step_relancar(self):
        """Rede de seguranca: `step` mal comportado numa etapa informativa nao
        pode derrubar a onda."""
        vistos = []

        def step(nome, args, bloqueante=True):
            vistos.append(nome)
            if nome == "auditar-ritmo":
                raise pipeline.vx_runner.ErroDeEtapa("exit 1", codigo=1, etapa=nome)

        pipeline._executar_fases_em_ondas(step, self._plano(), self.ORDEM, jobs=4)
        self.assertEqual(sorted(vistos), sorted(self.ORDEM))


def vx_dag_corrente():
    from vx import dag as _d
    return set(_d.construir().corrente)


if __name__ == "__main__":
    unittest.main()
