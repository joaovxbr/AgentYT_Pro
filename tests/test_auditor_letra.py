from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import auditor_letra as al
import sincronizar_letra as sl
import transcrever as tr


def _words(texto: str, inicio: float, passo: float = 0.4, prob: float = 0.9) -> list[dict]:
    out, t = [], inicio
    for w in texto.split():
        out.append({"word": w, "start": round(t, 2), "end": round(t + passo * 0.9, 2), "probability": prob})
        t += passo
    return out


REFRAO = "INFINITO eu não tenho limite"
VERSO_A = "Satoru Gojo o homem mais forte do mundo"
VERSO_B = "Azul atraindo tudo convergiu pra mim"
PONTE = "Removo a venda e o mundo congela"


class LetraPendenteTests(unittest.TestCase):
    """Douma (30/09/2026): 156-164 s era vocalise depois da ULTIMA linha (nao e erro);
    30-35 s tinha 3 linhas do verso 1 sem relogio (e erro). O porteiro distingue pela letra."""
    LINHAS = [VERSO_A, VERSO_B, PONTE]

    def test_gap_with_expected_lyric_is_flagged(self):
        tokens = tr.tokens_da_letra(self.LINHAS)
        words = _words(VERSO_A, 5.0) + _words(PONTE, 40.0)           # VERSO_B nao foi transcrito
        lac = {"inicio": 12.0, "fim": 30.0, "voz_s": 18.0}
        com, sem = tr.classificar_lacunas([lac], words, tokens)
        self.assertEqual(len(com), 1)
        self.assertEqual(com[0]["letra_pendente"], VERSO_B.split())
        self.assertEqual(sem, [])

    def test_loose_function_words_do_not_hide_pending_lines(self):
        # Douma: ASR ouviu so "o", "de" soltos no meio do verso; nao pode virar "vocalise"
        tokens = tr.tokens_da_letra(self.LINHAS)
        words = _words(VERSO_A, 5.0) + _words("o de", 14.0) + _words(PONTE, 40.0)
        lac = {"inicio": 12.0, "fim": 30.0, "voz_s": 18.0}
        com, _sem = tr.classificar_lacunas([lac], words, tokens)
        self.assertEqual(len(com), 1)
        self.assertGreaterEqual(len(com[0]["letra_pendente"]), 5)

    def test_vocalise_after_last_line_is_not_an_error(self):
        tokens = tr.tokens_da_letra(self.LINHAS)
        words = _words(VERSO_A, 5.0) + _words(VERSO_B, 12.0) + _words(PONTE, 20.0)
        outro = {"inicio": 30.0, "fim": 38.0, "voz_s": 8.0}
        com, sem = tr.classificar_lacunas([outro], words, tokens)
        self.assertEqual(com, [])
        self.assertEqual(len(sem), 1)

    def test_retranscription_window_spans_the_pending_lines(self):
        # Douma: lacuna de energia 30,5-35,5 s, mas as linhas pendentes vao de ~29 a ~42 s
        tokens = tr.tokens_da_letra(self.LINHAS)
        words = _words(VERSO_A, 5.0) + _words(PONTE, 30.0)          # VERSO_A acaba ~8,2 s
        lac = {"inicio": 12.0, "fim": 16.0, "voz_s": 4.0}
        a, b = tr.janela_da_letra_pendente(lac, words, tokens)
        self.assertLessEqual(a, 8.6)                                  # comeca no fim da linha anterior
        self.assertGreaterEqual(b, 29.9)                              # vai ate a proxima linha casada
        longe = _words(VERSO_A, 5.0) + _words(PONTE, 60.0)
        a2, b2 = tr.janela_da_letra_pendente(lac, longe, tokens)
        self.assertLessEqual(b2 - a2, 28.0 + 1e-6)                    # nunca janela gigante

    def test_replacement_is_limited_to_what_the_new_pass_explained(self):
        # Douma: janela ia ate o meio do refrao; so o trecho casado com a letra pendente troca
        novos = _words(VERSO_B, 20.0, passo=0.5) + _words("PARAISO ETERNO", 24.0, passo=0.5)
        s0, s1 = tr.trecho_explicado(novos, VERSO_B.split())
        self.assertAlmostEqual(s0, 19.95, places=2)
        self.assertLess(s1, 24.0)                                     # o refrao seguinte nao entra
        self.assertEqual(tr.trecho_explicado(_words("oh oh oh", 3.0), ["Douma", "Segunda"]), (0.0, -1.0))

    def test_vocalise_with_one_matching_word_is_not_accepted(self):
        energia = [(i * 0.5, -18.0) for i in range(40)]
        vocalise = _words("a a a a a a a", 2.0, passo=1.0, prob=0.8)
        self.assertFalse(tr.aceitar_passada_guiada(vocalise, ["Douma,", "a"], energia, limiar_db=-30.0))

    def test_guided_pass_rejects_prompt_copied_over_silence(self):
        esperados = VERSO_B.split()
        energia = [(i * 0.5, -18.0 if 20 <= i * 0.5 < 24 else -60.0) for i in range(80)]
        bons = _words(VERSO_B, 20.0, passo=0.5, prob=0.8)
        self.assertTrue(tr.aceitar_passada_guiada(bons, esperados, energia, limiar_db=-30.0))
        copiado = _words(VERSO_B, 30.0, passo=0.5, prob=0.8)            # caiu no silencio
        self.assertFalse(tr.aceitar_passada_guiada(copiado, esperados, energia, limiar_db=-30.0))
        fraco = _words(VERSO_B, 20.0, passo=0.5, prob=0.2)              # confianca baixa
        self.assertFalse(tr.aceitar_passada_guiada(fraco, esperados, energia, limiar_db=-30.0))
        outra = _words("nada a ver com isso aqui agora", 20.0, passo=0.5, prob=0.9)
        self.assertFalse(tr.aceitar_passada_guiada(outra, esperados, energia, limiar_db=-30.0))


class LacunaVocalTests(unittest.TestCase):
    def test_voice_without_words_is_flagged(self):
        # Caso Gojo: stem vocal com voz de 30 a 58 s e Whisper sem nenhuma palavra.
        energia = [(t * 0.5, -18.0) for t in range(0, 200)]  # voz o tempo todo (0-100 s)
        words = _words(VERSO_A, 10.0) + _words(PONTE, 60.0)
        lacunas = tr.lacunas_vocais(words, energia)
        self.assertTrue(any(x["inicio"] < 20 and x["fim"] > 55 for x in lacunas), lacunas)

    def test_fully_transcribed_voice_has_no_gap(self):
        words = []
        t = 0.0
        while t < 20:
            words += _words("la la la la", t)
            t += 1.6
        energia = [(i * 0.5, -18.0) for i in range(40)]
        self.assertEqual(tr.lacunas_vocais(words, energia), [])


class AlucinacaoWhisperTests(unittest.TestCase):
    def test_youtube_outro_hallucination_is_removed(self):
        lixo = _words("Inscreva-se no canal e ative o sininho", 130.0, prob=0.98)
        bom = _words(VERSO_A, 10.0)
        dados = {"words": bom + lixo, "segments": [
            {"start": 10, "end": 14, "text": VERSO_A, "words": bom},
            {"start": 130, "end": 133, "text": "Inscreva-se no canal e ative o sininho", "words": lixo}]}
        removidas = tr.limpar_alucinacoes(dados)
        self.assertEqual(removidas, len(lixo))
        self.assertEqual(dados["words"], bom)

    def test_degenerate_stretched_word_does_not_count_as_voice(self):
        # "o" com prob 0.00 esticado por 2.5 s escondia um verso inteiro
        esticada = {"word": "o", "start": 73.16, "end": 75.68, "probability": 0.0}
        self.assertFalse(tr.palavra_confiavel(esticada))
        energia = [(70 + i * 0.5, -18.0) for i in range(20)]
        lac = tr.lacunas_vocais([esticada], energia, min_lacuna=2.0)
        self.assertTrue(lac)


class AuditorLetraTests(unittest.TestCase):
    def test_sung_block_missing_from_lyrics_is_reported(self):
        # Audio: verso A, verso B, REFRAO, ponte. Letra esqueceu o refrao do meio.
        words = (_words(VERSO_A, 10) + _words(VERSO_B, 20) +
                 _words(REFRAO, 30) + _words(PONTE, 40))
        rel = al.auditar([VERSO_A, VERSO_B, PONTE], words)
        self.assertFalse(rel["aprovado"])
        self.assertEqual(len(rel["cantado_fora_da_letra"]), 1)
        self.assertIn("limite", rel["cantado_fora_da_letra"][0]["ouvido"])

    def test_lyric_line_not_sung_is_reported(self):
        words = _words(VERSO_A, 10) + _words(PONTE, 20)
        rel = al.auditar([VERSO_A, "Vermelho repelindo explodindo o que tem", PONTE], words)
        self.assertFalse(rel["aprovado"])
        self.assertEqual([l["indice"] for l in rel["linhas_sem_audio"]], [1])

    def test_low_confidence_hallucination_is_noise_not_missing_verse(self):
        words = _words(VERSO_A, 10) + _words("Tchau Staff bouro Schools Tchau tchau", 30, prob=0.05)
        rel = al.auditar([VERSO_A], words)
        self.assertTrue(rel["aprovado"], rel["motivos"])
        self.assertEqual(len(rel["ruido_asr"]), 1)

    def test_matching_lyrics_approve(self):
        words = _words(VERSO_A, 10) + _words(REFRAO, 20) + _words(PONTE, 30) + _words(REFRAO, 40)
        rel = al.auditar([VERSO_A, REFRAO, PONTE, REFRAO], words)
        self.assertTrue(rel["aprovado"], rel["motivos"])


class AlinharRefraoRepetidoTests(unittest.TestCase):
    def test_repeated_chorus_lines_land_on_their_own_occurrence(self):
        words = _words(VERSO_A, 10) + _words(REFRAO, 20) + _words(PONTE, 30) + _words(REFRAO, 40)
        sync = sl.alinhar([VERSO_A, REFRAO, PONTE, REFRAO], words)
        starts = [round(l["start"]) for l in sync]
        self.assertEqual(starts, [10, 20, 30, 40])

    def test_section_markers_are_removed(self):
        self.assertEqual(sl.extrair_linhas_suno("[Refrão]\nINFINITO\n[Ponte]\n"), ["INFINITO"])


class ExtrairLinhasSunoTests(unittest.TestCase):
    """Asta (05/10/2026): `transcricao-canonica` leu o suno_lyrics.txt, cujo
    [Style of Music] tem 5 linhas de prosa sem tag — viraram "linhas da letra" e
    a legenda do master saiu com "anime battle energy..." queimada na tela."""

    SUNO = (
        "[Style of Music]\n"
        "Brazilian rap, hard trap beat, dark orchestral, heavy 808 bass,\n"
        "anime battle energy, male vocalist aggressive confident delivery,\n"
        "\n"
        "[Lyrics]\n"
        "[Verso 1]\n"
        "Nasci no Vale de Hage, eu não tinha nada\n"
        "\n"
        "[Refrão]\n"
        "ANTI-MAGIA — eu nasci com zero de magia\n"
    )

    def test_style_prose_is_not_sung_text(self):
        self.assertEqual(
            sl.extrair_linhas_suno(self.SUNO),
            ["Nasci no Vale de Hage, eu não tinha nada",
             "ANTI-MAGIA — eu nasci com zero de magia"],
        )

    def test_style_block_does_not_swallow_lyrics(self):
        # a tag seguinte reabre o bloco lírico (o bloqueio não "gruda" no arquivo)
        self.assertTrue(sl.extrair_linhas_suno(self.SUNO)[-1].startswith("ANTI-MAGIA"))

    def test_sections_without_style_keep_working(self):
        self.assertEqual(
            sl.extrair_linhas_suno("[Intro]\n\n[Refrão]\nINFINITO\n[Ponte]\n"),
            ["INFINITO"],
        )


if __name__ == "__main__":
    unittest.main()
