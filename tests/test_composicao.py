"""Fase 2b: timeline recomposta da base limpa + ComfyUI sob demanda."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ferramentas"))

from vx import composicao
import gerador_imagem_local as gil

BASE = {"segments": [{"type": "lyric", "start": 0, "end": 2, "clip": "a.mp4", "src": 0}]}
COMPOSTA = {"segments": [{"type": "vx_graphics_auto", "start": 0, "end": 2, "clip": "g.mp4", "src": 0}]}


def _proj(tmp):
    p = Path(tmp) / "p"
    (p / "qa").mkdir(parents=True)
    (p / "letra_sincronizada.json").write_text('[{"text": "a"}]', encoding="utf-8")
    (p / "timeline.json").write_text(json.dumps(BASE), encoding="utf-8")
    return p


class ComposicaoTests(unittest.TestCase):
    def test_recompose_restores_base_and_archives_stage_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _proj(tmp)
            composicao.registrar_base(p)
            (p / "timeline.json").write_text(json.dumps(COMPOSTA), encoding="utf-8")
            composicao.registrar_composicao(p)
            (p / "qa/vx_graphics_auto").mkdir(parents=True)
            (p / "qa/vx_graphics_auto/state.json").write_text('{"applied_hash": "x"}')
            info = composicao.recompor(p, Path(tmp) / "bk")
            self.assertEqual(json.loads((p / "timeline.json").read_text()), BASE)
            self.assertFalse((p / "qa/vx_graphics_auto/state.json").exists())
            self.assertIn("qa/vx_graphics_auto/state.json", info["estados_arquivados"])
            self.assertIsNone(info["timeline_externa_arquivada"])  # era a composicao da esteira

    def test_externally_edited_timeline_is_backed_up_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _proj(tmp)
            composicao.registrar_base(p)
            editada = {"segments": [{"type": "lyric", "start": 0, "end": 2, "clip": "manual.mp4", "src": 3}]}
            (p / "timeline.json").write_text(json.dumps(editada), encoding="utf-8")
            info = composicao.recompor(p, Path(tmp) / "bk")
            copia = Path(info["timeline_externa_arquivada"])
            self.assertEqual(json.loads(copia.read_text()), editada)

    def test_changed_synced_lyrics_marks_base_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _proj(tmp)
            composicao.registrar_base(p)
            self.assertFalse(composicao.base_desatualizada(p))
            (p / "letra_sincronizada.json").write_text('[{"text": "nova letra"}]', encoding="utf-8")
            self.assertTrue(composicao.base_desatualizada(p))

    def test_legacy_project_adopts_clean_base_from_matcher_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _proj(tmp)
            (p / "timeline.json").write_text(json.dumps(COMPOSTA), encoding="utf-8")
            (p / "qa/scene_matcher").mkdir(parents=True)
            (p / "qa/scene_matcher/state.json").write_text(json.dumps({"base_timeline": BASE}))
            info = composicao.recompor(p, Path(tmp) / "bk")
            self.assertEqual(info["modo"], "recomposto")
            self.assertIn("scene_matcher", info["base_adotada"])
            self.assertEqual(json.loads((p / "timeline.json").read_text()), BASE)

    def test_legacy_project_without_clean_base_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _proj(tmp)
            (p / "timeline.json").write_text(json.dumps(COMPOSTA), encoding="utf-8")
            info = composicao.recompor(p, Path(tmp) / "bk")
            self.assertEqual(info["modo"], "legado")
            self.assertEqual(json.loads((p / "timeline.json").read_text()), COMPOSTA)


class ComfySobDemandaTests(unittest.TestCase):
    def test_cached_images_never_start_comfy(self):
        with patch.object(gil, "garantir_comfy") as garantir, patch.object(gil, "parar_comfy") as parar:
            with gil.sessao_comfy() as s:
                pass  # nenhuma imagem precisou ser gerada
            garantir.assert_not_called()
            parar.assert_not_called()
            self.assertFalse(s["usou_comfy"])

    def test_comfy_started_by_us_is_stopped_on_exit(self):
        with patch.object(gil, "parar_comfy") as parar, \
             patch.object(gil, "ComfyClient") as cliente:
            with gil.sessao_comfy() as s:
                gil._registrar_sessao({"online": True, "iniciado_por_nos": True})
            self.assertTrue(s["usou_comfy"])
            parar.assert_called_once()
            cliente.return_value.liberar_vram.assert_called_once()

    def test_comfy_already_running_is_not_stopped(self):
        with patch.object(gil, "parar_comfy") as parar, patch.object(gil, "ComfyClient"):
            with gil.sessao_comfy():
                gil._registrar_sessao({"online": True, "iniciado_por_nos": False})
            parar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
