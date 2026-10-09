from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import transcrever as tr  # noqa: E402


class DllsCudaTests(unittest.TestCase):
    """Regressao: ctranslate2/faster-whisper no Windows precisa achar as DLLs
    CUDA (cublas64_12.dll) empacotadas no torch quando nao existe CUDA Toolkit
    global. `_garantir_dlls_cuda` deve carregar o torch (que registra as DLLs)
    ou, se o import falhar, apontar torch/lib via add_dll_directory."""

    def test_carrega_torch_quando_disponivel(self):
        with patch.dict(sys.modules, {"torch": types.ModuleType("torch")}):
            with patch("os.add_dll_directory") as add:
                tr._garantir_dlls_cuda()
                add.assert_not_called()  # torch presente: basta o import

    def test_fallback_add_dll_directory_sem_torch(self):
        if os.name != "nt":
            self.skipTest("comportamento so existe no Windows")
        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def fake_import(name, *a, **kw):
            if name == "torch":
                raise ImportError("torch indisponivel")
            return real_import(name, *a, **kw)

        with patch.dict(sys.modules, {"torch": None}):
            with patch("builtins.__import__", side_effect=fake_import):
                with patch("os.add_dll_directory") as add:
                    tr._garantir_dlls_cuda()
                    self.assertEqual(add.call_count, 1)
                    self.assertIn("torch", str(add.call_args[0][0]))

    def test_transcrever_garante_dlls_antes_do_modelo(self):
        """`transcrever` deve chamar o garante antes de instanciar o WhisperModel."""
        chamadas = []
        fake_fw = types.ModuleType("faster_whisper")

        class FakeModel:
            def __init__(self, *a, **kw):
                chamadas.append("modelo")

            def transcribe(self, *a, **kw):
                seg = types.SimpleNamespace(
                    start=0.0, end=1.0, text="oi",
                    words=[types.SimpleNamespace(word="oi", start=0.0, end=1.0)])
                info = types.SimpleNamespace(language="pt", duration=1.0)
                return [seg], info

        fake_fw.WhisperModel = FakeModel

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "a.wav"
            audio.write_bytes(b"RIFF0000")
            with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
                with patch.object(tr, "_garantir_dlls_cuda",
                                  side_effect=lambda: chamadas.append("dlls")):
                    dados = tr.transcrever(audio, Path(tmp) / "t.json", modelo="large-v3")
        self.assertEqual(chamadas[0], "dlls")
        self.assertIn("modelo", chamadas)
        self.assertEqual(len(dados["words"]), 1)


if __name__ == "__main__":
    unittest.main()
