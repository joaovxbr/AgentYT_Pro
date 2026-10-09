"""Linha da letra CONDENSADA pelo ASR (caso Megumi 09/10/2026).

Existem dois jeitos de o Whisper "perder" um verso, e eles precisam de gatilhos diferentes:

1. `lacunas_vocais` — o trecho tem voz e NENHUMA palavra transcrita (Douma 30-35 s).
   E o que a 3a passada (`passada_guiada`) cobre.
2. Linha com POUCAS palavras — o ASR ouve 2 de 7 e comprime o resto. A voz tem
   transcricao, entao NAO existe lacuna; nada disparava, e o `auditar-letra` reprovava
   uma linha que ESTA cantada. E o que `linhas_fracas` cobre.

Caso real: "Cada shikigami meu sabe onde atacar" saiu como "shikigami ... atacar" (2/6).
O Mureka (gerador) e uma retranscricao guiada concordam que a linha inteira foi cantada.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import transcrever as tr  # noqa: E402

LINHAS = [
    "Nao sou o mais forte, mas eu nao vou recuar",
    "Cada shikigami meu sabe onde atacar",
    "Quem subestima o lobo nao vai se levantar",
]


def _w(palavra, a, b, p=0.9):
    return {"word": palavra, "start": a, "end": b, "probability": p}


class LinhasFracasTest(unittest.TestCase):
    def test_linha_condensada_e_detectada(self):
        """2 de 6 palavras casadas = 33% -> fraca."""
        dados = {"words": [
            _w("Nao", 33.3, 33.6), _w("sou", 33.6, 33.8), _w("o", 33.8, 33.9),
            _w("mais", 33.9, 34.1), _w("forte", 34.1, 34.4), _w("mas", 34.4, 34.6),
            _w("eu", 34.6, 34.7), _w("nao", 34.7, 34.9), _w("vou", 34.9, 35.1), _w("recuar", 35.1, 35.4),
            _w("shikigami", 36.68, 37.4, 0.33), _w("atacar", 38.12, 38.84, 0.71),
            _w("Quem", 43.7, 43.9), _w("subestima", 43.9, 44.3), _w("o", 44.3, 44.4),
            _w("lobo", 44.4, 44.7), _w("nao", 44.7, 44.9), _w("vai", 44.9, 45.0),
            _w("se", 45.0, 45.1), _w("levantar", 45.1, 45.6),
        ]}
        fracas = tr.linhas_fracas(dados, LINHAS)
        self.assertEqual([f["indice"] for f in fracas], [1])
        f = fracas[0]
        self.assertAlmostEqual(f["cobertura"], 2 / 6, places=3)
        self.assertLess(f["inicio"], 36.68)     # janela abre antes da 1a palavra casada
        self.assertGreater(f["fim"], 38.84)
        # `esperados` e a LINHA INTEIRA: a passada retranscreve a frase toda e o aceite
        # exige a linha toda. Devolver so os buracos embaralha o alinhamento.
        self.assertEqual(f["esperados"], ["Cada", "shikigami", "meu", "sabe", "onde", "atacar"])

    def test_linha_cheia_nao_e_fraca(self):
        """100% casada nunca entra, mesmo com muitas palavras."""
        dados = {"words": [_w(t, i, i + 0.2) for i, t in enumerate(
            ["Cada", "shikigami", "meu", "sabe", "onde", "atacar"])]}
        self.assertEqual(tr.linhas_fracas(dados, ["Cada shikigami meu sabe onde atacar"]), [])

    def test_linha_sem_nenhuma_palavra_nao_e_daqui(self):
        """Cobertura ZERO e caso de lacuna de voz, nao de linha fraca.

        Deixar as duas passadas com gatilhos disjuntos evita retranscrever duas vezes.
        """
        dados = {"words": [_w("recuar", 35.1, 35.4)]}
        fracas = tr.linhas_fracas(dados, ["Cada shikigami meu sabe onde atacar"])
        self.assertEqual(fracas, [])

    def test_linha_curta_demais_e_ignorada(self):
        """'Dez silhuetas' (2 palavras) nao justifica retranscrever (evita vocalise)."""
        linhas = ["Dez silhuetas"]
        dados = {"words": [_w("silhuetas", 5.0, 5.4)]}
        self.assertEqual(tr.linhas_fracas(dados, linhas), [])

    def test_limiar_de_cobertura_e_respeitado(self):
        """45% e o limiar do porteiro; acima dele a linha nao e fraca."""
        dados = {"words": [_w(t, i, i + 0.2) for i, t in enumerate(
            ["Cada", "shikigami", "meu"])]}          # 3 de 6 = 50%
        self.assertEqual(tr.linhas_fracas(dados, ["Cada shikigami meu sabe onde atacar"]), [])

    def test_sem_palavras_ou_sem_linhas_nao_quebra(self):
        self.assertEqual(tr.linhas_fracas({"words": []}, LINHAS), [])
        self.assertEqual(tr.linhas_fracas({"words": [_w("x", 1, 2)]}, []), [])

    def test_indice_aponta_a_linha_certa(self):
        """O indice devolvido tem de casar com a posicao na lista de linhas."""
        dados = {"words": [_w("atacar", 38.12, 38.84)]}
        fracas = tr.linhas_fracas(dados, LINHAS)
        self.assertTrue(fracas)
        for f in fracas:
            self.assertEqual(f["texto"], LINHAS[f["indice"]])

    def test_janela_nao_ultrapassa_o_inicio(self):
        """Linha no comeco do audio: janela nunca comeca negativa."""
        dados = {"words": [_w("silhuetas", 0.2, 0.5)]}
        fracas = tr.linhas_fracas(dados, ["Dez silhuetas na minha mao"])
        for f in fracas:
            self.assertGreaterEqual(f["inicio"], 0.0)


class AceiteGuardaATentativaBoaTest(unittest.TestCase):
    """A tentativa ACEITA tem de ser a que volta — nunca a ultima tentativa.

    Regressao Megumi (09/10/2026): a passada tenta primeiro SEM prompt (o Whisper ouve
    melhor) e depois COM a frase de prompt. Sem prompt casou sabe/onde/atacar e foi
    aceita; com prompt casou so shikigami/meu e foi rejeitada. O codigo guardava a
    ULTIMA tentativa, entao a rejeitada apagou a aceita e a passada nao fazia nada.
    """

    def _fake_chunked(self, por_prompt):
        def f(audio, *, modelo, idioma, prompt, chunk_seconds, overlap, inicio, fim, model):
            ws = por_prompt[prompt]
            return {"words": ws, "segments": [{"start": inicio, "end": fim}]}
        return f

    def test_tentativa_aceita_sobrevive_a_rejeitada(self):
        import numpy as np
        linhas = ["Cada shikigami meu sabe onde atacar"]
        bons = [_w("Cada", 35.2, 35.5), _w("shikigami", 35.5, 36.2), _w("meu", 36.2, 36.5),
                _w("sabe", 36.5, 36.9), _w("onde", 36.9, 37.2), _w("atacar", 37.2, 37.8)]
        ruins = [_w("shikigami", 36.68, 37.4, 0.46), _w("atacar", 38.14, 38.66, 0.63)]
        dados = {"words": [_w("shikigami", 36.68, 37.4, 0.33), _w("atacar", 38.12, 38.84, 0.71)],
                 "segments": []}
        # energia sempre em voz alta -> o aceite so depende do casamento
        energia = [(t, -20.0) for t in np.arange(0, 45, 0.5)]
        orig_chunk, orig_energia = tr.transcrever_chunked, tr.energia_vocal
        tr.transcrever_chunked = self._fake_chunked({None: bons, "Cada shikigami meu sabe onde atacar": ruins})
        tr.energia_vocal = lambda *_a, **_k: energia
        try:
            res = tr.passada_por_linha_fraca("fake.wav", dados, linhas, modelo="x", model=object())
        finally:
            tr.transcrever_chunked, tr.energia_vocal = orig_chunk, orig_energia
        self.assertTrue(res and res[0]["aceita"], "a tentativa sem prompt deveria ser aceita")
        self.assertFalse(res[0]["com_prompt"], "nao pode ter usado o prompt")
        # a tentativa BOA e a que vale: 'sabe' e 'onde' so existem na versao sem prompt
        # (a versao com prompt so tinha shikigami/atacar). Se a rejeitada tivesse
        # sobrescrito a aceita, estas palavras nao estariam aqui.
        palavras = [w["word"] for w in dados["words"]]
        self.assertIn("sabe", palavras)
        self.assertIn("onde", palavras)
        self.assertFalse(any(w["probability"] == 0.46 for w in dados["words"]),
                         "palavra da tentativa rejeitada (prompt) nao pode ter entrado")


if __name__ == "__main__":
    unittest.main()
