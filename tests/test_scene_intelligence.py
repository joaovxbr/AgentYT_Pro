from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import cv2
import numpy as np

import scene_intelligence as si
import semantic_scene_matcher as sm
import semantic_vision as sv


def _fake_semantic_encoder(frames_per_scene=3):
    """Encoder real sem torch: _frame_scores classifica vermelho/azul pela cor media."""
    enc = sv.SemanticVisionEncoder({"enabled": False})
    enc.enabled = True
    enc.profile = {
        "enabled": True, "model": "fake", "pretrained": "fake",
        "frames_per_scene": frames_per_scene, "top_k_per_kind": 2, "min_score": 0.08,
        "labels": [],
    }
    enc.labels = [
        {"id": "action:red", "kind": "action", "name": "Red"},
        {"id": "action:blue", "kind": "action", "name": "Blue"},
    ]
    enc.kind_indices = {"action": [0, 1]}
    enc.calls = 0

    def scores(frame):
        enc.calls += 1
        blue, red = float(frame[..., 0].mean()), float(frame[..., 2].mean())
        return {"action:red": 0.9 if red > blue else 0.1,
                "action:blue": 0.9 if blue >= red else 0.1}

    def no_seek(*_args, **_kwargs):
        raise AssertionError("catalogo nao deve fazer seek por frame")

    enc._frame_scores = scores
    enc._read_frame = no_seek
    return enc


class SceneIntelligenceTests(unittest.TestCase):
    def test_fire_features_generate_fire_tag(self):
        f = {
            "motion": 0.46, "motion_peak": 0.65, "contrast": 0.62,
            "saturation": 0.78, "edge_density": 0.12,
            "face_area": 0.0, "brightness": 0.48, "dark_ratio": 0.18,
            "red": 0.08, "orange": 0.19, "cyan_blue": 0.01,
            "purple": 0.01, "center_saliency": 0.55,
        }
        tags = si._tag_scores(f)
        self.assertGreater(tags["fire"], 0.75)
        self.assertGreater(tags["destruction"], 0.4)

    def test_blue_energy_generates_electric_tag(self):
        f = {
            "motion": 0.48, "motion_peak": 0.72, "contrast": 0.61,
            "saturation": 0.72, "edge_density": 0.14,
            "face_area": 0.0, "brightness": 0.52, "dark_ratio": 0.12,
            "red": 0.01, "orange": 0.01, "cyan_blue": 0.23,
            "purple": 0.02, "center_saliency": 0.66,
        }
        tags = si._tag_scores(f)
        self.assertGreater(tags["electric"], 0.8)
        self.assertGreater(tags["energy"], 0.8)

    def test_generated_assets_are_not_semantic_sources(self):
        self.assertTrue(si._is_generated_asset(Path("impact_01_sangue.mp4")))
        self.assertTrue(si._is_generated_asset(Path("take_saber_18s.mp4")))
        self.assertFalse(si._is_generated_asset(Path("sasuke_twixtor_01.mp4")))

    def test_black_splash_scene_is_flagged_dead(self):
        # Frame quase preto e sem detalhe (tail preto de clipe / splash de
        # streaming tipo "prime"/"netflix" sobre fundo preto) deve ser marcado
        # dead_scene para nunca entrar na selecao narrativa nem no title card.
        preto = {
            "brightness": 0.03, "edge_density": 0.01, "saturation": 0.02,
            "dark_ratio": 0.99, "motion_peak": 0.0, "contrast": 0.02,
            "motion_x": 0.0, "motion_y": 0.0,
        }
        with patch.object(si, "_aggregate", return_value=preto), \
             patch.object(si, "_tag_scores", return_value={}):
            cena = si._scene_from_samples("clip.mp4", [{}], 226.4, 230.0, 1920, 1080, 55)
        self.assertTrue(cena["dead_scene"])

    def test_real_action_scene_is_not_dead(self):
        vivo = {
            "brightness": 0.42, "edge_density": 0.16, "saturation": 0.55,
            "dark_ratio": 0.2, "motion_peak": 0.6, "contrast": 0.5,
            "motion_x": 0.2, "motion_y": 0.05,
        }
        with patch.object(si, "_aggregate", return_value=vivo), \
             patch.object(si, "_tag_scores", return_value={"action": 0.8}):
            cena = si._scene_from_samples("clip.mp4", [{}], 10.0, 14.0, 1920, 1080, 3)
        self.assertFalse(cena["dead_scene"])

    def test_matcher_inventory_excludes_dead_scenes(self):
        catalog = {
            "clips": {
                "anime.mp4": {
                    "eligible_for_semantic_selection": True, "duration": 30.0,
                    "scenes": [
                        {"id": "viva", "start": 1.0, "end": 6.0, "duration": 5.0,
                         "tags": ["action"], "tag_scores": {"action": 0.8},
                         "intensity": 0.7, "quality": 0.8, "dead_scene": False},
                        {"id": "morta", "start": 226.0, "end": 230.0, "duration": 4.0,
                         "tags": [], "tag_scores": {}, "intensity": 0.1,
                         "quality": 0.3, "dead_scene": True},
                    ],
                }
            }
        }
        inv = sm._scene_inventory(catalog)
        ids = {s["id"] for s in inv}
        self.assertIn("viva", ids)
        self.assertNotIn("morta", ids)

    def test_pick_sample_indices_spreads_and_caps(self):
        self.assertEqual(sv.pick_sample_indices(0, 3), [])
        self.assertEqual(sv.pick_sample_indices(2, 3), [0, 1])
        self.assertEqual(sv.pick_sample_indices(4, 3), [1, 2, 3])
        self.assertEqual(sv.pick_sample_indices(7, 3), [1, 3, 5])

    def test_semantic_scores_use_sequential_samples_without_seek(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "anime_red_blue.mp4"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30, (160, 96))
            if not writer.isOpened():
                self.skipTest("encoder mp4v indisponivel no OpenCV")
            for i in range(120):  # 2 s vermelho, 2 s azul -> duas cenas
                frame = np.zeros((96, 160, 3), np.uint8)
                frame[:] = (0, 0, 255) if i < 60 else (255, 0, 0)
                writer.write(frame)
            writer.release()

            enc = _fake_semantic_encoder(frames_per_scene=2)
            with patch.object(si, "_hwdec_enabled", return_value=False), \
                 patch.object(si, "_log"):
                result = si.analisar_clipe(video, sample_interval=0.5, semantic_encoder=enc)

        self.assertEqual(result["analysis"]["semantic_sampling"], "sequential_samples")
        # cada amostra pontuada uma unica vez, na mesma passada; nenhum seek
        self.assertEqual(enc.calls, result["analysis"]["sample_count"])
        self.assertGreaterEqual(result["scene_count"], 2)
        for scene in result["scenes"]:
            self.assertIn(scene["semantic_frames"], (1, 2))
        self.assertEqual(result["scenes"][0]["actions"][0], "action:red")
        self.assertEqual(result["scenes"][-1]["actions"][0], "action:blue")

    def test_hw_decode_short_read_falls_back_to_software(self):
        meta = {"fps": 30.0, "frames": 100, "width": 1920, "height": 1080, "duration": 3.3333}
        samples = [
            {"time": 0.18, "features": {"hist_diff": 0.0}},
            {"time": 0.9, "features": {"hist_diff": 0.0}},
        ]
        calls = []

        def fake_pass(path, meta_, interval, encoder, hw):
            calls.append(hw)
            return samples, (40 if hw else 100), ("hw" if hw else "sw")

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"x")
            with patch.object(si, "_probe", return_value=meta), \
                 patch.object(si, "_sample_pass", side_effect=fake_pass), \
                 patch.object(si, "_hwdec_enabled", return_value=True), \
                 patch.object(si, "_log"):
                result = si.analisar_clipe(video)
        self.assertEqual(calls, [True, False])
        self.assertEqual(result["analysis"]["decoder"], "sw")
        self.assertEqual(result["analysis"]["frames_decoded"], 100)

    def test_catalog_persists_each_clip_and_resumes_after_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            clips = p / "clips_raw"
            clips.mkdir()
            (clips / "a.mp4").write_bytes(b"a")
            (clips / "b.mp4").write_bytes(b"bb")
            (p / "projeto.json").write_text("{}", encoding="utf-8")
            profile_hash = sv.profile_hash(sv.profile_from_manifest({}))

            def fake_entry(path, **_kwargs):
                return {
                    "file": path.name, "fingerprint": si._fingerprint(path),
                    "duration": 10.0, "eligible_for_semantic_selection": True,
                    "analysis": {
                        "sample_interval": si.DEFAULT_SAMPLE_INTERVAL,
                        "semantic_profile_hash": profile_hash, "decoder": "sw",
                    },
                    "scene_count": 1, "scenes": [{"id": f"{path.stem}_scene_001"}],
                }

            def interrupted(path, **kwargs):
                if path.name == "b.mp4":
                    raise KeyboardInterrupt  # timeout/kill no meio do catalogo
                return fake_entry(path, **kwargs)

            with patch.object(si, "analisar_clipe", side_effect=interrupted), \
                 patch.object(si, "_log"):
                with self.assertRaises(KeyboardInterrupt):
                    si.catalogar_projeto(p)
            partial = json.loads((p / "scene_intelligence.json").read_text(encoding="utf-8"))
            self.assertFalse(partial["complete"])
            self.assertEqual(sorted(partial["clips"]), ["a.mp4"])

            analyzed = []

            def resumed(path, **kwargs):
                analyzed.append(path.name)
                return fake_entry(path, **kwargs)

            with patch.object(si, "analisar_clipe", side_effect=resumed), \
                 patch.object(si, "_log"):
                final = si.catalogar_projeto(p)
            self.assertEqual(analyzed, ["b.mp4"])
            self.assertEqual(final["cache"], {"reused": 1, "analyzed": 1, "failed": 0})
            self.assertTrue(final["complete"])
            self.assertEqual(sorted(final["clips"]), ["a.mp4", "b.mp4"])


class SemanticSceneMatcherTests(unittest.TestCase):
    def test_kirin_requests_electric_scene(self):
        intent = sm.interpretar_texto("DO CÉU CAI O TROVÃO O KIRIN RUGIU", {})
        self.assertIn("electric", intent["concepts"])
        self.assertGreater(intent["tag_weights"]["electric"], 0.9)
        self.assertGreater(intent["target_intensity"], 0.8)

    def test_amaterasu_requests_fire_scene(self):
        intent = sm.interpretar_texto("CHAMAS DO AMATERASU NÃO VÃO SE APAGAR", {})
        self.assertIn("fire", intent["concepts"])
        self.assertGreater(intent["tag_weights"]["fire"], 0.9)

    def test_matcher_prefers_semantically_correct_scene(self):
        intent = sm.interpretar_texto("Kirin e trovão", {})
        scenes = [
            {
                "id": "fire", "clip": "a.mp4", "start": 0.0, "end": 4.0,
                "duration": 4.0, "clip_duration": 10.0,
                "tag_scores": {"fire": 1.0, "electric": 0.05, "energy": 0.2, "action": 0.6},
                "intensity": 0.84, "quality": 0.9,
            },
            {
                "id": "electric", "clip": "b.mp4", "start": 0.0, "end": 4.0,
                "duration": 4.0, "clip_duration": 10.0,
                "tag_scores": {"fire": 0.02, "electric": 0.96, "energy": 0.9, "action": 0.7},
                "intensity": 0.88, "quality": 0.82,
            },
        ]
        scene, breakdown = sm.escolher_cena(intent, scenes, 2.0, {}, [], {})
        self.assertEqual(scene["id"], "electric")
        self.assertGreater(breakdown["semantic"], 0.8)

    def test_timeline_special_segment_is_preserved(self):
        timeline = {
            "segments": [
                {
                    "type": "impact_typography", "start": 0.0, "end": 1.0,
                    "duration": 1.0, "clip": "impact.mp4", "src": 0.0,
                }
            ]
        }
        catalog = {
            "clips": {
                "anime.mp4": {
                    "eligible_for_semantic_selection": True,
                    "duration": 10.0,
                    "scenes": [{
                        "id": "s1", "start": 0.0, "end": 5.0, "duration": 5.0,
                        "tags": ["action"], "tag_scores": {"action": 1.0},
                        "intensity": 0.6, "quality": 0.8,
                    }],
                }
            }
        }
        result = sm.planejar_timeline(Path("."), timeline, catalog=catalog, manifesto={})
        seg = result["timeline"]["segments"][0]
        self.assertEqual(seg["clip"], "impact.mp4")
        self.assertNotIn("scene_match", seg)

    def test_segment_without_note_uses_overlapping_lyric(self):
        seg = {"start": 10.2, "end": 11.0, "note": ""}
        lyrics = [
            {"start": 10.0, "end": 11.4, "text": "Kirin corta o céu"},
            {"start": 11.5, "end": 12.4, "text": "Outra linha"},
        ]
        text, source = sm._text_for_segment(seg, lyrics)
        self.assertEqual(text, "Kirin corta o céu")
        self.assertEqual(source, "aligned_lyrics")

    def test_section_markers_never_become_lyric_lines(self):
        import sincronizar_letra as sl
        texto = "[Intro]\n\n[Verso 1]\nSatoru Gojo, o homem mais forte\n[Refrão]\nINFINITO\n[Refrão Final]\n"
        self.assertEqual(
            sl.extrair_linhas_suno(texto),
            ["Satoru Gojo, o homem mais forte", "INFINITO"],
        )

    def test_primary_segment_anchors_line_by_max_overlap(self):
        # Linha curta (0.5s) inteiramente dentro do 2o segmento vs linha longa
        # que cruza os dois. Cada linha deve ancorar no segmento de maior
        # sobreposicao, evitando que a linha longa sequestre os dois segmentos.
        segs = [
            {"type": "lyric", "start": 87.16, "end": 88.76},
            {"type": "lyric", "start": 88.76, "end": 89.36},
        ]
        linha_longa = {"start": 87.74, "end": 89.24, "text": "purple"}
        linha_curta = {"start": 88.86, "end": 89.36, "text": "red"}
        # Segmento 1 e primario da linha longa, nao da curta.
        self.assertTrue(sm._is_primary_segment_for_line(segs[0], linha_longa, segs))
        self.assertFalse(sm._is_primary_segment_for_line(segs[0], linha_curta, segs))
        # Segmento 2 e primario da linha curta (0.5 > 0.48 da longa).
        self.assertTrue(sm._is_primary_segment_for_line(segs[1], linha_curta, segs))
        self.assertFalse(sm._is_primary_segment_for_line(segs[1], linha_longa, segs))

    def test_segment_target_score_prefers_full_scene_scores(self):
        seg = {
            "scene_match": {
                "scene_semantic_scores": {"action:red": 0.62},
                "semantic_target_scores": {},
            }
        }
        self.assertAlmostEqual(sm._segment_target_score(seg, "action:red"), 0.62)
        # alvo ausente nos scores completos cai para 0.0 sem estourar
        self.assertEqual(sm._segment_target_score(seg, "action:blue"), 0.0)
        # compatibilidade: sem scores completos, usa o subconjunto antigo
        legacy = {"scene_match": {"semantic_target_scores": {"action:blue": 0.3}}}
        self.assertAlmostEqual(sm._segment_target_score(legacy, "action:blue"), 0.3)

    def test_overlapping_required_lines_both_covered(self):
        # Duas linhas obrigatorias sobrepostas (red e blue) devem ambas ser
        # atendidas quando existe cena forte para cada uma. Regressao do bug em
        # que a linha dominante roubava as duas cenas e a vizinha reprovava.
        manifesto = {
            "personagem": "Demo Hero",
            "audio_fonte": "audio.wav",
            "scene_semantics": {
                "enabled": True, "strict": True, "required_score": 0.14,
                "labels": [
                    {"id": "action:red", "kind": "action", "name": "Red",
                     "prompt": "red technique", "aliases": ["vermelho"],
                     "required": True},
                    {"id": "action:blue", "kind": "action", "name": "Blue",
                     "prompt": "blue technique", "aliases": ["azul"],
                     "required": True},
                ],
            },
        }
        catalog = {
            "schema_version": 1, "clips_total": 1, "eligible_clips": 1,
            "scenes_total": 2, "cache": {"reused": 1, "analyzed": 0, "failed": 0},
            "clips": {
                "anime.mp4": {
                    "eligible_for_semantic_selection": True, "duration": 30.0,
                    "scenes": [
                        {"id": "red_scene", "start": 1.0, "end": 6.0, "duration": 5.0,
                         "tags": ["action"], "tag_scores": {"action": 0.8},
                         "semantic_scores": {"action:red": 0.9, "action:blue": 0.02},
                         "intensity": 0.8, "quality": 0.85},
                        {"id": "blue_scene", "start": 10.0, "end": 15.0, "duration": 5.0,
                         "tags": ["action"], "tag_scores": {"action": 0.8},
                         "semantic_scores": {"action:red": 0.02, "action:blue": 0.9},
                         "intensity": 0.8, "quality": 0.85},
                    ],
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "qa").mkdir()
            (p / "projeto.json").write_text(json.dumps(manifesto), encoding="utf-8")
            # Duas linhas curtas obrigatorias, uma logo apos a outra.
            (p / "letra_sincronizada.json").write_text(json.dumps([
                {"start": 0.0, "end": 2.0, "text": "azul atraindo tudo"},
                {"start": 2.0, "end": 4.0, "text": "vermelho repelindo tudo"},
            ]), encoding="utf-8")
            (p / "timeline.json").write_text(json.dumps({
                "audio": "audio.wav", "audio_duration": 4.0,
                "segments": [
                    {"type": "lyric", "start": 0.0, "end": 2.0, "duration": 2.0,
                     "clip": "old.mp4", "src": 0.0},
                    {"type": "lyric", "start": 2.0, "end": 4.0, "duration": 2.0,
                     "clip": "old.mp4", "src": 0.0},
                ],
            }), encoding="utf-8")
            plan = sm.planejar_timeline(p, json.loads(
                (p / "timeline.json").read_text(encoding="utf-8")
            ), catalog=catalog, manifesto=manifesto)
        coverage = plan["coverage"]
        self.assertEqual(coverage["semantic_misses"], [])
        self.assertEqual(
            coverage["required_semantic_passes"],
            coverage["required_semantic_checks"],
        )

    def test_execute_is_idempotent_after_first_application(self):
        catalog = {
            "schema_version": 1,
            "clips_total": 1,
            "eligible_clips": 1,
            "scenes_total": 1,
            "cache": {"reused": 1, "analyzed": 0, "failed": 0},
            "clips": {
                "anime.mp4": {
                    "eligible_for_semantic_selection": True,
                    "duration": 12.0,
                    "scenes": [{
                        "id": "electric_01", "start": 1.0, "end": 6.0,
                        "duration": 5.0, "tags": ["electric", "energy"],
                        "tag_scores": {"electric": 0.98, "energy": 0.95, "action": 0.7},
                        "intensity": 0.88, "quality": 0.9,
                        "motion_direction": "right",
                    }],
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "qa").mkdir()
            (p / "projeto.json").write_text(json.dumps({
                "personagem": "Demo Hero", "audio_fonte": "audio.wav"
            }), encoding="utf-8")
            (p / "timeline.json").write_text(json.dumps({
                "audio": "audio.wav", "audio_duration": 4.0,
                "segments": [{
                    "type": "lyric", "start": 0.0, "end": 4.0,
                    "duration": 4.0, "clip": "old.mp4", "src": 0.0,
                    "note": "Kirin e trovão"
                }]
            }), encoding="utf-8")
            with patch.object(sm, "catalogar_projeto", return_value=catalog), \
                 patch.object(sm, "validar_timeline", return_value=[]):
                first = sm.executar(p)
                second = sm.executar(p)
            self.assertTrue(first["applied"])
            self.assertEqual(second["status"], "cached")
            timeline = json.loads((p / "timeline.json").read_text(encoding="utf-8"))
            self.assertEqual(timeline["segments"][0]["clip"], "anime.mp4")
            self.assertIn("scene_match", timeline["segments"][0])


class MarcarCenasPaginaTests(unittest.TestCase):
    """Asta (05/10/2026): o master reprovou com 3,0s de "pagina clara sem cor".
    O catalogo conhecia so a metade ESCURA do gate (tela preta -> dead_scene);
    fades brancos de clipe oficial e close de pele clara continuavam elegiveis e o
    Scene Matcher os escolhia. Agora os dois lados usam a mesma formula."""

    def _frames(self, n: int, cor) -> np.ndarray:
        arr = np.zeros((n, 90, 160, 3), dtype=np.uint8)
        arr[:] = cor
        return arr

    def test_fundo_branco_sem_detalhe_conta_como_pagina(self):
        import imagem as im
        self.assertTrue(bool(im.mascara_pagina(self._frames(4, (250, 250, 250))).all()))

    def test_flash_com_detalhe_nao_conta_como_pagina(self):
        # claro no geral, mas com traco preto: "detalhe" alto -> nao e pagina
        import imagem as im
        frames = self._frames(3, (250, 250, 250))
        frames[:, :, ::12, :] = 0
        self.assertFalse(bool(im.mascara_pagina(frames).any()))

    def test_cena_colorida_nao_conta_como_pagina(self):
        import imagem as im
        frames = self._frames(3, (60, 140, 220))
        frames[:, 10:80, 20:140, :] = (30, 30, 30)
        self.assertFalse(bool(im.mascara_pagina(frames).any()))

    def test_runs_pagina_ignora_quadro_isolado(self):
        dt = 1 / 6
        mascara = [False, True, False, True, True, False]
        janelas = si.runs_pagina(mascara, dt)
        self.assertEqual(len(janelas), 1)
        ini, fim = janelas[0]
        self.assertAlmostEqual(ini, 3 * dt, places=3)
        self.assertAlmostEqual(fim, 5 * dt, places=3)

    def test_cenas_alcancadas_pula_as_ja_mortas(self):
        cenas = [
            {"id": "branca", "start": 10.0, "end": 12.0},
            {"id": "longe", "start": 20.0, "end": 22.0},
            {"id": "morta", "start": 11.0, "end": 13.0, "dead_scene": True},
        ]
        ids = [c["id"] for c in si.cenas_alcancadas(cenas, [(10.5, 11.5)])]
        self.assertEqual(ids, ["branca"])

    def test_marcar_cenas_pagina_torna_dead_scene(self):
        import imagem as im
        catalog = {"clips": {"anime.mp4": {
            "scenes": [
                {"id": "a", "start": 0.0, "end": 2.0},
                {"id": "b", "start": 2.0, "end": 4.0},
            ],
        }}}
        # 6 quadros brancos a 6 fps = 1 s de pagina caindo em 0-1 s
        frames = self._frames(6, (252, 252, 252))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "clips_raw").mkdir()
            (p / "clips_raw" / "anime.mp4").touch()
            with patch.object(im, "_amostrar", return_value=frames):
                n = si.marcar_cenas_pagina(p, catalog)
        self.assertEqual(n, 1)
        self.assertEqual(catalog["cenas_pagina"], 1)
        self.assertTrue(catalog["clips"]["anime.mp4"]["scenes"][0]["dead_scene"])
        self.assertTrue(catalog["clips"]["anime.mp4"]["scenes"][0]["pagina"])
        self.assertNotIn(
            "dead_scene", catalog["clips"]["anime.mp4"]["scenes"][1]
        )


    def test_marcar_cenas_pagina_ignora_cena_escura(self):
        import imagem as im
        catalog = {"clips": {"anime.mp4": {
            "scenes": [{"id": "a", "start": 0.0, "end": 2.0,
                        "features": {"brightness": 0.02, "contrast": 0.05}}],
        }}}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "clips_raw").mkdir()
            (p / "clips_raw" / "anime.mp4").touch()
            # fonte escura: nada de pagina, e o criterio de clareza tambem nao bate
            with patch.object(im, "_amostrar", return_value=self._frames(6, (5, 5, 5))):
                n = si.marcar_cenas_pagina(p, catalog)
        self.assertEqual(n, 0)
        self.assertNotIn("dead_scene", catalog["clips"]["anime.mp4"]["scenes"][0])

    def test_marcar_cenas_pagina_tambem_pega_cena_clara_chapada(self):
        # close de olho do Asta: 0,03 de branco na fonte, 0,76 depois do grade do
        # render. So a mediacao na fonte nao pega; o chao de seguranca pega.
        import imagem as im
        catalog = {"clips": {"anime.mp4": {
            "scenes": [{"id": "olho", "start": 0.0, "end": 2.0,
                        "features": {"brightness": 0.62, "contrast": 0.255}}],
        }}}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "clips_raw").mkdir()
            (p / "clips_raw" / "anime.mp4").touch()
            with patch.object(im, "_amostrar", return_value=self._frames(6, (60, 140, 220))):
                n = si.marcar_cenas_pagina(p, catalog)
        self.assertEqual(n, 1)
        cena = catalog["clips"]["anime.mp4"]["scenes"][0]
        self.assertTrue(cena["dead_scene"])
        self.assertTrue(cena["pagina"])


class SceneSemanticsShapeTest(unittest.TestCase):
    """Regressao do incidente 2026-10-09: `scene_semantics` como LISTA de ids.

    O manifesto aceita a forma curta ("scene_semantics": ["megumi_fushiguro", ...]),
    mas `profile_from_manifest` fazia `cfg.get(...)` direto e estourava
    `AttributeError: 'list' object has no attribute 'get'`, derrubando `cenas-auto`
    (exit 1) na 4a etapa da esteira.
    """

    def test_lista_de_ids_vira_labels_validos(self):
        cfg = sv.scene_semantics_cfg({"scene_semantics": ["megumi_fushiguro", "shikigami"]})
        self.assertTrue(cfg["enabled"])
        ids = [r["id"] for r in cfg["labels"]]
        self.assertEqual(ids, ["megumi_fushiguro", "shikigami"])
        for r in cfg["labels"]:
            self.assertEqual(r["kind"], "concept")
            self.assertEqual(r["name"], r["id"])
            self.assertTrue(r["prompt"])          # prompt derivado do id
        # o prompt e legivel, nao o id cru com underscore
        self.assertEqual(cfg["labels"][0]["prompt"], "megumi fushiguro")

    def test_string_solta_tambem_e_aceita(self):
        cfg = sv.scene_semantics_cfg({"scene_semantics": "megumi_fushiguro"})
        self.assertEqual([r["id"] for r in cfg["labels"]], ["megumi_fushiguro"])

    def test_dict_canonico_passa_intacto(self):
        original = {"enabled": True, "strict": True, "required_score": 0.2,
                    "labels": [{"id": "action:red", "kind": "action", "name": "Red",
                                "prompt": "red technique"}]}
        cfg = sv.scene_semantics_cfg({"scene_semantics": original})
        self.assertIs(cfg, original)
        prof = sv.profile_from_manifest({"scene_semantics": original})
        self.assertEqual(prof["labels"][0]["id"], "action:red")
        self.assertEqual(prof["required_score"], 0.2)

    def test_lista_de_dicts_e_mesclada_com_ids(self):
        cfg = sv.scene_semantics_cfg({"scene_semantics": [
            "lobo_divino",
            {"id": "entity:megumi", "kind": "entity", "name": "Megumi",
             "prompt": "megumi fushiguro"},
        ]})
        self.assertEqual([r["id"] for r in cfg["labels"]], ["lobo_divino", "entity:megumi"])

    def test_ausente_ou_vazio_nao_estoura(self):
        for manifesto in ({}, {"scene_semantics": None}, {"scene_semantics": ""},
                          {"scene_semantics": []}, {"scene_semantics": [None, "  "]}):
            cfg = sv.scene_semantics_cfg(manifesto)
            self.assertIsInstance(cfg, dict)
            prof = sv.profile_from_manifest(manifesto)
            self.assertFalse(prof["enabled"])     # sem rotulo valido => desligado
            self.assertEqual(prof["labels"], [])

    def test_profile_from_manifest_aceita_a_forma_lista(self):
        """O caminho exato que estourava: catalogar_projeto -> profile_from_manifest."""
        prof = sv.profile_from_manifest({"scene_semantics": ["shadow_technique",
                                                             "domain_expansion"]})
        self.assertTrue(prof["enabled"])
        self.assertEqual([r["id"] for r in prof["labels"]],
                         ["shadow_technique", "domain_expansion"])
        self.assertIn("model", prof)              # defaults preservados

    def test_matcher_le_strict_e_required_score_da_forma_lista(self):
        manifesto = {"personagem": "Megumi", "audio_fonte": "a.wav",
                     "scene_semantics": ["megumi_fushiguro", "shikigami"]}
        # nao deve estourar; sem `strict` no manifesto assume False e o default de score
        self.assertFalse(sm._manifesto_strict(manifesto)
                         if hasattr(sm, "_manifesto_strict") else False)
        prof = sv.profile_from_manifest(manifesto)
        self.assertTrue(prof["enabled"])


class ImagemIaShapeTest(unittest.TestCase):
    """Regressao do incidente 2026-10-09: `imagem_ia` como LISTA de tags.

    Mesma armadilha do `scene_semantics`: o manifesto aceita a forma curta em
    lista, mas 8 consumidores faziam `bloco.get(...)` direto e estouravam
    `AttributeError: 'list' object has no attribute 'get'` (a etapa `titulos`
    foi a que caiu na esteira).
    """

    def test_lista_de_tags_vira_tags_estilo(self):
        cfg = sv.imagem_ia_cfg({"imagem_ia": ["jujutsu kaisen anime style",
                                              "dark blue shadow energy"]})
        self.assertEqual(cfg["tags_estilo"],
                         "jujutsu kaisen anime style, dark blue shadow energy")
        # os campos estruturados simplesmente nao existem => os consumidores caem
        # no fallback (personagem + anime), que e o comportamento desejado
        self.assertIsNone(cfg.get("tags_personagem"))
        self.assertIsNone(cfg.get("kanji"))

    def test_string_solta_tambem_e_aceita(self):
        cfg = sv.imagem_ia_cfg({"imagem_ia": "1boy, solo, megumi"})
        self.assertEqual(cfg["tags_estilo"], "1boy, solo, megumi")

    def test_dict_canonico_passa_intacto(self):
        original = {"tags_personagem": "1boy, solo, megumi", "kanji": ["影", "Megumi"],
                    "tags_alvos": {"shadow_technique": "dark shadows"}}
        cfg = sv.imagem_ia_cfg({"imagem_ia": original})
        self.assertIs(cfg, original)
        self.assertEqual(cfg["kanji"], ["影", "Megumi"])

    def test_ausente_vazio_ou_sujo_nao_estoura(self):
        for manifesto in ({}, {"imagem_ia": None}, {"imagem_ia": ""},
                          {"imagem_ia": []}, {"imagem_ia": [None, "   "]},
                          {"imagem_ia": 42}):
            cfg = sv.imagem_ia_cfg(manifesto)
            self.assertIsInstance(cfg, dict)
            self.assertNotIn("tags_estilo", cfg)   # nada util => sem campo

    def test_lista_vazia_de_prompt_nao_cria_tags(self):
        cfg = sv.imagem_ia_cfg({"imagem_ia": [" ", "", "  "]})
        self.assertEqual(cfg, {})

    def test_titulos_gera_arte_com_lista(self):
        """O caminho exato que estourou: titulos_pipeline.arte_titulo."""
        import tempfile
        from pathlib import Path

        import titulos_pipeline as tp

        manifest = {"personagem": "Megumi Fushiguro", "anime": "Jujutsu Kaisen",
                    "faixa": "Sombras",
                    "cor": {"destaque": "#2B3A55", "destaque_claro": "#8FB8DE"},
                    "imagem_ia": ["jujutsu kaisen anime style"]}
        with tempfile.TemporaryDirectory() as tmp:
            out = tp.arte_titulo(manifest, Path(tmp) / "tc.png")
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
