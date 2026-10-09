from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import cenas_ia_pipeline as cia  # noqa: E402
import compositor_master_gpu as comp  # noqa: E402
import direcao_clipe  # noqa: E402
import montar_timeline as mt  # noqa: E402
import titulos_pipeline as tp  # noqa: E402


def _tl(primeira=12.0, ultima=157.0, fim=174.8):
    return {"audio_duration": fim, "segments": [
        {"start": 0.0, "end": primeira, "type": "intro", "clip": "a.mp4", "src": 0.0},
        {"start": primeira, "end": ultima, "type": "lyric", "clip": "a.mp4", "src": 12.0},
        {"start": ultima, "end": fim, "type": "outro", "clip": "a.mp4", "src": 0.0},
    ]}


class TitulosPlanTests(unittest.TestCase):
    def _plan(self, tl, manifest=None):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "p"
            p.mkdir()
            (p / "projeto.json").write_text(json.dumps(manifest or {}), encoding="utf-8")
            with patch.object(tp, "PROJECTS", Path(tmp)):
                return tp.planejar("p", tl)

    def test_title_e_end_card_nas_bordas_sem_invadir_voz(self):
        r = self._plan(_tl())
        tit, fim = r["items"]
        self.assertEqual((tit["tipo"], tit["start"], tit["end"]), (tp.TIPO_TITULO, 0.0, 5.0))
        self.assertEqual(fim["tipo"], tp.TIPO_FIM)
        self.assertAlmostEqual(fim["end"], 174.8)
        self.assertGreaterEqual(fim["start"], 157.0)

    def test_encolhe_ou_pula_quando_a_voz_comeca_cedo(self):
        r = self._plan(_tl(primeira=3.6, ultima=173.0))
        tipos = [i["tipo"] for i in r["items"]]
        self.assertIn(tp.TIPO_TITULO, tipos)
        self.assertLessEqual(r["items"][0]["end"], 3.2 + 1e-6)
        self.assertNotIn(tp.TIPO_FIM, tipos)   # so 1.8s depois da ultima frase
        self.assertEqual(self._plan(_tl(primeira=2.0))["items"][0]["tipo"], tp.TIPO_FIM)

    def test_desligavel_no_manifesto(self):
        self.assertEqual(self._plan(_tl(), {"titulos": {"enabled": False}})["items"], [])

    def test_cards_sao_camera_travada_e_protegem_estagios_anteriores(self):
        tl = {"audio_duration": 5, "segments": [
            {"start": 0, "end": 5, "clip": "x.mp4", "src": 0, "type": tp.TIPO_TITULO}]}
        self.assertEqual(direcao_clipe.criar(tl)["shots"][0]["preset"], "graphics_locked")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "p"
            p.mkdir()
            (p / "projeto.json").write_text("{}", encoding="utf-8")
            (p / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
            with patch.object(cia, "PROJECTS", Path(tmp)):
                self.assertEqual(cia.executar("p")["status"], "preserved_after_downstream_visuals")

    def test_esteira_ordem(self):
        # a ordem vive no registro unico (vx/etapas.py), que a esteira executa
        sys.path.insert(0, str(ROOT))
        from vx import etapas
        ordem = etapas.nomes("producao")
        seq = ["cenas-auto", "chroma-auto", "cenas-ia", "titulos", "manga-auto", "graficos-auto"]
        i = ordem.index(seq[0])
        self.assertEqual(ordem[i:i + len(seq)], seq)
        # e a esteira de fato itera o registro
        fonte = (ROOT / "ferramentas" / "pipeline_autonomo_pro.py").read_text(encoding="utf-8")
        self.assertIn("vx_etapas.PRODUCAO", fonte)

    def test_master_faz_fade_da_musica(self):
        fonte = (ROOT / "ferramentas" / "compositor_master_gpu.py").read_text(encoding="utf-8")
        corpo = fonte[fonte.index("def concatenar_intro"):]
        self.assertIn("afade=t=in", corpo)
        self.assertIn("afade=t=out", corpo)
        self.assertGreater(comp.FADE_OUT_MUSICA, 0)


class RitmoTests(unittest.TestCase):
    def test_subdivide_planos_longos_no_pico_de_808(self):
        janelas = [{"tipo": "lyric", "start": 10.0, "end": 17.0, "line": 1, "text": "x"},
                   {"tipo": "lyric", "start": 17.0, "end": 18.5, "line": 2, "text": "y"}]
        out = mt.subdividir(janelas, batidas=[12.4, 14.9])
        self.assertEqual([round(j["start"], 3) for j in out], [10.0, 12.4, 14.9, 17.0])
        self.assertTrue(all(j["end"] - j["start"] <= mt.EDICAO_PADRAO["max_plano_lyric"] + 0.9 for j in out))
        for a, b in zip(out, out[1:]):
            self.assertAlmostEqual(a["end"], b["start"])
        self.assertTrue(all(j["line"] == 1 for j in out[:3]))

    def test_sem_batidas_divide_igual_e_respeita_minimo(self):
        out = mt.subdividir([{"tipo": "gap", "start": 0.0, "end": 9.0}], batidas=[])
        self.assertEqual(len(out), 3)
        self.assertAlmostEqual(out[-1]["end"], 9.0)
        self.assertTrue(all(j["end"] - j["start"] >= mt.EDICAO_PADRAO["min_plano"] for j in out))

    def test_reuso_de_cena_pega_outro_trecho(self):
        import semantic_scene_matcher as sm
        cena = {"start": 10.0, "end": 16.0, "clip_duration": 100.0}
        pos = [sm._source_start(cena, 2.0, uso=u) for u in range(3)]
        self.assertEqual(pos[0], 12.0)            # 1o uso: centro (comportamento antigo)
        self.assertEqual(len(set(pos)), 3)        # reusos nao repetem o mesmo quadro
        self.assertTrue(all(10.0 <= p <= 14.0 for p in pos))

    def test_cortes_no_grid_de_frames(self):
        out = mt.subdividir([{"tipo": "lyric", "start": 0.0, "end": 6.0}], batidas=[2.0171])
        for j in out[1:]:
            self.assertAlmostEqual(j["start"] * 30, round(j["start"] * 30), places=6)


if __name__ == "__main__":
    unittest.main()
