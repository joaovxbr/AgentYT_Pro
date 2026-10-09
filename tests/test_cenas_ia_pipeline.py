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
import direcao_clipe  # noqa: E402
import scene_intelligence  # noqa: E402
import semantic_scene_matcher as sm  # noqa: E402

MANIFESTO = {"personagem": "Fulano Heroi", "anime": "Anime X",
             "scene_semantics": {"required_score": 0.14}}


def _seg(a, b, score, texto="", concepts=None, targets=None, target_scores=None, typ="lyric"):
    return {"start": a, "end": b, "duration": b - a, "clip": "real.mp4", "src": a, "type": typ,
            "scene_match": {"score": score, "lyric_text": texto, "concepts": concepts or [],
                            "semantic_targets": targets or [],
                            "semantic_target_scores": target_scores or {}}}


def _timeline():
    return {"audio_duration": 120.0, "segments": [
        _seg(0, 14, 0.9, "intro", ["breathing_space"], typ="intro"),
        _seg(14, 30, 0.10, "Chamas na noite", ["fire", "dark"]),          # fraco -> candidato
        _seg(30, 32, 0.12, "Chamas na noite", ["fire", "dark"]),          # mesma letra: nao repete
        _seg(32, 33.0, 0.05, "curto demais", ["fire"]),                   # < duration_min
        _seg(33, 50, 0.80, "Tudo bem aqui", ["power"]),                   # material bom
        _seg(50, 53, 0.70, "Raio no ceu", ["electric"],
             targets=[{"id": "action:raio", "name": "Raio Supremo", "required": True}],
             target_scores={"action:raio": 0.02}),                        # alvo reprovado -> candidato
        _seg(53, 56, 0.70, "O vilao chegou", ["rage"],
             targets=[{"id": "entity:vilao", "name": "Vilao", "required": True}],
             target_scores={"entity:vilao": 0.0}),                        # so entity -> ignora
        _seg(56, 60, 0.10, "sem conceito", ["generic_lyric"]),            # generico -> ignora
        _seg(60, 118, 0.2, "Lagrimas sozinho", ["pain"]),
        _seg(118, 120, 0.1, "fim", ["pain"], typ="outro"),
    ]}


class PromptTests(unittest.TestCase):
    def test_prompt_une_conceito_palavra_e_alvo_sem_personagem_hardcoded(self):
        mapa = cia.carregar_mapa()
        p = cia.prompt_para_letra("Do céu cai o trovão", ["electric"],
                                  [{"id": "action:kirin", "name": "Kirin"}], MANIFESTO, mapa)
        self.assertEqual(p["tipo"], "cena")
        self.assertIn("lightning", p["tags"])
        self.assertIn("sky", p["tags"])
        self.assertIn("kirin", p["tags"])
        self.assertEqual(p["tags"].lower().count("lightning,"), p["tags"].lower().count("lightning,"))
        self.assertEqual(len(p["tags"].split(", ")), len(set(t.lower() for t in p["tags"].split(", "))))

    def test_alvo_entity_nao_vira_tag(self):
        p = cia.prompt_para_letra("x", ["rage"], [{"id": "entity:outro", "name": "Outro Cara"}],
                                  MANIFESTO, cia.carregar_mapa())
        self.assertNotIn("outro cara", p["tags"])

    def test_tags_alvos_do_manifesto_vencem(self):
        m = dict(MANIFESTO, imagem_ia={"tags_alvos": {"action:x": "custom move"}})
        p = cia.prompt_para_letra("x", ["fight"], [{"id": "action:x", "name": "X"}], m, cia.carregar_mapa())
        self.assertTrue(p["tags"].startswith("custom move"))

    def test_mapa_sem_personagem(self):
        texto = cia.MAPA_PADRAO.read_text(encoding="utf-8").lower()
        for nome in ("sasuke", "eren", "itachi", "uchiha"):
            self.assertNotIn(nome, texto)


class PlanTests(unittest.TestCase):
    def _plan(self, timeline, manifest=MANIFESTO):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "p"
            proj.mkdir()
            (proj / "projeto.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(cia, "PROJECTS", Path(tmp)):
                return cia.planejar("p", timeline_override=timeline)

    def test_seleciona_so_trechos_fracos_e_desenhaveis(self):
        r = self._plan(_timeline())
        textos = [s["text"] for s in r["selected"]]
        self.assertIn("Chamas na noite", textos)
        self.assertIn("Raio no ceu", textos)
        self.assertEqual(textos.count("Chamas na noite"), 1)
        for proibido in ("curto demais", "Tudo bem aqui", "O vilao chegou", "sem conceito", "intro", "fim"):
            self.assertNotIn(proibido, textos)

    def test_respeita_gap_limite_e_duracao(self):
        r = self._plan(_timeline())
        sel = r["selected"]
        centros = [(s["start"] + s["end"]) / 2 for s in sel]
        self.assertTrue(all(b - a >= cia.DEFAULTS["min_gap_seconds"] for a, b in zip(centros, centros[1:])))
        self.assertLessEqual(len(sel), cia.DEFAULTS["max_scenes"])
        self.assertTrue(all(s["duration"] <= cia.DEFAULTS["duration_max"] + 1e-6 for s in sel))
        self.assertEqual(len({s["movement"] for s in sel}), len(sel))

    def test_desligado_por_manifesto(self):
        r = self._plan(_timeline(), dict(MANIFESTO, cenas_ia={"enabled": False}))
        self.assertEqual(r["status"], "disabled")
        self.assertEqual(r["selected"], [])

    def test_sem_scene_matcher_nao_faz_nada(self):
        tl = {"segments": [{"start": 0, "end": 10, "clip": "a.mp4", "src": 0, "type": "lyric"}]}
        self.assertEqual(self._plan(tl)["status"], "skipped_sem_scene_matcher")


class InjecaoTests(unittest.TestCase):
    def test_inject_divide_timeline_sem_lacuna(self):
        base = {"segments": [
            {"start": 0.0, "end": 10.0, "duration": 10.0, "clip": "a.mp4", "src": 5.0, "type": "lyric"}]}
        item = {"start": 3.0, "end": 5.0, "duration": 2.0, "clip": "clips_raw/vx_cenas_ia/x.mp4",
                "text": "t", "tags": "fire", "tipo": "cena", "match_score": 0.1, "failed_targets": [],
                "concepts": ["fire"], "image": "artes_ia/x.png", "seed": 1, "movement": "push_in",
                "replaced_clip": "a.mp4"}
        tl = cia._inject(base, [item])
        segs = tl["segments"]
        self.assertEqual([s["type"] for s in segs], ["lyric", cia.TIPO_SEGMENTO, "lyric"])
        self.assertAlmostEqual(segs[2]["src"], 10.0)
        for a, b in zip(segs, segs[1:]):
            self.assertAlmostEqual(a["end"], b["start"])

    def test_filtro_movimento_tem_frames_e_saida_1080p(self):
        f = cia.filtro_movimento("pan_lr", 60)
        self.assertIn("d=60", f)
        self.assertIn("s=1920x1080", f)
        self.assertIn("format=yuv420p", f)


class ContratoTests(unittest.TestCase):
    def test_camera_travada_no_take_ia(self):
        tl = {"audio_duration": 2.0, "segments": [
            {"start": 0, "end": 2, "clip": "x.mp4", "src": 0, "type": cia.TIPO_SEGMENTO}]}
        shot = direcao_clipe.criar(tl)["shots"][0]
        self.assertEqual(shot["preset"], "graphics_locked")
        self.assertEqual(shot["efeitos"], [])

    def test_scene_matcher_preserva_timeline_com_cena_ia(self):
        self.assertTrue(sm._has_downstream_visuals({"segments": [{"type": cia.TIPO_SEGMENTO}]}))

    def test_take_ia_nao_e_fonte_narrativa(self):
        self.assertTrue(scene_intelligence.is_generated_asset(Path("01_x_cena_ia.mp4")))

    def test_esteira_ordem_cenas_ia(self):
        # a ordem vive no registro unico (vx/etapas.py), que a esteira executa
        sys.path.insert(0, str(ROOT))
        from vx import etapas
        ordem = etapas.nomes("producao")
        # chroma-auto entre cenas-auto e cenas-ia: tela verde vira cena composta antes da IA (Douma)
        seq = ["cenas-auto", "chroma-auto", "cenas-ia", "titulos", "manga-auto", "graficos-auto"]
        i = ordem.index(seq[0])
        self.assertEqual(ordem[i:i + len(seq)], seq)

    def test_executar_pula_sem_comfy_sem_quebrar(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "p"
            proj.mkdir()
            (proj / "projeto.json").write_text(json.dumps(MANIFESTO), encoding="utf-8")
            (proj / "timeline.json").write_text(json.dumps(_timeline()), encoding="utf-8")
            with patch.object(cia, "PROJECTS", Path(tmp)), \
                    patch.object(cia.gil, "garantir_comfy",
                                 side_effect=cia.gil.ComfyIndisponivel("offline")):
                r = cia.executar("p")
            self.assertEqual(r["status"], "skipped_comfy_indisponivel")
            self.assertEqual(json.loads((proj / "timeline.json").read_text(encoding="utf-8")), _timeline())

    def test_executar_preserva_depois_de_graphics(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "p"
            proj.mkdir()
            (proj / "projeto.json").write_text(json.dumps(MANIFESTO), encoding="utf-8")
            tl = _timeline()
            tl["segments"][4]["type"] = "vx_graphics_auto"
            (proj / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
            with patch.object(cia, "PROJECTS", Path(tmp)):
                self.assertEqual(cia.executar("p")["status"], "preserved_after_downstream_visuals")

    def test_timeline_editada_por_fora_falha_fechado(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "p"
            (proj / "qa" / "vx_cenas_ia").mkdir(parents=True)
            (proj / "projeto.json").write_text(json.dumps(MANIFESTO), encoding="utf-8")
            tl = _timeline()
            tl["segments"][1]["type"] = cia.TIPO_SEGMENTO
            (proj / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
            (proj / "qa" / "vx_cenas_ia" / "state.json").write_text('{"applied_hash": "outro"}',
                                                                    encoding="utf-8")
            with patch.object(cia, "PROJECTS", Path(tmp)):
                with self.assertRaisesRegex(RuntimeError, "falha fechada"):
                    cia.executar("p")


if __name__ == "__main__":
    unittest.main()
