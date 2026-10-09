"""Folha por quadro: diagnostico tem de achar o defeito conhecido e nao alucinarmais."""
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import folha_por_quadro as fq  # noqa: E402

DESTAQUE = "#69F0AE"


class NormalizarTests(unittest.TestCase):
    def test_acentos_e_pontuacao_saem(self):
        self.assertEqual(fq._normalizar("O Touro Negro!"), "otouronegro")
        self.assertEqual(fq._normalizar("Anti-Magia"), "antimagia")

    def test_vazio(self):
        self.assertEqual(fq._normalizar(None), "")


class LinhaEmTests(unittest.TestCase):
    LINHAS = [
        {"start": 24.04, "end": 27.28, "text": "O de quatro folhas subiu pro Yuno no ar"},
        {"start": 27.28, "end": 30.46, "text": "O meu desceu rasgado, sujo, sem par"},
    ]

    def test_pega_a_linha_da_janela(self):
        self.assertEqual(fq.linha_em(self.LINHAS, 25.0)["text"],
                         "O de quatro folhas subiu pro Yuno no ar")

    def test_aguarda_o_fim_da_anterior(self):
        # hold de 0,65 s (end + 0.65 = 27.93): a linha seguinte so assume depois disso
        self.assertEqual(fq.linha_em(self.LINHAS, 27.5)["text"],
                         "O de quatro folhas subiu pro Yuno no ar")
        self.assertEqual(fq.linha_em(self.LINHAS, 27.90)["text"],
                         "O de quatro folhas subiu pro Yuno no ar")
        self.assertEqual(fq.linha_em(self.LINHAS, 27.95)["text"],
                         "O meu desceu rasgado, sujo, sem par")


class RegrasCorTests(unittest.TestCase):
    def test_normaliza_e_tem_o_destaque_como_padrao(self):
        with tempfile.TemporaryDirectory() as tmp:
            projeto = Path(tmp) / "proj"
            projeto.mkdir()
            regras = fq._regras_cor(projeto, {"cor": {"destaque": DESTAQUE}})
        self.assertIn("", regras)                      # padrao = destaque do projeto
        self.assertEqual(regras[""], fq._rgb(DESTAQUE))

    def test_palavra_com_regra_devolve_rgb(self):
        with tempfile.TemporaryDirectory() as tmp:
            projeto = Path(tmp) / "proj"
            projeto.mkdir()
            regras = fq._regras_cor(projeto, {"cor": {"destaque": DESTAQUE}})
        # 'azul' e' regra padrao da biblioteca motion_lab
        self.assertIn("azul", regras)
        self.assertNotEqual(regras["azul"], (0, 0, 0))


class AmostrarTodosOsQuadrosTests(unittest.TestCase):
    """O dono pediu TODOS os quadros: uma motion pode ter efeito de poucos quadros."""

    def _video(self, tmp: str, n_frames: int = 90, fps: int = 30) -> Path:
        import subprocess
        v = Path(tmp) / "v.mp4"
        subprocess.run([
            r"D:\hermes\AgentYT_Pro\ferramentas\bin\ffmpeg.exe", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=size=320x180:rate={fps}:duration={n_frames / fps}",
            "-pix_fmt", "yuv420p", str(v)], check=True)
        return v

    def test_fps_none_traz_o_quadro_que_o_container_declara(self):
        import cv2
        with tempfile.TemporaryDirectory() as tmp:
            v = self._video(tmp)
            cap = cv2.VideoCapture(str(v))
            declarado = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps_real = float(cap.get(cv2.CAP_PROP_FPS))
            cap.release()
            todos = fq.amostrar(v, fps=None)
        self.assertEqual(len(todos), declarado, "fps=None tem de ler TODOS os quadros")
        self.assertAlmostEqual(todos[-1][0], (declarado - 1) / fps_real, places=3)

    def test_fps_numerico_e_amostragem_ralida(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = self._video(tmp)
            ralas = fq.amostrar(v, fps=4.0)
        self.assertEqual(len(ralas), 12)               # 3 s a 4 fps
        self.assertAlmostEqual(ralas[1][0] - ralas[0][0], 0.25, places=3)

    def test_nenhum_quadro_perdido_entre_uma_amostra_e_a_outra(self):
        # 30 fps = 3 quadros por 0,1 s: nenhum instante pode faltar no meio da janela
        with tempfile.TemporaryDirectory() as tmp:
            v = self._video(tmp, n_frames=60)
            todos = fq.amostrar(v, fps=None)
            ts = [t for t, _ in todos]
        self.assertEqual(ts, sorted(ts))
        for a, b in zip(ts, ts[1:]):
            self.assertAlmostEqual(b - a, 1 / 30, places=3)


class InicioDaFraseTests(unittest.TestCase):
    """A frase do take so pode ser cobrada depois da 1a palavra dela.

    Regressao (Asta 07/10/2026): a folha acusou HEAD/CAUDA em 6 takes do candidato JA
    corrigido. Os hits caiam todos nos primeiros 0,5-0,8 s de cada take — a janela
    comeca ~0,1 s antes da linha, e nesses quadros `linha_em` ainda devolve a linha
    ANTERIOR (que fica segurada 0,65 s apos o fim). O take ainda nao comecou a escrever.
    """

    SYNC = [
        {"start": 20.92, "end": 24.04, "text": "Eu respondia calado, apertando o punho inteiro",
         "words": [{"text": "Eu", "start": 20.92, "end": 21.4}]},
        {"start": 24.04, "end": 27.28, "text": "O de quatro folhas subiu pro Yuno no ar",
         "words": [{"text": "O", "start": 24.15, "end": 24.5},
                   {"text": "de", "start": 24.5, "end": 27.28}]},
    ]

    def test_acha_a_primeira_palavra(self):
        self.assertAlmostEqual(fq.inicio_da_frase("O de quatro folhas subiu pro Yuno no ar", self.SYNC),
                               24.15)

    def test_normaliza_acento_e_pontuacao(self):
        self.assertIsNotNone(fq.inicio_da_frase("O de quatro folhas subiu pro Yuno no ar!", self.SYNC))

    def test_sem_sync_ou_sem_frase(self):
        self.assertIsNone(fq.inicio_da_frase("", self.SYNC))
        self.assertIsNone(fq.inicio_da_frase("frase que nao existe", self.SYNC))
        self.assertIsNone(fq.inicio_da_frase("qualquer", None))

    def test_linha_sem_words_usa_o_inicio_da_linha(self):
        sync = [{"start": 5.0, "end": 7.0, "text": "so comeca", "words": []}]
        self.assertEqual(fq.inicio_da_frase("so comeca", sync), 5.0)


class TextoDaFraseEmTests(unittest.TestCase):
    """O texto lido na tela tem de pertencer a frase do take (a frase entra por partes).

    `lido` e `alvo` entram Crus (como o loop chama: o OCR le o texto, a frase vem do
    design.json). Normalizar antes de passar quebra a comparacao por palavra.
    """

    FRASE = "O de quatro folhas subiu pro Yuno no ar"

    def test_frase_completa(self):
        self.assertTrue(fq._texto_da_frase_em(self.FRASE, self.FRASE))

    def test_prefixo_da_frase(self):
        # a kinetic text vai aparecendo palavra a palavra
        self.assertTrue(fq._texto_da_frase_em("O DE QUATRO FOLHAS", self.FRASE))

    def test_comeca_pela_primeira_palavra(self):
        self.assertTrue(fq._texto_da_frase_em("O", self.FRASE, comecou=False))

    def test_ocr_comeu_e_colou_palavras(self):
        self.assertTrue(fq._texto_da_frase_em("DEQUATRO FOLHAS SUBUPRO YUNO NO AR", self.FRASE))

    def test_outra_frase_reprova(self):
        # o defeito real: a tela mostra a frase da LINHA VIZINHA
        outro = "O meu desceu rasgado, sujo, sem par"
        self.assertFalse(fq._texto_da_frase_em(outro, self.FRASE, comecou=True))

    def test_vazio_ou_sem_alvo_nao_acusa(self):
        self.assertTrue(fq._texto_da_frase_em("", self.FRASE))
        self.assertTrue(fq._texto_da_frase_em("qualquer coisa", ""))


class ChaveOcrTests(unittest.TestCase):
    def test_chave_por_tempo_relativo(self):
        self.assertEqual(fq._chave_ocr(0.0, 2.0), 0)
        self.assertEqual(fq._chave_ocr(0.5, 2.0), 1)
        self.assertEqual(fq._chave_ocr(2.0, 2.0), 4)


class IniDoTakeNoVideoTests(unittest.TestCase):
    def test_soma_a_intro(self):
        import cv2
        with unittest.mock.patch("cv2.VideoCapture") as cap:
            cap.return_value.get.side_effect = lambda p: (
                4608.0 if p == cv2.CAP_PROP_FRAME_COUNT else 30.0)
            self.assertAlmostEqual(fq._ini_do_take_no_video(Path("x.mp4"), 10.005, 23.93), 33.935)

    def test_fora_da_duracao_devolve_none(self):
        import cv2
        with unittest.mock.patch("cv2.VideoCapture") as cap:
            cap.return_value.get.side_effect = lambda p: (
                300.0 if p == cv2.CAP_PROP_FRAME_COUNT else 30.0)   # 10 s de video
            self.assertIsNone(fq._ini_do_take_no_video(Path("x.mp4"), 10.0, 500.0))


class ConteudoJaSaiuTests(unittest.TestCase):
    """`comecou` = a 1a palavra de conteudo da frase ja saiu em algum quadro do take."""

    def test_true_quando_a_primeira_palavra_de_conteudo_aparece(self):
        ocr = {"x": {0: "O", 1: "O DE QUATRO FOLHAS", 2: "O DE QUATRO FOLHAS SUBIU"}}
        tk = {"arquivo": "x", "frase": "O de quatro folhas subiu pro Yuno no ar"}
        self.assertTrue(fq._conteudo_ja_saiu(ocr, tk))

    def test_false_quando_so_apareceu_o_article(self):
        ocr = {"x": {0: "O", 1: "O"}}
        tk = {"arquivo": "x", "frase": "O de quatro folhas subiu pro Yuno no ar"}
        self.assertFalse(fq._conteudo_ja_saiu(ocr, tk))

    def test_false_quando_nada_foi_lido(self):
        tk = {"arquivo": "x", "frase": "O de quatro folhas subiu pro Yuno no ar"}
        self.assertFalse(fq._conteudo_ja_saiu({}, tk))

    def test_frase_so_de_palavras_curtas(self):
        tk = {"arquivo": "x", "frase": "e o la vem"}
        self.assertFalse(fq._conteudo_ja_saiu({"x": {0: "e"}}, tk))


class PalavrasEConteudoTests(unittest.TestCase):
    def test_palavras_normaliza_e_remove_vazias(self):
        self.assertEqual(fq._palavras("O  DE quatro!"), ["o", "de", "quatro"])

    def test_conteudo_descarta_curtas(self):
        self.assertEqual(fq._conteudo(["o", "de", "quatro", "no", "yuno"]), ["quatro", "yuno"])


class JanelaDosTakesTests(unittest.TestCase):
    def test_le_o_design_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            projeto = Path(tmp) / "proj"
            pasta = projeto / "clips_raw" / "vx_graphics_auto"
            pasta.mkdir(parents=True)
            (pasta / "01_x.design.json").write_text(json.dumps({
                "estilo": "card_letra", "start": 51.1, "duration": 4.1,
                "word": "TOURO", "line_text": "O Touro Negro me abriu a porta",
                "oculta_legenda": True}), encoding="utf-8")
            (pasta / "quebrado.design.json").write_text("{nao e json", encoding="utf-8")
            takes = fq.janela_dos_takes(projeto)
        self.assertEqual(len(takes), 1)
        self.assertEqual(takes[0]["frase"], "O Touro Negro me abriu a porta")
        self.assertEqual((takes[0]["ini"], takes[0]["fim"]), (51.1, 55.2))
        self.assertTrue(takes[0]["oculta_legenda"])


if __name__ == "__main__":
    unittest.main()