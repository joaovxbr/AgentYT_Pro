#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Efeito de particulas sobre o video em CAMADAS com mistura alfa: chuva realista e companhia.

Cada particula e desenhada numa camada RGBA separada (3 profundidades) e composta sobre o
quadro original com alfa. A cena de fundo continua visivel — a chuva e um overlay, nunca
um fundo.

O que faz parecer chuva de verdade (e nao "riscos"):
  3 profundidades — fundo (fina, lenta, borrada), meio, frente (gorda, rapida, nitida).
                    A profundidade e o que da volume.
  velocidade e tamanho variados por particula — o olho le como distancia.
  rastro — cada gota deixa um rastro vertical proporcional a velocidade.
  vento — inclinacao lateral, evitando o look de "chuva de grade".
  leve desfoque — movimento nas camadas de fundo, nitidez na de frente (DOF).

O motor e generico: `PERFIS` descreve o COMPORTAMENTO (direcao, forma, gravidade, cor, modo).
Adicionar neve/fogo/faiscas/folhas e so descrever um perfil — renderizador, mistura alfa e
encode nao mudam, entao nao ha custo extra por tipo.

GPU: encode NVENC via `render_dispatch`. A composicao e numpy; os campos de particula sao
gerados UMA vez (nao por quadro), e so o delta e aplicado a cada quadro.
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------- perfis


@dataclass
class Perfil:
    """Como um tipo de particula se move e desenha."""

    nome: str
    vx: float = 0.0                 # velocidade base em X (fracao de tela por segundo)
    vy: float = 1.0                 # velocidade base em Y (positivo = para baixo)
    gravidade: float = 0.0          # aceleracao extra em Y
    osc_amp: float = 0.0            # turbulencia (soma de senos), fracao de tela
    osc_freq: float = 1.0
    comprimento: float = 0.0        # rastro: fracao de altura (0 = ponto)
    largura: float = 0.0016         # fracao de largura
    cor: tuple[int, int, int] = (200, 220, 235)
    modo: str = "over"              # "over" (alpha) ou "add" (aditivo: fogo/faisca)
    cintila: bool = False
    alpha_por_camada: tuple[float, float, float] = (0.35, 0.62, 1.0)
    nitidez_por_camada: tuple[float, float, float] = (0.25, 0.55, 1.0)
    tamanho_por_camada: tuple[float, float, float] = (0.55, 0.85, 1.35)
    velocidade_por_camada: tuple[float, float, float] = (0.55, 0.85, 1.45)


PERFIS: dict[str, Perfil] = {
    "chuva": Perfil(
        nome="chuva", vx=0.10, vy=2.6, gravidade=1.6, comprimento=0.045,
        largura=0.0013, cor=(205, 222, 240), modo="over",
        # blur de profundidade mais forte: sem isto as 3 camadas ficavam nitidas
        # demais e a chuva lia "linha de efeito" (Asta, lab 05-10/2026)
        nitidez_por_camada=(0.12, 0.40, 1.0),
        alpha_por_camada=(0.30, 0.58, 1.0),
        # Turbulencia por gota: chuva real nao cai em paralelo perfeito. E o que tira
        # o aspecto de "emissor repetitivo" (todos os riscos com o mesmo angulo).
        osc_amp=0.012, osc_freq=2.2,
    ),
    # CHUVA-CINEMA: o look da referencia do dono (AMV noturno, 08/10/2026). Diferencas
    # em relacao a "chuva": (1) muito mais inclinada, (2) a camada da FRENTE e a mais
    # BORRADA (bokeh de gota perto da lente) e a do MEIO a nitida — o oposto do perfil
    # normal, onde a frente e a em foco; (3) neblina de fundo que tira contraste.
    "chuva_cinema": Perfil(
        nome="chuva_cinema", vx=0.62, vy=2.6, gravidade=1.6, comprimento=0.055,
        largura=0.0016, cor=(214, 228, 248), modo="over",
        osc_amp=0.016, osc_freq=1.8,
        nitidez_por_camada=(0.30, 1.0, 0.06),     # fundo nitido, MEIO nitido, frente bokeh
        alpha_por_camada=(0.34, 0.70, 0.85),
        tamanho_por_camada=(0.45, 0.80, 1.70),     # frente bem maior (gota na lente)
        velocidade_por_camada=(0.55, 0.85, 1.30),
    ),
    "neve": Perfil(
        nome="neve", vx=0.05, vy=0.45, gravidade=0.05, osc_amp=0.035, osc_freq=1.4,
        comprimento=0.0, largura=0.0028, cor=(245, 248, 255), modo="over",
    ),
    "fogo": Perfil(
        nome="fogo", vx=0.03, vy=-0.7, gravidade=-0.2, osc_amp=0.06, osc_freq=2.0,
        comprimento=0.0, largura=0.0042, cor=(255, 138, 42), modo="add", cintila=True,
        alpha_por_camada=(0.5, 0.8, 1.0), nitidez_por_camada=(0.15, 0.45, 0.9),
    ),
    "faiscas": Perfil(
        nome="faiscas", vx=0.22, vy=-0.5, gravidade=-0.1, osc_amp=0.09, osc_freq=3.0,
        comprimento=0.012, largura=0.0016, cor=(255, 196, 84), modo="add", cintila=True,
        nitidez_por_camada=(0.35, 0.7, 1.0),
    ),
    "folhas": Perfil(
        nome="folhas", vx=0.12, vy=0.5, gravidade=0.05, osc_amp=0.10, osc_freq=1.1,
        comprimento=0.0, largura=0.0055, cor=(214, 168, 92), modo="over",
        tamanho_por_camada=(0.7, 1.0, 1.4), velocidade_por_camada=(0.7, 0.95, 1.25),
    ),
}


# --------------------------------------------------------------------------- config


@dataclass
class ParticulasCfg:
    """Controles do efeito. `intensidade` e `opacidade` agem em separado."""

    tipo: str = "chuva"
    densidade: int = 900          # particulas no total (divididas em 3 camadas)
    intensidade: float = 1.0      # 0..1: quanto o efeito aparece (escala o alfa)
    opacidade: float = 0.55       # 0..1: opacidade master da camada
    rastro: float = 1.0           # comprimento do rastro em multiplo do perfil
    desfoque: float = 1.0         # 1 = normal; <1 desfoca as camadas (profundidade)
    vento: float = 0.0            # vento lateral (fracao de tela por segundo)
    inicio: float = 0.0           # onde o efeito comeca no video
    duracao: float = 5.0          # segundos de efeito (resto fica limpo)
    semente: int = 1234


# --------------------------------------------------------------------------- campos


class CampoParticulas:
    """Posicao/velocidade por particula, geradas UMA vez (nao por quadro)."""

    #: fracao do total que vai para cada profundidade (fundo, meio, frente)
    PESO_CAMADAS = (0.45, 0.35, 0.20)

    def __init__(self, h: int, w: int, perfil: Perfil, cfg: ParticulasCfg, camada: int,
                 rng: np.random.Generator):
        self.h, self.w, self.perfil, self.cfg = h, w, perfil, cfg
        esc_tam = perfil.tamanho_por_camada[camada]
        esc_vel = perfil.velocidade_por_camada[camada]
        self.n = max(1, int(max(1, cfg.densidade) * self.PESO_CAMADAS[camada]))
        # posicao inicial (Y com folga para o rastro entrar pelo topo)
        self.x = rng.random(self.n) * w * 1.15 - w * 0.08
        self.y = rng.random(self.n) * (h * 1.30) - h * 0.18
        # velocidade variada por particula (perspectiva)
        varia = 0.55 + rng.random(self.n) * 0.90
        self.vx = (perfil.vx + cfg.vento) * esc_vel * varia
        self.vy = perfil.vy * esc_vel * varia
        self.grav = perfil.gravidade * esc_vel
        self.fase = rng.random(self.n) * math.tau
        # `larg` e FRACAO da largura da tela. O piso de 0,5 e em PIXEL (uma gota nunca
        # some de vez), entao o piso vai em px e nao aqui — com o piso aqui (0,5 fracao)
        # TODA gota era clampada para 0,5 e o rastro saia com meia tela de largura
        # (bug do lab: 640 px de "gota", 2,9 ms por particula em 900 gotas).
        # Espessura log-uniforme: gotas nitidas de la near-a-fundo (2x..0,4x). Linear
        # dava quase todas iguais — a visao apontou "espessura praticamente nenhuma".
        self.larg = perfil.largura * esc_tam * (10 ** (rng.random(self.n) * 1.1 - 0.55))
        # Comprimento LOG-UNIFORME: a chuva real e dominada por gotas curtas (pontos) com
        # algumas muito longas. Linear (0.5..1.5) produzia quase so riscos de mesmo
        # tamanho — foi o que a visao apontou como "tile/emissor repetitivo".
        self.comp = perfil.comprimento * esc_tam * cfg.rastro * (10 ** (rng.random(self.n) * 2.0 - 1.4))
        # uma fracao bem menor fica com rastro quase nulo (so o ponto da gota)
        curto = rng.random(self.n) < 0.28
        self.comp[curto] *= 0.05
        self.brilho = 0.55 + rng.random(self.n) * 0.45
        self.cintila_f = (1.0 + rng.random(self.n) * 4.0) if perfil.cintila else None
        self.cintila_fase = rng.random(self.n) * math.tau if perfil.cintila else None

    def passo(self, dt: float) -> None:
        """Avanca o campo em dt segundos; respawn no topo com X novo (nao vira listra)."""
        h, w = self.h, self.w
        self.x = (self.x + self.vx * w * dt) % (w * 1.25) - w * 0.12
        vy = self.vy + self.grav * 0.5
        self.y = self.y + vy * h * dt + self.grav * h * dt * dt * 3.0
        fora = self.y > h * 1.14
        if fora.any():
            n = int(fora.sum())
            r = np.random.default_rng(n * 7919 + 13)
            self.y[fora] = -h * 0.12 - r.random(n) * h * 0.06
            self.x[fora] = r.random(n) * w * 1.15 - w * 0.08


# --------------------------------------------------------------------------- composicao

#: parabola (perfil radial) por raio, em cache: evita refazer mgrid por gota por quadro
_PARABOLA: dict[int, np.ndarray] = {}


def _mistura(base: np.ndarray, camada: np.ndarray, modo: str) -> np.ndarray:
    """Alpha-over ou aditivo. `camada[..., 3]` e o alfa em 0..255."""
    if modo == "add":
        return np.clip(base + camada[..., :3], 0, 255)
    a = camada[..., 3:4] / 255.0
    return base * (1.0 - a) + camada[..., :3] * a


class EfeitoParticulas:
    """Renderizador do efeito para uma resolucao/fps."""

    def __init__(self, h: int, w: int, cfg: ParticulasCfg, fps: float = 30.0):
        self.h, self.w, self.cfg, self.fps = int(h), int(w), cfg, float(fps)
        self.perfil = PERFIS.get(cfg.tipo, PERFIS["chuva"])
        rng = np.random.default_rng(cfg.semente)
        self.camadas = [CampoParticulas(self.h, self.w, self.perfil, cfg, k, rng)
                        for k in range(3)]
        self._buf = np.zeros((self.h, self.w, 4), np.float32)
        self.t = 0.0

    @staticmethod
    def _ponto(buf: np.ndarray, cx: int, cy: int, r: int, cor: np.ndarray, a: float) -> None:
        """Disco suave (ou ponto) no buffer RGBA.

        Sem `np.mgrid`: um parabola pre-calculada por raio e fatiada. Com 900 gotas por
        quadro o mgrid por gota custava 3,8 s/quadro (0,3 fps); o parabola em cache derruba
        para ~1,5 ms porque o custo vira so a fatiada.
        """
        h, w = buf.shape[:2]
        r = max(1, int(r))
        if r > 64:                      # guarda: raio absurdo viraria matriz gigante
            r = 64
        perfil = _PARABOLA.get(r)
        if perfil is None:
            d = np.arange(-r, r + 1, dtype=np.float32)
            perfil = np.clip(1.0 - np.hypot(d[:, None], d[None, :]) / (r + 0.5), 0.0, 1.0)
            _PARABOLA[r] = perfil
        x0, x1 = max(0, cx - r), min(w, cx + r + 1)
        y0, y1 = max(0, cy - r), min(h, cy + r + 1)
        if x1 <= x0 or y1 <= y0:
            return
        # `perfil` tem (2r+1)x(2r+1) com o pixel [r, r] = centro (cx, cy).
        # A regiao visivel começa em x0/y0, entao o offset no sub-array e x0 - (cx - r).
        ay0, ax0 = y0 - (cy - r), x0 - (cx - r)
        sub = perfil[ay0:ay0 + (y1 - y0), ax0:ax0 + (x1 - x0)]
        buf[y0:y1, x0:x1, :3] += cor[None, None, :] * sub[..., None]
        buf[y0:y1, x0:x1, 3] += sub * a

    def _desenhar(self, c: CampoParticulas, idx: int, t: float) -> np.ndarray:
        """Camada de particulas num buffer RGBA float 0..255."""
        h, w, p = self.h, self.w, self.perfil
        buf = self._buf
        buf[:] = 0.0
        cor = np.array(p.cor, np.float32)
        # Nitidez por CAMADA (indice fixo), nao por tamanho da gota: o blur tem que
        # vir da profundidade da camada. Medido no lab: com o blur por tamanho as
        # pequenas saiam mais nitidas que as grandes (ao contrario do real).
        nit = min(1.0, p.nitidez_por_camada[idx] * self.cfg.desfoque)
        alpha_base = p.alpha_por_camada[idx] * self.cfg.opacidade * 255.0

        # posicao com turbulencia
        if p.osc_amp:
            osc_x = p.osc_amp * w * np.sin(t * p.osc_freq * math.tau + c.fase)
            osc_y = p.osc_amp * h * np.cos(t * p.osc_freq * 0.7 * math.tau + c.fase) * 0.3
        else:
            osc_x = np.zeros(c.n)
            osc_y = np.zeros(c.n)
        xs = c.x + osc_x
        ys = c.y + osc_y
        larg_px = np.maximum(1.0, c.larg * w)   # piso de 1 px: a gota nunca some de vez
        comp_px = c.comp * h

        if p.cintila and c.cintila_f is not None:
            brilho = c.brilho * (0.45 + 0.55 * (0.5 + 0.5 * np.sin(t * c.cintila_f + c.cintila_fase)))
        else:
            brilho = c.brilho

        tem_rastro = float(np.max(comp_px)) > 0.5
        # direcao da queda por particula: o rastro tem de seguir o MESMO angulo do
        # movimento (vento), senao a chuva cai na vertical e o rastro fica reto —
        # foi o que a visao apontou no lab: "listras verticais uniforme".
        # dir = (vx, vy) normalizado; o rastro vai de (x,y) contra esse vetor.
        vx_dir = c.vx
        vy_dir = c.vy + c.grav * 0.5
        for k in range(c.n):
            x = int(xs[k])
            y = int(ys[k])
            lw = max(1, int(larg_px[k]))
            a = alpha_base * float(brilho[k])
            if tem_rastro:
                cr = float(comp_px[k]) * (0.5 + float(brilho[k]))
                if cr < 1.0:
                    self._ponto(buf, x, y, lw, cor, a)
                    continue
                # normaliza (vx,vy): o vento da arrasto lateral e o rastro acompanha
                vv = math.hypot(vx_dir[k], vy_dir[k]) or 1.0
                ux, uy = vx_dir[k] / vv, vy_dir[k] / vv
                # Caixa APERTADA ao longo do segmento: o tamanho e o do risco (lw), nao
                # uma margem de lw em cada lado. Antes, com margem em X e Y, a caixa
                # virava um quadrado grande e o rastro saia um triangulo pintado, nao
                # um risco (medido: ocupava 0..201 x 0..201 em vez de uma linha).
                xa = max(0, int(min(x, x - ux * cr) - lw))
                xb = min(w, int(max(x, x - ux * cr) + lw) + 1)
                ya = max(0, int(min(y, y - uy * cr) - lw))
                yb = min(h, int(max(y, y - uy * cr) + lw) + 1)
                if yb <= ya or xb <= xa:
                    self._ponto(buf, x, max(0, min(h - 1, y)), lw, cor, a)
                    continue
                # O rastro e um SEGMENTO de espessura `lw` ao longo de (ux,uy): a rampa
                # corre no eixo da queda (a gota = 1.0, a cauda apaga) E EEE pela largura
                # perpendicular. Sem esta segunda rampa, o piso 0.18 pintava a caixa
                # inteira e o risco saia um triangulo (medido: 0..201 x 0..201).
                yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
                dx, dy = xx - x, yy - y
                proj = dx * ux + dy * uy                       # 0 na gota, -cr na cauda
                perp = np.abs(-dx * uy + dy * ux)              # distancia ao eixo do rastro
                ao_longo = np.clip(1.0 + proj / max(1.0, cr) * 0.82, 0.0, 1.0)
                na_largura = np.clip(1.0 - perp / (lw + 0.5), 0.0, 1.0)
                # Taper: a gota e mais larga na CABECA e afina na cauda (e nao uma
                # constante) — e o que separa um risco desenhado de uma gota em movimento.
                # Taper forte: largura da CABECA ~2,2x a da CAUDA. Com 0.45..1.0 a
                # diferenca era de 2,2x mas diluida na antialias; aqui o expoente
                # acentua o contraste entre a gota e o rabo.
                taper = 0.28 + 0.72 * ao_longo ** 0.7
                na_largura = np.clip(1.0 - perp / np.maximum(0.6, (lw + 0.5) * taper), 0.0, 1.0)
                ramp = (na_largura * ao_longo ** 0.55).astype(np.float32)
                buf[ya:yb, xa:xb, :3] += (cor * float(brilho[k]))[None, None, :] * ramp[..., None] * 0.5
                buf[ya:yb, xa:xb, 3] += ramp * a
            else:
                self._ponto(buf, x, y, lw * 2, cor, a)

        out = buf
        if nit < 1.0:
            import cv2
            # GaussianBlur exige kernel IMPAR >= 3
            # kernel proporcional ao desfoque pedido: nit 0,12 -> ~17 px de borrão
            k = int(max(3, round((1.0 - nit) * 21))) | 1
            if k >= 3:
                out = cv2.GaussianBlur(np.clip(out, 0, 255).astype(np.uint8), (k, k), 0).astype(np.float32)
        return out

    def quadro(self, base: np.ndarray, i: int) -> np.ndarray:
        """Aplica o efeito ao quadro `base` (H,W,3 uint8) no instante i do video."""
        dt = 1.0 / self.fps
        self.t = i * dt
        t_ini, t_fim = self.cfg.inicio, self.cfg.inicio + self.cfg.duracao
        if self.t < t_ini or self.t > t_fim:
            return base
        # envelope: sobe e desce suave (nunca "liga" do nada)
        env = min(1.0, (self.t - t_ini) / 0.35, max(1e-3, (t_fim - self.t)) / 0.6)
        env = max(0.0, min(1.0, env)) * self.cfg.intensidade
        if env <= 0.001:
            return base
        for c in self.camadas:
            c.passo(dt)
        out = base.astype(np.float32)
        for idx, c in enumerate(self.camadas):
            camada = self._desenhar(c, idx, self.t)
            if env < 1.0:
                camada = camada * env
            out = _mistura(out, camada, self.perfil.modo)
        return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- video


def aplicar_particulas(video: str, saida: str, cfg: ParticulasCfg | None = None,
                       duracao: float | None = None, audio: str | None = None) -> dict:
    """Aplica o efeito ao video -> MP4 em `saida` (NVENC). Mantem o audio se houver."""
    import cv2
    import render_dispatch as rd

    cfg = cfg or ParticulasCfg()
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_efetivo = int(round(duracao * fps)) if duracao else None

    fx = EfeitoParticulas(h, w, cfg, fps)
    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(saida).with_suffix(".parcial.mp4")
    cmd = [rd.ffmpeg_bin(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if audio:
        cmd += ["-i", audio, "-map", "0:v", "-map", "1:a?", "-shortest"]
    cmd += rd.video_args() + ["-pix_fmt", "yuv420p", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    i, n = 0, 0
    while True:
        ok, img = cap.read()
        if not ok or (n_efetivo is not None and i >= n_efetivo):
            break
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        out = fx.quadro(rgb, i)
        proc.stdin.write(np.ascontiguousarray(out[:, :, ::-1]).tobytes())  # RGB->BGR
        i += 1
        n += 1
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", "ignore")
    proc.wait()
    cap.release()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {err[-400:]}")
    tmp.replace(saida)
    return {"arquivo": saida, "quadros": n, "fps": fps, "w": w, "h": h,
            "duracao": round(n / fps, 2), "tipo": cfg.tipo}