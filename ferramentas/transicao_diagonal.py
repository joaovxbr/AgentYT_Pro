#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transicao diagonal de AMV com linha de corte, brilho, motion blur e particulas.

O que existe hoje (legado/transicoes_vfx.py) sao filtros FFmpeg de impacto (whip_pan,
zoom_in_punch, glitch_rgb, flash_cut):小猫 Troca seca ou efeito de tela cheia. Esta e a
transicao DE CENA: a cena B entra por uma frente diagonal animada, com uma **linha de corte**
que vai na frente, brilho na borda, rastro de motion blur so na regiao que entra, e particulas
opcionais que explodem na virada.

Nucleo: a mascara e um campo escalar por quadro gerado em numpy (float32), e o compositor e
`A*(1-m) + B*m + linha + brilho`. Sem shader, sem dependencia nova — roda em 1080p e 4K, 30 e
60 fps, e o custo e o mesmo porque a mascara so depende da geometria e do progresso (cache por
(forma, tamanho, quadro) para nao recomputar a cada quadro).

Formas de mascara (`forma`):
  diagonal     frente a 45 graus da esquerda-baixa para a direita-alta (padrao)
  diagonal_inv espelho (direita-baixa -> esquerda-alta)
  chevron      duas frentes em ">" (mais rapida no centro)
  wipe_ang     angulo livre (`angulo` em graus; a mascara vira projecao)
  circular     raio crescente (fallback organico, nao linear)

Efeitos (`efeitos`, todos opcionais):
  linha        linha de corte na frente (cor, espessura, brilho)
  brilho       halo na linha + realce da borda que entra (bloom barato por box blur)
  motion_blur  rastro da frente (media direcional ao longo do vetor normal)
  particulas   explosive de pontos ao longo da linha, com gravidade e fade

Sincronia com a batida: `pulso` (0..1) de `audio_reactive_fx.pulso_no_tempo` empurra a
frente (avanco extra), acende a linha e estoura as particulas. O `progresso` da mascara e
`suave(t)` + `avanco_por_pulso`, e o envelope de brilho segue a curva de energia, entao o
corte "cai" na batida em vez de ser linear.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------- helpers


def hex_rgb(valor: str, fallback: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    if isinstance(valor, (tuple, list)) and len(valor) == 3:
        return tuple(int(x) for x in valor)
    h = str(valor or "").lstrip("#")
    if len(h) == 6:
        try:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return fallback
    return fallback


def suave(x):
    """smoothstep 0..1 (inicio/fim sem aceleracao dura). Aceita escalar ou array."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _grid(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return xx, yy


# --------------------------------------------------------------------------- mascara


@dataclass
class TransicaoCfg:
    """Tudo que a transicao precisa. Laterais e fps sao do video, nao da cfg."""

    forma: str = "diagonal"
    angulo: float = 45.0
    duracao: float = 0.35              # duracao da transicao (s)
    suavidade: float = 0.22            # largura da borda (0 = corte duro)
    particulas: int = 0                # 0 = sem particulas
    cor_linha: str = "#FFFFFF"
    espessura_linha: float = 0.012     # fra��ao da diagonal (pequeno = linha fina)
    brilho: float = 0.55               # 0..1 halo na linha
    brilho_borda: float = 0.30         # 0..1 realce da cena que entra
    motion_blur: float = 0.35          # 0..1 intensidade do rastro
    cor_particula: str = "#FFE9A8"
    raio_particula: float = 0.0035     # fra��ao da menor dimensao
    gravidade: float = 0.35
    semente: int = 7


@dataclass
class _CacheChave:
    forma: str
    angulo: float
    h: int
    w: int
    passo: int                      # a que granularity os quadros de cache sao


class Transicao:
    """Compositor de duas cenas com mascara diagonal animada. Reutilizavel (pool)."""

    def __init__(self, h: int, w: int, cfg: TransicaoCfg | None = None):
        self.h, self.w = int(h), int(w)
        self.cfg = cfg or TransicaoCfg()
        self.xx, self.yy = _grid(self.h, self.w)
        # vetor normal da frente (unidade) e ponto de origem
        a = math.radians(self.cfg.angulo if self.cfg.forma == "wipe_ang" else 45.0)
        self.nx, self.ny = -math.sin(a), math.cos(a)          # normal da frente
        self.ux, self.uy = math.cos(a), math.sin(a)           # direcao da frente
        self._cache: dict[tuple, np.ndarray] = {}
        self._rnd = np.random.default_rng(self.cfg.semente)

    # ------------------------------------------------------------ mascara
    def _dist(self) -> np.ndarray:
        """Projecao normalizada em 0..1 (0 = A, 1 = B) ao longo da frente."""
        p = self.xx * self.nx + self.yy * self.ny
        return p

    def _faixa(self, progresso: float) -> np.ndarray:
        """Mascara 0..1 do avanco da frente, com borda suave."""
        p = self._dist()
        lo, hi = float(p.min()), float(p.max())
        rng = max(1e-6, hi - lo)
        pos = (p - lo) / rng                        # 0..1 na tela (0 = fundo, 1 = frente)
        s = max(1e-4, self.cfg.suavidade)
        # O sinal importa: `pos` cresce na direcao da normal (nx,ny). A frente tem de
        # ARRANCAR em -s (nada de B na tela) e CHEGAR a 1+s (tudo B). Como `pos` cresce
        # para o lado OPOSTO ao que a frente avanca, o alvo caminha de 1+s para -s.
        # Sem essa inversao a mascara nasce 100% B e morre 0% B (wipe ao contrario).
        alvo = (1.0 + s) - progresso * (1.0 + 2 * s)
        m = np.clip(((1.0 - pos) - (alvo - s)) / (2 * s), 0.0, 1.0)
        m = suave(m)
        if self.cfg.forma == "circular":
            cx, cy = self.w * 0.5, self.h * 0.5
            d = np.hypot(self.xx - cx, self.yy - cy) / max(1.0, math.hypot(cx, cy))
            alvo = progresso * 1.45 - 0.22
            m = suave(np.clip((d - (alvo - s)) / (2 * s), 0.0, 1.0))
        elif self.cfg.forma == "chevron":
            # dobra o eixo: |u| da direcao da frente -> frente em ">"
            u = np.abs(self.xx * self.ux + self.yy * self.uy) / max(1.0, self.w * 0.5)
            pos2 = np.clip(u, 0.0, 1.0)
            alvo = progresso * 1.45 - 0.22
            m = suave(np.clip((pos2 - (alvo - s)) / (2 * s), 0.0, 1.0))
        return m.astype(np.float32)

    def mascara(self, i: int, n: int) -> np.ndarray:
        """Mascara do quadro i de n (float32 HxW em 0..1). Cache por passo de ~0.02."""
        passo = max(1, n // 96)
        k = int(round(i / passo))
        chave = (self.cfg.forma, round(self.cfg.angulo, 2), self.h, self.w, k)
        if chave in self._cache:
            return self._cache[chave]
        t = (k * passo) / max(1, n - 1)
        m = self._faixa(t)
        self._cache[chave] = m
        return m

    def pos_frente(self, i: int, n: int) -> tuple[float, float]:
        """Ponto na linha de corte (em px) no quadro i — usado por particulas."""
        t = i / max(1, n - 1)
        s = max(1e-4, self.cfg.suavidade)
        # mesma inversao da _faixa: a frente vai de 1+s (fora da tela) ate -s.
        alvo = (1.0 + s) - t * (1.0 + 2 * s)
        p = self._dist()
        lo, hi = float(p.min()), float(p.max())
        lvl = lo + (hi - lo) * float(np.clip(alvo, 0.0, 1.0))
        # ponto no meio da tela, projetado na frente
        cx, cy = self.w * 0.5, self.h * 0.5
        pn = cx * self.nx + cy * self.ny
        return (cx + self.ux * (lvl - pn), cy + self.uy * (lvl - pn))

    # ------------------------------------------------------------ efeitos
    def _linha(self, m: np.ndarray) -> np.ndarray:
        """Linha de corte fina na frente (brilho RGB)."""
        if self.cfg.espessura_linha <= 0:
            return np.zeros((self.h, self.w, 3), np.float32)
        frente = 0.5 * (m + np.roll(m, -1, axis=1))
        banda = np.clip(1.0 - np.abs(frente - 0.5) / max(1e-4, self.cfg.espessura_linha * 6), 0.0, 1.0)
        cor = np.array(hex_rgb(self.cfg.cor_linha), np.float32)
        return (banda[..., None] * cor) * min(1.0, self.cfg.brilho * 2.2)

    def _brilho_borda(self, m: np.ndarray, B: np.ndarray) -> np.ndarray:
        """Realce da cena que esta entrando (borda quente)."""
        if self.cfg.brilho_borda <= 0:
            return np.zeros_like(B, dtype=np.float32)
        borda = np.abs(m - 0.5) * 2.0
        borda = np.clip(1.0 - borda, 0.0, 1.0)
        # so onde B ja aparece (m>0.4) e suave
        peso = np.clip((m - 0.4) / 0.6, 0, 1)
        realce = borda * peso
        return B * (realce[..., None] * self.cfg.brilho_borda * 1.4)

    def _motion_blur(self, m: np.ndarray, n_passos: int = 5) -> np.ndarray:
        """Rastro da frente: media deslocada ao longo da normal (so onde entra)."""
        if self.cfg.motion_blur <= 0:
            return m
        passo = int(max(1, round(self.cfg.motion_blur * n_passos)))
        acc = np.zeros_like(m)
        peso = 0.0
        for k in range(1, passo + 1):
            desl = m * k / passo
            desl = np.roll(desl, -int(self.nx * k), axis=1)
            desl = np.roll(desl, -int(self.ny * k), axis=0)
            acc += desl
            peso += 1.0
        return np.clip(acc / max(1.0, peso), 0.0, 1.0)

    def _particulas(self, i: int, n: int, pulso: float) -> np.ndarray:
        """Explosao de pontos ao longo da linha de corte."""
        k = self.cfg.particulas
        if k <= 0:
            return np.zeros((self.h, self.w, 3), np.float32)
        t = i / max(1, n - 1)
        if t < 0.02 or t > 0.98:
            return np.zeros((self.h, self.w, 3), np.float32)
        out = np.zeros((self.h, self.w, 3), np.float32)
        cor = np.array(hex_rgb(self.cfg.cor_particula), np.float32)
        px, py = self.pos_frente(i, n)
        # sistema de particulas deterministico (mesma cena -> mesma chuva)
        vida = 0.6
        for j in range(k):
            s = (j * 2654435761) % 1000 / 1000.0        # posicao na frente
            spread = ((j * 40503) % 977) / 977.0         # posicao ao longo
            vel = (((j * 22695477) % 811) / 811.0 - 0.5) * 2
            # posicao na tela: ponto da frente deslocado tangencialmente
            tang = (spread - 0.5) * max(self.w, self.h) * 0.9
            bx = px + self.ux * tang
            by = py + self.uy * tang
            # avanco radial + gravidade ao longo do tempo
            r = vel * (self.w * 0.02) * (t + 0.1) * (1 + pulso)
            dx = bx + self.nx * r
            dy = by + self.ny * r + self.cfg.gravidade * self.h * 0.12 * t * t
            fade = max(0.0, 1.0 - t / vida) * (0.6 + 0.4 * pulso)
            raio = max(1, int(self.cfg.raio_particula * self.h * (0.6 + 0.6 * (j % 3))))
            y0, y1 = int(max(0, dy - raio)), int(min(self.h, dy + raio + 1))
            x0, x1 = int(max(0, dx - raio)), int(min(self.w, dx + raio + 1))
            if y1 <= y0 or x1 <= x0:
                continue
            yy0, xx0 = np.mgrid[y0:y1, x0:x1]
            dist = np.hypot(xx0 - dx, yy0 - dy)
            ponto = np.clip(1.0 - dist / raio, 0.0, 1.0)
            out[y0:y1, x0:x1] += ponto[..., None] * cor * fade
        return out

    # ------------------------------------------------------------ quadro
    def quadro(self, A: np.ndarray, B: np.ndarray, i: int, n: int, pulso: float = 0.0) -> np.ndarray:
        """Compõe o quadro i de n a partir de A e B (H,W,3 uint8/float). 0 = A, 1 = B."""
        pulso = float(max(0.0, min(1.0, pulso)))
        # avanco extra pela batida: a frente "salta" no pulso
        prog = suave(i / max(1, n - 1)) * (1.0 + 0.35 * pulso)
        prog = min(1.15, prog)
        m = self._faixa(min(1.0, prog))
        mb = self._motion_blur(m)
        ma = 1.0 - mb
        Af = A.astype(np.float32)
        Bf = B.astype(np.float32)
        base = Af * ma[..., None] + Bf * m[..., None]
        out = base + self._linha(m) + self._brilho_borda(m, Bf) + self._particulas(i, n, pulso)
        return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- video


def _abrir(caminho: str) -> tuple["cv2.VideoCapture", int, int, float, int]:
    import cv2
    cap = cv2.VideoCapture(caminho)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    return cap, w, h, fps, n


def _quadros(cap, i0: int, n: int, w: int, h: int) -> list[np.ndarray]:
    """Le n quadros a partir de i0 (repetindo o ultimo se faltar)."""
    import cv2
    saida = []
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, i0))
    for _ in range(n):
        ok, img = cap.read()
        if not ok:
            img = saida[-1] if saida else np.zeros((h, w, 3), np.uint8)
            saida.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            continue
        saida.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    return saida


def renderizar_transicao(video_a: str, video_b: str, saida: str,
                         corte: float = -1.0, cfg: TransicaoCfg | None = None,
                         audio: str | None = None, ate: int | None = None,
                         contexto_antes: float = 0.7, contexto_depois: float = 0.7,
                         delay: float = 0.0) -> dict:
    """Transicao entre o quadro `corte` de A e o inicio de B -> MP4 em `saida`.

    `corte`        em segundos dentro de A (onde a cena B entra)
    `ate`          limita quantos quadros de B usar (default: so o necessario)
    `delay`        segura a cena A por N segundos ANTES da frente comecar a andar. Sem
                   isso a transicao comeca no mesmo instante do corte e o efeito passa
                   rapido demais para ver (0,34 s de frente numa cena de 3 s).
    `contexto_*`   segundos de cena pura antes e depois, para a previa ter contexto.
    Sincroniza com a batida via `audio` quando dado.
    """
    import cv2
    import render_dispatch as rd
    from audio_reactive_fx import pulso_no_tempo

    cfg = cfg or TransicaoCfg()
    capA, wA, hA, fpsA, nA = _abrir(video_a)
    capB, wB, hB, fpsB, nB = _abrir(video_b)
    if (wA, hA) != (wB, hB):
        raise ValueError(f"cenas de tamanhos diferentes: {wA}x{hA} vs {wB}x{hB}")
    fps = fpsA
    corte_i = int((corte if corte >= 0 else 0) * fps)
    n_trans = max(2, int(round(cfg.duracao * fps)))
    n_trans = min(n_trans, (ate or nB) or n_trans)

    # picos de bass para a batida (tempo absoluto de A, relativo a corte)
    picos = []
    if audio:
        try:
            import audio_reactive_fx as arf
            from pathlib import Path as _P
            picos = arf.carregar_picos(_P("."), {})  # sem manifesto: pega cache global
        except Exception:
            picos = []

    trans = Transicao(hA, wA, cfg)
    # `delay`: a frente espera antes de comecar. O canto e 100% A durante a espera,
    # entao o efeito fica legivel em vez de passar correndo (0,34 s de frente).
    n_espera = max(0, int(round(delay * fps)))
    n_espera = min(n_espera, max(0, nA - corte_i - 2))
    n_total = n_espera + n_trans
    quadA = _quadros(capA, corte_i, n_total, wA, hA)
    quadB = _quadros(capB, 0, n_total, wA, hA)
    antes = max(0, int(contexto_antes * fps))
    depois = max(0, int(contexto_depois * fps))
    quad_antes = _quadros(capA, max(0, corte_i - antes), min(antes, corte_i), wA, hA)
    quad_depois = _quadros(capB, n_total, depois, wA, hA)

    quadros_tr = []
    for i in range(n_total):
        if i < n_espera:
            # durante a espera a frente nao andou: a cena e A puro
            quadros_tr.append(quadA[i].copy())
            continue
        j = i - n_espera
        pulso = (pulso_no_tempo(picos, (corte + i / fps) / fps) if picos else 0.0)
        quadros_tr.append(trans.quadro(quadA[i], quadB[i], j, n_trans, pulso=pulso))

    todos = quad_antes + quadros_tr + quad_depois
    capA.release()
    capB.release()

    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(saida).with_suffix(".parcial.mp4")
    # pipe frames -> ffmpeg (NVENC via render_dispatch)
    import subprocess
    cmd = [rd.ffmpeg_bin(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{wA}x{hA}", "-r", str(fps), "-i", "-"]
    if audio:
        cmd += ["-i", audio, "-map", "0:v", "-map", "1:a?", "-shortest", "-af", "atrim=0:"]
    cmd += rd.video_args() + ["-pix_fmt", "yuv420p", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for img in todos:
        proc.stdin.write(np.ascontiguousarray(img[:, :, ::-1]).tobytes())  # RGB->BGR
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", "ignore")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {err[-400:]}")
    tmp.replace(saida)
    return {"arquivo": saida, "quadros": len(todos), "fps": fps,
            "w": wA, "h": hA, "duracao": round(len(todos) / fps, 2),
            "espera_quadros": n_espera, "transicao_quadros": n_trans,
            "frente_inicio_s": round(antes / fps + delay, 2),
            "frente_fim_s": round(antes / fps + delay + cfg.duracao, 2)}