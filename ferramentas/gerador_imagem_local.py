#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gerador_imagem_local.py — VX Image Local: geracao de imagens na RTX 3090 via ComfyUI.

Motor local (sem API externa) para capas, fundos, verticais e artes quadradas.
Fala com a API HTTP do ComfyUI (padrao http://127.0.0.1:8188) e usa um checkpoint
SDXL de anime (padrao Animagine XL 3.1).

Contrato:
- Identidade do personagem vem do projeto.json (bloco ``imagem_ia``) ou do par
  ``personagem``/``anime``. Nunca hardcodar personagem aqui.
- Parametros de modelo/sampler/formatos vivem em assets/design/imagem_local.json.
- Seed deterministica por (slug, tipo, cena) quando nao informada: rerodar gera a
  mesma imagem. Cache por hash do workflow em projetos/<slug>/artes_ia/.
- Toda imagem e validada (nao preta/nao chapada) antes de ser entregue.

Portas:
    python estudio.py comfy-status
    python estudio.py gerar-imagem <slug> --tipo capa|fundo|vertical|quadrado [--cena "tags"]
    python estudio.py capa-ia <slug>              # usa este motor por padrao
"""
from __future__ import annotations

import colorsys
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from semantic_vision import imagem_ia_cfg
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageOps, ImageStat

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_PADRAO = RAIZ / "assets" / "design" / "imagem_local.json"
TIPOS = ("capa", "fundo", "vertical", "quadrado", "cena")
COMANDO_SUBIR = ("python <ComfyUI>\\main.py --listen 127.0.0.1 --port 8188 "
                 "--disable-pinned-memory")
DIR_LOGS = RAIZ / "logs"
PID_COMFY = DIR_LOGS / "comfyui.pid"
LOG_COMFY = DIR_LOGS / "comfyui.log"
CANDIDATOS_COMFY = (
    Path.home() / "Documents" / "comfy" / "ComfyUI",
    Path.home() / "Documents" / "ComfyUI",
    Path.home() / "ComfyUI",
    Path.home() / "Desktop" / "ComfyUI",
    Path("C:/ComfyUI"),
    Path("C:/ComfyUI_windows_portable/ComfyUI"),
)


class ComfyIndisponivel(RuntimeError):
    """ComfyUI nao respondeu; a mensagem explica como subir."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def carregar_config(caminho: Path = CONFIG_PADRAO) -> Dict[str, Any]:
    cfg = json.loads(Path(caminho).read_text(encoding="utf-8-sig"))
    url_env = os.environ.get("VX_COMFY_URL")
    if url_env:
        cfg["comfy_url"] = url_env
    ckpt_env = os.environ.get("VX_COMFY_CHECKPOINT")
    if ckpt_env:
        cfg["checkpoint"] = ckpt_env
    return cfg


# ---------------------------------------------------------------------------
# Cliente HTTP do ComfyUI
# ---------------------------------------------------------------------------

_SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ComfyClient:
    def __init__(self, url: str, timeout: float = 15.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex

    def _req(self, caminho: str, dados: Optional[bytes] = None,
             headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> bytes:
        req = urllib.request.Request(self.url + caminho, data=dados, headers=headers or {})
        # ComfyUI local nunca passa por proxy do sistema (Charles/Fiddler/HTTP_PROXY
        # devolviam 503 para 127.0.0.1 e o estudio achava que o ComfyUI estava quebrado)
        host = urllib.parse.urlparse(self.url).hostname or ""
        abrir = (_SEM_PROXY.open if host in ("127.0.0.1", "localhost", "::1")
                 else urllib.request.urlopen)
        try:
            with abrir(req, timeout=timeout or self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            corpo = exc.read().decode("utf-8", "replace")[:2000]
            raise RuntimeError(f"ComfyUI HTTP {exc.code} em {caminho}: {corpo}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise ComfyIndisponivel(
                f"ComfyUI nao respondeu em {self.url} ({exc}). Suba com: {COMANDO_SUBIR}") from exc

    def _json(self, caminho: str, payload: Optional[dict] = None) -> Any:
        dados = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        return json.loads(self._req(caminho, dados, headers).decode("utf-8") or "{}")

    def status(self) -> Dict[str, Any]:
        return self._json("/system_stats")

    def checkpoints(self) -> List[str]:
        info = self._json("/object_info/CheckpointLoaderSimple")
        try:
            return list(info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
        except (KeyError, IndexError, TypeError):
            return []

    def upload_imagem(self, img: Image.Image, nome: str) -> str:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        limite = "----vx" + uuid.uuid4().hex
        corpo = (
            f"--{limite}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
            f"--{limite}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{nome}\"\r\n"
            f"Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + buf.getvalue() + f"\r\n--{limite}--\r\n".encode("utf-8")
        resp = json.loads(self._req("/upload/image", corpo,
                                    {"Content-Type": f"multipart/form-data; boundary={limite}"}))
        sub = resp.get("subfolder") or ""
        return f"{sub}/{resp['name']}" if sub else resp["name"]

    def enfileirar(self, workflow: Dict[str, Any]) -> str:
        resp = self._json("/prompt", {"prompt": workflow, "client_id": self.client_id})
        if resp.get("node_errors"):
            raise RuntimeError(f"ComfyUI rejeitou o workflow: {resp['node_errors']}")
        return resp["prompt_id"]

    def aguardar(self, prompt_id: str, timeout_s: float = 600, intervalo: float = 1.0) -> List[dict]:
        fim = time.monotonic() + timeout_s
        while time.monotonic() < fim:
            hist = self._json(f"/history/{prompt_id}")
            item = hist.get(prompt_id)
            if item:
                st = item.get("status", {})
                if st.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI falhou: {st.get('messages')}")
                if st.get("completed", True):
                    imgs = [im for out in item.get("outputs", {}).values()
                            for im in out.get("images", []) if im.get("type") == "output"]
                    if imgs:
                        return imgs
                    raise RuntimeError("ComfyUI concluiu sem imagens de saida")
            time.sleep(intervalo)
        raise TimeoutError(f"ComfyUI nao terminou em {timeout_s}s (prompt {prompt_id})")

    def baixar(self, info: dict) -> bytes:
        q = urllib.parse.urlencode({"filename": info["filename"],
                                    "subfolder": info.get("subfolder", ""),
                                    "type": info.get("type", "output")})
        return self._req(f"/view?{q}", timeout=60)

    def liberar_vram(self) -> None:
        self._json("/free", {"unload_models": True, "free_memory": True})


# ---------------------------------------------------------------------------
# Prompt a partir do manifesto (generico)
# ---------------------------------------------------------------------------

def nome_cor(hex_cor: str) -> str:
    """Nome de cor em ingles (tags SDXL) a partir do matiz de um hex."""
    h = (hex_cor or "").lstrip("#")
    if len(h) != 6:
        return ""
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return ""
    hue, luz, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.18:
        return "white" if luz > 0.75 else ("black" if luz < 0.2 else "silver")
    graus = hue * 360
    for limite, nome in ((15, "red"), (40, "orange"), (65, "golden"), (160, "green"),
                         (200, "cyan"), (255, "blue"), (290, "purple"), (335, "magenta"),
                         (361, "red")):
        if graus < limite:
            return nome
    return ""


def _anime_base(anime: str) -> str:
    return (anime or "").split("(")[0].strip()


def tags_personagem(manifesto: Dict[str, Any]) -> str:
    bloco = imagem_ia_cfg(manifesto)
    if bloco.get("tags_personagem"):
        return str(bloco["tags_personagem"]).strip()
    partes = [p for p in (str(manifesto.get("personagem", "")).lower().strip(),
                          _anime_base(str(manifesto.get("anime", ""))).lower()) if p]
    return ", ".join(partes)


def montar_prompt(manifesto: Dict[str, Any], tipo: str, cfg: Dict[str, Any],
                  cena: Optional[str] = None) -> Tuple[str, str]:
    if tipo not in TIPOS:
        raise ValueError(f"tipo invalido: {tipo} (use {', '.join(TIPOS)})")
    bloco = imagem_ia_cfg(manifesto)
    cores = manifesto.get("cor") or {}
    tons = [c for c in (nome_cor(cores.get("destaque", "")),
                        nome_cor(cores.get("destaque_claro", ""))) if c]
    tons = list(dict.fromkeys(tons))
    partes: List[str] = []
    if tipo == "fundo":
        anime = _anime_base(str(manifesto.get("anime", ""))).lower()
        if anime:
            partes.append(anime)
        if bloco.get("tags_cenario"):
            partes.append(str(bloco["tags_cenario"]))
    else:
        partes.append(tags_personagem(manifesto))
    if cena:
        partes.append(cena)
    partes.append(cfg["estilos"].get(tipo, ""))
    if tons:
        partes.append(", ".join(f"{t} theme" for t in tons) + f", {tons[0]} aura")
    if bloco.get("tags_estilo"):
        partes.append(str(bloco["tags_estilo"]))
    partes.append(cfg["qualidade_tags"])
    positivo = ", ".join(p.strip(" ,") for p in partes if p and p.strip(" ,"))
    negativos = [cfg["negativo_base"], cfg.get("negativo_extra", {}).get(tipo, ""),
                 str(bloco.get("negativo", ""))]
    negativo = ", ".join(n.strip(" ,") for n in negativos if n and n.strip(" ,"))
    return positivo, negativo


def seed_deterministica(*partes: Any) -> int:
    dig = hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).digest()
    return int.from_bytes(dig[:6], "big")


# ---------------------------------------------------------------------------
# Workflow SDXL (formato API do ComfyUI)
# ---------------------------------------------------------------------------

def montar_workflow(positivo: str, negativo: str, largura: int, altura: int, seed: int,
                    cfg: Dict[str, Any], ref_nome: Optional[str] = None,
                    denoise: float = 1.0, prefixo: str = "vx") -> Dict[str, Any]:
    wf: Dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": cfg["checkpoint"]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positivo, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negativo, "clip": ["1", 1]}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": int(seed), "steps": int(cfg["steps"]), "cfg": float(cfg["cfg"]),
                         "sampler_name": cfg["sampler"], "scheduler": cfg["scheduler"],
                         "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0],
                         "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefixo}},
    }
    if ref_nome:
        if not 0.05 <= denoise <= 1.0:
            raise ValueError("denoise do img2img deve ficar entre 0.05 e 1.0")
        wf["8"] = {"class_type": "LoadImage", "inputs": {"image": ref_nome}}
        wf["4"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["1", 2]}}
        wf["5"]["inputs"]["denoise"] = float(denoise)
    else:
        wf["4"] = {"class_type": "EmptyLatentImage",
                   "inputs": {"width": int(largura), "height": int(altura), "batch_size": 1}}
    return wf


def hash_workflow(wf: Dict[str, Any], ref_digest: str = "") -> str:
    limpo = json.loads(json.dumps(wf))
    limpo["7"]["inputs"].pop("filename_prefix", None)
    if "8" in limpo:
        limpo["8"]["inputs"]["image"] = ref_digest
    return hashlib.sha256(json.dumps(limpo, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Imagem
# ---------------------------------------------------------------------------

def enquadrar(img: Image.Image, largura: int, altura: int, foco_y: float = 0.35) -> Image.Image:
    """Crop 'cover' + resize LANCZOS. foco_y puxa o corte para cima (rosto)."""
    return ImageOps.fit(img, (largura, altura), Image.Resampling.LANCZOS,
                        centering=(0.5, foco_y))


def validar_imagem(img: Image.Image) -> None:
    st = ImageStat.Stat(img.convert("L"))
    media, desvio = st.mean[0], st.stddev[0]
    if media < 8:
        raise RuntimeError(f"Imagem gerada praticamente preta (luma media {media:.1f})")
    if desvio < 6:
        raise RuntimeError(f"Imagem gerada chapada/sem detalhe (desvio {desvio:.1f})")


def gerar_via_api_openai(cfg: Dict[str, Any], prompt: str,
                         largura: int, altura: int) -> Optional[Image.Image]:
    """Tenta gerar via endpoint de API compativel (ex: /v1/images/generations)."""
    import base64
    endpoint = cfg.get("api_endpoint")
    key = cfg.get("api_key")
    modelo = cfg.get("api_model") or "ag/gemini-3.1-flash-image"
    if not endpoint or not key:
        return None
    payload = {
        "model": modelo,
        "prompt": prompt,
        "n": 1,
        "size": "auto",
        "quality": "auto",
        "background": "auto",
        "image_detail": "high",
        "output_format": "png"
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}"
        }
    )
    host = urllib.parse.urlparse(endpoint).hostname or ""
    abrir = (_SEM_PROXY.open if host in ("127.0.0.1", "localhost", "::1")
             else urllib.request.urlopen)
    try:
        with abrir(req, timeout=30) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            data = d.get("data", [])
            if not data:
                return None
            item = data[0]
            if "b64_json" in item:
                buf = io.BytesIO(base64.b64decode(item["b64_json"]))
                return Image.open(buf).convert("RGB")
            elif "url" in item:
                with urllib.request.urlopen(item["url"], timeout=30) as img_resp:
                    return Image.open(io.BytesIO(img_resp.read())).convert("RGB")
    except Exception as exc:
        print(f"[VX IMAGE] API externa ({modelo} em {host}) indisponivel: {exc}")
        return None


# ---------------------------------------------------------------------------
# Porta principal
# ---------------------------------------------------------------------------

def gerar(projeto_dir: Path, tipo: str = "capa", cena: Optional[str] = None,
          seed: Optional[int] = None, variacoes: int = 1, ref: Optional[Path] = None,
          denoise: float = 0.6, forcar: bool = False, cfg: Optional[Dict[str, Any]] = None,
          cliente: Optional[ComfyClient] = None) -> List[Path]:
    """Gera ``variacoes`` imagens para o projeto. Retorna PNGs em artes_ia/ (resolucao nativa)."""
    projeto_dir = Path(projeto_dir)
    cfg = cfg or carregar_config()
    manifesto = json.loads((projeto_dir / "projeto.json").read_text(encoding="utf-8-sig"))
    if tipo not in cfg["formatos"]:
        raise ValueError(f"tipo invalido: {tipo}")
    fmt = cfg["formatos"][tipo]
    largura, altura = int(fmt["largura"]), int(fmt["altura"])
    positivo, negativo = montar_prompt(manifesto, tipo, cfg, cena)
    base_seed = seed if seed is not None else seed_deterministica(projeto_dir.name, tipo, cena or "")
    pasta = projeto_dir / "artes_ia"
    pasta.mkdir(parents=True, exist_ok=True)

    ref_img = ref_digest = None
    if ref:
        ref_path = Path(ref)
        if not ref_path.is_absolute():
            ref_path = projeto_dir / ref_path
        ref_img = enquadrar(Image.open(ref_path).convert("RGB"), largura, altura, foco_y=0.5)
        ref_digest = hashlib.sha256(ref_img.tobytes()).hexdigest()[:16]

    cliente_padrao = cliente is None
    cliente = cliente or ComfyClient(cfg["comfy_url"])
    ref_nome: Optional[str] = None
    checado = False
    saidas: List[Path] = []
    for i in range(max(1, int(variacoes))):
        s = int(base_seed) + i
        wf = montar_workflow(positivo, negativo, largura, altura, s, cfg,
                             ref_nome="__ref__" if ref_img is not None else None,
                             denoise=denoise, prefixo=f"vx_{projeto_dir.name}_{tipo}")
        digest = hash_workflow(wf, ref_digest or "")[:12]
        destino = pasta / f"{tipo}_{s}_{digest}.png"
        if destino.is_file() and destino.stat().st_size and not forcar:
            print(f"[VX IMAGE] cache: {destino.name}")
            saidas.append(destino)
            continue
        # Tenta API externa configurada (se houver) antes do ComfyUI local
        if cfg.get("api_endpoint"):
            img_api = gerar_via_api_openai(cfg, positivo, largura, altura)
            if img_api is not None:
                validar_imagem(img_api)
                img_api.save(destino, "PNG")
                print(f"[VX IMAGE] ok via API externa -> {destino}")
                saidas.append(destino)
                continue
        if not checado:
            if cliente_padrao:
                _registrar_sessao(garantir_comfy(cfg))
            else:
                cliente.status()
            disponiveis = cliente.checkpoints()
            efetivo = escolher_checkpoint(cfg["checkpoint"], disponiveis)
            if efetivo is None:
                raise RuntimeError("Checkpoint: nenhum modelo em ComfyUI/models/checkpoints")
            if efetivo != cfg["checkpoint"]:
                print(f"[VX IMAGE] aviso: {cfg['checkpoint']} ausente; usando {efetivo}")
                cfg = dict(cfg, checkpoint=efetivo)
                wf["1"]["inputs"]["ckpt_name"] = efetivo
            checado = True
        if ref_img is not None:
            if ref_nome is None:
                ref_nome = cliente.upload_imagem(ref_img, f"vx_ref_{ref_digest}.png")
            wf["8"]["inputs"]["image"] = ref_nome
        print(f"[VX IMAGE] gerando {tipo} seed={s} ({largura}x{altura}) via {cfg['checkpoint']}...")
        t0 = time.monotonic()
        infos = cliente.aguardar(cliente.enfileirar(wf), float(cfg.get("timeout_s", 600)))
        img = Image.open(io.BytesIO(cliente.baixar(infos[0]))).convert("RGB")
        validar_imagem(img)
        tmp = destino.with_suffix(".tmp.png")
        img.save(tmp, "PNG")
        tmp.replace(destino)
        destino.with_suffix(".json").write_text(json.dumps({
            "tipo": tipo, "seed": s, "checkpoint": cfg["checkpoint"], "positivo": positivo,
            "negativo": negativo, "largura": largura, "altura": altura,
            "sampler": cfg["sampler"], "scheduler": cfg["scheduler"], "steps": cfg["steps"],
            "cfg": cfg["cfg"], "ref": str(ref) if ref else None,
            "denoise": denoise if ref else 1.0, "segundos": round(time.monotonic() - t0, 1),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[VX IMAGE] ok em {time.monotonic() - t0:.1f}s -> {destino}")
        saidas.append(destino)
    return saidas


def intencao_clip(manifesto: Dict[str, Any], tipo: str, cena: Optional[str]) -> str:
    """Frase natural para o critico CLIP (nao vai para o SDXL)."""
    bloco = imagem_ia_cfg(manifesto)
    anime = _anime_base(str(manifesto.get("anime", "")))
    if tipo == "fundo":
        return f"anime background scenery from {anime}, {cena or bloco.get('tags_cenario', '')}".strip(", ")
    pers = manifesto.get("personagem", "")
    return f"anime illustration of {pers} from {anime}, {cena or bloco.get('tags_estilo', '')}".strip(", ")


def identidade_clip(manifesto: Dict[str, Any], tipo: str) -> Optional[str]:
    if tipo == "fundo":
        return None
    bloco = imagem_ia_cfg(manifesto)
    if bloco.get("clip_identidade"):
        return str(bloco["clip_identidade"])
    pers = manifesto.get("personagem", "")
    anime = _anime_base(str(manifesto.get("anime", "")))
    return f"{pers} from the anime {anime}" if pers else None


def gerar_melhor(projeto_dir: Path, tipo: str = "capa", cena: Optional[str] = None,
                 variacoes: int = 3, seed: Optional[int] = None, ref: Optional[Path] = None,
                 denoise: float = 0.6, forcar: bool = False, cfg: Optional[Dict[str, Any]] = None,
                 cliente: Optional[ComfyClient] = None, pontuar=None) -> Path:
    """Gera N variacoes, o VX Image Critic escolhe a melhor e as perdedoras sao apagadas.

    A escolha fica em artes_ia/escolhas.json: rerodar devolve a vencedora sem gerar de novo.
    """
    projeto_dir = Path(projeto_dir)
    cfg = cfg or carregar_config()
    manifesto = json.loads((projeto_dir / "projeto.json").read_text(encoding="utf-8-sig"))
    base_seed = seed if seed is not None else seed_deterministica(projeto_dir.name, tipo, cena or "")
    chave = hashlib.sha256(json.dumps(
        [tipo, cena or "", int(variacoes), int(base_seed), str(ref or ""), denoise, cfg["checkpoint"],
         cfg["steps"], cfg["cfg"], cfg["sampler"]], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    registro_path = projeto_dir / "artes_ia" / "escolhas.json"
    try:
        registro = json.loads(registro_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        registro = {}
    if not forcar and chave in registro:
        vencedora = projeto_dir / registro[chave]["vencedora"]
        if vencedora.is_file():
            print(f"[VX CRITIC] escolha em cache: {vencedora.name}")
            return vencedora
    paths = gerar(projeto_dir, tipo, cena=cena, seed=base_seed, variacoes=variacoes, ref=ref,
                  denoise=denoise, forcar=forcar, cfg=cfg, cliente=cliente)
    ranking: List[dict] = []
    if len(paths) > 1:
        if pontuar is None:
            import critico_imagem
            pontuar = critico_imagem.pontuar
        ranking = pontuar(paths, intencao_clip(manifesto, tipo, cena), identidade_clip(manifesto, tipo))
        vencedora = Path(ranking[0]["path"])
    else:
        vencedora = paths[0]
    for p in paths:
        if p != vencedora:
            p.unlink(missing_ok=True)
            p.with_suffix(".json").unlink(missing_ok=True)
    registro[chave] = {
        "tipo": tipo, "cena": cena, "vencedora": str(vencedora.relative_to(projeto_dir)).replace("\\", "/"),
        "ranking": [{**r, "path": Path(r["path"]).name} for r in ranking],
    }
    registro_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = registro_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(registro_path)
    if ranking:
        print(f"[VX CRITIC] {tipo}: vencedora {vencedora.name} (final={ranking[0]['final']:.4f}"
              f" de {len(ranking)} variacoes)")
    return vencedora


def status(cfg: Optional[Dict[str, Any]] = None, iniciar: bool = False) -> Dict[str, Any]:
    cfg = cfg or carregar_config()
    pasta = localizar_comfy(cfg)
    base = {"url": cfg["comfy_url"], "comfy_dir": str(pasta) if pasta else None,
            "auto_iniciar": bool(cfg.get("auto_iniciar", True))}
    if iniciar:
        try:
            base.update(garantir_comfy(cfg))
        except ComfyIndisponivel as exc:
            return {**base, "online": False, "erro": str(exc)}
    cli = ComfyClient(cfg["comfy_url"], timeout=5)
    try:
        st = cli.status()
        ckpts = cli.checkpoints()
    except ComfyIndisponivel as exc:
        return {**base, "online": False, "erro": str(exc)}
    dev = (st.get("devices") or [{}])[0]
    return {**base, "online": True,
            "versao": st.get("system", {}).get("comfyui_version"),
            "gpu": dev.get("name"),
            "vram_livre_mb": round(dev.get("vram_free", 0) / 2**20),
            "checkpoint": cfg["checkpoint"],
            "checkpoint_ok": cfg["checkpoint"] in ckpts,
            "checkpoint_efetivo": escolher_checkpoint(cfg["checkpoint"], ckpts),
            "checkpoints": ckpts}


# ---------------------------------------------------------------------------
# Autoconfiguracao: localizar, subir e desligar o ComfyUI local
# ---------------------------------------------------------------------------

def escolher_checkpoint(preferido: str, disponiveis: List[str]) -> Optional[str]:
    """Preferido se existir; senao o primeiro SDXL (xl no nome); senao o primeiro."""
    if not disponiveis or preferido in disponiveis:
        return preferido
    xl = [c for c in disponiveis if "xl" in c.lower()]
    return (xl or disponiveis)[0]


def localizar_comfy(cfg: Dict[str, Any]) -> Optional[Path]:
    candidatos = [os.environ.get("VX_COMFY_DIR", ""), str(cfg.get("comfy_dir") or "")]
    for c in [Path(x) for x in candidatos if x] + list(CANDIDATOS_COMFY):
        if (c / "main.py").is_file():
            return c
    return None


def _python_do_comfy(pasta: Path) -> str:
    import sys
    for c in (pasta / "venv" / "Scripts" / "python.exe", pasta / ".venv" / "Scripts" / "python.exe",
              pasta.parent / "python_embeded" / "python.exe",
              pasta / "venv" / "bin" / "python", pasta / ".venv" / "bin" / "python"):
        if c.is_file():
            return str(c)
    return sys.executable


def _url_local(url: str) -> Tuple[str, int]:
    p = urllib.parse.urlparse(url)
    return p.hostname or "127.0.0.1", int(p.port or 8188)


def garantir_comfy(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Garante ComfyUI online. Sobe automaticamente (local) se configurado.

    Retorna {"online": True, "iniciado_por_nos": bool, "pid": int|None}.
    """
    import subprocess
    cfg = cfg or carregar_config()
    cli = ComfyClient(cfg["comfy_url"], timeout=4)
    try:
        cli.status()
        return {"online": True, "iniciado_por_nos": False, "pid": None}
    except ComfyIndisponivel:
        pass
    host, porta = _url_local(cfg["comfy_url"])
    if not cfg.get("auto_iniciar", True):
        raise ComfyIndisponivel(f"ComfyUI offline e auto_iniciar=false. Suba com: {COMANDO_SUBIR}")
    if host not in ("127.0.0.1", "localhost"):
        raise ComfyIndisponivel(f"ComfyUI remoto ({host}) offline; auto-inicio so vale para localhost")
    pasta = localizar_comfy(cfg)
    if pasta is None:
        raise ComfyIndisponivel("ComfyUI nao encontrado. Defina comfy_dir em "
                                "assets/design/imagem_local.json ou VX_COMFY_DIR.")
    DIR_LOGS.mkdir(parents=True, exist_ok=True)
    cmd = [_python_do_comfy(pasta), str(pasta / "main.py"), "--listen", host, "--port", str(porta),
           "--disable-pinned-memory"]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x8)
    log = LOG_COMFY.open("ab")
    print(f"[VX IMAGE] subindo ComfyUI em {pasta} (log: {LOG_COMFY})...", flush=True)
    proc = subprocess.Popen(cmd, cwd=str(pasta), stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=flags)
    log.close()
    PID_COMFY.write_text(str(proc.pid), encoding="utf-8")
    fim = time.monotonic() + float(cfg.get("espera_inicio_s", 240))
    while time.monotonic() < fim:
        if proc.poll() is not None:
            PID_COMFY.unlink(missing_ok=True)
            cauda = LOG_COMFY.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise ComfyIndisponivel(f"ComfyUI encerrou ao iniciar (codigo {proc.returncode}):\n{cauda}")
        try:
            cli.status()
            print(f"[VX IMAGE] ComfyUI online (pid {proc.pid})", flush=True)
            return {"online": True, "iniciado_por_nos": True, "pid": proc.pid}
        except ComfyIndisponivel:
            time.sleep(2)
    parar_comfy()
    raise ComfyIndisponivel(f"ComfyUI nao respondeu em {cfg.get('espera_inicio_s', 240)}s; veja {LOG_COMFY}")


_SESSOES: List[Dict[str, Any]] = []


def _registrar_sessao(info: Dict[str, Any]) -> Dict[str, Any]:
    for s in _SESSOES:
        s["usou_comfy"] = True
        s["iniciado_por_nos"] = s["iniciado_por_nos"] or bool(info.get("iniciado_por_nos"))
    return info


class sessao_comfy:
    """ComfyUI sob demanda: so sobe se alguma imagem nao estiver em cache.

    Uso:
        with gil.sessao_comfy(desligar=True) as s:
            png = gil.gerar_melhor(...)   # cache -> nem toca no ComfyUI
    Ao sair: libera VRAM se o ComfyUI foi usado e desliga se foi o estudio que subiu.
    Antes, cenas-ia/titulos chamavam garantir_comfy() antes de olhar o cache e
    subiam o ComfyUI (~30-60 s) a cada esteira mesmo sem gerar nada.
    """

    def __init__(self, desligar: bool = True):
        self.desligar = desligar
        self.info = {"usou_comfy": False, "iniciado_por_nos": False}

    def __enter__(self):
        _SESSOES.append(self.info)
        return self.info

    def __exit__(self, *exc):
        _SESSOES.remove(self.info)
        if self.info["usou_comfy"]:
            try:
                ComfyClient(carregar_config()["comfy_url"], timeout=10).liberar_vram()
            except Exception:
                pass
            if self.info["iniciado_por_nos"] and self.desligar:
                parar_comfy()
        return False


def parar_comfy() -> bool:
    """Encerra SOMENTE o ComfyUI que o estudio subiu (pid registrado)."""
    import subprocess
    if not PID_COMFY.is_file():
        return False
    try:
        pid = int(PID_COMFY.read_text(encoding="utf-8").strip())
    except ValueError:
        PID_COMFY.unlink(missing_ok=True)
        return False
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass
    PID_COMFY.unlink(missing_ok=True)
    print(f"[VX IMAGE] ComfyUI (pid {pid}) encerrado", flush=True)
    return True
