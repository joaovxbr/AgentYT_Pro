#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
legendas_word_by_word.py — Legenda Dinâmica Estilo TikTok/Mugen (Palavra por Palavra).
Em vez de mostrar a frase inteira de uma vez:
1. Conforme cada palavra é cantada/falada, ela aparece na tela (ou varre em destaque com cor vibrante).
2. As palavras anteriores ficam acesas e a palavra atual brilha em ciano/dourado com escala maior.
3. Isso cria o efeito hipnótico exato de retenção onde o texto "escreve" junto com a voz do MC.
"""
from pathlib import Path
import json
import re

COR_DESTAQUE_ASS = "&H00E0F000&"  # Ciano elétrico BGR
COR_BRANCO_ASS = "&H00FFFFFF&"     # Branco BGR
COR_PASSADA_ASS = "&H00D0D0D0&"    # Cinza claro para palavras já ditas

CABECALHO_ASS = """[Script Info]
Title: VX RAPS Word-By-Word
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Cinzel,64,&H00FFFFFF&,&H000000FF&,&H00050505&,&H90000000,-1,0,0,0,100,100,1.8,0,1,3.4,2.5,2,100,100,75,1
Style: Highlight,Cinzel,66,&H00E0F000&,&H000000FF&,&H00050505&,&HA0000000,-1,0,0,0,105,105,2.0,0,1,3.8,2.8,2,100,100,75,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def tc(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = segundos % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def gerar_ass_word_by_word(transcricao_json_path: Path, ass_saida_path: Path):
    """
    Lê transcricao.json (que tem cada palavra com start e end) e gera eventos
    onde a frase vai se completando palavra a palavra dinamicamente.
    """
    dados = json.loads(transcricao_json_path.read_text(encoding="utf-8"))
    segments = dados.get("segments", [])
    
    dialogues = []

    for seg in segments:
        words = seg.get("words", [])
        if not words:
            continue

        # Para cada palavra que entra no segmento
        for idx, w in enumerate(words):
            t_ini = float(w["start"])
            t_fim = float(words[idx + 1]["start"]) if idx + 1 < len(words) else float(w["end"]) + 0.35
            
            # Constrói o texto do momento:
            # Palavras antes do idx aparecem em cinza claro/branco
            # A palavra atual (idx) aparece em CIANO VIBRANTE destacada
            partes_texto = []
            for j, w_item in enumerate(words[:idx + 1]):
                texto_w = w_item["word"].strip().upper()
                if j == idx:
                    # Palavra atual sendo cantada: CIANO LUMINOSO + BOLD
                    partes_texto.append(f"{{\\c{COR_DESTAQUE_ASS}\\b1}}{texto_w}{{\\c{COR_BRANCO_ASS}\\b0}}")
                else:
                    # Palavras anteriores já ditas
                    partes_texto.append(f"{{\\c{COR_PASSADA_ASS}}}{texto_w}{{\\c{COR_BRANCO_ASS}}}")

            linha_final = " ".join(partes_texto)
            dialogues.append(f"Dialogue: 0,{tc(t_ini)},{tc(t_fim)},Default,,0,0,0,,{linha_final}")

    conteudo = CABECALHO_ASS + "\n".join(dialogues) + "\n"
    ass_saida_path.parent.mkdir(parents=True, exist_ok=True)
    ass_saida_path.write_text(conteudo, encoding="utf-8")
    print(f"[WORD-BY-WORD] Gerado arquivo ASS com {len(dialogues)} estados de palavra em: {ass_saida_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Uso: python legendas_word_by_word.py <transcricao.json> <saida.ass>")
        sys.exit(1)
    gerar_ass_word_by_word(Path(sys.argv[1]), Path(sys.argv[2]))
