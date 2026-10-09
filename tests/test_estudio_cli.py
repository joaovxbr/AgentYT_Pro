from __future__ import annotations

import ast
import builtins
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ESTUDIO = ROOT / "ferramentas" / "estudio.py"


class EstudioCliTests(unittest.TestCase):
    def test_nomes_de_modulo_usados_estao_definidos(self):
        """Pega regressao tipo 'textoback' chamando txt_mod nunca importado."""
        arvore = ast.parse(ESTUDIO.read_text(encoding="utf-8"))
        definidos = set(dir(builtins))
        for no in ast.walk(arvore):
            if isinstance(no, (ast.Import, ast.ImportFrom)):
                definidos.update((a.asname or a.name).split(".")[0] for a in no.names)
            elif isinstance(no, (ast.FunctionDef, ast.ClassDef)):
                definidos.add(no.name)
            elif isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store):
                definidos.add(no.id)
            elif isinstance(no, ast.arg):
                definidos.add(no.arg)
        usados = {n.id for n in ast.walk(arvore)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id.endswith("_mod")}
        self.assertEqual(usados - definidos, set())

    def test_todo_dispatch_tem_parser(self):
        fonte = ESTUDIO.read_text(encoding="utf-8")
        parsers = set(re.findall(r'add_parser\(\s*"([^"]+)"', fonte))
        dispatch = set(re.findall(r'a\.cmd\s*==\s*"([^"]+)"', fonte))
        for grupo in re.findall(r'a\.cmd\s+in\s+\(([^)]*)\)', fonte):
            dispatch.update(re.findall(r'"([^"]+)"', grupo))
        self.assertEqual(dispatch - parsers, set())

    def test_help_lista_portas_de_imagem(self):
        out = subprocess.run([sys.executable, str(ESTUDIO), "-h"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        for cmd in ("gerar-imagem", "comfy-status", "capa-ia"):
            self.assertIn(cmd, out.stdout)


if __name__ == "__main__":
    unittest.main()
