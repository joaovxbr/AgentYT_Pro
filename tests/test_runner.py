"""Contrato de `vx/runner.py` — execucao in-process das etapas.

O que este teste protege -- e o que NAO pode regredir:

1. `SystemExit` do `estudio.py` vira `ErroDeEtapa`, nunca atravessa a esteira.
   Esse e o risco central: 28 pontos de `estudio.py` levantam SystemExit para
   sinalizar erro de entrada. Em subprocess era so o exit code; in-process, um
   SystemExit cru mataria o processo da esteira e o `finally` do pipeline nunca
   fecharia metricas nem checkpoint.
2. codigo de saida != 0 reprova; `None` e `0` (contrato de `estudio.main`).
3. o log da etapa e escrito E a saida continua aparecendo no console.
4. cwd e sys.stdout voltam ao normal depois da etapa, mesmo se ela falhar.
5. `isolado=True` faz o mesmo trabalho por subprocess -- mesma interface,
   mesmo contrato de erro.
6. chamar a etapa nao deixa o dispatcher do estudio em estado esquisito: a
   segunda chamada funciona.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))
sys.path.insert(0, str(ROOT))

from vx import runner  # noqa: E402


class ArgumentosTest(unittest.TestCase):
    def test_slug_entra_depois_do_subcomando(self):
        argv = runner._argumentos("transcrever", ["transcrever", "--modelo", "large-v3"], "demo")
        self.assertEqual(argv, ["transcrever", "demo", "--modelo", "large-v3"])

    def test_slug_nao_duplica(self):
        argv = runner._argumentos("transcrever", ["transcrever", "demo"], "demo")
        self.assertEqual(argv, ["transcrever", "demo"])

    def test_sem_slug_passa_como_esta(self):
        argv = runner._argumentos("doutor", ["doutor"], None)
        self.assertEqual(argv, ["doutor"])

    def test_args_que_ja_trazem_o_subcomando_nao_ganham_outro(self):
        """executar_bootstrap passa ["stems", <audio>, "--saida", <dir>] com slug=None."""
        argv = runner._argumentos("stems", ["stems", "a.wav", "--saida", "s"], None)
        self.assertEqual(argv, ["stems", "a.wav", "--saida", "s"])


class ExecucaoTest(unittest.TestCase):
    def test_etapa_que_passa_devolve_resultado_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "01_doutor.log"
            r = runner.executar("doutor", ["doutor"], log_path=log)
            self.assertTrue(r.ok)
            self.assertEqual(r.codigo, 0)
            self.assertEqual(r.nome, "doutor")
            self.assertFalse(r.isolado)
            self.assertGreaterEqual(r.duracao_s, 0)

    def test_log_da_etapa_e_escrito(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "sub" / "01_doutor.log"
            runner.executar("doutor", ["doutor"], log_path=log)
            self.assertTrue(log.is_file())
            self.assertGreater(log.stat().st_size, 0)
            self.assertIn("estudio", log.read_text(encoding="utf-8"))

    def test_systemexit_vira_erro_de_etapa(self):
        """`estudio.py` levanta SystemExit em 28 pontos: nenhum pode atravessar."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "02.log"
            with self.assertRaises(runner.ErroDeEtapa) as ctx:
                runner.executar("sincronia", ["sincronia", "faixa_inexistente"], log_path=log)
            self.assertEqual(ctx.exception.codigo, 1)
            self.assertEqual(ctx.exception.etapa, "sincronia")
            self.assertEqual(ctx.exception.log, log)

    def test_systemexit_com_codigo_zero_nao_reprova(self):
        """`sys.exit()` sem argumento e sucesso, nao falha."""
        with patch("estudio.main", side_effect=SystemExit()):
            r = runner.executar("doutor", ["doutor"])
            self.assertTrue(r.ok)

    def test_excecao_generica_vira_erro_de_etapa_com_causa(self):
        def _boom(argv):
            raise ValueError("config invalida")

        with patch("estudio.main", side_effect=_boom):
            with self.assertRaises(runner.ErroDeEtapa) as ctx:
                runner.executar("doutor", ["doutor"])
            self.assertIn("config invalida", str(ctx.exception))
            self.assertIsInstance(ctx.exception.__cause__, ValueError)

    def test_codigo_de_saida_nao_zero_reprova(self):
        with patch("estudio.main", return_value=2):
            with self.assertRaises(runner.ErroDeEtapa) as ctx:
                runner.executar("doutor", ["doutor"])
            self.assertEqual(ctx.exception.codigo, 2)

    def test_none_conta_como_sucesso(self):
        """Contrato de `estudio.main`: None e o caminho feliz do dispatcher."""
        with patch("estudio.main", return_value=None):
            self.assertTrue(runner.executar("doutor", ["doutor"]).ok)

    def test_sem_nome_de_etapa_e_erro_de_programacao(self):
        with self.assertRaises(ValueError):
            runner.executar("", ["doutor"])


class HigieneTest(unittest.TestCase):
    def test_cwd_volta_ao_normal_depois_de_falhar(self):
        antes = Path.cwd()
        with patch("estudio.main", side_effect=SystemExit("erro")):
            with self.assertRaises(runner.ErroDeEtapa):
                runner.executar("doutor", ["doutor"])
        self.assertEqual(Path.cwd(), antes)

    def test_stdout_e_restaurado_depois_do_log(self):
        original = sys.stdout
        with tempfile.TemporaryDirectory() as tmp:
            runner.executar("doutor", ["doutor"], log_path=Path(tmp) / "l.log")
        self.assertIs(sys.stdout, original)

    def test_stderr_e_restaurado_mesmo_se_a_etapa_falhar(self):
        original_err = sys.stderr
        with patch("estudio.main", side_effect=RuntimeError("boom")):
            with self.assertRaises(runner.ErroDeEtapa):
                runner.executar("doutor", ["doutor"])
        self.assertIs(sys.stderr, original_err)

    def test_log_impossivel_nao_derruba_a_etapa(self):
        """Log e conveniencia; falhar ao escrever nao pode reprovar a etapa."""
        with patch.object(Path, "open", side_effect=OSError("sem permissao")):
            r = runner.executar("doutor", ["doutor"],
                                log_path=Path(tempfile.gettempdir()) / "vx_x" / "l.log")
            self.assertTrue(r.ok)

    def test_duas_chamadas_seguidas_funcionam(self):
        """A etapa nao pode deixar o processo num estado que quebre a proxima."""
        with tempfile.TemporaryDirectory() as tmp:
            a = runner.executar("doutor", ["doutor"], log_path=Path(tmp) / "a.log")
            b = runner.executar("doutor", ["doutor"], log_path=Path(tmp) / "b.log")
            self.assertTrue(a.ok and b.ok)
            self.assertEqual((Path(tmp) / "a.log").read_text(encoding="utf-8"),
                             (Path(tmp) / "b.log").read_text(encoding="utf-8"))

    def test_preparar_processo_deixa_ferramentas_importavel(self):
        runner.preparar_processo()
        import estudio  # noqa: F401
        self.assertIn(str(ROOT / "ferramentas"), sys.path)
        self.assertIn(str(ROOT), sys.path)


class IsoladoTest(unittest.TestCase):
    def test_isolado_roda_em_subprocess_e_marca_resultado(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "01_doutor.log"
            r = runner.executar("doutor", ["doutor"], log_path=log, isolado=True)
            self.assertTrue(r.ok)
            self.assertTrue(r.isolado)
            self.assertTrue(log.is_file())

    def test_isolado_falha_vira_erro_de_etapa(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(runner.ErroDeEtapa) as ctx:
                runner.executar("sincronia", ["sincronia", "faixa_inexistente"],
                                log_path=Path(tmp) / "l.log", isolado=True)
            self.assertEqual(ctx.exception.codigo, 1)

    def test_isolado_e_in_process_entregam_o_mesmo_conteudo(self):
        """O log nao pode mudar de etapa para etapa so por causa do modo."""
        with tempfile.TemporaryDirectory() as tmp:
            inproc = Path(tmp) / "inproc.log"
            isolado = Path(tmp) / "isolado.log"
            runner.executar("doutor", ["doutor"], log_path=inproc)
            runner.executar("doutor", ["doutor"], log_path=isolado, isolado=True)
            self.assertIn("doutor", inproc.read_text(encoding="utf-8"))
            self.assertIn("doutor", isolado.read_text(encoding="utf-8"))


class EspelhoTest(unittest.TestCase):
    def test_saida_aparece_no_console_e_no_log(self):
        """O operador ve a etapa acontecendo -- nao fica mudo como no subprocess."""
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "l.log"
            with patch.object(sys, "stdout", buffer):
                runner.executar("doutor", ["doutor"], log_path=log)
            # o _Tee duplica: o stream visto pela etapa foi o espelho, nao o buffer
            texto_log = log.read_text(encoding="utf-8")
            self.assertIn("doutor", texto_log)


class ErroDeEtapaTest(unittest.TestCase):
    def test_codigo_nunca_e_zero(self):
        self.assertEqual(runner.ErroDeEtapa("x", codigo=0).codigo, 1)
        self.assertEqual(runner.ErroDeEtapa("x", codigo=None).codigo, 1)
        self.assertEqual(runner.ErroDeEtapa("x", codigo=7).codigo, 7)

    def test_carrega_etapa_e_log(self):
        log = Path("/tmp/x.log")
        e = runner.ErroDeEtapa("falhou", codigo=3, etapa="render-clipe", log=log)
        self.assertEqual(e.etapa, "render-clipe")
        self.assertEqual(e.log, log)
        self.assertEqual(e.origem, "ErroDeEtapa")

    def test_e_runtime_error_para_o_pipeline_tratar_como_antes(self):
        """O pipeline captura (ValueError, RuntimeError, OSError) em estudio.py."""
        self.assertTrue(issubclass(runner.ErroDeEtapa, RuntimeError))


if __name__ == "__main__":
    unittest.main()
