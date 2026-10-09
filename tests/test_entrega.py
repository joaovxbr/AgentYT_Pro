"""Pacote de entrega: nunca 'pronto' faltando thumb, textos ou shorts; promocao so de candidato aprovado."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import entrega  # noqa: E402

PACOTE_OK = {"video_principal": {
    "arquivo": "saidas/x_master.mp4", "miniatura": "saidas/x_capa_ia.jpg",
    "titulo": "X – FAIXA | Rap | VX RAPS", "descricao": "desc\n0:00 Intro", "tags": ["x", "rap"],
    "capitulos": [{"t": 0, "nome": "Intro"}, {"t": 10, "nome": "Verso"}, {"t": 40, "nome": "Refrão"}],
    "comentario_fixado": "Qual parte?", "titulos_ab": ["a", "b"]}, "artes": [], "shorts": []}


class EntregaTests(unittest.TestCase):
    def _projeto(self, tmp: str) -> Path:
        d = Path(tmp) / "x"
        (d / "saidas" / "shorts").mkdir(parents=True)
        (d / "projeto.json").write_text(json.dumps({"master": "saidas/x_master.mp4"}), encoding="utf-8")
        return d

    def _completo(self, d: Path) -> None:
        (d / "saidas" / "x_master.mp4").write_bytes(b"v")
        Image.new("RGB", (1280, 720)).save(d / "saidas" / "x_capa_ia.jpg")
        for n in ("x_banner_canal.jpg", "x_capa_streaming_3000.jpg"):
            Image.new("RGB", (8, 8)).save(d / "saidas" / n)
        (d / "saidas" / "shorts" / "01.mp4").write_bytes(b"s")
        (d / "saidas" / "shorts" / "pacote.json").write_text(json.dumps({"shorts": [
            {"arquivo": "01.mp4", "titulo": "t", "descricao": "d", "tiktok": "k"}]}), encoding="utf-8")

    def test_complete_package_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._projeto(tmp)
            self._completo(d)
            self.assertEqual({k: v for k, v in entrega.conferir(d, PACOTE_OK).items() if v}, {})

    def test_missing_thumb_or_texts_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._projeto(tmp)
            self._completo(d)
            (d / "saidas" / "x_capa_ia.jpg").unlink()
            ruim = json.loads(json.dumps(PACOTE_OK))
            ruim["video_principal"]["descricao"] = ""
            falta = entrega.conferir(d, ruim)
            self.assertTrue(falta["thumb"])
            self.assertTrue(falta["descricao"])
            Image.new("RGB", (1920, 1080)).save(d / "saidas" / "x_capa_ia.jpg")
            self.assertIn("fora do padrao", entrega.conferir(d, PACOTE_OK)["thumb"])
            (d / "saidas" / "shorts" / "pacote.json").write_text(json.dumps({"shorts": [
                {"arquivo": "01.mp4", "titulo": "t", "descricao": "", "tiktok": "k"}]}), encoding="utf-8")
            self.assertTrue(entrega.conferir(d, PACOTE_OK)["shorts_textos"])

    def test_every_checklist_item_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._projeto(tmp)
            self.assertEqual(set(entrega.conferir(d, {})), {k for k, _ in entrega.ITENS})

    def test_promote_only_approved_and_backs_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            projetos = Path(tmp)
            d = projetos / "x"
            (d / "qa" / "esteira" / "r1").mkdir(parents=True)
            (d / "saidas").mkdir()
            (d / "projeto.json").write_text(json.dumps({"master": "saidas/x_master.mp4"}), encoding="utf-8")
            cand = d / "cand.mp4"
            cand.write_bytes(b"novo")
            (d / "saidas" / "x_master.mp4").write_bytes(b"antigo")
            exe = d / "qa" / "esteira" / "r1" / "execucao.json"
            exe.write_text(json.dumps({"status": "reprovado", "saida": str(cand)}), encoding="utf-8")
            with patch.object(entrega, "PROJETOS", projetos):
                with self.assertRaises(ValueError):
                    entrega.promover("x", "r1")
                exe.write_text(json.dumps({"status": "aprovado_qa_automatico", "saida": str(cand)}), encoding="utf-8")
                reg = entrega.promover("x", "r1")
            self.assertEqual((d / "saidas" / "x_master.mp4").read_bytes(), b"novo")
            self.assertEqual((d / reg["backup_anterior"]).read_bytes(), b"antigo")
            self.assertEqual(json.loads((d / "qa" / "promocoes.json").read_text(encoding="utf-8"))[0]["run_id"], "r1")

class FolhaNaEntregaTests(unittest.TestCase):
    """A entrega roda a folha por quadro: o QA visual que os porteiros nao cobrem."""

    def _projeto(self, tmp: str) -> Path:
        d = Path(tmp) / "x"
        (d / "saidas" / "shorts").mkdir(parents=True)
        (d / "qa" / "folha_por_quadro").mkdir(parents=True)
        (d / "projeto.json").write_text(json.dumps({"master": "saidas/x_master.mp4"}), encoding="utf-8")
        (d / "saidas" / "x_master.mp4").write_bytes(b"video")
        return d

    def test_roda_a_folha_e_registra_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            projetos = Path(tmp)
            d = self._projeto(tmp)
            res = {"amostras": 4608, "folhas": ["a.jpg", "b.jpg"], "cobertura": {"HEAD/CAUDA": 0.75}}
            log = []
            with patch.object(entrega, "PROJETOS", projetos), \
                 patch("folha_por_quadro.auditar", return_value=res) as aud:
                entrega._rodar_folha("x", d / "saidas" / "x_master.mp4", log)
            self.assertTrue(aud.called)
            self.assertIn("4608", log[0])
            self.assertIn("HEAD/CAUDA", log[0])

    def test_folha_no_tempo_do_master_nao_roda_de_novo(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            projetos = Path(tmp)
            d = self._projeto(tmp)
            csv = d / "qa" / "folha_por_quadro" / "x_folha.csv"
            csv.write_text("t\n0\n", encoding="utf-8")
            master = d / "saidas" / "x_master.mp4"
            novo = master.stat().st_mtime + 10
            os.utime(csv, (novo, novo))
            log = []
            with patch.object(entrega, "PROJETOS", projetos), \
                 patch("folha_por_quadro.auditar") as aud:
                entrega._rodar_folha("x", master, log)
            self.assertFalse(aud.called, "a folha nova do master nao pode ficar na versao velha")
            self.assertEqual(log, [])

    def test_falha_da_folha_nao_derruba_a_entrega(self):
        with tempfile.TemporaryDirectory() as tmp:
            projetos = Path(tmp)
            d = self._projeto(tmp)
            log = []
            with patch.object(entrega, "PROJETOS", projetos), \
                 patch("folha_por_quadro.auditar", side_effect=RuntimeError("sem ffmpeg")):
                entrega._rodar_folha("x", d / "saidas" / "x_master.mp4", log)
            self.assertTrue(log and "AVISO" in log[0])

    def test_entrega_md_aponta_a_folha(self):
        md = entrega.markdown(Path("x"), PACOTE_OK, {}, ["folha por quadro: 4608 quadros"])
        self.assertIn("QA visual", md)
        self.assertIn("_take_NN.jpg", md)
        self.assertIn("folha por quadro: 4608 quadros", md)


class MiniaturaContractTests(unittest.TestCase):
    """A porta `capa` escreve `_capa_youtube.jpg`; o pacote exigia `_capa_ia.jpg`.

    Dois nomes para a MESMA miniatura 1280x720: 4 consumidores cobravam um arquivo que
    a ferramenta que gera a capa nunca escrevia. `conferir` reprovava a entrega de um
    projeto com capa pronta, e o `lancamento` apontava miniatura inexistente.
    """

    def _projeto(self, tmp: str) -> Path:
        d = Path(tmp) / "x"
        (d / "saidas" / "shorts").mkdir(parents=True)
        (d / "projeto.json").write_text(json.dumps({"master": "saidas/x_master.mp4"}), encoding="utf-8")
        return d

    def test_thumb_aceita_a_capa_youtube(self):
        """A capa que a porta `capa` gera de verdade conta como miniatura valida."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._projeto(tmp)
            (d / "saidas" / "x_master.mp4").write_bytes(b"v")
            Image.new("RGB", (1280, 720)).save(d / "saidas" / "x_capa_youtube.jpg")
            for n in ("x_banner_canal.jpg", "x_capa_streaming_3000.jpg"):
                Image.new("RGB", (8, 8)).save(d / "saidas" / n)
            (d / "saidas" / "shorts" / "01.mp4").write_bytes(b"s")
            (d / "saidas" / "shorts" / "pacote.json").write_text(json.dumps({"shorts": [
                {"arquivo": "01.mp4", "titulo": "t", "descricao": "d", "tiktok": "k"}]}), encoding="utf-8")
            self.assertEqual({k: v for k, v in entrega.conferir(d, PACOTE_OK).items() if v}, {})

    def test_thumb_tamanho_errado_ainda_reprova(self):
        """Aceitar o novo nome NAO afrouxa o padrao: 1920x1080 continua reprovado."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._projeto(tmp)
            Image.new("RGB", (1920, 1080)).save(d / "saidas" / "x_capa_youtube.jpg")
            self.assertIn("fora do padrao", entrega.conferir(d, PACOTE_OK)["thumb"])

    def test_mesma_thumb_para_conferir_e_lancamento(self):
        """Os dois consumidores precisam apontar para o MESMO arquivo, nunca um cada."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._projeto(tmp)
            Image.new("RGB", (1280, 720)).save(d / "saidas" / "x_capa_youtube.jpg")
            import distribuicao_social_pro as soc
            with patch.object(soc, "pacote_lancamento", wraps=soc.pacote_lancamento):
                pass
            alvo = entrega._thumb(d)
            self.assertEqual(alvo, d / "saidas" / "x_capa_youtube.jpg")
            self.assertTrue(alvo.is_file())


if __name__ == "__main__":
    unittest.main()