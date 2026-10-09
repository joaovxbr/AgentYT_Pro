"""Fase 1 (fundacao): ambiente, lock com PID e porteiros que nao aprovam sem medir."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ferramentas"))

from vx import ambiente, lock as vx_lock
import audio
import legenda


class AmbienteTests(unittest.TestCase):
    def test_bin_dir_is_prepended_once(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PATH": "C:\\outro"}):
            self.assertTrue(ambiente.garantir_path(Path(tmp)))
            self.assertTrue(os.environ["PATH"].startswith(tmp))
            self.assertFalse(ambiente.garantir_path(Path(tmp)))  # idempotente
            self.assertEqual(os.environ["PATH"].count(tmp), 1)

    def test_missing_bin_dir_changes_nothing(self):
        with patch.dict(os.environ, {"PATH": "C:\\outro"}):
            self.assertFalse(ambiente.garantir_path(Path("Z:/nao/existe")))
            self.assertEqual(os.environ["PATH"], "C:\\outro")


class LockTests(unittest.TestCase):
    def test_orphan_lock_from_dead_pid_is_reclaimed(self):
        morto = subprocess.Popen([sys.executable, "-c", "pass"])
        morto.wait()
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / ".esteira.lock"
            lock.write_text(json.dumps({"pid": morto.pid, "run_id": "velho"}))
            info = vx_lock.adquirir(lock, "novo")
            self.assertEqual(info["lock_orfao_removido"]["run_id"], "velho")
            self.assertEqual(json.loads(lock.read_text())["run_id"], "novo")
            vx_lock.liberar(lock, "novo")
            self.assertFalse(lock.exists())

    def test_live_lock_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / ".esteira.lock"
            lock.write_text(json.dumps({"pid": os.getpid(), "run_id": "vivo"}))
            with self.assertRaisesRegex(RuntimeError, "bloqueada"):
                vx_lock.adquirir(lock, "novo")
            self.assertEqual(json.loads(lock.read_text())["run_id"], "vivo")

    def test_unreadable_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / ".esteira.lock"
            lock.write_text("formato estranho")
            with self.assertRaises(vx_lock.LockOcupado):
                vx_lock.adquirir(lock, "novo")
            self.assertEqual(lock.read_text(), "formato estranho")

    def test_release_only_removes_own_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / ".esteira.lock"
            lock.write_text(json.dumps({"pid": os.getpid(), "run_id": "outro"}))
            vx_lock.liberar(lock, "meu")
            self.assertTrue(lock.exists())


class AudioGateTests(unittest.TestCase):
    def _analisar(self, loudness):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "m.mp4"
            f.write_bytes(b"x")
            with patch.object(audio, "_medir_loudness", return_value=loudness), \
                 patch.object(audio, "_medir_sample_rate", return_value=48000), \
                 patch.object(audio, "_medir_clareza_vocal", return_value=0.5), \
                 patch.object(audio.subprocess, "run", return_value=SimpleNamespace(stdout="10\n")):
                return audio.analisar(f)

    def test_failed_measurement_is_rejected_not_approved(self):
        rel = self._analisar(audio.MEDICAO_FALHOU)
        self.assertFalse(rel.aprovado)
        self.assertTrue(any("medicao" in m for m in rel.motivos))

    def test_valid_measurement_still_approves(self):
        rel = self._analisar((-14.0, 5.0, -1.8))
        self.assertTrue(rel.aprovado, rel.motivos)


class LegendaVozTests(unittest.TestCase):
    def test_subtitle_over_vocal_silence_is_flagged(self):
        # voz em 0-10 s, silencio em 10-20 s; uma linha exibida no silencio
        energia = [(i * 0.5, -18.0 if i * 0.5 < 10 else -70.0) for i in range(40)]
        eventos = [(2.0, 5.0, "linha certa"), (12.0, 15.0, "linha no silencio")]
        ruins = legenda.eventos_sobre_silencio(eventos, energia)
        self.assertEqual([x["texto"] for x in ruins], ["linha no silencio"])

    def test_synced_subtitles_pass(self):
        energia = [(i * 0.5, -18.0) for i in range(40)]
        eventos = [(1.0, 4.0, "a"), (5.0, 9.0, "b")]
        self.assertEqual(legenda.eventos_sobre_silencio(eventos, energia), [])


if __name__ == "__main__":
    unittest.main()
