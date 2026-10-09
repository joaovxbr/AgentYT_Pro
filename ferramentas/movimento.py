#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""movimento.py — motion graphics de CAMERA por cena (zoom/pan continuos).

Biblioteca de composicao. Traduz o plano de camera de cada shot
(plano_visual.json -> camera.zoom_inicio/zoom_fim) num filtro FFmpeg de
movimento CONTINUO (estilo ken-burns), que da vida a planos parados sem
depender do beat. Impacto ganha um zoom mais agressivo; respiro, um leve.

Diferente do zoom_pulse do filtros.py, que pulsa NA BATIDA: aqui o movimento
e suave e cobre a cena inteira, resolvendo o 'congelado' de planos estaticos.

    vf = movimento.filtro_zoom(dur=3.2, z0=1.0, z1=1.06, largura=1920, altura=1080)

Usa zoompan (reavalia por quadro; crop avalia so na init e falha com expr em t).
"""
from __future__ import annotations

FPS = 30


def filtro_zoom(dur: float, z0: float, z1: float,
                largura: int = 1920, altura: int = 1080,
                fps: int = FPS, pan: str = "centro") -> str:
    """Zoom linear de z0->z1 ao longo de `dur` segundos, com pan opcional.

    pan: 'centro' (fixo), 'cima', 'baixo', 'esq', 'dir' — desloca o quadro
    devagar na direcao, dando sensacao de movimento de camera.
    """
    n = max(1, int(round(dur * fps)))
    # 🔴 zoompan em VIDEO: d=1 (um frame de saida por frame de entrada). Com d>1
    # ele DUPLICA frames (o clipe "congela"). A progressao usa 'on' = indice do
    # frame de SAIDA, que aqui anda 1:1 com a entrada porque d=1.
    if n > 1:
        prog = f"on/{n - 1}"
    else:
        prog = "0"
    z = f"min({z1:.5f}\\,{z0:.5f}+({z1 - z0:.5f})*{prog})"

    # centro do recorte segue o zoom; pan desloca devagar dentro da margem.
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    desl = f"(iw*0.05)*{prog}"
    desl_y = f"(ih*0.05)*{prog}"
    if pan == "cima":
        cy = f"ih/2-(ih/zoom/2)-{desl_y}"
    elif pan == "baixo":
        cy = f"ih/2-(ih/zoom/2)+{desl_y}"
    elif pan == "esq":
        cx = f"iw/2-(iw/zoom/2)-{desl}"
    elif pan == "dir":
        cx = f"iw/2-(iw/zoom/2)+{desl}"

    return (f"zoompan=z='{z}':x='{cx}':y='{cy}'"
            f":d=1:s={largura}x{altura}:fps={fps:g}")


def parametros_do_shot(shot: dict) -> dict:
    """Extrai z0/z1/pan de um shot do plano_visual, com defaults sensatos.

    'impacto' zooma mais forte; 'respiro'/'narrativo', leve. Alterna o pan por
    linha para o movimento nao ficar sempre igual.
    """
    cam = shot.get("camera", {}) or {}
    preset = shot.get("preset", "narrativo")
    z0 = float(cam.get("zoom_inicio", 1.0))
    z1 = float(cam.get("zoom_fim", 1.05 if preset == "impacto" else 1.03))
    # Motion Match tem prioridade. O pan ciclico antigo fica apenas como fallback.
    pan_map = {"left": "esq", "right": "dir", "up": "cima", "down": "baixo",
               "esq": "esq", "dir": "dir", "cima": "cima", "baixo": "baixo",
               "static": "centro", "centro": "centro"}
    requested = str(cam.get("pan", "")).lower()
    if requested in pan_map:
        pan = pan_map[requested]
    else:
        linha = shot.get("line")
        pans = ["centro", "cima", "dir", "baixo", "esq"]
        pan = pans[(linha or 0) % len(pans)] if isinstance(linha, int) else "centro"
    return {"z0": z0, "z1": z1, "pan": pan}
