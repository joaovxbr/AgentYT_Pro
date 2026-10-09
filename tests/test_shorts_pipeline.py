from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import pov_lyrics_official as pov  # noqa: E402
import shorts_pipeline as sp  # noqa: E402

MANIFEST = {
    "faixa": "VINGADOR", "personagem": "Fulano Heroi", "anime": "Anime X (Studio)",
    "scene_semantics": {"labels": [
        {"id": "action:raio", "kind": "action", "name": "Raio Supremo", "aliases": ["raiozao", "golpe final"]},
        {"id": "entity:outro", "kind": "entity", "name": "Outro", "aliases": ["outro"]},
    ]},
}


def _linhas():
    # 60 frases de 2.5s; frases 20-27 repetem (refrao) e vivem num trecho de energia alta
    out = []
    for i in range(60):
        texto = "refrao do fogo e sangue" if 20 <= i <= 27 else f"verso numero {i}"
        a = 5.0 + i * 2.5
        out.append({"start": a, "end": a + 2.3, "text": texto,
                    "words": [{"word": w, "start": a, "end": a + 0.5} for w in texto.split()]})
    return out


class ShortsTests(unittest.TestCase):
    def _proj(self, tmp, timeline_segments=()):
        p = Path(tmp) / "p"
        p.mkdir()
        (p / "projeto.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        (p / "transcricao_canonica.json").write_text(json.dumps({"lines": _linhas()}), encoding="utf-8")
        (p / "timeline.json").write_text(json.dumps({"audio_duration": 160.0,
                                                     "segments": list(timeline_segments)}), encoding="utf-8")
        return p

    def test_palavras_especiais_vem_do_manifesto(self):
        esp = sp.palavras_especiais(MANIFEST)
        self.assertEqual(esp.get("RAIOZAO"), sp.FONTE_ACAO)
        self.assertEqual(esp.get("VINGADOR"), sp.FONTE_TITULO)
        self.assertNotIn("OUTRO", esp)          # entity nao vira destaque
        self.assertNotIn("GOLPE FINAL", esp)    # so palavra unica

    def test_plano_nao_sobrepoe_comeca_em_frase_e_prefere_refrao(self):
        energia = [0.2] * 320
        for i in range(110, 150):   # 55s-75s = frases 20-27
            energia[i] = 1.0
        with tempfile.TemporaryDirectory() as tmp:
            self._proj(tmp)
            with patch.object(sp, "PROJECTS", Path(tmp)):
                plano = sp.planejar("p", n=3, dur=30.0, energia=energia)
        sel = plano["selected"]
        self.assertEqual(len(sel), 3)
        inicios = {round(l["start"] - 0.25, 3) for l in _linhas()}
        for s in sel:
            self.assertIn(s["start"], inicios)
            self.assertLessEqual(s["duration"], 31.6)
        for a, b in zip(sel, sel[1:]):
            self.assertLessEqual(a["end"], b["start"])
        melhor = max(sel, key=lambda s: s["score"])
        self.assertGreater(melhor["refrao"], 0.5)

    def test_gancho_manual_do_manifesto_vence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._proj(tmp)
            m = dict(MANIFEST, shorts={"ganchos": ["POV: GANCHO DO DIRETOR"]})
            (p / "projeto.json").write_text(json.dumps(m), encoding="utf-8")
            with patch.object(sp, "PROJECTS", Path(tmp)):
                plano = sp.planejar("p", n=2, dur=30.0, energia=[0.5] * 320)
        self.assertEqual(plano["selected"][0]["gancho"], "POV: GANCHO DO DIRETOR")
        self.assertNotEqual(plano["selected"][1]["gancho"], "POV: GANCHO DO DIRETOR")

    def test_ganchos_nao_se_repetem_mesmo_com_refrao(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._proj(tmp)
            with patch.object(sp, "PROJECTS", Path(tmp)):
                plano = sp.planejar("p", n=3, dur=30.0, energia=[0.5] * 320)
        ganchos = [s["gancho"] for s in plano["selected"]]
        self.assertEqual(len(ganchos), len(set(ganchos)))

    def test_metadados_curtos_e_com_hashtags(self):
        meta = sp.metadados(MANIFEST, {"gancho": "X" * 150, "linha_gancho": "linha"})
        self.assertLessEqual(len(meta["titulo"]), 100)
        self.assertIn("#VXRaps", meta["descricao"])
        self.assertIn("#AnimeX", meta["descricao"])

    def test_pov_aceita_letra_sincronizada_em_lista(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "letra_sincronizada.json"
            f.write_text(json.dumps([{"start": 1, "end": 2, "text": "oi mundo",
                                      "words": [{"text": "oi", "start": 1, "end": 1.4},
                                                {"text": "mundo", "start": 1.4, "end": 2}]}]),
                         encoding="utf-8")
            ass = pov.build_ass(f, Path(tmp) / "x.ass", 0.0, 5.0, especiais={"MUNDO": "Bangers"})
            txt = ass.read_text(encoding="utf-8-sig")
        self.assertIn("Dialogue:", txt)
        self.assertIn(r"\fnBangers", txt)


if __name__ == "__main__":
    unittest.main()
