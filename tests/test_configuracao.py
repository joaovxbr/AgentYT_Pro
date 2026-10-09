"""Fase 3: configuracao em camadas, porteiros centralizados, caminhos do manifesto."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ferramentas"))

from vx import config, projeto
import graphic_auto_pipeline as gfx
import cenas_ia_pipeline as cia
import manga_auto_pipeline as manga
import titulos_pipeline as tit
import montar_timeline as mt
import sincronizar_letra as sl

SECOES = {"graphics_auto": gfx.DEFAULT_CONFIG, "cenas_ia": cia.DEFAULTS,
          "manga_auto": manga.DEFAULTS, "titulos": tit.DEFAULTS, "edicao": mt.EDICAO_PADRAO}


class CamadasTests(unittest.TestCase):
    def test_precedence_code_then_studio_then_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "estudio.json"
            arq.write_text(json.dumps({"x": {"a": 2, "b": 2}}))
            cfg = config.secao("x", {"a": 1, "b": 1, "c": 1}, {"x": {"b": 3, "zz": 9}}, arquivo=arq)
            self.assertEqual(cfg, {"a": 2, "b": 3, "c": 1})  # chave desconhecida ignorada

    def test_studio_config_has_only_known_keys(self):
        dados = json.loads((ROOT / "config" / "estudio.json").read_text(encoding="utf-8"))
        for secao, valores in dados.items():
            if secao.startswith("_"):
                continue
            self.assertIn(secao, SECOES, f"secao desconhecida em config/estudio.json: {secao}")
            extras = set(valores) - set(SECOES[secao])
            self.assertEqual(extras, set(), f"chaves desconhecidas em {secao}: {extras}")

    def test_studio_config_matches_code_defaults(self):
        # hoje o config espelha o codigo; se divergir, foi decisao consciente -> atualize o padrao
        dados = json.loads((ROOT / "config" / "estudio.json").read_text(encoding="utf-8"))
        for secao, valores in dados.items():
            if secao.startswith("_"):
                continue
            for k, v in valores.items():
                self.assertEqual(SECOES[secao][k], v, f"{secao}.{k}")

    def test_project_override_still_wins(self):
        cfg = gfx._cfg({"graphics_auto": {"max_scenes": 2}})
        self.assertEqual(cfg["max_scenes"], 2)
        self.assertEqual(cfg["min_gap_seconds"], gfx.DEFAULT_CONFIG["min_gap_seconds"])


class PorteirosTests(unittest.TestCase):
    def test_project_cannot_loosen_gates(self):
        # porteiro() nao recebe manifesto: nao existe caminho para afrouxar por projeto
        import inspect
        self.assertNotIn("manifesto", inspect.signature(config.porteiro).parameters)

    def test_gate_config_matches_module_values(self):
        import audio, imagem, auditor_letra
        dados = json.loads((ROOT / "config" / "porteiros.json").read_text(encoding="utf-8"))
        self.assertEqual(dados["audio"]["lufs_min"], audio.LUFS_MIN)
        self.assertEqual(dados["audio"]["true_peak_max"], audio.TRUE_PEAK_MAX)
        self.assertEqual(dados["imagem_master"], imagem.LIMITES_MASTER)
        self.assertEqual(dados["auditar_letra"]["min_cobertura_linha"], auditor_letra.MIN_COBERTURA_LINHA)


class CaminhosTests(unittest.TestCase):
    def test_audio_fonte_from_manifest_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "novo"
            p.mkdir()
            m = {"audio_fonte": "entradas/minha_musica.wav"}
            self.assertEqual(projeto.audio(p, m), p / "entradas" / "minha_musica.wav")
            self.assertEqual(projeto.stem(p, "vocals", m).name, "minha_musica_vocals.wav")

    def test_default_audio_name_kept_for_old_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "gojo"
            p.mkdir()
            self.assertEqual(projeto.audio(p, {}).name, "gojo_normalizado.wav")
            self.assertEqual(projeto.stem(p, "vocals", {}).name, "gojo_normalizado_vocals.wav")

    def test_no_hardcoded_normalizado_left_in_pipeline(self):
        fonte = (ROOT / "ferramentas" / "pipeline_autonomo_pro.py").read_text(encoding="utf-8")
        self.assertNotIn("_normalizado", fonte)


class VocabularioTests(unittest.TestCase):
    def test_vocabulary_comes_from_manifest_not_code(self):
        self.assertFalse(hasattr(sl, "_VOCABULARIO_CANONICO"))
        voc = sl.vocabulario_do_manifesto({"vocabulario": {"termos": ["Gojo", "Hollow Purple"],
                                                            "variantes": {"satoro": "Satoru"}}})
        self.assertEqual(sl.corrigir_vocabulario_canonico("gojo e satoro", voc), "Gojo e Satoru")

    def test_project_without_vocabulary_is_untouched(self):
        self.assertEqual(sl.corrigir_vocabulario_canonico("mangekyo", {}), "mangekyo")


if __name__ == "__main__":
    unittest.main()
