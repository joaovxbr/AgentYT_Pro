"""Laboratorio de tipografia em movimento: funcoes puras (sem GPU, rembg ou ffmpeg)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import motion_lab as ml  # noqa: E402

TIMELINE = {"segments": [
    {"type": "lyric", "start": 0.0, "end": 2.0, "clip": "a.mp4", "src": 100.0},
    {"type": "vx_graphics_auto", "start": 2.0, "end": 3.0, "clip": "vx_graphics_auto/x.mp4", "src": 0.0},
    {"type": "lyric", "start": 3.0, "end": 6.0, "clip": "b.mp4", "src": 50.0},
]}


class TrechosTests(unittest.TestCase):
    def test_window_maps_to_source_times(self):
        tr = ml.trechos_fonte(TIMELINE, 1.0, 4.0)
        # take gerado (2..3) vira continuacao do plano real anterior
        self.assertEqual(tr[0], {"clip": "a.mp4", "src": 101.0, "t_ini": 0.0, "t_fim": 2.0})
        self.assertEqual(tr[1], {"clip": "b.mp4", "src": 50.0, "t_ini": 2.0, "t_fim": 4.0})

    def test_generated_takes_are_never_background(self):
        self.assertFalse(ml.e_real(TIMELINE["segments"][1]))
        self.assertTrue(all(t["clip"] != "vx_graphics_auto/x.mp4" for t in ml.trechos_fonte(TIMELINE, 0, 6)))


class TextoTests(unittest.TestCase):
    def test_dominant_word_prefers_names_then_longest(self):
        ln = {"text": "eu sou o Gojo e o infinito me protege"}
        self.assertEqual(ml.palavra_dominante(ln, ["Satoru", "Gojo"]), "GOJO")
        self.assertEqual(ml.palavra_dominante(ln, []), "INFINITO")
        self.assertEqual(ml.palavra_dominante({"text": "x", "keyword": "roxo"}), "ROXO")

    def test_names_from_manifest(self):
        m = {"personagem": "Satoru Gojo", "anime": "Jujutsu Kaisen",
             "vocabulario": {"termos": ["Hollow Purple"]}}
        self.assertEqual(ml.nomes_do_manifesto(m), ["Satoru", "Gojo", "Jujutsu", "Kaisen", "Hollow", "Purple"])

    def test_kanji_lookup_accent_insensitive(self):
        mapa = {"infinito": "無限", "mais forte": "最強", "dominio": "領域"}
        self.assertEqual(ml.kanji_para("INFINITO", mapa, "力"), "無限")
        self.assertEqual(ml.kanji_para("DOMÍNIO", mapa, "力"), "領域")
        self.assertEqual(ml.kanji_para("NADA", mapa, "力"), "力")

    def test_active_line_holds_briefly(self):
        linhas = ml.linhas_no_trecho([{"start": 10, "end": 11, "text": "a", "words": []},
                                      {"start": 12, "end": 13, "text": "b", "words": []}], 9.0, 5.0)
        self.assertEqual(linhas[0]["start"], 1.0)
        self.assertEqual(ml.linha_ativa(linhas, 1.5)["text"], "a")
        self.assertEqual(ml.linha_ativa(linhas, 2.3)["text"], "a")    # segura 0.45s
        self.assertIsNone(ml.linha_ativa(linhas, 2.8))
        self.assertEqual(ml.linha_ativa(linhas, 3.2)["text"], "b")


class CorTests(unittest.TestCase):
    def test_dominant_hue_is_not_the_average(self):
        import numpy as np
        azul = np.tile([0.1, 0.2, 1.0], (70, 1))
        vermelho = np.tile([1.0, 0.1, 0.1], (30, 1))
        h = ml.matiz_dominante(np.vstack([azul, vermelho]).astype(np.float32))
        self.assertTrue(0.58 < h < 0.7, h)   # azul (~0.64), nao a media esverdeada/cinza

    def test_contact_sheet_and_coverage(self):
        mins = [Image.new("RGB", (10, 6), (k * 50, 0, 0)) for k in range(4)]
        self.assertEqual(ml.folha_img(mins).size, (20, 12))
        vazio = [Image.new("L", (96, 54), 0)] * 3
        self.assertIn("quase vazio", ml.cobertura_recorte(vazio)["aviso"])
        meio = Image.new("L", (96, 54), 0); meio.paste(255, (0, 0, 30, 54))
        self.assertEqual(ml.cobertura_recorte([meio])["aviso"], "")


class CorPelaLetraTests(unittest.TestCase):
    CORES = ml.carregar_cfg()["cores"]

    def test_color_follows_the_sung_concept(self):
        c = self.CORES
        self.assertEqual(ml.cor_da_letra("Azul atraindo, tudo convergiu pra mim", c), c["azul"])
        self.assertEqual(ml.cor_da_letra("Vermelho repelindo, explodindo o que tem", c), c["vermelho"])
        self.assertEqual(ml.cor_da_letra("Nada sobra quando o Purple é liberado", c), c["purple"])
        self.assertEqual(ml.cor_da_letra("Domínio Expansivo, o vazio infinito", c), c["dominio"])  # 1a que aparece
        self.assertEqual(ml.cor_da_letra("a chama vermelha", c), c["chama"])
        self.assertEqual(ml.cor_da_letra("cabelo avermelhado", c), None)     # so comeco de palavra
        self.assertIsNone(ml.cor_da_letra("eu sou o mais forte", c))

    def test_context_priority_and_smooth_transition(self):
        cfg = ml.carregar_cfg()
        linhas = [{"text": "Azul atraindo", "start": 0.0, "end": 1.0, "words": []},
                  {"text": "Vermelho repelindo", "start": 2.0, "end": 3.0, "words": []}]
        ctx = ml.Contexto(cfg, linhas, 3.0, (10, 200, 10), [], [])
        self.assertEqual(ctx.cor_alvo(0.5), ml._rgb(cfg["cores"]["azul"]))
        self.assertEqual(ctx.cor_alvo(2.0), ml._rgb(cfg["cores"]["vermelho"]))
        self.assertEqual(ctx.cor_alvo(1.7), (10, 200, 10))                  # entre linhas: cor da cena
        ctx.atualizar_cor(0.5)
        self.assertEqual(ctx.acento, ml._rgb(cfg["cores"]["azul"]))
        ctx.atualizar_cor(2.0)                                              # transicao, nao salto
        self.assertNotIn(ctx.acento, (ml._rgb(cfg["cores"]["azul"]), ml._rgb(cfg["cores"]["vermelho"])))
        for _ in range(20):
            ctx.atualizar_cor(2.0)
        self.assertEqual(ctx.acento, ml._rgb(cfg["cores"]["vermelho"]))
        take = ml.Contexto(cfg, [], 2.0, (10, 200, 10), [], [], palavra="PURPLE")
        self.assertEqual(take.cor_alvo(0.3), ml._rgb(cfg["cores"]["purple"]))  # palavra do take vence


class BibliotecaTests(unittest.TestCase):
    """assets/design/biblioteca_motion.json e a fonte unica: status e regras de cada efeito."""

    def test_catalog_matches_code(self):
        lib = ml.biblioteca()["estilos"]
        self.assertEqual(set(lib), set(ml.ESTILOS), "todo estilo do codigo precisa estar na biblioteca e vice-versa")
        for nome, info in lib.items():
            self.assertIn(info["status"], ml.STATUS_VALIDOS, nome)
            self.assertIn(info["tipo"], {"palavra", "linha", "card"}, nome)
            self.assertTrue(set(info.get("gatilhos") or {}) <= ml.CATEGORIAS, nome)
            self.assertTrue(info.get("gatilhos"), f"{nome} sem gatilho: nunca seria escolhido")
            for campo in ("descricao", "quando_usar", "evitar"):
                self.assertTrue(info.get(campo), f"{nome} sem '{campo}' (a biblioteca precisa explicar o uso)")
        self.assertEqual(ml.ESTILOS_DE_LINHA, {n for n, i in lib.items() if i["tipo"] == "linha"})

    def test_cerebro_doc_is_in_sync_with_library(self):
        doc = (ROOT / "cerebro" / "biblioteca_motion.md").read_text(encoding="utf-8")
        self.assertEqual(doc.strip(), ml.documentacao_biblioteca().strip(),
                         "cerebro/biblioteca_motion.md defasado: rode `estudio.py cerebro`")

    def test_visual_appearance_drops_names_and_generic_tags(self):
        man = {"personagem": "Satoru Gojo", "anime": "Jujutsu Kaisen", "imagem_ia": {"tags_personagem":
               "1boy, solo, gojo satoru, jujutsu kaisen, white hair, blue eyes, blindfold, tall, male focus"}}
        self.assertEqual(ml.aparencia_protagonista(man), "white hair, blue eyes, blindfold")
        self.assertIsNone(ml.aparencia_protagonista({"personagem": "X"}))

    def test_visual_score_overrides_scene_labels(self):
        import graphic_auto_pipeline as gfx
        item = _cand(name_hit=True, line_end=20)
        cfg = dict(gfx.DEFAULT_CONFIG, motion_estilos=["contorno_energia"])
        base = {"segments": [{"type": "lyric", "start": 0.0, "end": 30.0, "clip": "a.mp4", "src": 0.0}]}
        com = gfx.aplicar_motion_real([item], base, cfg, 60.0, {}, False, None, lambda i, d: 0.9)[0]
        self.assertEqual(com["spec"]["estilo"], "contorno_energia")
        sem = gfx.aplicar_motion_real([item], base, cfg, 60.0, {}, False, None, lambda i, d: 0.1)[0]
        self.assertNotEqual(sem.get("spec", {}).get("estilo"), "contorno_energia")

    def test_kanji_is_disabled_and_never_chosen(self):
        import graphic_auto_pipeline as gfx
        self.assertEqual(ml.status_de("kanji_fundo"), "desativado")
        self.assertNotIn("kanji_fundo", ml.ativos())
        prod = gfx.DEFAULT_CONFIG["motion_estilos"]
        for hist in ([], ["card_cenario"], ["card_cenario", "eco_repeticao", "card_cena_escura"]):
            self.assertNotEqual(ml.escolher_estilo(_cand(line_end=20), hist, prod), "kanji_fundo")

    def test_energy_outline_only_with_protagonist(self):
        self.assertIn("protagonista", ml.exige("contorno_energia"))
        prod = list(ml.ESTILOS)
        hist = ["atras_personagem", "card_cena_escura", "letterbox_cinema"]
        sem = [ml.escolher_estilo(_cand(name_hit=True, line_end=20), hist[:k], prod) for k in range(4)]
        self.assertNotIn("contorno_energia", sem)
        self.assertNotIn("card_retrato", sem)
        com = ml.escolher_estilo(_cand(name_hit=True, line_end=20, protagonista=True), ["atras_personagem"], prod)
        self.assertEqual(com, "card_retrato")                      # nome + protagonista: retrato vem logo
        com2 = ml.escolher_estilo(_cand(name_hit=True, line_end=20, protagonista=True),
                                  ["atras_personagem", "card_retrato"], prod)
        self.assertEqual(com2, "contorno_energia")

    def test_protagonist_detection_from_scene_scores(self):
        import graphic_auto_pipeline as gfx
        man = {"personagem": "Satoru Gojo", "scene_semantics": {"labels": [
            {"id": "entity:sukuna", "kind": "entity", "name": "Ryomen Sukuna", "prompt": "Sukuna"},
            {"id": "entity:gojo", "kind": "entity", "name": "Satoru Gojo", "prompt": "Satoru Gojo from JJK"}]}}
        self.assertEqual(gfx.entidade_protagonista(man), "entity:gojo")
        def seg(a, b, gojo, sukuna):
            return {"start": a, "end": b, "scene_match": {"scene_semantic_scores":
                                                          {"entity:gojo": gojo, "entity:sukuna": sukuna}}}
        base = {"segments": [seg(0, 5, 0.8, 0.1), seg(5, 10, 0.22, 0.67), seg(10, 15, 0.5, 0.2)]}
        self.assertTrue(gfx.protagonista_em_cena(base, 1, 4, "entity:gojo"))
        self.assertFalse(gfx.protagonista_em_cena(base, 6, 9, "entity:gojo"))      # Sukuna em cena
        self.assertFalse(gfx.protagonista_em_cena(base, 4, 6, "entity:gojo"))      # pega plano do Sukuna
        self.assertFalse(gfx.protagonista_em_cena({"segments": [{"start": 0, "end": 5}]}, 1, 4, "entity:gojo"))


class RetratoTests(unittest.TestCase):
    """Regressao 30/09: card_retrato pegou um ombro em close (59 % do quadro, desfocado) e o titulo sumiu."""

    @staticmethod
    def _quadro_com_detalhe(w=640, h=360):
        import numpy as np
        rng = np.random.default_rng(1)
        return (rng.integers(0, 255, (h, w, 3))).astype(np.uint8)   # textura forte = nitido

    @staticmethod
    def _mascara(caixa, w=640, h=360):
        m = Image.new("L", (w, h), 0)
        m.paste(255, caixa)
        return m

    def test_giant_blurry_close_is_rejected(self):
        import numpy as np
        liso = np.full((360, 640, 3), 180, np.uint8)
        gigante = self._mascara((0, 0, 640, 360))
        a = ml.avaliar_retrato(gigante, self._quadro_com_detalhe())
        self.assertFalse(a["valido"])
        medio = self._mascara((220, 60, 420, 360))
        self.assertFalse(ml.avaliar_retrato(medio, liso)["valido"])          # desfocado/sem detalhe
        self.assertTrue(ml.avaliar_retrato(medio, self._quadro_com_detalhe())["valido"])

    def test_best_frame_and_text_side(self):
        q = self._quadro_com_detalhe()
        mascaras = [self._mascara((0, 0, 640, 360)), self._mascara((220, 60, 420, 360)), self._mascara((0, 0, 20, 20))]
        self.assertEqual(ml.escolher_quadro_retrato(mascaras, [q, q, q]), 1)
        self.assertIsNone(ml.escolher_quadro_retrato([mascaras[0], mascaras[2]], [q, q]))
        self.assertLess(ml.tapa_texto(mascaras[1]), ml.RETRATO_MAX_TAPA_TEXTO)   # personagem no meio: texto atras
        largo = self._mascara((40, 70, 600, 360))
        self.assertGreater(ml.tapa_texto(largo), ml.RETRATO_MAX_TAPA_TEXTO)     # taparia o titulo: texto na frente


class MovimentoTests(unittest.TestCase):
    def test_tracking_follows_camera_clamps_and_resets_on_cut(self):
        deltas = [(0, 0)] + [(10, 0)] * 30 + [(0, 0)] * 5
        offs = ml.acumular_tracking(deltas, cortes={31}, fator=1.0, suavizacao=0.5, max_px=40)
        self.assertGreater(offs[10][0], 5)
        self.assertLessEqual(max(o[0] for o in offs), 40)
        self.assertLess(abs(offs[34][0]), abs(offs[30][0]))       # corte zera e suaviza


class ComposicaoTests(unittest.TestCase):
    def test_text_goes_behind_subject(self):
        plate = Image.new("RGB", (4, 1), (10, 10, 10))
        sujeito = Image.new("RGB", (4, 1), (200, 0, 0))
        mascara = Image.new("L", (4, 1), 0)
        mascara.putpixel((0, 0), 255)                            # personagem so no pixel 0
        texto = Image.new("RGBA", (4, 1), (0, 0, 255, 255))
        atras = ml.compor_camadas(plate, sujeito, mascara, texto, None)
        self.assertEqual(atras.getpixel((0, 0)), (200, 0, 0))     # personagem cobre o texto
        self.assertEqual(atras.getpixel((1, 0)), (0, 0, 255))     # texto sobre o fundo
        frente = ml.compor_camadas(plate, sujeito, mascara, None, texto)
        self.assertEqual(frente.getpixel((0, 0)), (0, 0, 255))    # texto da frente cobre tudo

    def test_every_style_renders_without_footage(self):
        cfg = ml.carregar_cfg()
        cfg["largura"], cfg["altura"] = 640, 360
        linhas = [{"text": "o infinito do Gojo", "start": 0.1, "end": 1.2, "keyword": None,
                   "words": [{"text": "o", "start": 0.1, "end": 0.2}, {"text": "infinito", "start": 0.2, "end": 0.7},
                             {"text": "do", "start": 0.7, "end": 0.8}, {"text": "Gojo", "start": 0.8, "end": 1.2}]}]
        ctx = ml.Contexto(cfg, linhas, 1.5, (0, 200, 255), ["Gojo"], [{"tempo": 0.5, "intensidade": 1.0}])
        mascara = Image.new("L", (640, 360), 0)
        mascara.paste(255, (250, 60, 390, 360))                   # "personagem" no meio
        import numpy as np
        ctx.quadros = [np.full((360, 640, 3), 60 + k * 10, np.uint8) for k in range(6)]
        ctx.mascaras = [mascara] * 6
        for nome, fn in ml.ESTILOS.items():
            desenhou = False
            ctx.cache = {}
            for i in range(0, 45, 5):
                ctx.mascara, ctx.efeito_plate, ctx.plate_custom = mascara, None, None
                atras, frente = fn(ctx, i / 30, i, (0.0, 0.0))
                if nome.startswith("card_"):
                    self.assertIsNotNone(ctx.plate_custom, f"{nome} nao desenhou o fundo")
                    self.assertEqual(ctx.plate_custom[0].size, (640, 360), nome)
                for lay in (atras, frente):
                    if lay is not None:
                        self.assertEqual(lay.size, (640, 360), nome)
                        desenhou = desenhou or lay.getbbox() is not None
            self.assertTrue(desenhou, f"{nome} nao desenhou nada")

    def test_styles_in_test_never_reach_production(self):
        import graphic_auto_pipeline as gfx
        prod = set(gfx.DEFAULT_CONFIG["motion_estilos"])
        cfg_estudio = json.loads((ROOT / "config" / "estudio.json").read_text(encoding="utf-8"))
        self.assertEqual(prod & set(ml.EM_TESTE), set())
        self.assertEqual(set(cfg_estudio["graphics_auto"]["motion_estilos"]) & set(ml.EM_TESTE), set())
        self.assertTrue(set(ml.EM_TESTE) <= set(ml.ESTILOS))

    def test_camera_transform_moves_scene_and_mask_together(self):
        img = Image.new("L", (100, 50), 0)
        img.paste(255, (48, 20, 52, 30))
        self.assertIs(ml.transformar(img, 1.0, 0, 0), img)
        z = ml.transformar(img, 2.0, 0, 0)
        self.assertEqual(z.size, (100, 50))
        import numpy as np
        self.assertGreater(int((np.asarray(z) > 128).sum()), int((np.asarray(img) > 128).sum()))
        # deslocamento maior que a folga nao puxa borda preta para dentro
        self.assertEqual(ml.transformar(Image.new("L", (100, 50), 200), 1.1, 500, 0).getpixel((0, 25)), 200)

    def test_outline_is_hollow(self):
        f = ml._fonte(ml.PADRAO["fontes"]["impacto"], 120)
        cont = ml._contorno("O", f, (255, 0, 0), 4)
        cheio = ml._texto("O", f, cor=(255, 0, 0), stroke=4, stroke_cor=(255, 0, 0), pad=4 * 3 + 8)
        self.assertEqual(cont.size, cheio.size)
        import numpy as np
        soma = lambda im: int(np.asarray(im.getchannel("A"), dtype=np.int64).sum())
        self.assertLess(soma(cont), soma(cheio) * 0.6)            # miolo vazado
        self.assertGreater(soma(cont), 0)

    def test_config_file_keys_are_known_and_styles_exist(self):
        dados = json.loads((ROOT / "assets" / "design" / "motion_lab.json").read_text(encoding="utf-8"))
        self.assertEqual({k for k in dados if not k.startswith("_")} - set(ml.PADRAO), set())
        self.assertEqual(set(dados["estilos"]) - set(ml.ESTILOS), set())

    def test_project_override_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "c.json"
            arq.write_text(json.dumps({"grao": 0.1, "plate": {"escurecer": 0.5}}))
            cfg = ml.carregar_cfg(arq, {"motion_lab": {"plate": {"saturacao": 0.3}}})
        self.assertEqual((cfg["grao"], cfg["plate"]["escurecer"], cfg["plate"]["saturacao"]), (0.1, 0.5, 0.3))
        self.assertEqual(cfg["plate"]["push_in"], ml.PADRAO["plate"]["push_in"])


def _cand(**kw):
    base = {"line_start": 10.0, "line_end": 12.5, "name_hit": False, "beat_score": 0.2,
            "start": 11.0, "end": 12.4, "duration": 1.4, "word": "INFINITO", "word_start": 11.2,
            "preset": "void_glitch", "layout": "hero_center", "spec": {"engine": "vx_graphics_pro"}}
    base.update(kw)
    return base


class EscolhaEstiloTests(unittest.TestCase):
    TODOS = list(ml.ESTILOS)

    def test_name_goes_behind_character_and_808_goes_glitch(self):
        self.assertEqual(ml.escolher_estilo(_cand(name_hit=True, line_end=20), [], self.TODOS), "atras_personagem")
        self.assertEqual(ml.escolher_estilo(_cand(beat_score=0.8, line_end=20), [], self.TODOS), "impacto_zoom")
        self.assertEqual(ml.escolher_estilo(_cand(beat_score=0.8, line_end=20), ["impacto_zoom"], self.TODOS),
                         "glitch_slice")

    def test_no_repeat_of_last_three(self):
        import graphic_auto_pipeline as gfx
        prod = gfx.DEFAULT_CONFIG["motion_estilos"]
        rec = ["atras_personagem", "contorno_energia", "card_cena_escura"]
        self.assertEqual(ml.escolher_estilo(_cand(name_hit=True, line_end=20), rec, prod), "letterbox_cinema")

    def test_style_in_test_is_never_chosen_in_production(self):
        import graphic_auto_pipeline as gfx
        prod = gfx.DEFAULT_CONFIG["motion_estilos"]
        for hist in ([], ["atras_personagem"], ["atras_personagem", "contorno_energia"]):
            self.assertNotIn(ml.escolher_estilo(_cand(name_hit=True, line_end=20), hist, prod), ml.EM_TESTE)

    def test_manga_closes_the_video(self):
        import graphic_auto_pipeline as gfx
        prod = gfx.DEFAULT_CONFIG["motion_estilos"]
        self.assertEqual(ml.escolher_estilo(_cand(line_end=20, posicao=0.85), [], prod), "card_manga")
        self.assertNotEqual(ml.escolher_estilo(_cand(line_end=20, posicao=0.4), [], prod), "card_manga")

    def test_short_line_allows_line_styles_and_no_repeat(self):
        e1 = ml.escolher_estilo(_cand(), ["card_cenario"], self.TODOS)
        self.assertEqual(e1, "palavra_por_palavra")
        e2 = ml.escolher_estilo(_cand(), ["card_cenario", "palavra_por_palavra"], self.TODOS)
        self.assertEqual(e2, "card_letra")
        e3 = ml.escolher_estilo(_cand(), ["card_cenario", "palavra_por_palavra", "card_letra"], self.TODOS)
        self.assertEqual(e3, "maquina_escrever")
        self.assertNotIn(ml.escolher_estilo(_cand(line_end=20), [], self.TODOS), ml.ESTILOS_DE_LINHA)


class GraficosAutoMotionTests(unittest.TestCase):
    BASE = {"segments": [
        {"type": "lyric", "start": 0.0, "end": 30.0, "clip": "a.mp4", "src": 0.0},
        {"type": "vx_cena_ia", "start": 30.0, "end": 33.0, "clip": "vx_cenas_ia/x.mp4", "src": 0.0},
    ]}

    def setUp(self):
        import graphic_auto_pipeline as gfx
        self.gfx = gfx
        self.cfg = dict(gfx.DEFAULT_CONFIG)

    def test_line_style_covers_line_and_hides_subtitle(self):
        item = _cand()
        # kanji_fundo seria o 1o; forcar recentes via lista de estilos so de linha
        self.cfg["motion_estilos"] = ["palavra_por_palavra"]
        out = self.gfx.aplicar_motion_real([item], self.BASE, self.cfg, 60.0, {}, True)[0]
        self.assertEqual(out["spec"]["engine"], "vx_motion_real")
        self.assertLessEqual(out["start"], 10.0 - 0.1 + 1e-6)
        self.assertGreaterEqual(out["end"], 12.5)
        self.assertTrue(out["oculta_legenda"])
        self.assertEqual(out["spec"]["fonte"][0]["clip"], "a.mp4")

    def test_collision_falls_back_to_word_style(self):
        self.cfg["motion_estilos"] = ["palavra_por_palavra", "card_cena_escura"]
        vizinho = _cand(start=12.45, end=13.5, duration=1.05, line_start=12.45, line_end=20)
        item = _cand()
        out = self.gfx.aplicar_motion_real([item, vizinho], self.BASE, self.cfg, 60.0, {}, True)
        self.assertEqual(out[0]["spec"]["estilo"], "card_cena_escura")
        self.assertFalse(out[0]["oculta_legenda"])
        self.assertEqual((out[0]["start"], out[0]["end"]), (11.0, 12.4))

    # incidente 2026-09-30 "tormento": ASR encurtou a ultima palavra sustentada; o take de
    # linha acabava antes dela e a legenda do trecho estava oculta -> palavra sumia.
    SYNC_TORMENTO = [
        {"start": 108.86, "end": 112.38, "text": "Limitless — a técnica que transcende o tormento",
         "words": [{"text": "Limitless", "start": 108.86, "end": 109.78},
                   {"text": "o", "start": 111.32, "end": 112.38},
                   {"text": "tormento", "start": 112.38, "end": 112.58}]},
        {"start": 116.0, "end": 118.0, "text": "proxima", "words": []},
    ]

    def test_last_sustained_word_extends_line_end(self):
        fim = ml.fim_da_linha(self.SYNC_TORMENTO[0], 116.0)
        self.assertGreaterEqual(fim, 112.38 + 0.7)            # 'tormento' fica ~0.7 s no minimo
        self.assertLess(ml.fim_da_linha(self.SYNC_TORMENTO[0], 112.5), 112.5)   # nao invade a proxima
        rel = ml.linhas_no_trecho(self.SYNC_TORMENTO, 108.7, 6.0)[0]
        self.assertAlmostEqual(rel["end"], fim - 108.7, places=4)

    def test_line_take_covers_last_word_plus_fade(self):
        item = _cand(line_start=108.86, line_end=112.38)
        jan = self.gfx.janela_de_linha(item, self.SYNC_TORMENTO, 142.8, 5.5)
        self.assertIsNotNone(jan)
        s, e, _d = jan
        ultima = self.SYNC_TORMENTO[0]["words"][-1]
        self.assertGreaterEqual(e, ml.fim_da_linha(self.SYNC_TORMENTO[0], 116.0) + ml.TAKE_LINHA_SOBRA - 0.04)
        self.assertGreater(e - ultima["start"], 1.0)
        self.assertLessEqual(s, 108.86 - 0.1)
        self.assertIsNone(self.gfx.janela_de_linha(item, self.SYNC_TORMENTO, 142.8, 3.0))  # longo demais

    def test_rendered_line_style_shows_last_word(self):
        cfg = ml.carregar_cfg()
        cfg["largura"], cfg["altura"] = 640, 360
        linhas = ml.linhas_no_trecho(self.SYNC_TORMENTO, 108.7, 5.2)
        ctx = ml.Contexto(cfg, linhas, 5.2, (0, 200, 255), [], [])
        t_ultima = 112.38 - 108.7 + 0.3                      # 0.3 s depois de 'tormento' comecar
        so_sem = ml.Contexto(cfg, [dict(linhas[0], words=linhas[0]["words"][:-1])], 5.2, (0, 200, 255), [], [])
        com = ml.estilo_palavra_por_palavra(ctx, t_ultima, 0, (0, 0))[1]
        sem = ml.estilo_palavra_por_palavra(so_sem, t_ultima, 0, (0, 0))[1]
        import numpy as np
        self.assertGreater(int(np.asarray(com.getchannel("A")).sum()), int(np.asarray(sem.getchannel("A")).sum()))

    def test_partially_covered_subtitle_stays(self):
        import render_clipe as rc
        ass = "Dialogue: 0,0:00:10.00,0:00:14.00,Default,,0,0,0,,metade fora\n"
        self.assertIn("metade fora", rc.ass_sem_intervalos(ass, [(9.0, 12.0)]))     # 50% coberto: fica
        self.assertNotIn("metade fora", rc.ass_sem_intervalos(ass, [(9.9, 14.2)]))  # inteiro: saiu

    # incidente 2026-10-05 (Asta): a janela do take tambem puxava as linhas vizinhas que
    # so ENCOSTAM nela, e `linha_ativa` trocava a frase no meio do take. Vazamento de CAUDA
    # ('O TOURO NEGRO' -> 'FACA' a 54.8s, linha seguinte comeca 54.54s) e de CABECA
    # ('O' acendia na linha errada a 27.0s, janela comeca 23.93s e a anterior termina 24.04s).
    SYNC_VAZAMENTO = [
        {"start": 20.92, "end": 24.04, "text": "Eu respondia calado, apertando o punho inteiro",
         "words": [{"text": "Eu", "start": 20.92, "end": 21.4}, {"text": "respondia", "start": 21.4, "end": 24.04}]},
        {"start": 24.04, "end": 27.28, "text": "O de quatro folhas subiu pro Yuno no ar",
         "words": [{"text": "O", "start": 24.04, "end": 24.4}, {"text": "folhas", "start": 24.4, "end": 27.28}]},
        {"start": 27.28, "end": 30.46, "text": "O meu desceu rasgado, sujo, sem par",
         "words": [{"text": "O", "start": 27.28, "end": 27.6}, {"text": "meu", "start": 27.6, "end": 30.46}]},
    ]
    LINHA_TAKE = "O de quatro folhas subiu pro Yuno no ar"

    def test_so_linha_entrega_somente_a_linha_do_take(self):
        todas = ml.linhas_no_trecho(self.SYNC_VAZAMENTO, 23.93, 4.0)
        self.assertEqual(len(todas), 3, "sem so_linha a janela traz as tres linhas que encostam")
        uma = ml.linhas_no_trecho(self.SYNC_VAZAMENTO, 23.93, 4.0, self.LINHA_TAKE)
        self.assertEqual([l["text"] for l in uma], [self.LINHA_TAKE])

    def test_so_linha_tira_o_vazamento_de_cauda(self):
        # take 23.93-27.93; a linha seguinte comeca 27.28 e nao pode assumir antes do fim
        ls = ml.linhas_no_trecho(self.SYNC_VAZAMENTO, 23.93, 4.0, self.LINHA_TAKE)
        for i in range(41):
            t = i * 0.1
            ln = ml.linha_ativa(ls, min(t, 4.0))
            self.assertIsNotNone(ln, f"a frase do take sumiu em {t:.1f}s")
            self.assertEqual(ln["text"], self.LINHA_TAKE, f"vazou para outra linha em {t:.1f}s")

    def test_so_linha_tira_o_vazamento_de_cabeca(self):
        # take comeca 23.93 mas a linha anterior so termina 24.04: a CABECA nao pode
        # mostrar a frase antiga (foi ela que acendeu 'O' na linha errada a 27.0s)
        ls = ml.linhas_no_trecho(self.SYNC_VAZAMENTO, 23.93, 4.0, self.LINHA_TAKE)
        ln = ml.linha_ativa(ls, 0.0)
        self.assertEqual(ln["text"], self.LINHA_TAKE)

    def test_sem_so_linha_o_lab_continua_vendo_a_janela_inteira(self):
        lab = ml.linhas_no_trecho(self.SYNC_VAZAMENTO, 23.93, 4.0)
        self.assertEqual(len(lab), 3)
        self.assertEqual(ml.linha_ativa(lab, 3.9)["text"], "O meu desceu rasgado, sujo, sem par")

    def test_renderizar_take_passa_a_linha_do_take(self):
        # o take sabe o que escreve (design.json -> line_text): tem de chegar ate o render
        with unittest.mock.patch.object(ml, "preparar",
                                               return_value={"linhas": [], "acento": (0, 0, 0),
                                                             "recorte": 1.0}) as p, \
                     unittest.mock.patch.object(ml, "renderizar") as r:
            ml.renderizar_take(Path("."), {}, {}, [], {"estilo": "card_letra", "start": 1.0,
                                                       "duration": 2.0, "line_text": self.LINHA_TAKE},
                               Path("out.mp4"))
        self.assertEqual(p.call_args.kwargs["so_linha"], self.LINHA_TAKE)
        self.assertEqual(r.call_args.kwargs["linha_take"], self.LINHA_TAKE)

    def test_variety_prefers_least_used_style(self):
        hist = ["kanji_fundo", "eco_repeticao", "faiscas", "letterbox_cinema", "kanji_fundo", "atras_personagem"]
        e = ml.escolher_estilo(_cand(line_end=20), hist, list(ml.ESTILOS))
        self.assertEqual(e, "card_cenario")                  # nunca usado, vence os ja usados

    def test_motion_select_is_denser_and_repeats_chorus_word_spaced(self):
        cfg = dict(self.gfx.DEFAULT_CONFIG)
        def c(t, palavra, score=0.7):
            return {"start": t, "end": t + 1.5, "score": score, "word_norm": palavra}
        cands = [c(20, "infinito", .9), c(30, "infinito", .85), c(50, "infinito", .8), c(80, "infinito", .8),
                 c(110, "infinito", .8), c(27, "azul"), c(38, "vermelho"), c(60, "purple"), c(70, "dominio")]
        sel = self.gfx._select(cands, {"segments": []}, cfg, 140.0)
        infinitos = [x["start"] for x in sel if x["word_norm"] == "infinito"]
        self.assertEqual(len(infinitos), 3)                                    # repete ate 3x
        self.assertTrue(all(b - a >= 25 for a, b in zip(infinitos, infinitos[1:])))
        self.assertGreaterEqual(len(sel), 7)
        sem = self.gfx._select(cands, {"segments": []}, dict(cfg, motion_real=False), 140.0)
        self.assertLess(len(sem), len(sel))                                    # ritmo antigo sem motion

    def test_motion_vocabulary_widens_candidates(self):
        voc = self.gfx.vocabulario_motion({"vocabulario": {"termos": ["Hollow Purple"]}})
        self.assertEqual(voc["purple"], 0.90)
        self.assertEqual(voc["infinito"], 0.74)           # conceito com kanji
        linha = {"text": "o infinito me protege", "start": 1.0, "end": 3.0, "words": []}
        self.assertIsNone(self.gfx._dominant(linha, set()))               # sem motion: nada
        dom = self.gfx._dominant(linha, set(), voc)
        self.assertEqual((dom["norm"], dom["strength"]), ("infinito", 0.74))

    def test_no_real_footage_keeps_procedural_take(self):
        base = {"segments": [{"type": "vx_cena_ia", "start": 0, "end": 60, "clip": "vx_cenas_ia/x.mp4", "src": 0}]}
        item = _cand(line_end=20)
        out = self.gfx.aplicar_motion_real([item], base, self.cfg, 60.0, {}, True)[0]
        self.assertEqual(out["spec"]["engine"], "vx_graphics_pro")

    def test_subtitle_filter_drops_only_events_inside_takes(self):
        import render_clipe as rc
        ass = ("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
               "Dialogue: 0,0:00:10.00,0:00:12.50,Default,,0,0,0,,dentro\n"
               "Dialogue: 0,0:00:20.00,0:00:21.00,Default,,0,0,0,,fora, com virgula\n")
        tl = {"segments": [{"start": 9.9, "end": 12.8, "graphics_auto": {"oculta_legenda": True}},
                           {"start": 19.0, "end": 22.0, "graphics_auto": {"oculta_legenda": False}}]}
        filtrado = rc.ass_sem_intervalos(ass, rc.intervalos_sem_legenda(tl))
        self.assertNotIn("dentro", filtrado)
        self.assertIn("fora, com virgula", filtrado)
        self.assertIn("Format:", filtrado)


if __name__ == "__main__":
    unittest.main()
