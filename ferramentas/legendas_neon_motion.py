#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
legendas_neon_motion.py — Legenda Word-by-Word com MOTION GRAPHICS DE NEON NATIVO (ASS puro).
Combina o efeito palavra-por-palavra com desenho de neon animado direto no ASS
(sem sequência PNG externa — é tudo tag ASS, renderizado na GPU pelo libass):

1. Palavra atual acende em ciano/dourado com \\t (transform) de escala pop (1.0 -> 1.15 -> 1.0)
2. Um TRAÇO DE NEON GLOW se DESENHA por baixo da palavra usando \\clip animado (revelação da esquerda p/ direita)
3. Glow forte (\\blur + \\3c cor de neon) na palavra ativa, simulando emissão de luz
4. Palavras já ditas ficam em cinza translúcido; as por-vir invisíveis até a hora
5. Camada de "energia" (linha neon horizontal no rodapé) que pulsa a cada onset

O resultado é a legenda "escrevendo" na tela com rastros de luz neon como motion graphics.
"""
from pathlib import Path
import json
import re

# Cores em formato ASS &HAABBGGRR (AA=alpha invertido, 00=opaco)
COR_NEON_CIANO = "&H00F0E000&"      # ciano elétrico
COR_NEON_DOURADO = "&H0020C0FF&"    # dourado/laranja
COR_NEON_VERMELHO = "&H002030FF&"   # vermelho sangue
COR_BRANCO = "&H00FFFFFF&"
COR_CINZA = "&H00B0B0B0&"

# Palavras que ganham neon dourado/vermelho (impacto) em vez do ciano padrão
PALAVRAS_FOGO = re.compile(r"(chamas|fogo|sangue|morte|fúria|amaterasu|queimar|destruir|ódio|vingador)", re.I)
PALAVRAS_PODER = re.compile(r"(chidori|kirin|susanoo|sharingan|rinnegan|uchiha|trovão|relâmpago|poder|monarca)", re.I)

CABECALHO = """[Script Info]
Title: VX RAPS Neon Motion
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Cinzel,60,&H00FFFFFF&,&H000000FF&,&H00101010&,&H90000000,-1,0,0,0,100,100,1.6,0,1,3.2,2.4,2,90,90,170,1
Style: Neon,Cinzel,60,&H00F0E000&,&H000000FF&,&H00101010&,&H80000000,-1,0,0,0,100,100,1.6,0,1,3.5,2.6,2,90,90,170,1
Style: NeonLinha,Cinzel,60,&H00F0E000&,&H000000FF&,&H00F0E000&,&H00000000&,-1,0,0,0,100,100,0,0,1,2.0,0,2,90,90,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def tc(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = segundos % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _cor_da_palavra(palavra: str) -> str:
    if PALAVRAS_FOGO.search(palavra):
        return COR_NEON_VERMELHO
    if PALAVRAS_PODER.search(palavra):
        return COR_NEON_DOURADO
    return COR_NEON_CIANO


def gerar_ass_neon_motion(transcricao_json_path: Path, ass_saida_path: Path):
    """
    Lê transcricao.json com palavras (start/end) e gera legenda com neon motion graphics.
    Cada palavra: aparece com pop de escala + glow neon + traço de neon desenhando por baixo.
    """
    dados = json.loads(transcricao_json_path.read_text(encoding="utf-8"))
    segments = dados.get("segments", [])

    dialogues = []

    for seg in segments:
        words = seg.get("words", [])
        if not words:
            continue

        for idx, w in enumerate(words):
            t_ini = float(w["start"])
            t_fim = float(words[idx + 1]["start"]) if idx + 1 < len(words) else float(w["end"]) + 0.35
            dur_ms = int((t_fim - t_ini) * 1000)
            cor_neon = _cor_da_palavra(w["word"])

            # Monta o texto acumulado (palavra por palavra)
            partes = []
            for j, wj in enumerate(words[:idx + 1]):
                txt = wj["word"].strip().upper()
                if j == idx:
                    # PALAVRA ATIVA: preenchimento tingido na cor neon + glow bloom emissivo + pop
                    pop = (
                        "{\\b1\\3c" + cor_neon + "\\c" + cor_neon + "\\blur5"
                        "\\t(0,120,\\fscx118\\fscy118)\\t(120,260,\\fscx100\\fscy100)}"
                    )
                    partes.append(pop + txt + "{\\r}")
                else:
                    partes.append("{\\c" + COR_CINZA + "\\alpha&H40&}" + txt + "{\\r}")

            linha_txt = " ".join(partes)
            # camada 1: o texto
            dialogues.append(
                f"Dialogue: 1,{tc(t_ini)},{tc(t_fim)},Base,,0,0,0,,{{\\fad(60,60)}}{linha_txt}"
            )

            # camada 0 (por baixo): TRAÇO DE NEON que se desenha da esquerda p/ direita.
            # Y ajustado para 905px para acompanhar a margem da legenda e ficar perfeitamente
            # sobre a área de imagem (dentro do 2.39:1, acima da barra preta).
            y_linha = 905
            texto_linha = " ".join(wj["word"].strip().upper() for wj in words[:idx + 1])
            n_chars = max(6, len(texto_linha))
            largura_px = min(1500, n_chars * 41)  # ~41px por char na Cinzel 64 bold
            cx = 960
            x1 = cx - largura_px // 2
            x2 = cx + largura_px // 2
            dur_reveal = max(120, int(dur_ms * 0.8))
            neon = (
                f"Dialogue: 0,{tc(t_ini)},{tc(t_fim)},NeonLinha,,0,0,0,,"
                f"{{\\an7\\pos(0,0)\\p1\\blur7\\3c{cor_neon}\\c{cor_neon}"
                f"\\clip({x1},{y_linha-5},{x1},{y_linha+5})"
                f"\\t(0,{dur_reveal},\\clip({x1},{y_linha-5},{x2},{y_linha+5}))}}"
                f"m {x1} {y_linha} l {x2} {y_linha} l {x2} {y_linha+4} l {x1} {y_linha+4}"
            )
            dialogues.append(neon)

    conteudo = CABECALHO + "\n".join(dialogues) + "\n"
    ass_saida_path.parent.mkdir(parents=True, exist_ok=True)
    ass_saida_path.write_text(conteudo, encoding="utf-8")
    print(f"[NEON MOTION] Gerado ASS com {len(dialogues)} eventos (texto + neon) em: {ass_saida_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Uso: python legendas_neon_motion.py <transcricao.json> <saida.ass>")
        sys.exit(1)
    gerar_ass_neon_motion(Path(sys.argv[1]), Path(sys.argv[2]))
