"""Testes das transições Snap Impact com Flash Pop e Zoom Punch."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import snap_impact_transition as sit
import motion_match_director as mm
import render_clipe


class SnapImpactTransitionTests(unittest.TestCase):
    def test_gerar_filtro_snap_impact_estrutura(self):
        filtro = sit.gerar_filtro_snap_impact(16.0, duracao_zoom=0.35, duracao_flash=0.10)
        self.assertIn("16", filtro)
        self.assertIn("scale=", filtro)
        self.assertIn("crop=", filtro)
        self.assertIn("brightness=", filtro)

    def test_transicao_snap_impact_em_render_clipe(self):
        s = {"start": 20.0, "end": 23.0}
        sh = {
            "transition_in": {"type": "snap_impact", "duration": 0.12, "strength": 0.75},
            "transition_out": {"type": "snap_impact", "duration": 0.08, "strength": 0.60},
        }
        filtros_borda = render_clipe._filtros_transicao(sh, s, 20.0, 23.0)
        self.assertTrue(any("eq=brightness" in f for f in filtros_borda))
        self.assertTrue(any("rgbashift" in f for f in filtros_borda))
        self.assertTrue(any("gblur" in f for f in filtros_borda))

        # No meio do clipe (fora da borda), não deve ativar
        filtros_meio = render_clipe._filtros_transicao(sh, s, 20.5, 22.5)
        self.assertEqual(filtros_meio, [])

    def test_decidir_transicao_com_drop_de_grave(self):
        a = {
            "start": 10.0, "end": 12.0, "preset": "narrativo", "type": "lyric",
            "scene_match": {"motion_direction": "left", "scene_intensity": 0.72, "scene_tags": ["fight"]},
        }
        b = {
            "start": 12.0, "end": 14.0, "preset": "impacto", "type": "lyric",
            "scene_match": {"motion_direction": "right", "scene_intensity": 0.85, "scene_tags": ["impact"]},
        }
        # Drop de grave exatamente no corte (12.0s) como float
        tr = mm.decidir_transicao(a, b, last_fx_time=0.0, drops_grave=[12.02])
        self.assertEqual(tr["type"], "snap_impact")
        self.assertEqual(tr["reason"], "bass_drop_808")
        self.assertGreaterEqual(tr["strength"], 0.70)

        # Drop de grave vindo como lista de dicts (saida de bass_shake.extrair_picos_subgrave)
        eventos = [{"tempo": 12.01, "intensidade": 0.9, "duracao": 0.16}]
        tr_dict = mm.decidir_transicao(a, b, last_fx_time=0.0, drops_grave=eventos)
        self.assertEqual(tr_dict["type"], "snap_impact")
        self.assertEqual(tr_dict["reason"], "bass_drop_808")


if __name__ == "__main__":
    unittest.main()
