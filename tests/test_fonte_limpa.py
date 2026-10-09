"""Porteiro de fonte: marca d'agua/logo e legenda queimada (incidente Douma 30/09/2026)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import fonte_limpa as fl  # noqa: E402

W, H = fl.W, fl.H


def _cenas(n=24, logo=None, seed=0):
    """Quadros com conteudo que muda (blocos aleatorios) + logo fixo opcional."""
    import cv2
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        q = np.zeros((H, W, 3), np.uint8)
        for _k in range(6):
            x, y = int(rng.integers(0, W - 60)), int(rng.integers(0, H - 60))
            cor = tuple(int(v) for v in rng.integers(40, 255, 3))
            cv2.rectangle(q, (x, y), (x + 60, y + 60), cor, -1)
        if logo:
            x, y, w, h = logo
            cv2.putText(q, "LOGO", (x, y + h), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        out.append(q)
    return out


def _legenda(q, texto="THIS IS A BURNED SUBTITLE"):
    import cv2
    q = q.copy()
    tam = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0]
    org = ((W - tam[0]) // 2, int(H * 0.86))
    cv2.putText(q, texto, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)      # contorno
    cv2.putText(q, texto, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return q


class MarcaTests(unittest.TestCase):
    def test_static_logo_is_found_in_the_corner(self):
        caixas = fl.caixas_persistentes(_cenas(logo=(400, 240, 60, 16)))
        self.assertTrue(caixas)
        self.assertEqual(caixas[0]["posicao"], "canto")
        self.assertGreater(caixas[0]["x"], 0.8)

    def test_clean_changing_clip_has_no_mark(self):
        self.assertEqual(fl.caixas_persistentes(_cenas()), [])

    def test_static_clip_is_not_a_watermark(self):
        um = _cenas(1)[0]
        self.assertEqual(fl.caixas_persistentes([um] * 20), [])       # tudo parado: nao acusa

    def test_crop_hides_boxes_by_their_side(self):
        rodape = [{"x": 0.40, "y": 0.90, "w": 0.15, "h": 0.04}]
        e = fl.enquadramento_limpo(rodape, 1.18)
        self.assertIsNotNone(e)
        self.assertLessEqual(e["y"] + e["s"], 0.90)                    # recorte termina acima da marca
        self.assertLess(e["zoom"], 1.15)
        canto = [{"x": 0.85, "y": 0.02, "w": 0.13, "h": 0.06}]
        e2 = fl.enquadramento_limpo(canto, 1.18)
        self.assertTrue(e2["y"] >= 0.08 or e2["x"] + e2["s"] <= 0.85)
        meio = [{"x": 0.45, "y": 0.45, "w": 0.1, "h": 0.1}]
        self.assertIsNone(fl.enquadramento_limpo(meio, 1.18))          # meio: vai para delogo


class MarcaPorTrechoTests(unittest.TestCase):
    """'watermark ta cheio' (Douma): marca que aparece so num sub-clipe do pack."""

    def test_logo_only_in_second_half_is_found_with_its_time(self):
        quadros = _cenas(24, seed=1) + _cenas(24, logo=(400, 240, 60, 16), seed=2)
        achadas = fl.marcas_por_trecho(quadros, fps=4.0, janela_s=4.0)
        self.assertTrue(achadas)
        self.assertGreaterEqual(achadas[0]["t0"], 4.0)            # comeca na 2a metade (6 s)
        self.assertGreater(achadas[0]["x"], 0.8)

    def test_static_scenery_detail_is_not_a_watermark(self):
        # detalhe que fica parado JUNTO com o entorno (cenario quase estatico) nao e marca
        um = _cenas(1, seed=5)[0]
        self.assertEqual(fl.marcas_por_trecho([um] * 32, fps=4.0), [])


class ChromaTests(unittest.TestCase):
    def test_green_screen_frame_is_detected(self):
        q = np.zeros((H, W, 3), np.uint8)
        q[:] = (20, 200, 30)                                       # verde chroma
        q[60:220, 180:300] = (200, 180, 170)                       # personagem
        self.assertGreater(fl.chroma_no_quadro(q), 0.6)
        self.assertEqual(fl.chroma_no_quadro(_cenas(1, seed=4)[0]), 0.0)

    def test_chroma_mask_despill_and_aura(self):
        sys.path.insert(0, str(ROOT / "ferramentas"))
        import chroma_auto as ch
        q = np.zeros((H, W, 3), np.uint8)
        q[:] = (20, 200, 30)
        q[60:220, 180:300] = (200, 180, 170)
        q[60:220, 300:304] = (120, 190, 110)                       # borda com verde vazando
        m = np.asarray(ch.mascara_chroma(q, feather=0))
        self.assertEqual(m[10, 10], 0)                             # fundo verde some
        self.assertEqual(m[140, 240], 255)                         # personagem fica
        d = ch.despill(q)
        self.assertLessEqual(int(d[100, 301, 1]), int(max(d[100, 301, 0], d[100, 301, 2])))
        borda = np.asarray(ch.borda_aura(ch.mascara_chroma(q, feather=0)))
        self.assertGreater(int(borda[140, 170]), 0)                # aura logo fora do contorno
        self.assertEqual(int(borda[140, 240]), 0)                  # nunca dentro do personagem
        self.assertGreater(ch.forca_aura(0.0, 1.0), ch.forca_aura(0.0, 0.0))   # pulsa no 808

    def test_segments_on_green_screen_are_selected(self):
        import chroma_auto as ch
        tl = {"segments": [{"type": "lyric", "start": 0, "end": 2, "clip": "pack.mp4", "src": 10.0},
                           {"type": "lyric", "start": 2, "end": 4, "clip": "pack.mp4", "src": 50.0},
                           {"type": "vx_cena_ia", "start": 4, "end": 6, "clip": "vx_cenas_ia/x.mp4", "src": 0}]}
        linhas = {"pack.mp4": [(t / 2, 0.8 if 9 <= t / 2 <= 13 else 0.0) for t in range(0, 140)]}
        self.assertEqual(ch.segmentos_chroma(tl, linhas, 0.5, 0.25), [0])


class SepararTrechosTests(unittest.TestCase):
    """Douma/Crunchyroll: legenda que fica parada virou 'marca' e levou delogo no rosto."""

    def _v(self, marcas, legenda=0.0, chroma=0.0):
        linha = [(t / 2, legenda) for t in range(0, 60)]
        return {"marcas_trecho": marcas, "legenda": linha, "chroma": [(t, chroma) for t, _ in linha]}

    def test_static_subtitle_in_subtitle_band_is_not_a_watermark(self):
        m = {"x": 0.28, "y": 0.85, "w": 0.02, "h": 0.03, "t0": 6.0, "t1": 15.0}
        reais, parada = fl.separar_trechos(self._v([m], legenda=0.9))
        self.assertEqual(reais, [])
        self.assertEqual(len(parada), 1)

    def test_logo_in_corner_stays_a_watermark_even_with_subtitles(self):
        m = {"x": 0.85, "y": 0.04, "w": 0.1, "h": 0.05, "t0": 6.0, "t1": 15.0}
        reais, parada = fl.separar_trechos(self._v([m], legenda=0.9))
        self.assertEqual(len(reais), 1)
        self.assertEqual(parada, [])

    def test_mark_in_subtitle_band_without_subtitle_is_a_watermark(self):
        m = {"x": 0.28, "y": 0.85, "w": 0.02, "h": 0.03, "t0": 6.0, "t1": 15.0}
        reais, _ = fl.separar_trechos(self._v([m], legenda=0.0))
        self.assertEqual(len(reais), 1)

    def test_green_screen_window_gets_no_delogo(self):
        m = {"x": 0.4, "y": 0.4, "w": 0.05, "h": 0.05, "t0": 6.0, "t1": 15.0}
        reais, _ = fl.separar_trechos(self._v([m], chroma=0.6))
        self.assertEqual(reais, [])


def _cx(x, y, w, h, texto):
    return {"x": x, "y": y, "w": w, "h": h, "texto": texto, "conf": 0.95}


class OcrTests(unittest.TestCase):
    """Douma 01/10/2026: logo Crunchyroll, 'DESTROY' (1 palavra) e cartela do filme passaram."""

    def test_streaming_logo_and_copyright_are_marks_subtitles_are_text(self):
        logo = _cx(0.02, 0.02, 0.28, 0.08, "Crunchyroll")
        copy_ = _cx(0.72, 0.95, 0.27, 0.03, "Koyoharu Gotoge/SHUEISHA")
        amostras = []
        for t in range(60):
            cx = [logo, copy_ if t % 2 else _cx(0.72, 0.95, 0.27, 0.03, "KoyoharuGotege/SHUEISHA")]
            if 20 <= t < 22:
                cx.append(_cx(0.44, 0.83, 0.12, 0.05, "DESTROY"))
            if 30 <= t < 34:      # legendas diferentes no mesmo lugar nao viram marca
                cx.append(_cx(0.30, 0.83, 0.40, 0.05, ["You look so young", "and tasty!", "Who are you", "Run"][t - 30]))
            amostras.append((float(t), cx))
        for t in range(50, 60):   # cartela final do trailer: 3 textos parados juntos
            amostras[t][1].extend([_cx(0.3, 0.3, 0.4, 0.05, "Watch Full Episodes"),
                                   _cx(0.3, 0.5, 0.4, 0.05, "Continue Watching"),
                                   _cx(0.3, 0.7, 0.2, 0.05, "Watch on")])
        g = fl.agrupar_ocr(amostras, 60.0)
        textos = sorted(m["texto"] for m in g["marcas"])
        self.assertEqual(dict(g["texto_linha"])[55.0], 1.0)
        self.assertEqual(len(g["marcas"]), 2, textos)
        self.assertTrue(all(m["todo"] for m in g["marcas"]))
        linha = dict(g["texto_linha"])
        self.assertEqual(linha[20.0], 1.0)
        self.assertEqual(linha[31.0], 1.0)
        self.assertEqual(linha[10.0], 0.0)

    def test_low_confidence_and_kanji_are_ignored(self):
        res = [([[0, 0], [90, 0], [90, 20], [0, 20]], "参", 0.9),
               ([[0, 0], [90, 0], [90, 20], [0, 20]], "Crunchyroll", 0.3),
               ([[96, 54], [384, 54], [384, 108], [96, 108]], "Crunchyroll", 0.98)]
        cx = fl.caixas_ocr(res)
        self.assertEqual([c["texto"] for c in cx], ["Crunchyroll"])
        self.assertAlmostEqual(cx[0]["x"], 0.1, places=3)

    def test_cleanup_plan_crops_the_big_logo_and_delogos_the_rest(self):
        logo = {"x": 0.0, "y": 0.0, "w": 0.29, "h": 0.10}
        copy_ = {"x": 0.72, "y": 0.95, "w": 0.27, "h": 0.04}
        p = fl.plano_limpeza([logo, copy_], 1.18)
        self.assertIsNotNone(p["recorte"])
        self.assertLessEqual(p["recorte"]["zoom"], 1.18)
        self.assertEqual(len(p["delogo"]), 1)
        self.assertIs(p["escondidas"][0], logo)

    def test_box_is_remapped_after_crop(self):
        e = {"s": 0.8, "x": 0.1, "y": 0.2, "zoom": 1.25}
        b = fl.no_recorte({"x": 0.5, "y": 0.6, "w": 0.08, "h": 0.08}, e)
        self.assertAlmostEqual(b["x"], 0.5)
        self.assertAlmostEqual(b["w"], 0.1)
        self.assertIsNone(fl.no_recorte({"x": 0.0, "y": 0.0, "w": 0.05, "h": 0.05}, e))

    def test_residual_text_after_cleanup_pollutes_the_span(self):
        linha = [(float(t), 0.0) for t in range(10)]
        m = dict(fl.marcar_trechos(linha, [(6.0, 8.0)]))
        self.assertEqual([m[t] for t in (5.0, 6.0, 8.0, 9.0)], [0.0, 1.0, 1.0, 0.0])

    def test_ocr_text_marks_subtitle_line(self):
        base = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.3), (1.5, 0.0)]
        m = fl.mesclar_linha(base, [(0.0, 0.0), (1.0, 1.0)], 0.51)
        self.assertEqual([s for _t, s in m], [0.0, 0.0, 1.0, 1.0])


class TextoRenderTests(unittest.TestCase):
    """Porteiro final: OCR no corpo; so a nossa letra/titulos podem aparecer."""
    CORPUS = "|".join(fl._norm(x) for x in ["Eu escuto o seu choro", "Mas o veneno de glicínia",
                                              "Paraíso Eterno", "VX RAPS"])

    def test_our_lyrics_even_with_ocr_typos_pass(self):
        am = [(0.0, [_cx(.3, .8, .4, .05, "EUESCUTOOSEUCHORO")]),
              (0.5, [_cx(.3, .8, .4, .05, "MASOVENENODECLICINIA")]),
              (1.0, [_cx(.3, .3, .1, .05, "PAP")])]
        self.assertEqual(fl.intrusos_render(am, self.CORPUS), [])

    def test_streaming_brand_fails_immediately(self):
        am = [(9.0, [_cx(.1, .9, .1, .05, "Crunchyroll")])]
        self.assertEqual(len(fl.intrusos_render(am, self.CORPUS)), 1)

    def test_english_subtitle_needs_two_reads(self):
        um = [(12.0, [_cx(.4, .05, .2, .05, "Constantly...")])]
        dois = um + [(12.5, [_cx(.4, .05, .2, .05, "Constantly...")])]
        self.assertEqual(fl.intrusos_render(um, self.CORPUS), [])
        self.assertEqual(len(fl.intrusos_render(dois, self.CORPUS)), 2)

    def test_scene_with_any_ocr_text_is_polluted(self):
        self.assertEqual(fl.texto_na_janela([(5.0, 0.0), (6.0, 1.0)], 6.1, 8.0), 1)
        self.assertEqual(fl.texto_na_janela([(5.0, 0.0), (6.0, 1.0)], 6.5, 8.0), 0)


class LinhasDeBordaTests(unittest.TestCase):
    def test_logo_touching_player_frame_line_survives(self):
        m = np.zeros((H, W), np.uint8)
        m[3, :] = 1                          # linha da moldura
        m[4:30, 5:140] = 1                   # logo encostado nela
        limpa = fl.sem_linhas_de_borda(m)
        self.assertEqual(int(limpa[3].sum()), 0)
        self.assertGreater(int(limpa[10:30, 5:140].sum()), 1000)


class LegendaTests(unittest.TestCase):
    def test_burned_subtitle_scores_high_and_clean_frame_low(self):
        base = _cenas(1, seed=3)[0]
        self.assertGreaterEqual(fl.legenda_no_quadro(_legenda(base)), fl.PADRAO["legenda_score_min"])
        self.assertLess(fl.legenda_no_quadro(base), fl.PADRAO["legenda_score_min"])

    def test_fraction_per_scene(self):
        linha = [(0.0, 0.9), (0.5, 0.9), (1.0, 0.1), (1.5, 0.1)]
        self.assertAlmostEqual(fl.fracao_legenda(linha, 0.0, 2.0, 0.55), 0.5)
        self.assertEqual(fl.fracao_legenda(linha, 5.0, 6.0, 0.55), 0.0)


class ExcecaoRegistradaTest(unittest.TestCase):
    """Excecao humana por clipe (qa/excecao_fonte_limpa.json): so as caixas listadas saem."""

    def setUp(self):
        import json
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "qa").mkdir()
        self.reg = {
            "clipe": "c.mp4", "tipo": "excecao_humana_decisao_002",
            "caixas_falso_positivo": [
                {"t0": 66.0, "t1": 72.0, "x": 0.040, "y": 0.444, "w": 0.035, "h": 0.052}],
        }
        (self.tmp / "qa" / "excecao_fonte_limpa.json").write_text(json.dumps(self.reg), encoding="utf-8")

    def _caixa(self, t0, t1, x, y):
        return {"t0": t0, "t1": t1, "x": x, "y": y, "w": 0.03, "h": 0.05}

    def test_registered_box_is_removed(self):
        sobra, usadas = fl._aplicar_excecao(self.tmp, "c.mp4", [self._caixa(66.0, 72.0, 0.040, 0.444)])
        self.assertEqual(sobra, [])
        self.assertEqual(len(usadas), 1)

    def test_other_box_still_fails(self):
        outra = self._caixa(66.0, 72.0, 0.600, 0.100)   # mesma janela, outro lugar
        sobra, usadas = fl._aplicar_excecao(self.tmp, "c.mp4", [outra])
        self.assertEqual(sobra, [outra])
        self.assertEqual(usadas, [])

    def test_registered_box_at_other_time_still_fails(self):
        tarde = self._caixa(150.0, 156.0, 0.040, 0.444)  # mesma posicao, outro trecho
        sobra, _ = fl._aplicar_excecao(self.tmp, "c.mp4", [tarde])
        self.assertEqual(sobra, [tarde])

    def test_exception_only_for_its_clip(self):
        caixa = self._caixa(66.0, 72.0, 0.040, 0.444)
        sobra, usadas = fl._aplicar_excecao(self.tmp, "outro.mp4", [caixa])
        self.assertEqual(sobra, [caixa])
        self.assertEqual(usadas, [])

    def test_no_file_means_no_exception(self):
        import tempfile
        vazio = Path(tempfile.mkdtemp())
        caixa = self._caixa(66.0, 72.0, 0.040, 0.444)
        sobra, usadas = fl._aplicar_excecao(vazio, "c.mp4", [caixa])
        self.assertEqual(sobra, [caixa])
        self.assertEqual(usadas, [])


class PersistenciaNaSementeTest(unittest.TestCase):
    """Incidente 09/10/2026 (corredor do Sukuna): a persistencia era medida no blob JA
    DILUIDO, entao um logo real (0.975) e bordas estaticas de cenario (ate 0.21 no blob,
    0.58-0.73 na semente) pontuavam juntos e o detector reprovava clipe limpo.
    Medir na SEMENTE separa os dois."""

    def _logo_fixo(self, n=48, x=10, y=30):
        import cv2
        rng = np.random.default_rng(0)
        q = []
        for i in range(n):
            f = rng.integers(30, 90, (H, W, 3), dtype=np.uint8)
            f = cv2.circle(f, (20 + i * 6, 140), 18, (200, 200, 200), -1)
            cv2.putText(f, "LOGO", (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            q.append(f)
        return q

    def test_marca_real_e_detectada(self):
        cx = fl.caixas_persistentes(self._logo_fixo(), fl.cfg())
        self.assertGreaterEqual(len(cx), 1, "um logo fixo por 48 quadros tem que ser achado")
        self.assertGreater(cx[0]["persistencia"], 0.9, "logo real persiste ~1.0")
        self.assertGreater(cx[0]["densidade"], 0.18)

    def test_cenario_estatico_nao_vira_marca(self):
        """Bloco parado no meio do quadro (borda de cenario) com fundo variando muito:
        NAO pode virar 'marca d'agua'. Era o falso positivo do corredor."""
        import cv2
        rng = np.random.default_rng(7)
        q = []
        for i in range(48):
            f = rng.integers(20, 110, (H, W, 3), dtype=np.uint8)
            cv2.rectangle(f, (150, 60), (250, 170), (240, 240, 240), 3)   # borda FIXA
            f = cv2.circle(f, (60 + i * 7, 220), 25, (150, 150, 150), -1)  # movimento forte
            q.append(f)
        cx = fl.caixas_persistentes(q, fl.cfg())
        self.assertEqual(cx, [], "borda estatica de cenario nao pode reprovar o clipe")

    def test_persistencia_reportada_e_da_semente(self):
        """O campo `persistencia` tem que refletir os pixels ACIMA do limiar, nunca a
        media do blob dilatado (que diluia 0.9 para 0.08)."""
        import inspect
        src = inspect.getsource(fl.caixas_persistentes)
        self.assertIn("persist_seed", src)
        self.assertNotIn("persist[rot == k]", src)

    def test_blob_esparso_e_descartado(self):
        """Semente esparsa (poucos pixels densos num blob grande) nao e logo."""
        c = fl.cfg()
        self.assertGreater(float(c["densidade_seed_min"]), 0.0)
        self.assertLessEqual(float(c["densidade_seed_min"]), 1.0)


class QuadrosTravadosTest(unittest.TestCase):
    """Incidente 09/10/2026: `_quadros` lia o pipe do ffmpeg com `read()` SEM timeout.
    O ffmpeg travou no OCR pos-delogo e a esteira ficou 32 min parada — nem terminava nem
    falhava. Agora o silencio tem teto e vira erro alto (falha fechada)."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.video = self.tmp / "c.mp4"
        self.video.write_bytes(b"nao importa")

    def test_ffmpeg_travado_levanta_erro_alto(self):
        """O ffmpeg abre o pipe e nunca escreve: a thread de leitura fica presa no read(),
        a fila expira e a etapa falha com erro alto em vez de congelar."""
        import threading

        class PipeMudo:
            def __init__(self):
                self.liberado = threading.Event()
            def read(self, _n):
                self.liberado.wait(30)      # preso como um read() de pipe travado
                return b""
            def close(self):
                self.liberado.set()
        class ProcMudo:
            def __init__(self):
                self.stdout = PipeMudo()
                self.killed = False
            def kill(self):
                self.killed = True
                self.stdout.liberado.set()
            def wait(self, timeout=None):
                return 0
        proc = ProcMudo()

        with unittest.mock.patch.object(fl.subprocess, "Popen", return_value=proc), \
             unittest.mock.patch.object(fl, "TIMEOUT_S", 0.05), \
             unittest.mock.patch.object(fl, "_duracao", return_value=10.0):
            gerador = fl._quadros(self.video, 2.0)
            with self.assertRaises(RuntimeError) as ctx:
                next(gerador)
        msg = str(ctx.exception)
        self.assertIn("parou de entregar quadros", msg)
        self.assertIn("c.mp4", msg)
        self.assertTrue(proc.killed, "ffmpeg travado tem que ser morto")

    def test_clipe_curto_normal_continua_lerdo(self):
        """O teto e por SILENCIO, nao por duracao: clipe que entrega quadros passa inteiro."""
        q = np.zeros((H, W, 3), np.uint8)
        tam = W * H * 3
        dados = q.tobytes() + q.tobytes() + q.tobytes()   # 3 quadros e depois EOF

        class PipeFixo:
            def __init__(self, buf):
                self.buf, self.i = buf, 0
            def read(self, n):
                parte = self.buf[self.i:self.i + n]
                self.i += len(parte)
                return parte
            def close(self):
                pass
        class ProcFixo:
            def __init__(self, buf):
                self.stdout = PipeFixo(buf)
            def kill(self):
                pass
            def wait(self, timeout=None):
                return 0

        with unittest.mock.patch.object(fl.subprocess, "Popen", return_value=ProcFixo(dados)), \
             unittest.mock.patch.object(fl, "_duracao", return_value=1.0):
            quadros = list(fl._quadros(self.video, 2.0))
        self.assertEqual(len(quadros), 3)
        self.assertEqual(quadros[0].shape, (H, W, 3))

    def test_nao_usa_select_no_pipe(self):
        """Regressao: no Windows `select` so aceita soquete e explode num pipe do ffmpeg
        (WinError 10038). O teto de silencio tem que vir de thread + fila."""
        import inspect
        src = inspect.getsource(fl._quadros)
        self.assertNotIn("select.select", src)
        self.assertIn("queue.Queue", src)
        self.assertIn("Thread", src)

    def test_cache_pos_limpeza_tem_arquivo_proprio(self):
        """O OCR de verificacao precisa de cache proprio: sem ele relia o clipe inteiro
        de novo a cada delogo (era onde o ffmpeg travava)."""
        import inspect
        src = inspect.getsource(fl.auditar_projeto)
        self.assertIn("__poslimpeza", src)
        self.assertNotIn('ocr_do_clipe(clip, float(c["ocr_fps_verificacao"]), None, c)', src)


class CartelaCompostaTests(unittest.TestCase):
    """Regressao do incidente 2026-10-09: o QA de texto reprovava o NOSSO Title Card.

    A cartela de abertura escreve `MEGUMI FUSHIGURO • JUJUTSU KAISEN` na mesma
    linha. Como o `corpus_permitido` une os campos ja normalizados com `"|"`, e
    `_norm` apaga o `|`, o corpus virava um blob: `megumifushiguro` e
    `jujutsukaisen` ficavam colados sem separador, e a string composta lida pelo
    OCR nunca casava. O gate reprovava 12 amostras do proprio card.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _projeto(self, **extra):
        man = {"personagem": "Megumi Fushiguro", "anime": "Jujutsu Kaisen",
               "faixa": "Megumi Shadows", "titulo_linhas": ["MEGUMI", "SHADOWS"]}
        man.update(extra)
        (self.d / "projeto.json").write_text(
            json.dumps(man, ensure_ascii=False), encoding="utf-8")
        return fl.corpus_permitido(self.d)

    def test_cartela_composta_e_nossa(self):
        corpus = self._projeto()
        for texto in ("MEGUMI FUSHIGURO JUJUTSU KAISEN",
                      "MEGUMI FUSHIGUROJUJUTSU KAISEN",   # OCR come o bullet
                      "VX RAPS APRESENTA",
                      "MEGUMI SHADOWS",
                      "VX RAPS @VXRaps"):
            self.assertTrue(fl.texto_e_nosso(texto, corpus), texto)

    def test_campos_isolados_continuam_nossos(self):
        corpus = self._projeto()
        for texto in ("MEGUMI FUSHIGURO", "JUJUTSU KAISEN", "MEGUMI SHADOWS"):
            self.assertTrue(fl.texto_e_nosso(texto, corpus), texto)

    def test_intruso_de_verdade_ainda_reprova(self):
        """A correcao nao pode afrouxar o gate: marca de terceiros segue caindo."""
        corpus = self._projeto()
        for texto in ("ANIME FLV", "Canal do Joao", "ASSISTA AGORA EM HD",
                      "naruto shippuden opening", "GLICINIA TV"):
            self.assertFalse(fl.texto_e_nosso(texto, corpus), texto)

    def test_separador_sobrevive_a_normalizacao(self):
        corpus = self._projeto()
        self.assertIn("|", corpus)
        self.assertGreater(len([c for c in corpus.split("|") if c]), 3)

    def test_nao_casa_atravessando_a_fronteira(self):
        """Um trecho que junta dois campos DIFERENTES nao e texto nosso."""
        corpus = "|".join(fl._norm(x) for x in ["Megumi Fushiguro", "Jujutsu Kaisen"])
        # o composto entra no corpus via projeto.json, mas um cruzamento que nao
        # existe em nenhum campo nao pode ser aceito por acidente
        self.assertFalse(fl.texto_e_nosso("SHADOWSPIRIT BLAZING", corpus))

    def test_texto_render_real_do_projeto(self):
        """O caso exato: as 12 amostras reprovadas voltam a ser aprovadas."""
        corpus = self._projeto()
        amostras = [(t / 2.0, [_cx(.3, .1, .4, .06, t_)]) for t, t_ in enumerate(
            ["MEGUMI FUSHIGUROJUJUTSU KAISEN"] * 8 + ["MEGUMI FUSHIGURO JUJUTSU KAISEN"] * 4, 1)]
        self.assertEqual(fl.intrusos_render(amostras, corpus), [])


class CorpusPermitidoTests(unittest.TestCase):
    """O separador `|` e contrato: `texto_e_nosso` divide o corpus por ele."""

    def test_corpus_sem_projeto_nao_estoura(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = fl.corpus_permitido(Path(tmp))
        self.assertIsInstance(corpus, str)

    def test_letra_entra_no_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "LETRA_LINHAS.txt").write_text("Sombras se abrem no chao\n",
                                                encoding="utf-8")
            corpus = fl.corpus_permitido(d)
        self.assertTrue(fl.texto_e_nosso("SOMBRAS SE ABREM NO CHAO", corpus))


class ScreentoneOcrTests(unittest.TestCase):
    """Regressao do incidente 2026-10-09: screentone de quadrinho virava 'texto intruso'.

    O manga take do `graficos-auto` (motion card com retícula de meio-tom) faz o OCR
    ler um texto minusculo e repetido — '888888' — numa caixa de 25x8 px em 960x540
    (area 0.0005), no canto inferior esquerdo. A menor caixa de texto REAL do mesmo
    render tem area 0.00367 (112x17 px): ha um vao de 8x entre ruido e texto.

    O filtro de tamanho NAO pode valer para marcas conhecidas: logo de canal pequeno
    continua reprovando pelo NOME (Crunchyroll e afins).
    """

    CORPUS = "|".join(fl._norm(x) for x in ["Sombras se abrem no chao", "VX RAPS"])

    def _sliver(self, texto="888888", w=0.026, h=0.015):
        """Caixa do tamanho medido do screentone (25x8 px em 960x540)."""
        return _cx(0.03, 0.95, w, h, texto)

    def _real(self, texto, w=0.12, h=0.031):
        """Caixa do tamanho medido do menor texto real (112x17 px)."""
        return _cx(0.30, 0.87, w, h, texto)

    def test_screentone_minusculo_nao_e_intruso(self):
        am = [(143.0, [self._sliver()]), (143.5, [self._sliver()])]
        self.assertEqual(fl.intrusos_render(am, self.CORPUS), [])

    def test_screentone_repetido_tambem_nao_e_intruso(self):
        """Antes, 3 leituras em 1 s passavam no criterio de '2 amostras' e reprovavam."""
        am = [(143.0, [self._sliver()])] + [(143.0 + i * 0.5, [self._sliver()])
                                            for i in range(1, 4)]
        self.assertEqual(fl.intrusos_render(am, self.CORPUS), [])

    def test_texto_real_grande_continua_reprovando(self):
        """O filtro e de TAMANHO: texto estranho de tamanho normal segue caindo."""
        am = [(12.0, [self._real("Constantly...")]),
              (12.5, [self._real("Constantly...")])]
        self.assertEqual(len(fl.intrusos_render(am, self.CORPUS)), 2)

    def test_marca_pequena_ainda_reprova_pelo_nome(self):
        """Logo de canal pequeno NAO pode escapar: a checagem de marca ignora o tamanho."""
        am = [(9.0, [self._sliver("Crunchyroll", 0.02, 0.012)])]
        out = fl.intrusos_render(am, self.CORPUS)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["marca"])

    def test_limiar_e_mais_justo_que_o_vao_medido(self):
        """O limiar tem folga para os dois lados (nao esta colado em nenhum extremo)."""
        c = fl.PADRAO
        area_min = float(c["texto_area_min"])
        ruido = 0.026 * 0.015          # 25x8 px medido
        real = 0.12 * 0.031            # 112x17 px medido
        self.assertGreater(area_min, ruido * 2)      # folga > 2x sobre o ruido
        self.assertLess(area_min, real / 2)          # folga > 2x sob o texto real

    def test_altura_minima_discrimina(self):
        """As caixas de screentone tinham 8 px; texto real, >= 17 px."""
        self.assertTrue(fl._caixa_pequena({"w": 0.026, "h": 0.015}, 0.0015, 11))
        self.assertFalse(fl._caixa_pequena({"w": 0.12, "h": 0.031}, 0.0015, 11))


if __name__ == "__main__":
    unittest.main()
