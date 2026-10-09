"""Contrato de `vx/cache.py` — reaproveitar trabalho ENTRE execucoes.

O que este teste protege -- e o que NAO pode regredir:

1. cache e checkpoint sao coisas diferentes: o cache sobrevive ao `run_id`.
2. falha fechada: na duvida RODA. Reaproveitar errado = video errado em silencio.
3. as 6 etapas de composicao e as 3 de master NAO sao cacheaveis -- elas editam a
   timeline sobre a base limpa a cada esteira (vx/composicao.py) ou escrevem em
   `saidas/esteira/<run_id>/`, que e da execucao atual.
4. o cache nunca derruba a esteira: ler e gravar engolem erro de I/O.
5. `hash_obj` e canonico (mesmo dado -> mesmo hash) e aceita `Path`/`datetime`.
6. a poda mantem o registro limitado sem perder o que interessa.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))
sys.path.insert(0, str(ROOT))

from vx import cache as cx  # noqa: E402
from vx import etapas as et  # noqa: E402


def _projeto(base: Path, slug: str = "demo") -> Path:
    """Projeto minimo com entradas e saidas de `stems` de verdade no disco."""
    p = base / slug
    (p / "entradas" / "stems").mkdir(parents=True)
    (p / "entradas" / f"{slug}_normalizado.wav").write_bytes(b"audio" * 100)
    for tipo in ("vocals", "drums", "bass", "other"):
        (p / "entradas" / "stems" / f"{slug}_normalizado_{tipo}.wav").write_bytes(b"s" * 50)
    return p


class ReaproveitarTest(unittest.TestCase):
    def _le_escreve(self):
        e = et.POR_NOME["stems"]
        return e.le, e.escreve

    def test_cache_vazio_roda(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            d = cx.pode_reaproveitar("stems", le, escreve, p, "demo")
            self.assertFalse(d.reaproveitar)
            self.assertIn("cache vazio", d.motivo)

    def test_reaproveita_em_execucao_diferente(self):
        """O cache nao mora no run_id -- e isso que o distingue do checkpoint."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            cx.registrar("stems", le, escreve, p, "demo")
            # nenhuma pasta qa/esteira/<run_id>/ existe; mesmo assim reaproveita
            d = cx.pode_reaproveitar("stems", le, escreve, p, "demo")
            self.assertTrue(d.reaproveitar, d.motivo)
            self.assertGreater(d.bytes, 0)
            self.assertTrue(d.saidas)

    def test_entrada_mudou_roda(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            cx.registrar("stems", le, escreve, p, "demo")
            (p / "entradas" / "demo_normalizado.wav").write_bytes(b"audio NOVO" * 100)
            d = cx.pode_reaproveitar("stems", le, escreve, p, "demo")
            self.assertFalse(d.reaproveitar)
            self.assertIn("mudaram", d.motivo)

    def test_voltar_a_entrada_antiga_volta_a_reaproveitar(self):
        """O cache guarda VARIACOES: alternar entre duas versoes nao recomeca tudo."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            original = (p / "entradas" / "demo_normalizado.wav").read_bytes()
            cx.registrar("stems", le, escreve, p, "demo")

            (p / "entradas" / "demo_normalizado.wav").write_bytes(b"outra" * 300)
            self.assertFalse(cx.pode_reaproveitar("stems", le, escreve, p, "demo").reaproveitar)

            (p / "entradas" / "demo_normalizado.wav").write_bytes(original)
            self.assertTrue(cx.pode_reaproveitar("stems", le, escreve, p, "demo").reaproveitar)

    def test_saida_apagada_derruba_o_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            cx.registrar("stems", le, escreve, p, "demo")
            (p / "entradas" / "stems" / "demo_normalizado_vocals.wav").unlink()
            d = cx.pode_reaproveitar("stems", le, escreve, p, "demo")
            self.assertFalse(d.reaproveitar)
            self.assertIn("ausente", d.motivo)

    def test_saida_esvaziada_derruba_o_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            cx.registrar("stems", le, escreve, p, "demo")
            (p / "entradas" / "stems" / "demo_normalizado_drums.wav").write_bytes(b"")
            self.assertFalse(cx.pode_reaproveitar("stems", le, escreve, p, "demo").reaproveitar)

    def test_saida_registrada_apagada_derruba_mesmo_com_glob_ok(self):
        """`escreve` de algumas etapas e glob -- o registro e a prova mais forte."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            # etapa real com saida em glob cujo arquivo foi registrado
            (p / "clips_raw" / "vx_x").mkdir(parents=True)
            (p / "clips_raw" / "vx_x" / "take.mp4").write_bytes(b"v" * 30)
            le = ("entradas/{slug}_normalizado.wav",)
            escreve = ("clips_raw/vx_x/*",)
            cx.registrar("x", le, escreve, p, "demo")
            self.assertTrue(cx.pode_reaproveitar("x", le, escreve, p, "demo").reaproveitar)
            (p / "clips_raw" / "vx_x" / "take.mp4").unlink()
            d = cx.pode_reaproveitar("x", le, escreve, p, "demo")
            self.assertFalse(d.reaproveitar)
            self.assertIn("apagada", d.motivo)

    def test_registro_corrompido_roda(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            caminho = cx.cache_dir(p) / "stems.json"
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text("{ corrompido", encoding="utf-8")
            self.assertFalse(cx.pode_reaproveitar("stems", le, escreve, p, "demo").reaproveitar)

    def test_registro_com_estrutura_errada_roda(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            caminho = cx.cache_dir(p) / "stems.json"
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(json.dumps({"etapa": "stems", "entradas": "nao e dict"}),
                               encoding="utf-8")
            self.assertFalse(cx.pode_reaproveitar("stems", le, escreve, p, "demo").reaproveitar)

    def test_hash_impossivel_roda(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            le, escreve = self._le_escreve()
            cx.registrar("stems", le, escreve, p, "demo")
            with patch.object(cx._checkpoint, "hash_entradas", side_effect=OSError("disco")):
                d = cx.pode_reaproveitar("stems", le, escreve, p, "demo")
            self.assertFalse(d.reaproveitar)


class PersistenciaTest(unittest.TestCase):
    def test_gravar_nunca_levanta(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            with patch.object(Path, "write_text", side_effect=OSError("disco cheio")):
                self.assertIsNone(cx.gravar(p, "stems", {"etapa": "stems", "entradas": {}}))

    def test_registrar_devolve_false_em_falha_de_escrita(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            e = et.POR_NOME["stems"]
            with patch.object(Path, "write_text", side_effect=OSError("cheio")):
                self.assertFalse(cx.registrar("stems", e.le, e.escreve, p, "demo"))

    def test_nao_guarda_conteudo_so_metadados(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            e = et.POR_NOME["stems"]
            cx.registrar("stems", e.le, e.escreve, p, "demo")
            texto = (cx.cache_dir(p) / "stems.json").read_text(encoding="utf-8")
            self.assertNotIn("audio", texto)
            self.assertIn("bytes", texto)

    def test_nome_de_etapa_nao_escapa_do_diretorio(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            cx.gravar(p, "../../etc/passwd", {"entradas": {}})
            escritos = list(cx.cache_dir(p).glob("*.json"))
            self.assertEqual(len(escritos), 1)
            self.assertTrue(escritos[0].parent == cx.cache_dir(p))

    def test_poda_mantem_limite(self):
        entradas = {f"h{i}": {"criado_em": f"2026-01-{i+1:02d}", "usos": i, "bytes": 1}
                    for i in range(20)}
        podado = cx._podar(entradas, limite=5)
        self.assertEqual(len(podado), 5)
        # mantem as mais recentes, nao as mais antigas
        self.assertIn("h19", podado)
        self.assertNotIn("h0", podado)

    def test_registrar_muitas_variacoes_nao_cresce_sem_limite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            e = et.POR_NOME["stems"]
            for i in range(cx.LIMITE_POR_ETAPA + 4):
                (p / "entradas" / "demo_normalizado.wav").write_bytes(b"v" * (10 + i * 3))
                cx.registrar("stems", e.le, e.escreve, p, "demo")
            dados = cx.carregar(p, "stems")
            self.assertLessEqual(len(dados["entradas"]), cx.LIMITE_POR_ETAPA)


class HashObjTest(unittest.TestCase):
    def test_mesmo_dado_mesmo_hash_independente_da_ordem(self):
        self.assertEqual(cx.hash_obj({"b": 1, "a": 2}), cx.hash_obj({"a": 2, "b": 1}))

    def test_dado_diferente_hash_diferente(self):
        self.assertNotEqual(cx.hash_obj({"a": 1}), cx.hash_obj({"a": 2}))

    def test_aceita_path_e_datetime(self):
        """Sem `default=str` isto explodiria -- era a divergencia entre as 6 copias."""
        h = cx.hash_obj({"p": Path("/x"), "t": datetime(2026, 1, 1, tzinfo=timezone.utc)})
        self.assertEqual(len(h), 64)
        int(h, 16)

    def test_devolve_sha256_hex(self):
        self.assertEqual(len(cx.hash_obj({"a": 1})), 64)


class EtapasCacheaveisTest(unittest.TestCase):
    def test_composicao_nao_e_cacheavel(self):
        """Estas editam timeline.json sobre a base limpa: cachear brigaria com vx/composicao.py."""
        for nome in ("cenas-auto", "chroma-auto", "cenas-ia", "titulos",
                     "manga-auto", "graficos-auto"):
            self.assertFalse(et.POR_NOME[nome].cacheavel, f"{nome} deveria ser nao-cacheavel")

    def test_master_nao_e_cacheavel(self):
        """Escrevem em saidas/esteira/<run_id>/, que e da execucao atual."""
        for nome in ("render-clipe", "intro", "qa-master"):
            self.assertFalse(et.POR_NOME[nome].cacheavel, f"{nome} deveria ser nao-cacheavel")

    def test_bootstrap_e_os_porteiros_sao_cacheaveis(self):
        for nome in ("stems", "transcrever", "sincronizar", "timeline",
                     "fonte-limpa", "auditar-letra", "planejar"):
            self.assertTrue(et.POR_NOME[nome].cacheavel, f"{nome} deveria ser cacheavel")

    def test_toda_etapa_cacheavel_tem_le(self):
        """Sem `le` nao existe hash de entrada -- o cache nunca acertaria."""
        for e in et.TODAS:
            if e.cacheavel:
                self.assertTrue(e.le, f"{e.nome} e cacheavel mas nao declara entradas")


class ResumoTest(unittest.TestCase):
    def test_resumo_conta_variacoes_e_usos(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            e = et.POR_NOME["stems"]
            cx.registrar("stems", e.le, e.escreve, p, "demo")
            cx.confirmar_uso("stems", e.le, p, "demo")
            cx.confirmar_uso("stems", e.le, p, "demo")
            r = cx.resumo(p)
            self.assertEqual(r["etapas"]["stems"]["variacoes"], 1)
            self.assertEqual(r["etapas"]["stems"]["usos"], 2)

    def test_confirmar_uso_de_entrada_desconhecida_nao_quebra(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            cx.confirmar_uso("inexistente", ("entradas/{slug}_normalizado.wav",), p, "demo")

    def test_projeto_sem_cache_resume_vazio(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = cx.resumo(Path(tmp))
            self.assertEqual(r["etapas"], {})
            self.assertEqual(r["total_variacoes"], 0)

    def test_invalidar_remove_so_a_etapa_pedida(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto(Path(tmp))
            e = et.POR_NOME["stems"]
            cx.registrar("stems", e.le, e.escreve, p, "demo")
            (p / "x.json").write_bytes(b"1")
            cx.registrar("outra", ("x.json",), ("x.json",), p, "demo")
            self.assertEqual(cx.invalidar(p, "stems"), 1)
            self.assertFalse((cx.cache_dir(p) / "stems.json").exists())
            self.assertTrue((cx.cache_dir(p) / "outra.json").exists())


if __name__ == "__main__":
    unittest.main()
