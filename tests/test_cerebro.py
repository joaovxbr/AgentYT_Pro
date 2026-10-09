"""Fase 4: o cerebro nao pode mentir sobre o codigo.

- todo caminho de arquivo citado em cerebro/*.md e AGENTS.md existe;
- todo `estudio.py <comando>` citado existe no parser;
- todo ferramentas/*.py esta no catalogo cerebro/modulos.md (modulo novo precisa ser documentado);
- o catalogo nao cita modulo que nao existe mais.
cerebro/historico/ e excluido: e registro do passado, pode citar coisas removidas.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CEREBRO = ROOT / "cerebro"
PREFIXOS = ("ferramentas/", "vx/", "config/", "cerebro/", "assets/", "tests/")


def _docs():
    docs = [ROOT / "AGENTS.md"]
    docs += [p for p in CEREBRO.rglob("*.md") if "historico" not in p.parts]
    return docs


def _caminhos_citados(texto: str):
    for trecho in re.findall(r"`([^`\n]+)`", texto):
        trecho = trecho.strip().replace("\\", "/")
        if trecho.startswith(PREFIXOS) and not any(c in trecho for c in "<>*{} "):
            yield trecho.split(":")[0].split("#")[0].rstrip("/")


class CerebroTests(unittest.TestCase):
    def test_cited_paths_exist(self):
        faltando = []
        for doc in _docs():
            for rel in _caminhos_citados(doc.read_text(encoding="utf-8")):
                if not (ROOT / rel).exists():
                    faltando.append(f"{doc.relative_to(ROOT)} -> {rel}")
        self.assertEqual(faltando, [], "cerebro cita arquivo inexistente")

    def test_cited_commands_exist(self):
        fonte = (ROOT / "ferramentas" / "estudio.py").read_text(encoding="utf-8")
        parsers = set(re.findall(r'add_parser\(\s*"([^"]+)"', fonte))
        faltando = []
        for doc in _docs():
            for cmd in re.findall(r"estudio\.py\s+([a-z][a-z0-9-]+)", doc.read_text(encoding="utf-8")):
                if cmd not in parsers:
                    faltando.append(f"{doc.relative_to(ROOT)} -> estudio.py {cmd}")
        self.assertEqual(sorted(set(faltando)), [], "cerebro cita comando inexistente")

    def test_every_tool_module_is_cataloged(self):
        catalogo = (CEREBRO / "modulos.md").read_text(encoding="utf-8")
        citados = set(re.findall(r"`([A-Za-z0-9_]+)\.py`", catalogo))
        existentes = {p.stem for p in (ROOT / "ferramentas").glob("*.py")}
        self.assertEqual(sorted(existentes - citados - {"_vx"}), [],
                         "modulo sem entrada em cerebro/modulos.md")

    def test_catalog_has_no_ghost_modules(self):
        catalogo = (CEREBRO / "modulos.md").read_text(encoding="utf-8")
        existentes = {p.stem for p in (ROOT / "ferramentas").glob("*.py")} | \
                     {p.stem for p in (ROOT / "vx").glob("*.py")}
        fantasmas = [m for m in set(re.findall(r"`(?:vx/|ferramentas/)?([A-Za-z0-9_]+)\.py`", catalogo))
                     if m not in existentes]
        self.assertEqual(sorted(fantasmas), [], "catalogo cita modulo que nao existe")

    def test_module_template_is_valid_python(self):
        texto = (CEREBRO / "novo_modulo.md").read_text(encoding="utf-8")
        blocos = re.findall(r"```python\n(.*?)```", texto, flags=re.S)
        self.assertTrue(blocos, "cerebro/novo_modulo.md sem modelo de codigo")
        for bloco in blocos:
            compile(bloco, "novo_modulo.md", "exec")

    def test_single_pinned_requirements_file(self):
        self.assertFalse((ROOT / "ferramentas" / "requirements.txt").exists(),
                         "requirements unico e requerimentos.txt na raiz")
        linhas = [l.split("#")[0].strip() for l in
                  (ROOT / "requerimentos.txt").read_text(encoding="utf-8").splitlines()]
        soltos = [l for l in linhas if l and "==" not in l]
        self.assertEqual(soltos, [], "dependencia sem versao fixada")

    def test_agents_md_is_an_index(self):
        linhas = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        self.assertLess(len(linhas), 80, "AGENTS.md deve continuar um indice curto; conteudo vai no cerebro/")


if __name__ == "__main__":
    unittest.main()
