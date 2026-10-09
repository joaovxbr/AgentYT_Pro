"""Regressoes de producao: falhas, preservacao de arquivos e intro."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import render_dispatch as rd
import compositor_master_gpu as compositor
import pipeline_autonomo_pro as pipeline


class AtomicRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "master.mp4"
        self.path.write_bytes(b"original")
        for name in ("tem_nvenc", "tem_gpu_nvidia"):
            p = patch.object(rd, name, return_value=True)
            p.start()
            self.addCleanup(p.stop)

    def test_failed_encode_keeps_original_and_cleans_partial(self):
        def fail(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"partial")
            return SimpleNamespace(returncode=1, stderr="driver error")
        with patch.object(rd.subprocess, "run", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "driver error"):
                rd.encode(str(self.path), ["-i", "input.mp4"])
        self.assertEqual(self.path.read_bytes(), b"original")
        self.assertFalse(list(self.path.parent.glob("*.partial.mp4")))

    def test_success_promotes_file_atomically(self):
        def succeed(cmd, **kwargs):
            self.assertEqual(self.path.read_bytes(), b"original")
            self.assertNotEqual(Path(cmd[-1]), self.path)
            Path(cmd[-1]).write_bytes(b"new-video")
            return SimpleNamespace(returncode=0, stderr="")
        with patch.object(rd.subprocess, "run", side_effect=succeed):
            rd.encode(str(self.path), ["-i", "input.mp4"])
        self.assertEqual(self.path.read_bytes(), b"new-video")

    def test_zero_exit_without_output_is_failure(self):
        with patch.object(rd.subprocess, "run", return_value=SimpleNamespace(returncode=0, stderr="")):
            with self.assertRaisesRegex(RuntimeError, "arquivo valido"):
                rd.encode(str(self.path), ["-i", "input.mp4"])
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_interrupt_preserves_original(self):
        with patch.object(rd.subprocess, "run", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                rd.encode(str(self.path), ["-i", "input.mp4"])
        self.assertEqual(self.path.read_bytes(), b"original")


class IntroTests(unittest.TestCase):
    def test_missing_intro_fails_before_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            video = p / "body.mp4"
            video.write_bytes(b"body")
            with patch.object(compositor, "INTRO_OFICIAL", p / "missing.mp4"), \
                 patch.object(rd, "encode") as encode:
                with self.assertRaises(FileNotFoundError):
                    compositor.concatenar_intro(video, p / "out.mp4")
                encode.assert_not_called()

    def test_bad_duration_does_not_replace_existing_master(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            intro, video, out = [p / name for name in ("intro.mp4", "body.mp4", "out.mp4")]
            for f in (intro, video, out):
                f.write_bytes(b"original")
            def encode(dest, *args, **kwargs):
                Path(dest).write_bytes(b"candidate")
            media = [({"audio", "video"}, 20), ({"audio", "video"}, 10),
                     ({"audio", "video"}, 12)]
            with patch.object(compositor, "INTRO_OFICIAL", intro), \
                 patch.object(compositor, "inspecionar_midia", side_effect=media), \
                 patch.object(rd, "encode", side_effect=encode):
                with self.assertRaisesRegex(RuntimeError, "duracao"):
                    compositor.concatenar_intro(video, out)
            self.assertEqual(out.read_bytes(), b"original")

    def test_concat_normalizes_both_streams_and_uses_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            intro, video, out = [p / name for name in ("intro.mp4", "body.mp4", "out.mp4")]
            intro.write_bytes(b"intro")
            video.write_bytes(b"body")
            def encode(dest, inputs, **kwargs):
                graph = kwargs["filtro_complexo"]
                self.assertIn("concat=n=2:v=1:a=1", graph)
                self.assertEqual(graph.count("setsar=1"), 2)
                self.assertEqual(graph.count("channel_layouts=stereo"), 2)
                Path(dest).write_bytes(b"combined")
            media = [({"audio", "video"}, 20), ({"audio", "video"}, 10),
                     ({"audio", "video"}, 30)]
            with patch.object(compositor, "INTRO_OFICIAL", intro), \
                 patch.object(compositor, "inspecionar_midia", side_effect=media), \
                 patch.object(rd, "encode", side_effect=encode):
                compositor.concatenar_intro(video, out)
            self.assertEqual(out.read_bytes(), b"combined")


class PreflightTests(unittest.TestCase):
    def test_rejects_parent_traversal(self):
        for slug in ("../sasuke", "..", "a/b", "a\\b"):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                pipeline.projeto(slug)

    def test_plan_does_not_start_processes(self):
        report = {"aprovado": True, "erros": [], "etapas": []}
        with patch.object(pipeline, "preflight", return_value=report), \
             patch.object(pipeline.subprocess, "run") as run:
            self.assertEqual(pipeline.executar_esteira_completa("demo", True), 0)
            run.assert_not_called()

    def test_invalid_plan_returns_failure(self):
        with patch.object(pipeline, "preflight", return_value={"aprovado": False, "erros": ["audio ausente"]}):
            self.assertEqual(pipeline.executar_esteira_completa("demo", True), 1)

if __name__ == "__main__":
    unittest.main()


class PipelineIsolationTests(unittest.TestCase):
    def test_preflight_reports_timeline_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p = base / "projetos/demo"
            (p / "entradas").mkdir(parents=True)
            (base / "assets/intro").mkdir(parents=True)
            (base / "assets/intro/Eu_preciso_criar_INTRO_para_o.mp4").write_bytes(b"intro")
            (p / "entradas/demo_normalizado.wav").write_bytes(b"audio")
            (p / "lyrics.ass").write_text("Style: Default\nDialogue: event", encoding="utf-8")
            (p / "projeto.json").write_text(json.dumps({"legenda_ass": "lyrics.ass"}))
            (p / "timeline.json").write_text(json.dumps({"segments": []}))
            with patch.object(pipeline, "RAIZ", base), patch.object(pipeline.shutil, "which", return_value="ffprobe"), patch("timeline_clipe.validar", return_value=["lacuna na timeline"]):
                result = pipeline.preflight("demo")
            self.assertFalse(result["aprovado"])
            self.assertIn("lacuna na timeline", result["erros"])
            self.assertIn("cenas-auto", result["etapas"])
            self.assertIn("manga-auto", result["etapas"])
            self.assertIn("graficos-auto", result["etapas"])
            self.assertLess(result["etapas"].index("cenas-auto"), result["etapas"].index("manga-auto"))
            self.assertLess(result["etapas"].index("manga-auto"), result["etapas"].index("graficos-auto"))
            self.assertNotIn("semantica", result["etapas"])

    def test_failure_releases_lock_and_records_failed_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            report = {"aprovado": True, "erros": [], "saida": str(p / "out.mp4")}
            with patch.object(pipeline, "preflight", return_value=report), patch.object(pipeline, "projeto", return_value=p), patch.object(rd, "video_args", return_value=[]), patch.object(pipeline.vx_runner, "executar", side_effect=RuntimeError("falha simulada")):
                with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                    pipeline.executar_esteira_completa("demo")
            self.assertFalse((p / ".esteira.lock").exists())
            records = list((p / "qa/esteira").glob("*/execucao.json"))
            self.assertEqual(len(records), 1)
            state = json.loads(records[0].read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "falhou")
            self.assertEqual(state["etapas"][0]["status"], "falhou")
            self.assertIn("saidas", state["saida"])

    def test_existing_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / ".esteira.lock").write_text("another process")
            with patch.object(pipeline, "preflight", return_value={"aprovado": True}), patch.object(pipeline, "projeto", return_value=p), patch.object(rd, "video_args", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "bloqueada"):
                    pipeline.executar_esteira_completa("demo")
            self.assertEqual((p / ".esteira.lock").read_text(), "another process")
