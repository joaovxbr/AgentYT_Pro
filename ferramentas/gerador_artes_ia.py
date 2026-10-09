#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerador_artes_ia.py — Motor de Miniaturas (capa YouTube 1280x720).

Duas fontes de imagem base:
- ``local`` (padrao): ComfyUI + SDXL na RTX 3090 via gerador_imagem_local.py.
- ``remoto``: API compativel com OpenAI Images. URL/chave SOMENTE por ambiente:
  VX_IMAGE_API_URL, VX_IMAGE_API_KEY, VX_IMAGE_API_MODEL.

Identidade (kanji, tags, descricao) vem do projeto.json -> ``imagem_ia``; nada de
personagem hardcodado aqui.
"""
from pathlib import Path
import io
import os
import json
import base64
import random
import urllib.request
import urllib.error
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

API_URL = os.environ.get("VX_IMAGE_API_URL", "")
MODELO = os.environ.get("VX_IMAGE_API_MODEL", "claude-fabble-5")

DIR_FONTES = Path(__file__).resolve().parent / "fontes"
FONTE_BEBAS = DIR_FONTES / "BebasNeue-Regular.ttf"
FONTE_CINZEL = DIR_FONTES / "Cinzel-Bold.ttf"
FONTE_IMPACTO = Path("C:/Windows/Fonts/impact.ttf")
FONTE_JAPONESA = Path("C:/Windows/Fonts/msgothic.ttc")
FONTE_ARIAL_BOLD = Path("C:/Windows/Fonts/arialbd.ttf")

# Fallback por anime (titulo da obra). O nome do personagem em katakana deve vir
# do manifesto: imagem_ia.kanji = ["<coluna>", "<nome>"].
KANJIS_POR_ANIME = {
    "naruto": "ナルト",
    "shingeki": "進撃の巨人",
    "attack on titan": "進撃の巨人",
    "demon slayer": "鬼滅の刃",
    "kimetsu": "鬼滅の刃",
    "jujutsu": "呪術廻戦",
    "solo leveling": "俺だけレベルアップな件",
    "one piece": "ワンピース",
    "bleach": "ブリーチ",
    "dragon ball": "ドラゴンボール",
    "hunter": "ハンター",
    "chainsaw": "チェンソーマン",
}


def kanji_do_manifesto(manifesto: dict):
    """(coluna_kanji, rotulo) ou None. Prioriza imagem_ia.kanji do projeto."""
    bloco = manifesto.get("imagem_ia") or {}
    k = bloco.get("kanji")
    if isinstance(k, (list, tuple)) and k and k[0]:
        return str(k[0]), str(k[1]) if len(k) > 1 else ""
    anime = str(manifesto.get("anime", "")).lower()
    for chave, col in KANJIS_POR_ANIME.items():
        if chave in anime:
            return col, ""
    return None

def carregar_fonte(caminho: Path, tamanho: int):
    try:
        if caminho.exists():
            return ImageFont.truetype(str(caminho), tamanho)
    except Exception:
        pass
    try:
        return ImageFont.truetype(str(FONTE_IMPACTO), tamanho)
    except Exception:
        return ImageFont.load_default()

def gerar_imagem_api(prompt: str) -> Image.Image:
    api_key = os.environ.get("VX_IMAGE_API_KEY", "")
    if not API_URL or not api_key:
        raise RuntimeError("Motor remoto exige VX_IMAGE_API_URL e VX_IMAGE_API_KEY no ambiente; "
                           "ou use o motor local (padrao).")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": MODELO,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024"
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data_bytes, headers=headers)

    print(f"[API IA] Renderizando base cinematográfica via {MODELO}...")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            corpo = json.loads(resp.read().decode("utf-8"))
            b64_data = corpo["data"][0]["b64_json"]
            raw_bytes = base64.b64decode(b64_data)
            return Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    except Exception as e:
        raise RuntimeError(f"Falha na API: {e}")

def criar_texto_3d_master(
    texto: str,
    fonte: ImageFont.ImageFont,
    cor_topo: tuple = (255, 255, 255),
    extrusao_profundidade: int = 12,
    espessura_borda: int = 6
) -> Image.Image:
    dummy = Image.new("RGBA", (10, 10))
    d_draw = ImageDraw.Draw(dummy)
    bbox = d_draw.textbbox((0, 0), texto, font=fonte, stroke_width=espessura_borda)
    tw = bbox[2] - bbox[0] + extrusao_profundidade * 2 + 80
    th = bbox[3] - bbox[1] + extrusao_profundidade * 2 + 80

    canvas_txt = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas_txt)

    ox = 35
    oy = 35

    # Sombra projetada
    for s in range(1, 10):
        draw.text(
            (ox + extrusao_profundidade + s, oy + extrusao_profundidade + s),
            texto, font=fonte,
            fill=(0, 0, 0, 190 - s * 18),
            stroke_width=espessura_borda + 2, stroke_fill=(0, 0, 0, 190 - s * 18)
        )

    # Extrusão lateral
    for i in range(extrusao_profundidade, 0, -1):
        deg = i / extrusao_profundidade
        cor_ext = (int(35 * (1.0 - deg)), int(10 * (1.0 - deg)), int(5 * (1.0 - deg)), 255)
        draw.text(
            (ox + i, oy + i), texto, font=fonte,
            fill=cor_ext, stroke_width=espessura_borda, stroke_fill=(0, 0, 0, 255)
        )

    # Contorno externo preto
    draw.text(
        (ox, oy), texto, font=fonte,
        fill=(0, 0, 0, 255), stroke_width=espessura_borda, stroke_fill=(0, 0, 0, 255)
    )

    # Face frontal
    draw.text(
        (ox, oy), texto, font=fonte,
        fill=cor_topo, stroke_width=1, stroke_fill=(255, 255, 255, 140)
    )

    return canvas_txt

def compor_miniatura_elite(
    img_ia: Image.Image,
    personagem: str,
    musica: str,
    subtexto_anime: str,
    cor_destaque: str = "#FF4500",
    kanji=None,
    largura: int = 1280,
    altura: int = 720,
    cor_particulas: str = "#00E5FF",
    seed: int = 0
) -> Image.Image:
    rng = random.Random(seed)
    img_ia = img_ia.convert("RGBA")
    # 1. Enquadramento 16:9
    w_orig, h_orig = img_ia.size
    target_aspect = largura / altura
    orig_aspect = w_orig / h_orig

    if orig_aspect > target_aspect:
        new_w = int(h_orig * target_aspect)
        x_crop = (w_orig - new_w) // 2
        crop_box = (x_crop, 0, x_crop + new_w, h_orig)
    else:
        new_h = int(w_orig / target_aspect)
        y_crop = int((h_orig - new_h) * 0.10)
        crop_box = (0, y_crop, w_orig, y_crop + new_h)

    base = img_ia.crop(crop_box).resize((largura, altura), Image.Resampling.LANCZOS)

    # 2. Pós-Processamento Cinemático
    base = ImageEnhance.Contrast(base).enhance(1.40)
    base = ImageEnhance.Color(base).enhance(1.35)
    base = ImageEnhance.Sharpness(base).enhance(1.25)

    # 3. CAMADA DE CORTE DE CONTRASTE (Backing Scrim Denso no Canto do Texto)
    scrim = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    sc_draw = ImageDraw.Draw(scrim)
    sc_draw.polygon([
        (0, altura - 460),
        (620, altura - 400),
        (520, altura),
        (0, altura)
    ], fill=(2, 2, 6, 235))
    scrim_blur = scrim.filter(ImageFilter.GaussianBlur(38))
    base = Image.alpha_composite(base, scrim_blur)

    # 4. Kanjis Canônicos Dinâmicos por Anime
    overlay_k = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    k_draw = ImageDraw.Draw(overlay_k)
    if kanji and FONTE_JAPONESA.exists():
        kanji_col = kanji[0]
        try:
            f_k_col = ImageFont.truetype(str(FONTE_JAPONESA), 38)
            f_latin = carregar_fonte(FONTE_BEBAS, 26)
            rx = largura - 70
            ry_start = 120
            kanji_col = kanji_col[:8]  # coluna cabe na altura da capa
            for i, char in enumerate(kanji_col):
                k_draw.text((rx, ry_start + i * 48), char, font=f_k_col, fill=(240, 240, 240, 185))
            k_draw.text((rx - 6, ry_start + len(kanji_col) * 48 + 25), personagem.split()[0].upper(), font=f_latin, fill=(255, 210, 50, 210))
        except Exception:
            pass
    base = Image.alpha_composite(base, overlay_k)

    # 5. Brasas e Partículas Elétricas
    overlay_p = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    p_draw = ImageDraw.Draw(overlay_p)
    rgb_part = _hex_rgb(cor_particulas, (0, 229, 255))
    for _ in range(75):
        bx = rng.randint(0, largura)
        by = rng.randint(0, altura)
        raio = rng.randint(2, 5)
        alpha = rng.randint(120, 230)
        p_draw.ellipse([bx - raio, by - raio, bx + raio, by + raio], fill=(*rgb_part, alpha))
    overlay_glow = overlay_p.filter(ImageFilter.GaussianBlur(3))
    base = Image.alpha_composite(base, overlay_glow)
    base = Image.alpha_composite(base, overlay_p)

    # 6. TIPOGRAFIA MASTER
    f_p = carregar_fonte(FONTE_BEBAS, 150)
    f_m = carregar_fonte(FONTE_IMPACTO, 88)
    f_vx = carregar_fonte(FONTE_BEBAS, 70)
    f_sub = carregar_fonte(FONTE_CINZEL, 26)

    # A) NOME DO PERSONAGEM
    txt_p = criar_texto_3d_master(
        personagem.upper(), f_p,
        cor_topo=(255, 255, 255),
        extrusao_profundidade=12, espessura_borda=7
    )
    base.alpha_composite(txt_p, (30, altura - 435))

    # B) MÚSICA
    # Converte cor hex para tuple RGB
    rgb_destaque = _hex_rgb(cor_destaque, (255, 115, 15))

    txt_m = criar_texto_3d_master(
        musica.upper(), f_m,
        cor_topo=rgb_destaque,
        extrusao_profundidade=10, espessura_borda=6
    )
    base.alpha_composite(txt_m, (34, altura - 275))

    # C) VX RAPS
    txt_vx = criar_texto_3d_master(
        "VX RAPS", f_vx,
        cor_topo=(255, 225, 45),
        extrusao_profundidade=8, espessura_borda=6
    )
    base.alpha_composite(txt_vx, (36, altura - 170))

    # D) SUBTEXTO CINZEL
    draw_final = ImageDraw.Draw(base)
    tracking_str = "   ".join(subtexto_anime.upper().split())
    y_sub = altura - 62
    
    bbox_sub = draw_final.textbbox((72, y_sub), tracking_str, font=f_sub)
    pad_x, pad_y = 12, 6
    draw_final.rounded_rectangle([
        bbox_sub[0] - pad_x, bbox_sub[1] - pad_y,
        bbox_sub[2] + pad_x, bbox_sub[3] + pad_y
    ], radius=6, fill=(5, 5, 10, 240), outline=rgb_destaque, width=2)

    draw_final.text((72, y_sub), tracking_str, font=f_sub, fill=(255, 255, 255, 255))

    return base

def _hex_rgb(hex_cor: str, padrao: tuple) -> tuple:
    h = (hex_cor or "").lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else padrao
    except ValueError:
        return padrao


def prompt_remoto(manifesto: dict) -> str:
    """Prompt em linguagem natural para APIs remotas, montado so do manifesto."""
    bloco = manifesto.get("imagem_ia") or {}
    personagem = manifesto.get("personagem", "")
    anime = str(manifesto.get("anime", "")).split("(")[0].strip()
    aura = (manifesto.get("cor") or {}).get("destaque", "#FF4500")
    descricao = bloco.get("descricao") or f"dynamic strike towards camera with glowing {aura} energy aura"
    return (f"Masterpiece, cinematic dark trap anime rap poster of {personagem} from {anime}. "
            f"{descricao}. Dramatic dark shadows, dual lighting, anime key visual, 8k wallpaper")


def gerar_miniatura_completa(
    projeto_dir: Path,
    motor: str = "local",
    prompt_customizado: str = None,
    cena: str = None,
    seed: int = None,
    ref: str = None,
    denoise: float = 0.6,
    forcar: bool = False,
    variacoes: int = 4,
) -> Path:
    """Gera base (local/remoto) e compoe a capa final <slug>_capa_ia.jpg no projeto."""
    projeto_dir = Path(projeto_dir)
    slug = projeto_dir.name
    manifesto = json.loads((projeto_dir / "projeto.json").read_text(encoding="utf-8-sig"))
    personagem = manifesto.get("personagem") or slug
    anime = str(manifesto.get("anime", ""))
    musica = manifesto.get("faixa") or slug
    cores = manifesto.get("cor") or {}
    cor_aura = cores.get("destaque", "#FF4500")

    if motor == "local":
        import gerador_imagem_local as gil
        base_png = gil.gerar_melhor(projeto_dir, "capa", cena=cena or prompt_customizado, seed=seed,
                                    variacoes=variacoes, ref=ref, denoise=denoise, forcar=forcar)
        img_ia = Image.open(base_png).convert("RGBA")
        seed_comp = int(base_png.stem.split("_")[1])
    elif motor == "remoto":
        img_ia = gerar_imagem_api(prompt_customizado or prompt_remoto(manifesto))
        seed_comp = seed or 0
    else:
        raise ValueError(f"motor invalido: {motor} (use local ou remoto)")

    subtexto = f"TRAP GEEK  •  {anime.split('(')[0].strip()}" if anime else "TRAP GEEK"
    capa_final = compor_miniatura_elite(
        img_ia, personagem, musica, subtexto, cor_destaque=cor_aura,
        kanji=kanji_do_manifesto(manifesto),
        cor_particulas=cores.get("destaque_claro", "#00E5FF"), seed=seed_comp)

    saida_jpg = projeto_dir / "saidas" / f"{slug}_capa_ia.jpg"
    saida_jpg.parent.mkdir(parents=True, exist_ok=True)
    tmp = saida_jpg.with_suffix(".tmp.jpg")
    capa_final.convert("RGB").save(tmp, "JPEG", quality=92, optimize=True)
    tmp.replace(saida_jpg)
    print(f"[ARTE IA] Capa gerada ({motor}): {saida_jpg}")
    return saida_jpg


def gerar_pacote_artes(projeto_dir: Path, forcar: bool = False) -> dict:
    """Pacote de lancamento com arte IA local: thumb YouTube, banner do canal e capa 3000px.

    Thumb: base SDXL (4 variacoes, VX Image Critic) + composicao tipografica.
    Banner/streaming: bases SDXL escolhidas pelo critico + layouts do artes_base
    (safe area do banner, capa 1:1 sem decapitar).
    """
    import artes_base as ab
    import gerador_imagem_local as gil

    projeto_dir = Path(projeto_dir)
    slug = projeto_dir.name
    m = json.loads((projeto_dir / "projeto.json").read_text(encoding="utf-8-sig"))
    saidas = projeto_dir / "saidas"
    saidas.mkdir(parents=True, exist_ok=True)
    comfy = gil.garantir_comfy()
    try:
        thumb = gerar_miniatura_completa(projeto_dir, forcar=forcar, variacoes=4)
        base_banner = gil.gerar_melhor(
            projeto_dir, "capa", variacoes=3, forcar=forcar,
            cena="wide shot, cowboy shot, standing, looking at viewer, wind, cinematic composition")
        base_quadrada = gil.gerar_melhor(projeto_dir, "quadrado", variacoes=3, forcar=forcar)
    finally:
        try:
            gil.ComfyClient(gil.carregar_config()["comfy_url"], timeout=10).liberar_vram()
        except Exception:
            pass
        if comfy.get("iniciado_por_nos"):
            gil.parar_comfy()
        try:
            import critico_imagem
            critico_imagem.liberar()
        except ImportError:
            pass

    titulo = m.get("titulo_linhas") or [m.get("faixa", slug)]
    dados = ab.DadosArte(
        slug=slug, titulo_linhas=titulo,
        personagem=str(m.get("personagem", slug)).upper(),
        anime=str(m.get("anime", "")).split("(")[0].strip().upper(),
        cor_destaque=(m.get("cor") or {}).get("destaque", "#FF4500"),
        frame_capa=Image.open(base_quadrada).convert("RGB"),
        frame_banner=Image.open(base_banner).convert("RGB"),
        palavra_destaque=titulo[-1].split()[-1] if titulo else None,
    )
    banner = saidas / f"{slug}_banner_canal.jpg"
    ab.compor_banner(dados).save(banner, quality=92)
    streaming = saidas / f"{slug}_capa_streaming_3000.jpg"
    ab.compor_capa_streaming(dados).save(streaming, quality=92)
    return {"thumb_youtube": str(thumb), "banner_canal": str(banner),
            "capa_streaming": str(streaming),
            "bases_ia": [str(base_banner), str(base_quadrada)]}
