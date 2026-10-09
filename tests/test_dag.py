"""Testes do grafo de dependencias (vx/dag.py).

O que este modulo protege nao e performance: e a INTEGRIDADE do
`timeline.json`. Sete etapas o editam no lugar, e qualquer onda que as junte
produz uma timeline corrompida em silencio. Os testes abaixo fixam:

* a direcao REAL das arestas (o `stems` produz o vocal que o `transcrever` le --
  a versao antiga tinha isso invertido);
* a ausencia de arestas falsas entre as etapas de composicao;
* a invariante de seguranca (nenhuma onda com duas etapas incompativeis);
* `--serial` (ordem topologica) respeita todas as dependencias.
"""
from __future__ import annotations

import unittest

from vx import dag, etapas


class TestCasamentoDeCaminhos(unittest.TestCase):
    def test_glob_nao_atravessa_barra(self):
        """`*` nao engole `/`: era isso que criava a aresta falsa cenas-auto <- cenas-ia."""
        self.assertTrue(dag._casa("clips_raw/*.mp4", "clips_raw/a.mp4"))
        self.assertFalse(dag._casa("clips_raw/*.mp4", "clips_raw/sub/a.mp4"))
        self.assertFalse(dag._casa("clips_raw/*.mp4", "clips_raw/vx_cenas_ia/*.mp4"))

    def test_fundo_e_cena_sao_artefatos_distintos(self):
        """As artes de fundo sao assets do projeto; as cenas novas sao saida da IA."""
        self.assertFalse(dag._casa("artes_ia/fundo_*.png", "artes_ia/cena_*.png"))

    def test_glob_de_sufixo_casa_com_arquivo_concreto(self):
        self.assertTrue(dag._casa("entradas/stems/*_vocals.wav",
                                  "entradas/stems/{slug}_normalizado_vocals.wav"))

    def test_pasta_explicita_cobre_subdiretorios(self):
        self.assertTrue(dag._casa("clips_raw/", "clips_raw/vx_manga/x.mp4"))

    def test_identicos_casam(self):
        self.assertTrue(dag._casa("timeline.json", "timeline.json"))

    def test_glob_casa_com_arquivo_do_diretorio(self):
        self.assertTrue(dag._casa("clips_raw/*.mp4", "clips_raw/a.mp4"))

    def test_glob_nao_casa_com_arquivo_de_outro_diretorio(self):
        self.assertFalse(dag._casa("clips_raw/*.mp4", "artes_ia/a.png"))

    def test_dois_arquivos_concretos_diferentes_nao_casam(self):
        # Era exatamente isso que criava a aresta invertida stems <- transcrever
        self.assertFalse(dag._casa("entradas/transcrever.json",
                                   "entradas/stems/x_vocals.wav"))

    def test_diretorio_igual_sem_glob_nao_casa(self):
        self.assertFalse(dag._casa("entradas/transcricao.json",
                                   "entradas/stems/{slug}_x.wav"))

    def test_diretiva_de_projeto_vira_coringa(self):
        self.assertEqual(dag._norm("<projeto.json:legenda_ass>"), "*")

    def test_coringa_puro_nao_casa_nada(self):
        """Falha fechada: nao da para provar a ordem de um caminho desconhecido,
        entao nao se inventa aresta -- a etapa cai na onda serial."""
        self.assertFalse(dag._casa("<projeto.json:legenda_ass>", "legendas/a.ass"))
        self.assertFalse(dag._casa("*", "qualquer/coisa.mp4"))

    def test_slug_e_run_id_sao_irrelevantes(self):
        self.assertTrue(dag._casa("entradas/{slug}_a.wav", "entradas/*_a.wav"))
        self.assertTrue(dag._casa("saidas/esteira/<run_id>/x.mp4",
                                  "saidas/esteira/*/x.mp4"))


class TestGrafoReal(unittest.TestCase):
    """Invariantes do registro real (`vx/etapas.py`)."""

    @classmethod
    def setUpClass(cls):
        cls.g = dag.construir()
        cls.nomes = etapas.nomes()

    def test_validacao_sem_problemas(self):
        self.assertEqual(dag.validar(self.g), [])

    def test_sem_ciclos(self):
        probs = [p for p in dag.validar(self.g) if p.startswith("ciclo")]
        self.assertEqual(probs, [])

    def test_direcao_real_stems_para_transcrever(self):
        """O `stems` produz o vocal; o `transcrever` consome. Nunca o contrario."""
        self.assertIn("stems", self.g.deps("transcrever"))
        self.assertNotIn("transcrever", self.g.deps("stems"))

    def test_corrente_de_composicao_na_ordem_do_registro(self):
        self.assertEqual(
            self.g.corrente,
            ["timeline", "cenas-auto", "chroma-auto", "cenas-ia", "titulos",
             "manga-auto", "graficos-auto"])

    def test_composicao_nao_depende_de_composicao_posterior(self):
        """Nenhuma etapa da corrente pode depender de outra que venha depois."""
        for i, nome in enumerate(self.g.corrente):
            posteriores = set(self.g.corrente[i + 1:])
            cruzadas = self.g.deps(nome) & posteriores
            self.assertEqual(cruzadas, set(), f"{nome} depende de {cruzadas}")

    def test_cada_composicao_depende_das_anteriores(self):
        for i, nome in enumerate(self.g.corrente):
            self.assertTrue(set(self.g.corrente[:i]) <= self.g.deps(nome))

    def test_render_clipe_vem_depois_de_toda_a_composicao(self):
        """O bug original: render-clipe rodava antes de graficos-auto."""
        d = self.g.deps("render-clipe")
        for comp in self.g.corrente:
            self.assertIn(comp, d, f"render-clipe nao espera {comp}")

    def test_planejar_usa_a_timeline_final(self):
        self.assertIn("graficos-auto", self.g.deps("planejar"))

    def test_auditar_ritmo_le_a_timeline_final(self):
        self.assertIn("graficos-auto", self.g.deps("auditar-ritmo"))

    def test_qa_master_depende_do_render_e_da_intro(self):
        self.assertEqual({"intro", "render-clipe"}, self.g.deps("qa-master"))

    def test_sincronia_nao_espera_a_composicao(self):
        """Ela so olha a legenda ASS: nao deve herdar a corrente inteira."""
        self.assertFalse(self.g.deps("sincronia") & set(self.g.corrente))


class TestOndas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = dag.construir()
        cls.nomes = etapas.nomes()
        cls.ondas = cls.g.ondas(cls.nomes)

    def test_toda_etapa_aparece_uma_vez(self):
        vistas = [n for onda in self.ondas for n in onda]
        self.assertEqual(sorted(vistas), sorted(self.nomes))

    def test_onda_1_dois_paralelos(self):
        self.assertEqual(set(self.ondas[0]), {"stems", "fonte-limpa"})

    def test_composicao_em_ondas_proprias_e_em_ordem(self):
        posicao = {n: i for i, onda in enumerate(self.ondas) for n in onda}
        for a, b in zip(self.g.corrente, self.g.corrente[1:]):
            self.assertLess(posicao[a], posicao[b], f"{a} deveria vir antes de {b}")

    def test_onda_do_render_vem_depois_da_onda_dos_graficos(self):
        posicao = {n: i for i, onda in enumerate(self.ondas) for n in onda}
        self.assertGreater(posicao["render-clipe"], posicao["graficos-auto"])

    def test_nenhuma_onda_junta_etapas_incompativeis(self):
        """A invariante de seguranca: e isto que protege o timeline.json."""
        for i, onda in enumerate(self.ondas, 1):
            for a in range(len(onda)):
                for b in range(a + 1, len(onda)):
                    self.assertTrue(
                        self.g.pode_rodar_junto(onda[a], onda[b]),
                        f"onda {i}: {onda[a]} + {onda[b]} nao podem rodar juntas")

    def test_nunca_duas_etapas_da_corrente_na_mesma_onda(self):
        for onda in self.ondas:
            na_corrente = [n for n in onda if n in self.g.corrente]
            self.assertLessEqual(len(na_corrente), 1)

    def test_ganho_estimado_coerente(self):
        g_ = dag.ganho_estimado(self.g, self.nomes)
        self.assertEqual(g_["n_etapas"], len(self.nomes))
        self.assertEqual(g_["n_ondas"], len(self.ondas))
        self.assertGreater(g_["n_ondas"], 0)
        self.assertLessEqual(g_["n_ondas"], g_["n_etapas"])
        self.assertGreaterEqual(g_["etapas_em_paralelo"], 2)


class TestOrdemTopologica(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = dag.construir()
        cls.nomes = etapas.nomes()
        cls.ordem = dag.ordem_topologica(cls.g, cls.nomes)

    def test_tem_todas_as_etapas_sem_repetir(self):
        self.assertEqual(sorted(self.ordem), sorted(self.nomes))

    def test_respeita_todas_as_dependencias(self):
        posicao = {n: i for i, n in enumerate(self.ordem)}
        for nome in self.nomes:
            for d in self.g.deps(nome):
                self.assertLess(posicao[d], posicao[nome],
                                f"{d} deveria vir antes de {nome}")

    def test_serial_e_a_esteira_de_sempre(self):
        """`--serial` preserva a ordem do registro quando nao ha conflito."""
        self.assertEqual(self.ordem[0], "stems")


class TestGrafoSintetico(unittest.TestCase):
    """Casso-limite com um registro fabricado (nao depende das 18 etapas reais)."""

    def _etapa(self, nome, le=(), escreve=()):
        return etapas.Etapa(nome, nome, le=tuple(le), escreve=tuple(escreve))

    def test_escritores_do_compartilhado_viram_corrente(self):
        reg = (
            self._etapa("a", escreve=("timeline.json",)),
            self._etapa("b", escreve=("timeline.json",)),
            self._etapa("c", escreve=("outro.json",)),
        )
        g = dag.construir(reg)
        self.assertEqual(g.corrente, ["a", "b"])
        self.assertEqual(dag.validar(g, ["a", "b", "c"]), [])

    def test_leitor_do_compartilhado_espera_todos_os_escritores(self):
        reg = (
            self._etapa("a", escreve=("timeline.json",)),
            self._etapa("b", escreve=("timeline.json",)),
            self._etapa("render", le=("timeline.json",),
                        escreve=("saida.mp4",)),
        )
        g = dag.construir(reg)
        self.assertEqual(g.deps("render"), {"a", "b"})
        self.assertEqual(dag.validar(g, ["a", "b", "render"]), [])

    def test_duas_etapas_que_nao_se_tocam_podem_rodar_juntas(self):
        reg = (
            self._etapa("x", escreve=("x.out",)),
            self._etapa("y", escreve=("y.out",)),
        )
        g = dag.construir(reg)
        self.assertTrue(g.pode_rodar_junto("x", "y"))
        self.assertEqual(len(g.ondas(["x", "y"])), 1)

    def test_dependencia_impede_paralelismo(self):
        reg = (
            self._etapa("x", escreve=("meio.json",)),
            self._etapa("y", le=("meio.json",), escreve=("fim.json",)),
        )
        g = dag.construir(reg)
        self.assertFalse(g.pode_rodar_junto("x", "y"))
        self.assertEqual(g.ondas(["x", "y"]), [["x"], ["y"]])

    def test_ciclo_e_detectado_e_nao_trava(self):
        """Duas etapas que se declaram mutuamente: validar reprova, ondas termina."""
        reg = (
            self._etapa("a", le=("b.out",), escreve=("a.out",)),
            self._etapa("b", le=("a.out",), escreve=("b.out",)),
        )
        g = dag.construir(reg)
        probs = dag.validar(g, ["a", "b"])
        self.assertTrue(any(p.startswith("ciclo") for p in probs))
        ondas = g.ondas(["a", "b"])  # nao pode entrar em loop infinito
        self.assertEqual(len([n for o in ondas for n in o]), 2)


class TestDiagnostico(unittest.TestCase):
    def test_texto_tem_a_corrente_e_as_ondas(self):
        g = dag.construir()
        txt = dag.diagnosticar(g)
        self.assertIn("corrente serial", txt)
        self.assertIn("onda 1", txt)
        self.assertIn("timeline", txt)


if __name__ == "__main__":
    unittest.main()
