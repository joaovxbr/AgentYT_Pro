#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
legendas_mugen_pro.py — Gerador de Legendas ASS no Estilo Mugen Raps / Jiraiya.
Recursos inspirados no vídeo de referência:
1. Fonte Cinzel Bold em caixa alta clássica com serifa (estilo épico)
2. Destaques automáticos em palavras de impacto (Nomes de clãs, Akatsuki, vilas, técnicas, cores):
   - Ciano / Turquesa luminoso com glow neon suave
   - Vermelho sangue / Carmesim com outer glow
3. Fade-in e Fade-out suaves milimétricos (\\fad(120, 100))
4. Animação de preenchimento dinâmico e suporte a karaoke
"""
from pathlib import Path
import re
import json

PALAVRAS_DESTAQUE_CIANO = [
    r"\bakatsuki\b", r"\buchiha\b", r"\bsharingan\b", r"\brinnegan\b", r"\bkonoha\b",
    r"\brasengan\b", r"\bsannin\b", r"\blenda\b", r"\bmonarca\b", r"\bsombra\b",
    r"\barise\b", r"\bliberdade\b", r"\btatakae\b", r"\beremita\b", r"\bsábio\b"
]

PALAVRAS_DESTAQUE_VERMELHO = [
    r"\bvermelha\b", r"\bvermelho\b", r"\bsangue\b", r"\bmorte\b", r"\bmorrer\b",
    r"\bdestruidor\b", r"\bchamas\b", r"\bfogo\b", r"\bfúria\b", r"\bódio\b",
    r"\bmatar\b", r"\bgolpe\b", r"\bperigo\b"
]

COR_CIANO_ASS = "&H00E0F000&"       # Ciano vibrante em formato BGR ASS
COR_VERMELHO_ASS = "&H002020FF&"    # Vermelho sangue em formato BGR ASS
COR_BRANCO_ASS = "&H00FFFFFF&"

CABECALHO_ASS_MUGEN = """[Script Info]
Title: VX RAPS - Mugen Pro Style
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Cinzel,56,&H00FFFFFF&,&H000000FF&,&H00050505&,&H90000000,-1,0,0,0,100,100,1.8,0,1,3.2,2.4,2,100,100,65,1
Style: DestaqueCiano,Cinzel,56,&H00E0F000&,&H000000FF&,&H00050505&,&HB0004000,-1,0,0,0,102,102,2.0,0,1,3.6,3.0,2,100,100,65,1
Style: DestaqueVermelho,Cinzel,56,&H002020FF&,&H000000FF&,&H00050505&,&HB0000040,-1,0,0,0,102,102,2.0,0,1,3.6,3.0,2,100,100,65,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def formatar_tempo_ass(segundos: float) -> str:
    """Converte segundos float para formato H:MM:SS.CC do ASS."""
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = segundos % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def estilizar_linha_mugen(texto_verso: str) -> str:
    """
    Substitui palavras-chave por tags de cor ASS (ciano ou vermelho) com fade suave.
    """
    palavras = texto_verso.split()
    novas_palavras = []
    
    for p in palavras:
        p_clean = re.sub(r"[^\wáéíóúâêîôûãõç]", "", p, flags=re.I).lower()
        
        # Checa ciano
        eh_ciano = any(re.search(pat, p_clean) for pat in PALAVRAS_DESTAQUE_CIANO)
        # Checa vermelho
        eh_vermelho = any(re.search(pat, p_clean) for pat in PALAVRAS_DESTAQUE_VERMELHO)
        
        if eh_ciano:
            # Tag de cor ciano + reset para branco
            novas_palavras.append("{\\c" + COR_CIANO_ASS + "\\b1}" + p.upper() + "{\\c" + COR_BRANCO_ASS + "\\b0}")
        elif eh_vermelho:
            # Tag de cor vermelho + reset para branco
            novas_palavras.append("{\\c" + COR_VERMELHO_ASS + "\\b1}" + p.upper() + "{\\c" + COR_BRANCO_ASS + "\\b0}")
        else:
            novas_palavras.append(p.upper())
            
    linha_formatada = " ".join(novas_palavras)
    # Adiciona o fade de entrada e saída característico (120ms in, 90ms out)
    return "{\\fad(120,90)}" + linha_formatada

def converter_letra_para_ass_mugen(caminho_letra_txt: Path, caminho_saida_ass: Path):
    """
    Lê o arquivo LETRA.txt (com formato `<tempo>  <TEXTO>`) e gera o arquivo .ass estilizado.
    """
    linhas_orig = caminho_letra_txt.read_text(encoding="utf-8").splitlines()
    eventos = []
    
    itens = []
    for l in linhas_orig:
        l = l.strip()
        if not l: continue
        partes = l.split(maxsplit=1)
        if len(partes) == 2:
            try:
                t = float(partes[0].replace("s", ""))
                itens.append((t, partes[1]))
            except ValueError:
                continue
                
    for i, (t_ini, txt) in enumerate(itens):
        if i + 1 < len(itens):
            t_fim = itens[i+1][0]
        else:
            t_fim = t_ini + 3.5
            
        # Limita duração máxima de linha para não prender na tela
        if t_fim - t_ini > 5.5:
            t_fim = t_ini + 5.0
            
        ini_str = formatar_tempo_ass(t_ini)
        fim_str = formatar_tempo_ass(t_fim)
        texto_ass = estilizar_linha_mugen(txt)
        
        eventos.append(f"Dialogue: 0,{ini_str},{fim_str},Default,,0,0,0,,{texto_ass}")
        
    conteudo_final = CABECALHO_ASS_MUGEN + "\n".join(eventos) + "\n"
    caminho_saida_ass.parent.mkdir(parents=True, exist_ok=True)
    caminho_saida_ass.write_text(conteudo_final, encoding="utf-8")
    print(f"[LEGENDAS MUGEN PRO] Gerado arquivo ASS com {len(eventos)} versos em: {caminho_saida_ass}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Uso: python legendas_mugen_pro.py <LETRA.txt> <saida.ass>")
        sys.exit(1)
    converter_letra_para_ass_mugen(Path(sys.argv[1]), Path(sys.argv[2]))
