import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sincronizar_letra as sync
import revisao_master as rev
from _fixtures import projeto_sasuke_canonico


class CanonicalTranscriptContract(unittest.TestCase):
    def test_extract_suno_lines_ignores_performance_tags_and_preserves_accents(self):
        text = """[Chorus]\nEU SOU O VINGADOR MANGEKYŌ NO OLHAR\nCHAMAS DO AMATERASU NÃO VÃO SE APAGAR\nRinnegan supremo com seis tomoes\nDanzō caiu\n"""
        self.assertEqual(
            sync.extrair_linhas_suno(text),
            [
                "EU SOU O VINGADOR MANGEKYŌ NO OLHAR",
                "CHAMAS DO AMATERASU NÃO VÃO SE APAGAR",
                "Rinnegan supremo com seis tomoes",
                "Danzō caiu",
            ],
        )

    def test_canonical_vocabulary_fixes_required_names_and_diacritics(self):
        raw = "Mangekyo Amaterasu Susanoo Hokage Kirin Uchiha Rinnegan seis tomoes Danzō Chidori Kusanagi Itachi Naruto"
        # Fixture hermetica: nao le projetos/ real (suite verde num clone limpo).
        with projeto_sasuke_canonico(com_ato2=False) as (_raiz, projeto):
            manifesto = json.loads((projeto / "projeto.json").read_text(encoding="utf-8"))
        fixed = sync.corrigir_vocabulario_canonico(raw, sync.vocabulario_do_manifesto(manifesto))
        self.assertIn("Mangekyō", fixed)
        self.assertIn("seis tomoe", fixed)
        for name in ["Amaterasu", "Susanoo", "Hokage", "Kirin", "Uchiha", "Rinnegan", "Danzō", "Chidori", "Kusanagi", "Itachi", "Naruto"]:
            self.assertIn(name, fixed)

    def test_canonical_alignment_keeps_expected_spelling_not_asr_hallucination(self):
        lines = ["O Chidori perfura sua ilusão", "EU SOU O VINGADOR MANGEKYŌ NO OLHAR"]
        observations = [
            {
                "source": "mix",
                "words": [
                    {"word": "O", "start": 1.0, "end": 1.1, "probability": .95},
                    {"word": "jitori", "start": 1.1, "end": 1.5, "probability": .52},
                    {"word": "perfura", "start": 1.5, "end": 1.9, "probability": .9},
                    {"word": "sua", "start": 1.9, "end": 2.1, "probability": .9},
                    {"word": "ilusão", "start": 2.1, "end": 2.6, "probability": .9},
                    {"word": "eu", "start": 4.0, "end": 4.2, "probability": .9},
                    {"word": "sou", "start": 4.2, "end": 4.4, "probability": .9},
                    {"word": "o", "start": 4.4, "end": 4.5, "probability": .9},
                    {"word": "vingador", "start": 4.5, "end": 5.0, "probability": .9},
                    {"word": "manjeco", "start": 5.0, "end": 5.5, "probability": .4},
                    {"word": "no", "start": 5.5, "end": 5.7, "probability": .9},
                    {"word": "olhar", "start": 5.7, "end": 6.0, "probability": .9},
                ],
            }
        ]
        result = sync.construir_transcricao_canonica(lines, observations)
        words = [w for line in result["lines"] for w in line["words"]]
        self.assertEqual([w["word"] for w in words], "O Chidori perfura sua ilusão EU SOU O VINGADOR MANGEKYŌ NO OLHAR".split())
        canonical_text = " ".join(w["word"] for w in words).lower()
        self.assertNotIn("jitori", canonical_text)
        self.assertNotIn("manjeco", canonical_text)
        self.assertIn("jitori", json.dumps(words[1]["evidence"], ensure_ascii=False).lower())
        self.assertTrue(all(w["end"] > w["start"] for w in words))
        self.assertTrue(all(a["start"] <= b["start"] for a, b in zip(words, words[1:])))
        self.assertIn(words[1]["confidence"], {"high", "medium", "low", "gap"})
        self.assertTrue(words[1]["evidence"])

    def test_unmatched_expected_word_is_explicit_gap_not_fabricated_certainty(self):
        result = sync.construir_transcricao_canonica(
            ["Kirin rugiu"],
            [{"source": "vocal", "words": [{"word": "rugiu", "start": 2.0, "end": 2.4, "probability": .8}]}],
        )
        kirin = result["lines"][0]["words"][0]
        self.assertEqual(kirin["confidence"], "gap")
        self.assertIsNone(kirin["start"])
        self.assertFalse(kirin["identified_in_audio"])


class PreviewV2Contract(unittest.TestCase):
    def test_phrase_blocks_are_natural_and_cover_four_complete_lines(self):
        cfg = {
            "lyrics": [
                "Olhos vermelhos na escuridão",
                "Você não conhece a dor de perder tudo em uma noite",
                "Eu cortei meus laços",
                "E agora o mundo vai queimar",
            ],
            "phrase_blocks": [
                "OLHOS VERMELHOS", "NA ESCURIDÃO",
                "VOCÊ NÃO CONHECE A DOR", "DE PERDER TUDO EM UMA NOITE",
                "EU CORTEI MEUS LAÇOS", "E AGORA O MUNDO VAI QUEIMAR",
            ],
        }
        rev.validar_blocos_previa(cfg)
        forbidden = {"VOCÊ", "A DOR DE", "EM UMA"}
        self.assertFalse(forbidden.intersection(cfg["phrase_blocks"]))

    def test_pause_has_no_persistent_backing_or_lateral_template(self):
        ass = rev.gerar_ass_previa_v2(
            [{"word": "Olhos", "start": 12.4, "end": 13.0}],
            origin=12.0,
            duration=22.0,
            phrase_blocks=["OLHOS"],
        )
        self.assertNotIn("m 160 800 b", ass)
        self.assertNotIn("m 1760 800 b", ass)
        backing_events = [line for line in ass.splitlines() if ",Backing," in line]
        self.assertEqual(len(backing_events), 1)
        self.assertIn("0:00:00.40", backing_events[0])
        self.assertLess(float(rev.tc_seconds(backing_events[0].split(",")[2])), 2.0)

    def test_word_events_overlap_one_frame_to_prevent_boundary_flicker(self):
        ass = rev.gerar_ass_previa_v2(
            [
                {"word": "Agora", "start": 30.90, "end": 31.30},
                {"word": "o", "start": 31.30, "end": 31.56},
            ],
            origin=12.0,
            duration=22.0,
            phrase_blocks=["AGORA O"],
        )
        core = [line for line in ass.splitlines() if line.startswith("Dialogue: 2,") and ",Lyric," in line]
        self.assertEqual(len(core), 2)
        first_end = rev.tc_seconds(core[0].split(",")[2])
        second_start = rev.tc_seconds(core[1].split(",")[1])
        self.assertGreaterEqual(first_end - second_start, 1 / 30)


class PreviewV3Contract(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "version": 3,
            "start": 12.0,
            "end": 34.0,
            "lyrics": [
                "Olhos vermelhos na escuridão",
                "Você não conhece a dor de perder tudo em uma noite",
                "Eu cortei meus laços",
                "E agora o mundo vai queimar",
            ],
            "phrase_blocks": [
                "OLHOS VERMELHOS", "NA ESCURIDÃO",
                "VOCÊ NÃO CONHECE A DOR", "DE PERDER TUDO EM UMA NOITE",
                "EU CORTEI MEUS LAÇOS", "E AGORA O MUNDO VAI QUEIMAR",
            ],
            "shots": [
                {"start": 0, "end": 2, "clip": "a.mp4", "src": 0, "semantic": "sharingan", "fx": "eye_pulse"},
                {"start": 2, "end": 4, "clip": "a.mp4", "src": 5, "semantic": "sharingan", "fx": "eye_pulse"},
                {"start": 4, "end": 6, "clip": "a.mp4", "src": 10, "semantic": "darkness", "fx": "silhouette_rim"},
                {"start": 6, "end": 9, "clip": "a.mp4", "src": 15, "semantic": "family_loss", "fx": "loss_sweep"},
                {"start": 9, "end": 12, "clip": "a.mp4", "src": 20, "semantic": "family_loss", "fx": "loss_sweep"},
                {"start": 12, "end": 15, "clip": "a.mp4", "src": 25, "semantic": "loneliness", "fx": "silhouette_rim"},
                {"start": 15, "end": 17, "clip": "a.mp4", "src": 30, "semantic": "naruto_break", "fx": "bond_streak"},
                {"start": 17, "end": 19, "clip": "a.mp4", "src": 35, "semantic": "naruto_break", "fx": "bond_streak"},
                {"start": 19, "end": 22, "clip": "a.mp4", "src": 40, "semantic": "amaterasu", "fx": "fire_lightwrap"},
            ],
        }

    def test_v3_requires_eight_unique_windows_and_semantic_arc(self):
        self.assertTrue(rev.validar_previa_v3(self.cfg))

    def test_v3_rejects_repeated_source_window(self):
        self.cfg[1 if False else "shots"][1]["src"] = 0
        with self.assertRaisesRegex(ValueError, "source window"):
            rev.validar_previa_v3(self.cfg)

    def test_v3_environmental_fx_graph_uses_rgb_screen_and_scene_specific_motion(self):
        for fx, marker in [
            ("eye_pulse", "ellipse"),
            ("loss_sweep", "gradient sweep"),
            ("silhouette_rim", "rim"),
            ("bond_streak", "streak"),
            ("fire_lightwrap", "lightwrap"),
        ]:
            graph = rev.grafo_neon_ambiental(fx, 2.5)
            self.assertIn("format=gbrp", graph["filter"])
            self.assertIn("blend=all_mode=screen", graph["filter"])
            self.assertIn(marker, graph["description"])


class PreviewV4Contract(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "version": 4, "start": 12.0, "end": 34.0,
            "lyrics": [
                "Olhos vermelhos na escuridão",
                "Você não conhece a dor de perder tudo em uma noite",
                "Eu cortei meus laços",
                "E agora o mundo vai queimar",
            ],
            "phrase_blocks": [
                "OLHOS VERMELHOS", "NA ESCURIDÃO",
                "VOCÊ NÃO CONHECE A DOR", "DE PERDER TUDO EM UMA NOITE",
                "EU CORTEI MEUS LAÇOS", "E AGORA O MUNDO VAI QUEIMAR",
            ],
            "shots": [
                {"start": 0, "end": 2, "clip": "a.mp4", "src": 0, "semantic": "sharingan", "fx": "eye_pair"},
                {"start": 2, "end": 4, "clip": "a.mp4", "src": 5, "semantic": "sharingan", "fx": "eye_pair"},
                {"start": 4, "end": 6, "clip": "a.mp4", "src": 10, "semantic": "darkness", "fx": "silhouette_rim"},
                {"start": 6, "end": 8, "clip": "a.mp4", "src": 15, "semantic": "child", "fx": "silhouette_rim"},
                {"start": 8, "end": 10, "clip": "a.mp4", "src": 20, "semantic": "family_loss", "fx": "loss_rim"},
                {"start": 10, "end": 12, "clip": "a.mp4", "src": 25, "semantic": "family_loss", "fx": "loss_rim"},
                {"start": 12, "end": 15, "clip": "a.mp4", "src": 30, "semantic": "loneliness", "fx": "silhouette_rim"},
                {"start": 15, "end": 17, "clip": "a.mp4", "src": 35, "semantic": "naruto_break", "fx": "bond_crack"},
                {"start": 17, "end": 19, "clip": "a.mp4", "src": 40, "semantic": "destruction", "fx": "silhouette_rim"},
                {"start": 19, "end": 22, "clip": "a.mp4", "src": 45, "semantic": "amaterasu", "fx": "fire_lightwrap"},
            ],
        }

    def test_v4_requires_nine_unique_windows_and_child_to_destruction_arc(self):
        self.assertTrue(rev.validar_previa_v4(self.cfg))

    def test_v4_subtitle_baseline_is_safe_and_phrase_not_split_by_scene_cuts(self):
        words = [
            {"word": w, "start": 12.4 + i * .25, "end": 12.62 + i * .25}
            for i, w in enumerate("Você não conhece a dor de perder tudo em uma noite".split())
        ]
        ass = rev.gerar_ass_previa_v4(words, 12.0, 4.0, [
            "VOCÊ NÃO CONHECE A DOR", "DE PERDER TUDO EM UMA NOITE"
        ])
        positions = [int(x) for x in re.findall(r"\\pos\(960,(\d+)\)", ass)]
        self.assertTrue(positions and all(780 <= y <= 820 for y in positions))
        self.assertNotIn("875", ass)
        # One continuous crisp core per phrase block; scene and word boundaries never
        # duplicate the full phrase. Active-word glow lives on a separate layer.
        core = [line for line in ass.splitlines() if line.startswith("Dialogue: 2,")]
        self.assertEqual(len(core), 2)
        visible = [" ".join(re.sub(r"\{[^}]*\}", "", line).replace(r"\N", " ").split()) for line in core]
        self.assertIn("VOCÊ NÃO CONHECE A DOR", visible[0])
        self.assertIn("DE PERDER TUDO EM UMA NOITE", visible[1])
        glow = [line for line in ass.splitlines() if line.startswith("Dialogue: 1,")]
        self.assertEqual(len(glow), 2)
        for core_line, glow_line in zip(core, glow):
            core_text = " ".join(re.sub(r"\{[^}]*\}", "", core_line).replace(r"\N", " ").split())
            glow_text = " ".join(re.sub(r"\{[^}]*\}", "", glow_line).replace(r"\N", " ").split())
            self.assertEqual(core_text.split(",,")[-1], glow_text.split(",,")[-1])

    def test_v4_eye_fx_uses_two_small_radial_ellipses_not_horizontal_face_flare(self):
        graph = rev.grafo_neon_v4("eye_pair", 2.0, [[760, 405], [1040, 405]])
        self.assertEqual(graph["filter"].count("exp(-pow((X-"), 2)
        self.assertNotIn("/430", graph["filter"])
        self.assertIn("/55", graph["filter"])
        self.assertIn("gblur=sigma=6", graph["filter"])
        self.assertNotIn("horizontal", graph["description"])
        self.assertIn("two small", graph["description"])

    def test_v4_loss_and_bond_fx_are_edge_or_diagonal_without_rectangular_scan(self):
        loss = rev.grafo_neon_v4("loss_rim", 2.0)["filter"]
        bond = rev.grafo_neon_v4("bond_crack", 2.0, [820, 250, 280, 600])["filter"]
        self.assertIn("edgedetect", loss)
        self.assertNotIn("T/", loss)
        self.assertIn("X-0.77*Y", bond)
        self.assertNotIn("Y-(610", bond)


class PreviewV5Contract(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "version": 5, "start": 12.0, "end": 34.0,
            "lyrics": ["Olhos vermelhos na escuridão", "Você não conhece a dor de perder tudo em uma noite", "Eu cortei meus laços", "E agora o mundo vai queimar"],
            "phrase_blocks": ["OLHOS VERMELHOS", "NA ESCURIDÃO", "VOCÊ NÃO CONHECE A DOR", "DE PERDER TUDO EM UMA NOITE", "EU CORTEI MEUS LAÇOS", "E AGORA O MUNDO VAI QUEIMAR"],
            "shots": [
                {"start": 0, "end": 2.2, "clip": "a.mp4", "src": 0, "semantic": "sharingan", "fx": "eye_pair", "fx_region": [[810, 450], [1110, 450]], "eye_regions": [[760, 405, 100, 70], [1060, 405, 100, 70]]},
                {"start": 2.2, "end": 5, "clip": "a.mp4", "src": 5, "semantic": "darkness", "fx": "silhouette_rim", "scene_category": "interior_dark", "measured_luma": 28.0},
                {"start": 5, "end": 5.9, "clip": "a.mp4", "src": 10, "semantic": "darkness", "fx": "silhouette_rim", "scene_category": "cavern_dark", "measured_luma": 31.0},
                {"start": 5.9, "end": 7.2, "clip": "a.mp4", "src": 15, "semantic": "child", "fx": "loss_rim"},
                {"start": 7.2, "end": 8.6, "clip": "a.mp4", "src": 20, "semantic": "family_loss", "fx": "loss_rim"},
                {"start": 8.6, "end": 10, "clip": "a.mp4", "src": 25, "semantic": "family_loss", "fx": "loss_rim"},
                {"start": 10, "end": 11.5, "clip": "a.mp4", "src": 30, "semantic": "loneliness", "fx": "silhouette_rim"},
                {"start": 11.5, "end": 13.2, "clip": "a.mp4", "src": 35, "semantic": "destruction", "fx": "silhouette_rim"},
                {"start": 13.2, "end": 15.6, "clip": "a.mp4", "src": 40, "semantic": "naruto_break", "fx": "bond_crack", "fx_region": [960, 30, 80, 190], "crack_alpha": 0.95, "crack_amplitude": 255},
                {"start": 15.6, "end": 18.8, "clip": "a.mp4", "src": 45, "semantic": "destruction", "fx": "silhouette_rim"},
                {"start": 18.8, "end": 22, "clip": "a.mp4", "src": 50, "semantic": "amaterasu", "fx": "fire_lightwrap"},
            ],
        }

    def test_v5_darkness_is_measured_and_categorically_dark(self):
        self.assertTrue(rev.validar_previa_v5(self.cfg))
        darkness = [s for s in self.cfg["shots"] if s["semantic"] == "darkness"]
        self.assertTrue(all(s["scene_category"] in {"interior_dark", "night", "cavern_dark"} for s in darkness))
        self.assertTrue(all(s["measured_luma"] <= 45 for s in darkness))

    def test_v5_eye_centers_are_explicit_and_inside_expected_regions(self):
        self.assertTrue(rev.validar_previa_v5(self.cfg))
        eye = self.cfg["shots"][0]
        for (cx, cy), (x, y, w, h) in zip(eye["fx_region"], eye["eye_regions"]):
            self.assertTrue(x <= cx <= x + w and y <= cy <= y + h)
        graph = rev.grafo_neon_v5("eye_pair", 2.0, eye["fx_region"])
        self.assertIn("/8", graph["filter"])
        self.assertIn("upper", graph["filter"])
        self.assertIn("lower", graph["filter"])
        self.assertIn("255*", graph["filter"])
        self.assertIn("core", graph["description"])
        self.assertIn("eyelid", graph["description"])

    def test_v5_crack_has_visible_animated_branched_energy_in_mask(self):
        self.assertTrue(rev.validar_previa_v5(self.cfg))
        shot = self.cfg["shots"][8]
        graph = rev.grafo_neon_v5("bond_crack", 2.4, shot["fx_region"], shot)
        self.assertIn("sin(2*PI*T", graph["filter"])
        self.assertGreaterEqual(shot["crack_alpha"], .8)
        self.assertGreaterEqual(shot["crack_amplitude"], 200)
        self.assertIn("gblur=sigma=6", graph["filter"])
        self.assertIn("230*", graph["filter"])
        self.assertIn("/4.2", graph["filter"])
        self.assertIn("0.94+0.06*sin", graph["filter"])
        self.assertIn("g='180*", graph["filter"])
        self.assertIn("branched", graph["description"])


if __name__ == "__main__":
    unittest.main()
