"""Testes do filtro e efeito Color Splash Seletivo."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import color_splash as cs
import filtros


class ColorSplashTests(unittest.TestCase):
    def test_gerar_filtro_color_splash_contem_chromahold_e_eq(self):
        f = cs.gerar_filtro_color_splash("vermelho", t_inicio=1.0, duracao=2.5)
        self.assertIn("chromahold=", f)
        self.assertIn("eq=contrast=", f)
        self.assertIn("between(t,1.000,3.500)", f)

    def test_cores_suportadas(self):
        for cor in ("vermelho", "carmesim", "azul_ciano", "verde", "amarelo", "roxo"):
            f = cs.gerar_filtro_color_splash(cor)
            self.assertIn("chromahold=", f)

    def test_case_insensitive_e_espacos(self):
        f1 = cs.gerar_filtro_color_splash(" Vermelho ")
        f2 = cs.gerar_filtro_color_splash("AZUL_CIANO")
        self.assertIn("color=red", f1)
        self.assertIn("color=0x00D0FF", f2)

    def test_catalogo_filtros_contem_color_splash(self):
        self.assertIn("color_splash", filtros.CATALOGO)
        self.assertIn("climax", filtros.RECEITAS)
        self.assertIn("color_splash", filtros.RECEITAS["climax"])


if __name__ == "__main__":
    unittest.main()
