from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import gerador_imagem_local as gil  # noqa: E402
import gerador_artes_ia as gai  # noqa: E402


def _imagem_teste(w=64, h=64) -> Image.Image:
    img = Image.new("RGB", (w, h), (20, 20, 40))
    for x in range(0, w, 8):
        for y in range(0, h, 8):
            img.putpixel((x, y), (250, 200, 100))
    return img.resize((w, h))


class FakeComfy:
    """Cliente falso: registra workflows e devolve uma imagem valida."""

    def __init__(self, img=None):
        self.workflows = []
        self.uploads = 0
        self.img = img or _imagem_teste(128, 72)

    def status(self):
        return {"system": {}, "devices": [{}]}

    def checkpoints(self):
        return ["animagine-xl-3.1.safetensors"]

    def upload_imagem(self, img, nome):
        self.uploads += 1
        return nome

    def enfileirar(self, wf):
        self.workflows.append(json.loads(json.dumps(wf)))
        return f"id{len(self.workflows)}"

    def aguardar(self, pid, timeout_s=600):
        return [{"filename": "x.png", "subfolder": "", "type": "output"}]

    def baixar(self, info):
        buf = io.BytesIO()
        self.img.save(buf, "PNG")
        return buf.getvalue()


MANIFESTO = {
    "faixa": "TESTE", "personagem": "Fulano Heroi", "anime": "Anime X (Estudio)",
    "cor": {"destaque": "#7B1FA2", "destaque_claro": "#00E5FF"},
}


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.cfg = gil.carregar_config()

    def test_fallback_usa_personagem_e_anime_sem_parenteses(self):
        pos, neg = gil.montar_prompt(MANIFESTO, "capa", self.cfg)
        self.assertTrue(pos.startswith("fulano heroi, anime x"))
        self.assertIn("purple theme", pos)
        self.assertIn("cyan theme", pos)
        self.assertIn("watermark", neg)

    def test_tags_do_manifesto_vencem_o_fallback(self):
        m = dict(MANIFESTO, imagem_ia={"tags_personagem": "1boy, custom tag", "negativo": "hat"})
        pos, neg = gil.montar_prompt(m, "capa", self.cfg, cena="rain")
        self.assertTrue(pos.startswith("1boy, custom tag, rain"))
        self.assertNotIn("fulano", pos)
        self.assertTrue(neg.endswith("hat"))

    def test_fundo_nao_pede_personagem(self):
        pos, neg = gil.montar_prompt(MANIFESTO, "fundo", self.cfg)
        self.assertNotIn("fulano", pos)
        self.assertIn("no humans", pos)
        self.assertIn("1boy", neg)

    def test_tipo_invalido(self):
        with self.assertRaises(ValueError):
            gil.montar_prompt(MANIFESTO, "banner", self.cfg)

    def test_nome_cor(self):
        self.assertEqual(gil.nome_cor("#FF0000"), "red")
        self.assertEqual(gil.nome_cor("#FF8C00"), "orange")
        self.assertEqual(gil.nome_cor("#00E5FF"), "cyan")
        self.assertEqual(gil.nome_cor("#7B1FA2"), "purple")
        self.assertEqual(gil.nome_cor("#050505"), "black")
        self.assertEqual(gil.nome_cor("zzz"), "")

    def test_seed_deterministica(self):
        self.assertEqual(gil.seed_deterministica("a", "capa"), gil.seed_deterministica("a", "capa"))
        self.assertNotEqual(gil.seed_deterministica("a", "capa"), gil.seed_deterministica("a", "fundo"))

    def test_config_sem_personagem_hardcodado(self):
        texto = gil.CONFIG_PADRAO.read_text(encoding="utf-8").lower()
        for nome in ("sasuke", "eren", "naruto", "itachi"):
            self.assertNotIn(nome, texto)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.cfg = gil.carregar_config()

    def test_txt2img_estrutura(self):
        wf = gil.montar_workflow("p", "n", 1344, 768, 7, self.cfg)
        self.assertEqual(wf["4"]["class_type"], "EmptyLatentImage")
        self.assertEqual(wf["5"]["inputs"]["denoise"], 1.0)
        self.assertEqual(wf["5"]["inputs"]["seed"], 7)
        self.assertNotIn("8", wf)

    def test_img2img_estrutura_e_limite_denoise(self):
        wf = gil.montar_workflow("p", "n", 1344, 768, 7, self.cfg, ref_nome="r.png", denoise=0.5)
        self.assertEqual(wf["4"]["class_type"], "VAEEncode")
        self.assertEqual(wf["8"]["inputs"]["image"], "r.png")
        self.assertEqual(wf["5"]["inputs"]["denoise"], 0.5)
        with self.assertRaises(ValueError):
            gil.montar_workflow("p", "n", 8, 8, 1, self.cfg, ref_nome="r.png", denoise=0.0)

    def test_hash_ignora_prefixo(self):
        a = gil.montar_workflow("p", "n", 64, 64, 1, self.cfg, prefixo="a")
        b = gil.montar_workflow("p", "n", 64, 64, 1, self.cfg, prefixo="b")
        c = gil.montar_workflow("p", "n", 64, 64, 2, self.cfg)
        self.assertEqual(gil.hash_workflow(a), gil.hash_workflow(b))
        self.assertNotEqual(gil.hash_workflow(a), gil.hash_workflow(c))


class GerarTests(unittest.TestCase):
    def _projeto(self, tmp):
        p = Path(tmp) / "fulano"
        p.mkdir()
        (p / "projeto.json").write_text(json.dumps(MANIFESTO), encoding="utf-8")
        return p

    def test_gera_variacoes_com_sidecar_e_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._projeto(tmp)
            fake = FakeComfy()
            outs = gil.gerar(p, "capa", variacoes=2, cliente=fake)
            self.assertEqual(len(outs), 2)
            self.assertEqual(len(fake.workflows), 2)
            seeds = [wf["5"]["inputs"]["seed"] for wf in fake.workflows]
            self.assertEqual(seeds[1], seeds[0] + 1)
            meta = json.loads(outs[0].with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(meta["seed"], seeds[0])
            # reexecucao: cache, nenhum workflow novo
            again = gil.gerar(p, "capa", variacoes=2, cliente=fake)
            self.assertEqual(again, outs)
            self.assertEqual(len(fake.workflows), 2)
            # forcar regenera
            gil.gerar(p, "capa", variacoes=1, forcar=True, cliente=fake)
            self.assertEqual(len(fake.workflows), 3)

    def test_img2img_faz_upload_uma_vez(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._projeto(tmp)
            _imagem_teste(200, 100).save(p / "ref.png")
            fake = FakeComfy()
            gil.gerar(p, "capa", variacoes=2, ref="ref.png", denoise=0.5, cliente=fake)
            self.assertEqual(fake.uploads, 1)
            self.assertTrue(all(wf["8"]["inputs"]["image"].startswith("vx_ref_")
                                for wf in fake.workflows))

    def test_rejeita_imagem_preta(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._projeto(tmp)
            fake = FakeComfy(Image.new("RGB", (64, 64), (0, 0, 0)))
            with self.assertRaises(RuntimeError):
                gil.gerar(p, "capa", cliente=fake)
            self.assertEqual(list((p / "artes_ia").glob("*.png")), [])

    def test_checkpoint_ausente_autoescolhe_sdxl(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._projeto(tmp)
            fake = FakeComfy()
            fake.checkpoints = lambda: ["sd15.safetensors", "outroXL.safetensors"]
            gil.gerar(p, "capa", cliente=fake)
            self.assertEqual(fake.workflows[0]["1"]["inputs"]["ckpt_name"], "outroXL.safetensors")

    def test_escolher_checkpoint(self):
        self.assertEqual(gil.escolher_checkpoint("a.safetensors", []), "a.safetensors")
        self.assertEqual(gil.escolher_checkpoint("a.safetensors", ["a.safetensors"]), "a.safetensors")
        self.assertEqual(gil.escolher_checkpoint("a.safetensors", ["b.ckpt"]), "b.ckpt")

    def test_comfy_local_ignora_proxy_do_sistema(self):
        # Charles/Fiddler/HTTP_PROXY devolviam 503 para 127.0.0.1
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"HTTP_PROXY": "http://proxy.invalido.vx:8888",
                                     "http_proxy": "http://proxy.invalido.vx:8888"}):
            cli = gil.ComfyClient("http://127.0.0.1:9", timeout=1)
            with self.assertRaises(gil.ComfyIndisponivel) as ctx:
                cli.status()
        self.assertNotIn("proxy.invalido", str(ctx.exception))

    def test_comfy_offline_vira_erro_explicativo(self):
        cli = gil.ComfyClient("http://127.0.0.1:9", timeout=1)
        with self.assertRaises(gil.ComfyIndisponivel) as ctx:
            cli.status()
        self.assertIn("--disable-pinned-memory", str(ctx.exception))


class CriticoTests(unittest.TestCase):
    def _projeto(self, tmp):
        p = Path(tmp) / "fulano"
        p.mkdir()
        (p / "projeto.json").write_text(json.dumps(MANIFESTO), encoding="utf-8")
        return p

    def test_gerar_melhor_fica_so_com_a_vencedora_e_cacheia(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._projeto(tmp)
            fake = FakeComfy()
            chamadas = []

            def pontuar(paths, intencao, identidade):
                chamadas.append((intencao, identidade))
                # vencedora = a ultima variacao
                return [{"path": str(x), "final": float(i)} for i, x in reversed(list(enumerate(paths)))]

            win = gil.gerar_melhor(p, "capa", cena="rain", variacoes=3, cliente=fake, pontuar=pontuar)
            self.assertEqual(len(fake.workflows), 3)
            self.assertEqual(sorted(x.name for x in (p / "artes_ia").glob("*.png")), [win.name])
            self.assertIn("fulano heroi", chamadas[0][0].lower())
            self.assertIn("Anime X", chamadas[0][1])
            again = gil.gerar_melhor(p, "capa", cena="rain", variacoes=3, cliente=fake, pontuar=pontuar)
            self.assertEqual(again, win)
            self.assertEqual(len(fake.workflows), 3)
            reg = json.loads((p / "artes_ia" / "escolhas.json").read_text(encoding="utf-8"))
            self.assertEqual(len(next(iter(reg.values()))["ranking"]), 3)

    def test_fundo_sem_identidade_de_personagem(self):
        self.assertIsNone(gil.identidade_clip(MANIFESTO, "fundo"))
        self.assertIn("scenery", gil.intencao_clip(MANIFESTO, "fundo", "ruins"))

    def test_exposicao(self):
        import critico_imagem as ci
        self.assertEqual(ci.exposicao(Image.new("RGB", (8, 8), (100, 100, 100))), 1.0)
        self.assertLess(ci.exposicao(Image.new("RGB", (8, 8), (5, 5, 5))), 0.2)


class AutoConfigTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(gil.carregar_config(), comfy_url="http://127.0.0.1:9", espera_inicio_s=1)

    def test_localiza_comfy_pelo_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.py").write_text("", encoding="utf-8")
            self.assertEqual(gil.localizar_comfy(dict(self.cfg, comfy_dir=tmp)), Path(tmp))

    def test_auto_iniciar_desligado_nao_sobe(self):
        with self.assertRaisesRegex(gil.ComfyIndisponivel, "auto_iniciar"):
            gil.garantir_comfy(dict(self.cfg, auto_iniciar=False))

    def test_url_remota_nunca_autoinicia(self):
        with self.assertRaisesRegex(gil.ComfyIndisponivel, "remoto"):
            gil.garantir_comfy(dict(self.cfg, comfy_url="http://10.255.255.1:8188"))

    def test_parar_sem_pid_nao_mata_nada(self):
        orig = gil.PID_COMFY
        with tempfile.TemporaryDirectory() as tmp:
            gil.PID_COMFY = Path(tmp) / "nao_existe.pid"
            try:
                self.assertFalse(gil.parar_comfy())
            finally:
                gil.PID_COMFY = orig


class ArtesIATests(unittest.TestCase):
    def test_sem_chave_de_api_no_codigo(self):
        fonte = (ROOT / "ferramentas" / "gerador_artes_ia.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9-]{10,}", fonte))
        self.assertNotIn("sasuke", fonte.lower())

    def test_kanji_prioriza_manifesto(self):
        m = dict(MANIFESTO, imagem_ia={"kanji": ["漢字", "ナマエ"]})
        self.assertEqual(gai.kanji_do_manifesto(m), ("漢字", "ナマエ"))
        self.assertIsNone(gai.kanji_do_manifesto(MANIFESTO))
        self.assertEqual(gai.kanji_do_manifesto({"anime": "Jujutsu Kaisen"})[0], "呪術廻戦")

    def test_remoto_sem_env_falha_antes_de_rede(self):
        with self.assertRaisesRegex(RuntimeError, "VX_IMAGE_API_KEY"):
            gai.gerar_imagem_api("x")

    def test_capa_local_compoe_1280x720(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "fulano"
            p.mkdir()
            (p / "projeto.json").write_text(json.dumps(MANIFESTO), encoding="utf-8")
            fake = FakeComfy(_imagem_teste(1344, 768))
            orig = gil.ComfyClient
            gil.ComfyClient = lambda *a, **k: fake
            try:
                out = gai.gerar_miniatura_completa(p, variacoes=1)
            finally:
                gil.ComfyClient = orig
            self.assertEqual(out.name, "fulano_capa_ia.jpg")
            with Image.open(out) as img:
                self.assertEqual(img.size, (1280, 720))
            self.assertLess(out.stat().st_size, 2 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
