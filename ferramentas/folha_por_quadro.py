#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria quadro a quadro do master: a folha completa que nenhum porteiro cobre.

Os porteiros medem o master como um todo (dead, pagina, congelado, texto de terceiro).
Nenhum deles pergunta "a kinetic text desta janela escreveu a linha que devia?". Este
modulo varre o video inteiro, cruzando cada instante com o que a linha pede e com a
janela do take de motion, e escreve:

  - `qa/folha_por_quadro/<slug>_folha.csv`   uma linha por instante amostrado
  - `qa/folha_por_quadro/<slug>_achados.md`  o relatorio legivel, agrupado por problema

Achados por classe (nao sao porteiro: nao reprovam a esteira, elas pagam a folha):

  HEAD/TOPO       o take de motion escreve a frase da linha errada (vazamento de
                  CABECA/CAUDA) — incidente Asta 05/10/2026, `linhas_no_trecho`
  VAZIO           a frase do take some antes do fim da janela dele
  LEGENDA_CIELO   a legenda de canto aparece dentro de um take (`oculta_legenda`)
  DUPLA           duas legendas sobrepostas (legenda queimada + overlay)
  CARTAO          cartao de titulo/intro no meio do corpo (duplicado)
  COR             a cor de destaque nao bate com a cor do projeto
  CORTES          cortes de cena em intervalo curto demais (< 0,35 s)

Nenhuma mudanca de limiar de porteiro aqui: isto e diagnostico.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"

FPS_AMOSTRA = 4.0          # 4 quadros/s: pega o movimento curto sem gerar 6 mil linhas
LARGURA_AUDIT = 480        # largura dos thumbs da folha
CORTES_MIN = 0.35          # abaixo disso e' flicker, nao corte
OCR_FPS = 2.0              # leitura do texto na tela dentro dos takes (mesmo fps do fonte-limpa)
DUR_INTRO_PADRAO = 10.005


# --------------------------------------------------------------------------- dados

@dataclass
class Amostra:
    t: float                     # tempo do MASTER
    t_corpo: float               # t - intro
    cor: tuple[int, int, int]    # cor de destaque predominante do quadro
    claro: float                 # fracao de pixel claro e sem cor
    detalhe: float               # desvio-padrao (textura)
    movimento: float             # |quadro - anterior| medio
    linha: str = ""              # linha cantada em t (canonica)
    frase_take: str = ""         # frase que o take de motion deveria estar escrevendo
    estilo_take: str = ""
    texto_tela: str = ""          # o que o OCR leu na tela (verdade, nao deducao)
    comecou_frase: bool = False        # a 1a palavra da frase do take ja foi cantada?
    classes: list[str] = field(default_factory=list)

    def chave(self) -> str:
        return "|".join(sorted(self.classes))


# --------------------------------------------------------------------------- Takes

def janela_dos_takes(projeto: Path, sync=None) -> list[dict]:
    """Janelas de motion planejadas, com a frase que cada take escreve."""
    pasta = projeto / "clips_raw" / "vx_graphics_auto"
    takes: list[dict] = []
    for design in sorted(pasta.glob("*.design.json")):
        try:
            d = json.loads(design.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ini = float(d.get("start", 0.0))
        dur = float(d.get("duration", 0.0))
        takes.append({
            "arquivo": design.stem,
            "ini": ini,
            "fim": ini + dur,
            "estilo": str(d.get("estilo", "")),
            "frase": str(d.get("line_text", "")),
            "palavra": str(d.get("word", "")),
            "oculta_legenda": bool(d.get("oculta_legenda")),
            "t_frase": inicio_da_frase(d.get("line_text") or "", sync),
        })
    return takes


def _normalizar(txt: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", str(txt or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t)


def linha_em(linhas: list[dict], t: float) -> dict | None:
    for ln in linhas:
        if float(ln["start"]) - 0.05 <= t < float(ln["end"]) + 0.65:
            return ln
    return None


def inicio_da_frase(frase_take: str, sync) -> float | None:
    """Tempo absoluto (corpo) em que a PRIMEIRA PALAVRA da frase do take e cantada.

    Serve para saber quando o take ja pode ter escrito alguma coisa. Nao substitui a
    leitura do texto na tela: ver `texto_do_take` (OCR de verdade).
    """
    if not frase_take or not sync:
        return None
    alvo = _normalizar(frase_take)
    for ln in sorted(sync, key=lambda l: float(l["start"])):
        if _normalizar(ln.get("text", "")) == alvo:
            words = ln.get("words") or []
            if words:
                return float(words[0].get("start", ln["start"]))
            return float(ln["start"])
    return None


def _palavras(txt: str) -> list[str]:
    """Palavras do texto, minusculas e sem acento (mantem o espaco que separa)."""
    return [p for p in (_normalizar(p) for p in re.split(r"\s+", str(txt or ""))) if p]


PALAVRA_MIN = 4          # abaixo disso ("o", "de", "ar", "no") casa por acaso dentro
                        # de outra palavra e nao prova nada


def _conteudo(pa: list[str]) -> list[str]:
    """Palavras de conteudo da frase (>= 4 letras), na ordem."""
    return [w for w in pa if len(w) >= PALAVRA_MIN]


def _conteudo_ja_saiu(ocr_take: dict, tk: dict) -> bool:
    """A 1a palavra de conteudo da frase ja apareceu em algum quadro do take?

    E o sinal de "a frase comecou": antes disso o take ainda esta montando e nao ha
    evidencia de defeito. Le o OCR de todo o take, nao so o quadro atual.
    """
    conteudo = _conteudo(_palavras(tk["frase"]))
    if not conteudo:
        return False
    primeira = conteudo[0]
    for texto in (ocr_take.get(tk["arquivo"]) or {}).values():
        if primeira in "".join(_palavras(texto)):
            return True
    return False


def _texto_da_frase_em(lido: str, alvo: str, comecou: bool = True) -> bool:
    """O texto lido na tela pertence a frase do take?

    `comecou` = a PRIMEIRA palavra de conteudo da frase ja apareceu neste ou num quadro
    ANTERIOR do take (a kinetic text entra palavra a palavra). Ate la nao ha evidencia de
    defeito: no Asta o OCR leu "O" sozinho antes de "quatro" sair, e isso e' a montagem,
    nao o defeito. Depois que a frase comecou vale metade das palavras de conteudo
    (decisao do dono, para nao alarmer falso) e o resto e' texto de outra linha.

    Ignorar palavra curta e essencial: sem isso a linha vizinha casa com a frase --
    "O meu desceu rasgado, sujo, sem par" acha "o", "de" (dentro de desceu) e "ar"
    (dentro de rasgado) na frase "O de quatro folhas..." e passa por metade das palavras.
    """
    pl, pa = _palavras(lido), _palavras(alvo)
    if not pl or not pa:
        return True                      # nada lido: sem evidencia de defeito
    conteudo = _conteudo(pa)
    if not conteudo:
        return True                      # frase so de palavras curtas: nada a comparar
    lido_txt = "".join(pl)
    achadas, cursor = 0, 0
    for w in conteudo:
        pos = lido_txt.find(w, cursor)
        if pos >= 0:
            achadas += 1
            cursor = pos + len(w)
    if achadas * 2 >= len(conteudo):
        return True                      # metade das palavras de conteudo bate
    # A frase ainda nao comecou a entrar: montagem progressiva, sem evidencia de defeito.
    if not comecou:
        return True
    # A frase comecou e o que esta na tela nao bate: texto de outra linha.
    return False


def _ini_do_take_no_video(master: Path, intro: float, ini_corpo: float) -> float | None:
    """Tempo (no arquivo de video) em que o take comeca: corpo + intro oficial.

    A janela do take e planejada em tempo de CORPO; o master tem a intro oficial na
    frente. Sem converter, o OCR leria a intro no lugar do take.
    """
    t = float(ini_corpo) + float(intro)
    try:
        import cv2
        cap = cv2.VideoCapture(str(master))
        total = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(
            1.0, float(cap.get(cv2.CAP_PROP_FPS) or 30.0))
        cap.release()
        if total and t > total:
            return None
    except Exception:
        pass
    return t


def _chave_ocr(rel: float, fps_ocr: float) -> int:
    """Chave de tempo do OCR a partir do instante relativo ao inicio do take."""
    return int(round(rel * fps_ocr))


def texto_do_take(video: Path, ini: float, dur: float, fps: float = 2.0,
                  amostras_completas: list | None = None,
                  cache: Path | None = None) -> dict[int, str]:
    """LE o que esta escrito na tela dentro da janela do take, com o OCR do projeto.

    Substitui a deducao "a linha vigente tem de ser a do take": dentro do take a legenda
    de canto esta escondida (`oculta_legenda`) e o `linha_em` ainda devolve a linha
    ANTERIOR por causa do hold de 0,65 s -- foi o que fez a folha acusar HEAD/CAUDA em
    6 takes de um candidato ja corrigido (Asta 07/10/2026).

    Devolve {indice_do_quadro_ocr: texto} com as caixas da metade superior do quadro,
    onde a kinetic text aparece (a legenda de canto fica embaixo e e' ignorada).
    """
    if amostras_completas is not None:
        amostras = amostras_completas
    else:
        try:
            import fonte_limpa as fl
            amostras = fl.ocr_do_clipe(video, fps, cache, fl.cfg())
        except Exception:
            return {}
    ini = max(0.0, float(ini))
    fim = ini + max(0.0, float(dur))
    por_tempo: dict[int, str] = {}
    for t, caixas in amostras:
        if not (ini <= t < fim):
            continue
        textos = [c["texto"] for c in caixas if c["y"] < 0.72]
        if textos:
            por_tempo[_chave_ocr(t - ini, fps)] = " ".join(textos)
    return por_tempo


# --------------------------------------------------------------------------- cor

def cor_predominante(img: np.ndarray) -> tuple[int, int, int]:
    """Cor saturada que mais aparece no quadro (a cor de destaque da motion)."""
    f = np.asarray(img, dtype=np.int16)
    mx, mn = f.max(axis=2), f.min(axis=2)
    sat = (mx - mn).astype(np.float32)
    bril = f.mean(axis=2)
    # pixels de acento: saturados e nem escuros nem brancos
    m = (sat > 55) & (bril > 45) & (bril < 235)
    if int(m.sum()) < 40:
        return (0, 0, 0)
    sel = f[m]
    # agrupa em cubos de 32 e fica com o maior grupo
    q = (sel // 32).astype(np.int32)
    chave = q[:, 0] * 4096 + q[:, 1] * 64 + q[:, 2]
    valores, contagens = np.unique(chave, return_counts=True)
    k = int(np.argmax(contagens))
    grupo = sel[chave == valores[k]]
    return tuple(int(v) for v in np.median(grupo, axis=0))


def distancia_rgb(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, np.float32) - np.asarray(b, np.float32)))


# --------------------------------------------------------------------------- amostragem

def amostrar(master: Path, fps: float = FPS_AMOSTRA, largura: int = LARGURA_AUDIT):
    """Frames do master como lista de (t, img HxWx3 RGB).

    `fps=None` varre TODOS os quadros do video (30 fps do master): e o modo que o
    dono pediu, porque uma motion pode ter efeito de poucos quadros e amostrar a
    4 fps (1 a cada 7,5 quadros) perde o instante. `fps` numerico continua para a
    varredura rapida de triagem.
    """
    import shutil
    import subprocess

    ff = shutil.which("ffmpeg") or "ferramentas/bin/ffmpeg.exe"
    import cv2
    probe = cv2.VideoCapture(str(master))
    fps_real = float(probe.get(cv2.CAP_PROP_FPS) or 30.0)
    w = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    h = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    n_real = int(probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    probe.release()

    filtro = f"fps={fps}" if fps else "fps=30"   # fps=30 = todo quadro (fps do master)
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-i", str(master),
         "-vf", f"{filtro},scale={largura}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    buf = proc.stdout
    if not buf:
        raise RuntimeError(f"ffmpeg nao devolveu frames de {master}")
    alt = int(round(h * largura / w)) // 2 * 2
    fb = largura * alt * 3
    n = len(buf) // fb
    arr = np.frombuffer(buf[:n * fb], dtype=np.uint8).reshape(n, alt, largura, 3)
    fps_efetivo = float(fps) if fps else fps_real
    if n_real and abs(n - n_real) > 2 and not fps:
        # GuardarLOUD: perder quadro e exatamente o que o dono pediu para nao acontecer.
        print(f"  [folha] AVISO: {n} quadros lidos, container declara {n_real}")
    return [(i / fps_efetivo, a) for i, a in enumerate(arr)]


def dur_intro_do_master(master: Path) -> float:
    """Duracao da intro oficial no master (0.0 se nao comeca com ela)."""
    import compositor_master_gpu as comp
    try:
        intro = Path(comp.INTRO_OFICIAL)
        if not intro.exists():
            return 0.0
        _, d = comp.inspecionar_midia(intro)
        import cv2
        def quadro(video, t):
            cap = cv2.VideoCapture(str(video))
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, img = cap.read()
            cap.release()
            return cv2.resize(img, (160, 90)) if ok else None
        a, b = quadro(master, 0.10), quadro(intro, 0.10)
        if a is None or b is None:
            return 0.0
        return float(d) if float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) < 12.0 else 0.0
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- auditoria

def auditar(slug: str, fps: float | None = None, escrever_thumbs: bool = True,
            por_take: bool = True) -> dict:
    projeto = PROJETOS / slug
    manifesto = json.loads((projeto / "projeto.json").read_text(encoding="utf-8"))
    master = projeto / "saidas" / f"{slug}_master.mp4"
    if not master.exists():
        raise FileNotFoundError(f"sem master promovido: {master}")

    sync = json.loads((projeto / "letra_sincronizada.json").read_text(encoding="utf-8"))
    if isinstance(sync, dict):
        sync = sync.get("linhas", [])
    takes = janela_dos_takes(projeto, sync)
    cor_projeto = _rgb((manifesto.get("cor") or {}).get("destaque", "#00E5FF"))

    intro = dur_intro_do_master(master)
    frames = amostrar(master, fps=fps)
    dt = 1.0 / (float(fps) if fps else _fps_do_master(master))

    amostras: list[Amostra] = []
    anterior = None
    for t, img in frames:
        f = img.astype(np.float32)
        medio = f[int(f.shape[0] * 0.15):int(f.shape[0] * 0.85)]
        detalhe = float(medio.mean(axis=2).std())
        mx, mn = f.max(axis=2), f.min(axis=2)
        claro = float(((mn > 170) & ((mx - mn) < 30)).mean())
        mov = 0.0 if anterior is None else float(np.abs(f - anterior).mean())
        anterior = f
        amostras.append(Amostra(
            t=t, t_corpo=t - intro, cor=cor_predominante(img),
            claro=claro, detalhe=detalhe, movimento=mov,
            linha=(linha_em(sync, t - intro) or {}).get("text", ""),
        ))

    # ---- classes: cruzamento com a janela de cada take
    regras_cor = _regras_cor(projeto, manifesto)
    # Leitura de verdade do que esta escrito na tela dentro de cada take. Sem isso o
    # diagnostico so deduz (e deduz errado): dentro do take a legenda de canto some
    # e o `linha_em` devolve a linha anterior por 0,65 s depois do fim dela.
    ocr_take: dict[str, dict[int, str]] = {}
    amostras_ocr_master = None
    if takes:
        cache_ocr = projeto / "qa" / "folha_por_quadro" / f"{master.stem}_ocr_{OCR_FPS:.1f}fps.json"
        try:
            import fonte_limpa as fl
            amostras_ocr_master = fl.ocr_do_clipe(master, OCR_FPS, cache_ocr, fl.cfg())
        except Exception:
            amostras_ocr_master = None
    for tk in takes:
        t0 = _ini_do_take_no_video(master, intro, tk["ini"])
        if t0 is None:
            continue
        ocr_take[tk["arquivo"]] = texto_do_take(master, t0, tk["fim"] - tk["ini"], OCR_FPS,
                                                amostras_completas=amostras_ocr_master)
    comecou_por_take: dict[str, bool] = {}
    for a in amostras:
        tk = next((x for x in takes if x["ini"] <= a.t_corpo < x["fim"]), None)
        if tk is None:
            continue
        a.estilo_take = tk["estilo"]
        a.frase_take = tk["frase"]
        # Verdade lida na tela (OCR), nao deduzida: dentro do take a legenda de canto
        # esta escondida e o `linha_em` devolve a linha anterior (hold de 0,65 s),
        # entao comparar com a linha vigente so produz falso positivo.
        a.texto_tela = ocr_take.get(tk["arquivo"], {}).get(
            _chave_ocr(a.t_corpo - tk["ini"], OCR_FPS), "")
        if tk["t_frase"] is not None and a.t_corpo < tk["t_frase"]:
            continue          # a frase ainda nem comecou: nada a cobrar
        if tk["arquivo"] not in comecou_por_take:
            comecou_por_take[tk["arquivo"]] = _conteudo_ja_saiu(ocr_take, tk)
        sobra = tk["fim"] - a.t_corpo
        # A frase do take tem de estar na tela ate o fim da janela (nos ultimos 0,65 s
        # ela pode estar em fade). O texto vem do OCR da tela: comparar com a linha
        # vigente da letra dava falso positivo dentro do take, porque a legenda de canto
        # esta escondida e o `linha_em` ainda segura a linha anterior por 0,65 s.
        sobra_fade = 0.65
        if sobra > sobra_fade and a.texto_tela:
            if not _texto_da_frase_em(a.texto_tela, tk["frase"],
                                      comecou_por_take.get(tk["arquivo"], True)):
                a.classes.append("HEAD/CAUDA")   # a tela esta com texto de OUTRA frase
        if sobra > 0.9 and a.claro > 0.55 and a.detalhe < 26 and not tk["frase"]:
            a.classes.append("VAZIO")
        if tk["oculta_legenda"]:
            a.classes.append("LEGENDA_CIELO")
        # Cor: o take usa a cor PELA LETRA (palavra > linha > cor do projeto), entao o
        # palpite so vale quando a regra existe. Sem regra a cor e a da cena e nao ha
        # o que comparar (Asta: 'TOURO' -> #FFC940 dourado, e nao o verde do projeto).
        if sobra > 0.4:
            alvo = regras_cor.get(_normalizar(tk["palavra"])) or regras_cor.get(_normalizar(tk["frase"]))
            if alvo and a.cor != (0, 0, 0) and distancia_rgb(a.cor, alvo) > 150:
                a.classes.append("COR")
        # flicker: movimento grande com janela curtissima
        if sobra <= CORTES_MIN:
            a.classes.append("CORTES")

    # ---- cartoes no meio do corpo (titulo/intro duplicado)
    for a in amostras:
        if a.t_corpo > 2.0 and a.detalhe < 18 and a.claro > 0.30 and a.movimento < 0.6:
            a.classes.append("CARTAO")

    # ---- cobertura por classe
    cobertura: dict[str, float] = {}
    for classe in {c for a in amostras for c in a.classes}:
        estourado = [a for a in amostras if classe in a.classes]
        if not estourado:
            continue
        ini = estourado[0].t
        runs, atual = [], [ini]
        for x in estourado[1:]:
            if x.t - atual[-1] <= dt * 1.6:
                atual.append(x.t)
            else:
                runs.append(atual)
                atual = [x.t]
        runs.append(atual)
        maior = max(runs, key=len)
        cobertura[classe] = round(len(maior) * dt, 3)

    pasta = projeto / "qa" / "folha_por_quadro"
    pasta.mkdir(parents=True, exist_ok=True)
    csv_path = pasta / f"{slug}_folha.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.DictWriter(fh, fieldnames=list(asdict(Amostra(t=0.0, t_corpo=0.0, cor=(0, 0, 0),
                                                                     claro=0.0, detalhe=0.0,
                                                                     movimento=0.0)).keys()))
        wcsv.writeheader()
        for a in amostras:
            linha = asdict(a)
            linha["cor"] = "%d,%d,%d" % a.cor
            linha["classes"] = a.chave()
            wcsv.writerow(linha)

    folhas: list[str] = []
    if escrever_thumbs:
        folhas = _folha_thumbs(master, projeto, amostras, intro, por_take=por_take)

    md = _relatorio(slug, master, amostras, cobertura, takes, intro, dt)
    (pasta / f"{slug}_achados.md").write_text(md, encoding="utf-8")
    return {"csv": str(csv_path), "relatorio": md, "cobertura": cobertura,
            "amostras": len(amostras), "intro": intro, "takes": len(takes),
            "fps": (float(fps) if fps else _fps_do_master(master)), "folhas": folhas}


def _rgb(hexc: str) -> tuple[int, int, int]:
    """'#RRGGBB' -> (r,g,b). Aceita tambem tupla/lista ja numerico.

    Nao usa `motion_lab.hex_rgb`: essa funcao nao existe la (esta no
    kinetic_typography) e o `except` silencioso devolvia (0,0,0), o que fazia o
    palpite de cor casar com qualquer quadro. `hex_rgb` e o conversor do projeto,
    entao e ele que entra — com o proprio `cor_da_letra` para achar a cor da letra.
    """
    if isinstance(hexc, (tuple, list)) and len(hexc) == 3:
        return tuple(int(x) for x in hexc)
    import kinetic_typography as kt
    return tuple(int(x) for x in kt.hex_rgb(str(hexc), fallback=(0, 0, 0)))


def _regras_cor(projeto: Path, manifesto: dict) -> dict[str, tuple[int, int, int]]:
    """Regras de 'cor pela letra' normalizadas -> RGB, com o destaque do projeto como padrao."""
    try:
        import motion_lab as ml
        regras = ml.carregar_cfg(manifesto=manifesto).get("cores") or {}
    except Exception:
        regras = {}
    out = {_normalizar(k): _rgb(v) for k, v in regras.items() if isinstance(v, str)}
    destaque = (manifesto.get("cor") or {}).get("destaque")
    if destaque:
        out.setdefault("", _rgb(destaque))
    return out


# --------------------------------------------------------------------------- saida

CLASSES = {
    "HEAD/CAUDA": "a kinetic text escreveu a frase da linha vizinha (take vazando)",
    "VAZIO": "a frase do take sumiu antes do fim da janela dele",
    "LEGENDA_CIELO": "a legenda de canto some aqui (take esconde a legenda)",
    "CARTAO": "cartao de titulo/intro duplicado no meio do corpo",
    "COR": "cor de destaque diferente da cor PELA LETRA do take (ver motion_lab.cor_da_letra)",
    "CORTES": "corte de cena curto demais (flicker)",
}


def _fps_do_master(master: Path) -> float:
    import cv2
    cap = cv2.VideoCapture(str(master))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.release()
    return fps


def _folha_thumbs(master: Path, projeto: Path, amostras: list[Amostra], intro: float,
                  por_take: bool = True) -> list[str]:
    """Contact sheets: por take (padrao) ou do video inteiro.

    Por take e' o que o dono pediu para ver o resultado de TODAS as motions: cada
    folha e' uma janela do take, com todos os quadros (ou o passo de `fps`),
    carimbo de tempo e classes. A folha geral continua existindo, em passo grosso.
    """
    from PIL import Image, ImageDraw
    pasta = projeto / "qa" / "folha_por_quadro"
    pasta.mkdir(parents=True, exist_ok=True)
    import cv2
    fps_v = _fps_do_master(master)
    dt = 1.0 / fps_v
    tw = 240
    colunas = 8
    cap = cv2.VideoCapture(str(master))
    largura_v = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    altura_v = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    th = int(round(altura_v * tw / largura_v)) // 2 * 2
    gap = 3
    ctx = {"cap": cap, "tw": tw, "th": th, "gap": gap, "colunas": colunas, "img": None, "draw": None}

    def folha(sel: list[int], nome: str, titulo: str) -> str:
        if not sel:
            return ""
        linhas = (len(sel) + colunas - 1) // colunas
        g = Image.new("RGB", (colunas * tw + (colunas - 1) * gap + 8,
                              linhas * (th + 16) + 26), (24, 24, 27))
        d = ImageDraw.Draw(g)
        d.text((6, 6), titulo[:110], fill=(235, 235, 240))
        for k, i in enumerate(sel):
            a = amostras[i]
            cap.set(cv2.CAP_PROP_POS_MSEC, a.t * 1000)
            ok, img = cap.read()
            if not ok:
                continue
            im = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).resize((tw, th), Image.LANCZOS)
            r, c = divmod(k, colunas)
            x, y = 4 + c * (tw + gap), 22 + r * (th + 16)
            g.paste(im, (x, y))
            carimbo = f"{a.t:.2f}"
            if a.classes:
                carimbo += " " + a.chave()
            d.text((x + 2, y + th + 2), carimbo[:34],
                   fill=(255, 190, 60) if a.classes else (185, 185, 190))
        destino = pasta / nome
        g.save(destino, quality=86)
        return str(destino)

    saidas: list[str] = []
    if por_take:
        for tk in janela_dos_takes(projeto):
            sel = [i for i, a in enumerate(amostras) if tk["ini"] <= a.t_corpo < tk["fim"]]
            nome = f"{projeto.name}_take_{tk['arquivo'].split('_')[0]}.jpg"
            f = folha(sel, nome, f"{tk['arquivo']} | {tk['estilo']} | {tk['ini']:.2f}-{tk['fim']:.2f}s corpo"
                                 f" | {len(sel)} quadros | frase: {tk['frase'][:56]}")
            if f:
                saidas.append(f)
    passo = 1.5
    geral = [i for i, a in enumerate(amostras) if abs(a.t % passo) < dt * 0.6]
    f = folha(geral, f"{projeto.name}_folha.jpg", f"{projeto.name} | passo {passo}s | {len(geral)} quadros")
    if f:
        saidas.append(f)
    cap.release()
    return saidas


def _relatorio(slug, master, amostras, cobertura, takes, intro, dt: float = 0.25) -> str:
    fps_txt = f"{1.0 / dt:.0f} fps (TODOS os quadros)" if dt < 0.05 else f"{1.0 / dt:.2f} fps (triagem)"
    linhas = [
        f"# Folha por quadro — {slug}",
        "",
        f"Master: `{master.name}` | **{len(amostras)} quadros a {fps_txt}** "
        f"({len(amostras) * dt:.1f}s) | intro oficial {intro:.2f}s",
        "",
        "Tempos em **corpo** (0 = depois da intro). CSV completo: `<slug>_folha.csv` (uma linha por quadro).",
        "Contact sheets: `<slug>_take_NN.jpg` (uma por take de motion, **todos os quadros** da janela) "
        "+ `<slug>_folha.jpg` (vídeo inteiro, passo grosso).",
        "",
        "## Achados por classe",
        "",
        "| classe | maior bloco (s) | o que e |",
        "|---|---:|---|",
    ]
    if cobertura:
        for classe, seg in sorted(cobertura.items(), key=lambda kv: -kv[1]):
            linhas.append(f"| `{classe}` | {seg:.2f} | {CLASSES.get(classe, '—')} |")
    else:
        linhas.append("| — | — | nenhum achado nesta amostragem |")
    linhas += ["", "## Takes de motion no video", "",
               "| take | janela (corpo) | estilo | frase | esconde legenda |",
               "|---|---|---|---|---|"]
    for x in takes:
        linhas.append(f"| `{x['arquivo']}` | {x['ini']:.2f}–{x['fim']:.2f}s | `{x['estilo']}` | "
                      f"{x['frase'][:44] or '—'} | {'sim' if x['oculta_legenda'] else 'não'} |")
    # janelas suspectas em detalhe
    linhas += ["", "## Janelas suspeitas", ""]
    n = 0
    for a in amostras:
        if a.classes and n < 60:
            linhas.append(f"- **{a.t:.2f}s** (corpo {a.t_corpo:.2f}s) `{a.chave()}` "
                         f"— linha: {a.linha[:40] or '—'}")
            n += 1
    if not n:
        linhas.append("nenhuma.")
    return "\n".join(linhas) + "\n"


if __name__ == "__main__":
    import sys
    r = auditar(sys.argv[1] if len(sys.argv) > 1 else "asta")
    print(json.dumps({k: v for k, v in r.items() if k != "relatorio"}, ensure_ascii=False, indent=2))
