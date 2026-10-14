"""Testes do sistema de Color Grading Profissional por Arquétipo."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import color_grade_pro as cgp


class ColorGradeProTests(unittest.TestCase):
    def test_receitas_essenciais_existem(self):
        chaves = {"cursed_energy", "titan_fire", "dark_shadow", "demon_blood", "cinematic_clean"}
        self.assertTrue(chaves.issubset(set(cgp.RECEITAS_COLOR_GRADE.keys())))

    def test_resolver_arquetipo_por_anime_e_personagem(self):
        self.assertEqual(cgp.resolver_arquetipo(anime="Jujutsu Kaisen"), "cursed_energy")
        self.assertEqual(cgp.resolver_arquetipo(personagem="Ryomen Sukuna"), "cursed_energy")
        self.assertEqual(cgp.resolver_arquetipo(anime="O Rei das Maldições"), "cursed_energy")
        self.assertEqual(cgp.resolver_arquetipo(anime="Attack on Titan"), "titan_fire")
        self.assertEqual(cgp.resolver_arquetipo(personagem="Eren Yeager"), "titan_fire")
        self.assertEqual(cgp.resolver_arquetipo(anime="Solo Leveling"), "dark_shadow")
        self.assertEqual(cgp.resolver_arquetipo(personagem="Sung Jin-Woo"), "dark_shadow")
        self.assertEqual(cgp.resolver_arquetipo(anime="Demon Slayer"), "demon_blood")
        self.assertEqual(cgp.resolver_arquetipo(personagem="Akaza"), "demon_blood")
        self.assertEqual(cgp.resolver_arquetipo(personagem="Muzan"), "demon_blood")
        self.assertEqual(cgp.resolver_arquetipo(personagem="Muzán"), "demon_blood")

    def test_resolver_arquetipo_fallback_e_override(self):
        self.assertEqual(cgp.resolver_arquetipo(override="cursed_energy"), "cursed_energy")
        self.assertEqual(cgp.resolver_arquetipo(anime="Desconhecido"), "cinematic_clean")
        self.assertEqual(cgp.resolver_arquetipo(), "cinematic_clean")

    def test_obter_filtro_color_grade_com_lift_seguro(self):
        filtro = cgp.obter_filtro_color_grade("cursed_energy", lift_seguro=True)
        self.assertIn("eq=", filtro)
        self.assertIn("curves=", filtro)
        self.assertIn("vignette=", filtro)
        self.assertIn("gamma=", filtro)

    def test_obter_filtro_color_grade_sem_lift(self):
        filtro = cgp.obter_filtro_color_grade("titan_fire", lift_seguro=False)
        self.assertIn("eq=", filtro)
        self.assertIn("curves=", filtro)
        self.assertIn("vignette=", filtro)
        self.assertNotIn("gamma=", filtro)

    def test_estilo_invalido_usa_fallback(self):
        filtro = cgp.obter_filtro_color_grade("inexistente")
        self.assertTrue(len(filtro) > 0)


if __name__ == "__main__":
    unittest.main()
