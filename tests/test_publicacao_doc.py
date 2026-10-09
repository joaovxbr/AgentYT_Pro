from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import publicacao_doc as pd  # noqa: E402

MANIFEST = {
    "faixa": "VINGADOR", "personagem": "Fulano Heroi", "anime": "Anime X (Studio)",
    "scene_semantics": {"labels": [{"id": "action:raio", "kind": "action", "name": "Raio Supremo"}]},
}


def _linhas():
    out, t = [], 12.0
    for bloco, textos in (("verse", [f"verso {i}" for i in range(8)]),
                          ("refrain", ["CAI O RAIO Supremo", "o heroi chegou"]),
                          ("verse", [f"segundo verso {i}" for i in range(8)]),
                          ("refrain", ["CAI O RAIO Supremo", "o heroi chegou"]),
                          ("verse", ["ultima frase"])):
        for x in textos:
            out.append({"start": t, "end": t + 2.5, "text": x, "section": bloco})
            t += 3.0
    return out


class PublicacaoTests(unittest.TestCase):
    def test_secoes_nomeiam_versos_refrao_e_final(self):
        nomes = [b["nome"] for b in pd.secoes(_linhas())]
        self.assertEqual(nomes, ["Verso 1", "Refrão", "Verso 2", "Refrão", "Final"])

    def test_capitulos_seguem_regras_do_youtube(self):
        caps = pd.capitulos(pd.secoes(_linhas()), offset=10.0, fim_card=120.0, duracao=140.0)
        self.assertEqual(caps[0], {"t": 0.0, "nome": "Intro"})
        self.assertGreaterEqual(len(caps), 3)
        for a, b in zip(caps, caps[1:]):
            self.assertGreaterEqual(b["t"] - a["t"], pd.MIN_CAP)
        self.assertEqual(caps[-1]["nome"], "Encerramento")
        self.assertAlmostEqual(caps[1]["t"], 22.0)            # 1a frase + intro oficial

    def test_frase_natural_preserva_nomes_do_manifesto(self):
        self.assertEqual(pd.frase_natural("CAI O RAIO Supremo DO Fulano", MANIFEST),
                         "Cai o Raio Supremo do Fulano")

    def test_tags_respeitam_500_e_nao_repetem(self):
        tags = pd._cabe_tags(["a" * 200, "A" * 200, "b" * 200, "c" * 90, "d"])
        self.assertLessEqual(sum(len(t) for t in tags) + len(tags) - 1, pd.LIM_TAGS)
        self.assertEqual(len({t.lower() for t in tags}), len(tags))

    def test_gerar_documento_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "p"
            (p / "saidas").mkdir(parents=True)
            (p / "projeto.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
            (p / "transcricao_canonica.json").write_text(json.dumps({"lines": _linhas()}), encoding="utf-8")
            (p / "timeline.json").write_text(json.dumps({"segments": [
                {"start": 115.0, "end": 120.0, "type": "vx_end_card"}]}), encoding="utf-8")
            shorts = {"shorts": [{"arquivo": "01.mp4", "titulo": "T", "descricao": "D", "tiktok": "K"}]}
            doc = pd.gerar(p, 10.0, 130.0, shorts)
            md = (p / "saidas" / "PUBLICACAO.md").read_text(encoding="utf-8")
        self.assertEqual(doc["problemas"], [])
        self.assertLessEqual(doc["descricao_caracteres"], pd.LIM_DESC)
        self.assertTrue(all(t["ok"] for t in doc["titulos"]))
        for trecho in ("0:00 Intro", "LETRA", "CRÉDITOS", "#VXRaps", "[Refrão]"):
            self.assertIn(trecho, doc["descricao"])
        for trecho in ("## Vídeo principal", "### Tags", "### Comentário fixado", "01.mp4"):
            self.assertIn(trecho, md)


if __name__ == "__main__":
    unittest.main()
