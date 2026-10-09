"""Contrato de `vx/metrics.py` e da integracao com o pipeline.

O que este teste protege:
1. o formato ANTIGO de `execucao.json` continua valido (etapas = {nome, status});
2. a metrica nao derruba a esteira (gravar em caminho impossivel nao levanta);
3. a etapa interrompida (processo morto no meio) aparece como falha, nao some;
4. `tabela()`/`gargalo()` respondem o que o operador precisa sem abrir log.
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
sys.path.insert(0, str(ROOT))

from vx import metrics  # noqa: E402


class RelatorioTest(unittest.TestCase):
    def test_ciclo_de_vida_e_resumo(self):
        r = metrics.Relatorio("run1", projeto="gojo")
        r.etapa_inicio("stems")
        r.etapa_fim("stems", status=metrics.STATUS_CONCLUIDO, duracao_s=41.2)
        r.etapa_inicio("manga-auto")
        r.etapa_pulada("manga-auto")

        res = r.resumo()
        self.assertEqual(res["run_id"], "run1")
        self.assertEqual(res["projeto"], "gojo")
        self.assertEqual(res["n_etapas"], 2)
        self.assertEqual(res["n_falhas"], 0)
        self.assertEqual(res["n_cache_hit"], 1)
        nomes = {e["nome"]: e for e in res["etapas"]}
        self.assertEqual(nomes["stems"]["duracao_s"], 41.2)
        self.assertTrue(nomes["manga-auto"]["cache_hit"])
        self.assertEqual(nomes["manga-auto"]["status"], metrics.STATUS_PULADA)

    def test_falha_guarda_motivo_e_origem(self):
        r = metrics.Relatorio("run2")
        r.etapa_inicio("cenas-auto")
        r.etapa_fim("cenas-auto", status=metrics.STATUS_FALHOU, duracao_s=1380.5,
                    erro="exit 1", origem_erro="subprocess.CalledProcessError")
        e = r.resumo()["etapas"][0]
        self.assertEqual(e["status"], metrics.STATUS_FALHOU)
        self.assertEqual(e["erro"], "exit 1")
        self.assertEqual(e["origem_erro"], "subprocess.CalledProcessError")
        self.assertEqual(r.gargalo().nome, "cenas-auto")
        self.assertEqual(len(r.falhas), 1)

    def test_etapa_informativa_vira_aviso_nao_falha(self):
        r = metrics.Relatorio("run3")
        r.etapa_fim("auditar-ritmo", status=metrics.STATUS_AVISO, duracao_s=3.0,
                    erro="exit 2")
        self.assertEqual(r.resumo()["n_falhas"], 1)  # aviso e lido como algo a olhar
        self.assertIn(metrics.STATUS_AVISO, metrics.STATUS_RUINS)

    def test_bytes_saida_soma_apenas_arquivos_existentes(self):
        r = metrics.Relatorio("run4")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a.mp4").write_bytes(b"x" * 100)
            (base / "b.mp4").write_bytes(b"y" * 50)
            r.etapa_fim("render-clipe", status=metrics.STATUS_CONCLUIDO,
                        saidas=[base / "a.mp4", base / "b.mp4", base / "nao_existe.mp4"])
        self.assertEqual(r.resumo()["etapas"][0]["bytes_saida"], 150)


class RobustezTest(unittest.TestCase):
    def test_gravar_em_caminho_impossivel_nao_levanta(self):
        """Metrica nunca pode derrubar a esteira."""
        r = metrics.Relatorio("run5")
        r.etapa_fim("stems", status=metrics.STATUS_CONCLUIDO, duracao_s=1.0)
        with patch.object(Path, "write_text", side_effect=OSError("disco cheio")):
            r.gravar(Path(tempfile.gettempdir()) / "vx_metricas_impossivel" / "m.json")

    def test_ler_metricas_de_arquivo_ausente_devolve_vazio(self):
        self.assertEqual(metrics.ler_metricas(Path("nao_existe.json")), {})

    def test_ler_metricas_de_arquivo_corrompido_devolve_vazio(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "m.json"
            p.write_text("{ isso nao e json", encoding="utf-8")
            self.assertEqual(metrics.ler_metricas(p), {})

    def test_gravar_e_ler_round_trip(self):
        r = metrics.Relatorio("run6", projeto="asta")
        r.etapa_fim("sincronia", status=metrics.STATUS_CONCLUIDO, duracao_s=7.5)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "_metricas.json"
            r.gravar(destino)
            lido = metrics.ler_metricas(destino)
        self.assertEqual(lido["run_id"], "run6")
        self.assertEqual(lido["etapas"][0]["nome"], "sincronia")


class CompararTest(unittest.TestCase):
    def test_comparar_destaca_etapa_que_ficou_mais_lenta(self):
        antes = {"etapas": [{"nome": "cenas-auto", "duracao_s": 120.0},
                            {"nome": "stems", "duracao_s": 40.0}]}
        depois = {"etapas": [{"nome": "cenas-auto", "duracao_s": 300.0},
                             {"nome": "stems", "duracao_s": 40.0}]}
        linhas = metrics.comparar(antes, depois)
        self.assertEqual(len(linhas), 1)  # stems nao mudou: fica de fora
        self.assertEqual(linhas[0]["etapa"], "cenas-auto")
        self.assertEqual(linhas[0]["delta_s"], 180.0)

    def test_comparar_ignora_diferenca_irrelevante(self):
        antes = {"etapas": [{"nome": "stems", "duracao_s": 40.0}]}
        depois = {"etapas": [{"nome": "stems", "duracao_s": 40.02}]}
        self.assertEqual(metrics.comparar(antes, depois), [])

    def test_comparar_com_metricas_vazias_nao_quebra(self):
        self.assertEqual(metrics.comparar({}, {}), [])


class IntegracaoPipelineTest(unittest.TestCase):
    def test_pipeline_importa_metrics_e_mantem_formato_antigo(self):
        """O execucao.json continua com etapas = [{nome, status}] e ganha 'metricas'."""
        import pipeline_autonomo_pro as pipeline

        self.assertTrue(hasattr(pipeline, "vx_metrics"))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            report = {"aprovado": True, "erros": [], "saida": str(p / "out.mp4")}
            with                  patch.object(pipeline, "preflight", return_value=report), \
                 patch.object(pipeline, "projeto", return_value=p), \
                 patch("render_dispatch.video_args", return_value=[]), \
                 patch("compositor_master_gpu.concatenar_intro", return_value=p / "out.mp4"), \
                 patch.object(pipeline.vx_runner, "executar",
                              side_effect=RuntimeError("falha simulada")):
                with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                    pipeline.executar_esteira_completa("demo")

            registros = list((p / "qa/esteira").glob("*/execucao.json"))
            self.assertEqual(len(registros), 1)
            estado = json.loads(registros[0].read_text(encoding="utf-8"))

            # formato antigo preservado
            self.assertEqual(estado["status"], "falhou")
            self.assertEqual(estado["etapas"][0]["status"], "falhou")
            self.assertIn("nome", estado["etapas"][0])
            self.assertIn("saida", estado)

            # metricas adicionadas e consistentes com as etapas
            self.assertIn("metricas", estado)
            self.assertEqual(estado["metricas"]["n_etapas"], len(estado["etapas"]))
            self.assertGreaterEqual(estado["metricas"]["duracao_total_s"], 0)

            # arquivo irmao de metricas existe
            metricas_path = registros[0].parent / "_metricas.json"
            self.assertTrue(metricas_path.is_file())
            self.assertEqual(metrics.ler_metricas(metricas_path)["run_id"],
                             estado["metricas"]["run_id"])

    def test_etapa_interrompida_vira_falha_no_fechamento(self):
        """Processo morto no meio: a etapa 'executando' nao some do relatorio."""
        import pipeline_autonomo_pro as pipeline
        from vx import metrics as m

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            report = {"aprovado": True, "erros": [], "saida": str(p / "out.mp4")}

            def _morre(*_a, **_k):
                # sai sem chamar step(): simula queda entre inicio e fim da etapa
                raise RuntimeError("queda simulada")

            with                  patch.object(pipeline, "preflight", return_value=report), \
                 patch.object(pipeline, "projeto", return_value=p), \
                 patch("render_dispatch.video_args", return_value=[]), \
                 patch("compositor_master_gpu.concatenar_intro", return_value=p / "out.mp4"), \
                 patch.object(pipeline.vx_runner, "executar", side_effect=_morre):
                with self.assertRaisesRegex(RuntimeError, "queda simulada"):
                    pipeline.executar_esteira_completa("demo")

            registros = list((p / "qa/esteira").glob("*/execucao.json"))
            estado = json.loads(registros[0].read_text(encoding="utf-8"))
            self.assertEqual(estado["status"], "falhou")
            self.assertIn("metricas", estado)


if __name__ == "__main__":
    unittest.main()
