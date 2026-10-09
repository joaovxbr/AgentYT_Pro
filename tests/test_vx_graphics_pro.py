from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

from audio_reactive_fx import pulso_no_tempo
from creative_impact_director import identificar_palavra_dominante
from kinetic_typography import render_texto_cinetico
from style_preset_engine import (
    candidatos_semanticos,
    carregar_presets,
    listar_catalogo,
    montar_spec_design,
)


class VXGraphicsPresetTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "personagem": "Sasuke Uchiha",
            "faixa": "VINGADOR",
            "cor": {"destaque": "#7B1FA2", "destaque_claro": "#00E5FF"},
        }

    def test_semantic_blood_selects_blood_burn(self):
        spec = montar_spec_design("SANGUE", "sasuke", self.manifest)
        self.assertEqual(spec["theme"], "sasuke")
        self.assertEqual(spec["preset"], "blood_burn")
        self.assertEqual(spec["background"], "blood_eclipse")

    def test_destruction_selects_manga_brutal(self):
        spec = montar_spec_design("DESTRUIÇÃO", "sasuke", self.manifest)
        self.assertEqual(spec["preset"], "manga_brutal_pro")

    def test_recent_preset_is_avoided(self):
        spec = montar_spec_design(
            "SANGUE", "sasuke", self.manifest,
            presets_recentes=("blood_burn",))
        self.assertNotEqual(spec["preset"], "blood_burn")

    def test_accented_semantics_reach_creative_director(self):
        hierarchy = identificar_palavra_dominante("carrego ÓDIO no olhar")
        self.assertEqual(hierarchy["primary"], "ÓDIO")

    def test_short_words_do_not_match_by_substring(self):
        self.assertEqual(candidatos_semanticos("A"), [])
        self.assertEqual(candidatos_semanticos("EU"), [])

    def test_fire_has_dedicated_preset(self):
        spec = montar_spec_design("FOGO", "sasuke", self.manifest)
        self.assertEqual(spec["preset"], "fire_burst")
        self.assertEqual(spec["background"], "fire_smoke")

    def test_character_name_selects_write_on(self):
        spec = montar_spec_design("SASUKE", "sasuke", self.manifest)
        self.assertEqual(spec["preset"], "neon_write_on")
        self.assertEqual(spec["style"]["animation"], "write_on")

    def test_character_name_rotates_write_styles(self):
        second = montar_spec_design(
            "SASUKE", "sasuke", self.manifest,
            presets_recentes=("neon_write_on",))
        self.assertEqual(second["preset"], "neon_letter_reveal")
        third = montar_spec_design(
            "SASUKE", "sasuke", self.manifest,
            presets_recentes=("neon_write_on", "neon_letter_reveal"))
        self.assertEqual(third["preset"], "neon_outline_fill")
        fourth = montar_spec_design(
            "SASUKE", "sasuke", self.manifest,
            presets_recentes=("neon_write_on", "neon_letter_reveal", "neon_outline_fill"))
        self.assertEqual(fourth["preset"], "neon_trace")

    def test_write_on_reveals_progressively(self):
        spec = montar_spec_design("SASUKE", "sasuke", self.manifest, preset="neon_write_on")
        font = "C:/Windows/Fonts/impact.ttf"
        early, _ = render_texto_cinetico(
            "SASUKE", font, spec["style"], spec["theme_config"],
            0.18, 5, 0.9, (960, 540), "hero_center")
        late, _ = render_texto_cinetico(
            "SASUKE", font, spec["style"], spec["theme_config"],
            0.90, 25, 0.9, (960, 540), "hero_center")
        early_alpha = sum(early.getchannel("A").histogram()[21:])
        late_alpha = sum(late.getchannel("A").histogram()[21:])
        self.assertGreater(late_alpha, early_alpha * 1.4)

    def test_letter_and_outline_modes_render(self):
        font = "C:/Windows/Fonts/impact.ttf"
        for preset in ("neon_letter_reveal", "neon_outline_fill", "neon_trace"):
            spec = montar_spec_design("SASUKE", "sasuke", self.manifest, preset=preset)
            early, _ = render_texto_cinetico(
                "SASUKE", font, spec["style"], spec["theme_config"],
                0.15, 4, 0.9, (960, 540), "hero_center")
            late, _ = render_texto_cinetico(
                "SASUKE", font, spec["style"], spec["theme_config"],
                0.90, 25, 0.9, (960, 540), "hero_center")
            self.assertGreater(sum(late.getchannel("A").histogram()[21:]),
                               sum(early.getchannel("A").histogram()[21:]))

    def test_real_beat_envelope_peaks_at_event(self):
        events = [{"tempo": 0.5, "intensidade": 1.0, "duracao": 0.16}]
        self.assertGreater(pulso_no_tempo(events, 0.5), 0.95)
        self.assertEqual(pulso_no_tempo(events, 0.1), 0.0)

    def test_catalog_configs_are_complete(self):
        presets = carregar_presets()
        self.assertGreaterEqual(len(presets), 6)
        for name, cfg in presets.items():
            self.assertIn("background", cfg, name)
            self.assertIn("animation", cfg, name)
            self.assertIn("layouts", cfg, name)
        catalog = listar_catalogo()
        self.assertIn("sasuke", catalog["themes"])
        self.assertIn("energy_ring", catalog["layouts"])


if __name__ == "__main__":
    unittest.main()
