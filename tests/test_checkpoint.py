"""Contrato de `vx/checkpoint.py` e do `--resume` da esteira.

O que este teste protege -- e o que NAO pode regredir:

1. falha fechada: na duvida, RODAR. Pular etapa a toa gera video errado em silencio
   (o erro caro); rodar a toa custa tempo (o erro barato).
2. so pula com prova tripla: etapa concluida + entradas iguais + saidas no lugar.
3. o checkpoint nao inventa o que e entrada -- quem manda e `le` de vx/etapas.py.
4. `--resume auto` acha o checkpoint mais recente; sem checkpoint, comeca novo.
5. escrever checkpoint nunca derruba a esteira.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))
sys.path.insert(0, str(ROOT))

from vx import checkpoint as ck  # noqa: E402
from vx import etapas as et  # noqa: E402


def _projeto_falso(base: Path, slug: str = "demo") -> Path:
    """Projeto minimo com entradas e saidas de `stems` de verdade no disco."""
    p = base / slug
    (p / "entradas" / "stems").mkdir(parents=True)
    (p / "entradas" / f"{slug}_normalizado.wav").write_bytes(b"audio" * 100)
    for tipo in ("vocals", "drums", "bass", "other"):
        (p / "entradas" / "stems" / f"{slug}_normalizado_{tipo}.wav").write_bytes(b"s" * 50)
    return p


class DecisaoTest(unittest.TestCase):
    def test_sem_registro_roda(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            d = cp.pode_pular("stems", e.le, e.escreve)
            self.assertFalse(d.pular)
            self.assertIn("sem registro", d.motivo)

    def test_etapa_concluida_com_entradas_iguais_e_saidas_no_lugar_pula(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            cp.registrar("stems", padroes_le=e.le, padroes_escreve=e.escreve)
            d = cp.pode_pular("stems", e.le, e.escreve)
            self.assertTrue(d.pular, d.motivo)

    def test_entrada_mudou_roda_de_novo(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            cp.registrar("stems", padroes_le=e.le, padroes_escreve=e.escreve)
            (p / "entradas" / "demo_normalizado.wav").write_bytes(b"audio NOVO" * 100)
            d = cp.pode_pular("stems", e.le, e.escreve)
            self.assertFalse(d.pular)
            self.assertIn("entradas mudaram", d.motivo)

    def test_saida_sumiu_roda_de_novo(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            cp.registrar("stems", padroes_le=e.le, padroes_escreve=e.escreve)
            (p / "entradas" / "stems" / "demo_normalizado_vocals.wav").unlink()
            d = cp.pode_pular("stems", e.le, e.escreve)
            self.assertFalse(d.pular)
            self.assertIn("saida ausente", d.motivo)

    def test_saida_vazia_conta_como_ausente(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            cp.registrar("stems", padroes_le=e.le, padroes_escreve=e.escreve)
            (p / "entradas" / "stems" / "demo_normalizado_drums.wav").write_bytes(b"")
            d = cp.pode_pular("stems", e.le, e.escreve)
            self.assertFalse(d.pular)

    def test_status_anterior_de_falha_roda(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            cp.registrar("stems", padroes_le=e.le, padroes_escreve=e.escreve, status="falhou")
            d = cp.pode_pular("stems", e.le, e.escreve)
            self.assertFalse(d.pular)
            self.assertIn("falhou", d.motivo)

    def test_sem_projeto_para_validar_falha_fechado(self):
        cp = ck.Checkpoint("r1")  # sem projeto
        e = et.POR_NOME["stems"]
        cp.etapas["stems"] = {"status": "concluido", "entradas_hash": "x"}
        d = cp.pode_pular("stems", e.le, e.escreve)
        self.assertFalse(d.pular)
        self.assertIn("sem projeto", d.motivo)


class PersistenciaTest(unittest.TestCase):
    def test_gravar_e_ler_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            caminho = p / "qa" / "esteira" / "run1" / ck.ARQ
            cp = ck.Checkpoint("run1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            cp.registrar("stems", padroes_le=e.le, padroes_escreve=e.escreve)
            cp.gravar(caminho)

            lido = ck.Checkpoint.ler(caminho, projeto=p, slug="demo")
            self.assertEqual(lido.run_id, "run1")
            self.assertIn("stems", lido.etapas)
            self.assertTrue(lido.pode_pular("stems", e.le, e.escreve).pular)

    def test_arquivo_ausente_devolve_checkpoint_vazio(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            cp = ck.Checkpoint.ler(p / "nao_existe.json", projeto=p, slug="demo")
            self.assertEqual(cp.etapas, {})

    def test_arquivo_corrompido_devolve_checkpoint_vazio(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            caminho = p / ck.ARQ
            caminho.write_text("{ corrompido", encoding="utf-8")
            cp = ck.Checkpoint.ler(caminho, projeto=p, slug="demo")
            self.assertEqual(cp.etapas, {})

    def test_gravar_nunca_levanta(self):
        cp = ck.Checkpoint("r1")
        with patch.object(Path, "write_text", side_effect=OSError("disco cheio")):
            cp.gravar(Path(tempfile.gettempdir()) / "vx_ck_impossivel" / ck.ARQ)

    def test_checkpoint_nao_guarda_conteudo_so_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            e = et.POR_NOME["stems"]
            cp.registrar("stems", padroes_le=e.le, padroes_escreve=e.escreve)
            reg = cp.etapas["stems"]
            # hash de 64 hex, nao o conteudo do audio
            self.assertEqual(len(reg["entradas_hash"]), 64)
            int(reg["entradas_hash"], 16)
            self.assertNotIn("audio", json.dumps(cp.como_dict()))


class DescobertaTest(unittest.TestCase):
    def test_run_ids_disponiveis_ordena_do_mais_recente(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for rid in ("20260101T000000_aaaa", "20260202T000000_bbbb"):
                d = p / "qa" / "esteira" / rid
                d.mkdir(parents=True)
                (d / ck.ARQ).write_text("{}", encoding="utf-8")
            self.assertEqual(ck.run_ids_disponiveis(p),
                             ["20260202T000000_bbbb", "20260101T000000_aaaa"])
            self.assertEqual(ck.mais_recente(p), "20260202T000000_bbbb")

    def test_sem_execucoes_nao_quebra(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.assertEqual(ck.run_ids_disponiveis(p), [])
            self.assertIsNone(ck.mais_recente(p))


class EtapasReaisTest(unittest.TestCase):
    def test_hash_de_entradas_aceita_glob_e_placeholder(self):
        """Glob sem resultado e placeholder <run_id> nao podem quebrar o hash."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            h = ck.hash_entradas(("clips_raw/*.mp4", "saidas/esteira/<run_id>/x.mp4",
                                  "entradas/{slug}_normalizado.wav"), p, "demo")
            self.assertEqual(len(h), 64)

    def test_glob_sem_resultado_e_entrada_legitima(self):
        """Projeto sem clipes ainda: hash estavel, nao excecao."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            h1 = ck.hash_entradas(("clips_raw/*.mp4",), p, "demo")
            h2 = ck.hash_entradas(("clips_raw/*.mp4",), p, "demo")
            self.assertEqual(h1, h2)

    def test_saida_que_e_glob_nao_reprova_por_ausencia(self):
        """fonte-limpa declara saida com glob -- ausencia ali e design, nao falha."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            ok, faltando = ck.saidas_existem(("qa/fonte_limpa.json", "clips_raw/_originais/*"),
                                             p, "demo")
            self.assertFalse(ok)  # qa/fonte_limpa.json ainda nao existe
            self.assertEqual(faltando, ["qa/fonte_limpa.json"])

    def test_todas_as_etapas_do_registro_sao_avaliaveis(self):
        """Contrato com vx/etapas.py: nenhuma etapa pode explodir na avaliacao."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _projeto_falso(Path(tmp))
            cp = ck.Checkpoint("r1", projeto=p, slug="demo")
            for e in et.TODAS:
                d = cp.pode_pular(e.nome, e.le, e.escreve)
                self.assertIn(d.acao, (ck.RODAR, ck.PULAR))
                cp.registrar(e.nome, padroes_le=e.le, padroes_escreve=e.escreve)


if __name__ == "__main__":
    unittest.main()
