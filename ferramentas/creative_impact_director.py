#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
creative_impact_director.py — Diretor Criativo Autônomo de Cenas de Impacto e Tipografia Cinética.
Analisa a letra, energia sonora (stems e picos de 808/transientes), estrutura de versos e punchlines
para planejar organicamente cenas de impacto (0.3s a 4.0s) intercaladas na timeline,
evitando monotonia e aplicando rigoroso controle de variedade (memória temporal anti-repetição).
"""
import json
import re
from pathlib import Path
from collections import deque
from style_preset_engine import candidatos_semanticos, normalizar

TIPOS_CENA = [
    "TYPE_CHARACTER_BEHIND",  # Texto monumental atrás do personagem recortado
    "TYPE_BIG_IMPACT",        # Palavra gigante central com zoom punch e kanjis
    "TYPE_SPLIT",             # Frase quebrada em 2 ou 3 linhas assimétricas
    "TYPE_REPEATED",          # Palavra repetida no background em baixa opacidade
    "TYPE_GLOW",              # Neon glow emissivo vibrante com cores de lore
    "TYPE_RGB_SPLIT",         # Aberração cromática com distorção de impacto
    "TYPE_MINIMAL_HEAVY"      # Tipografia brutalista preto/branco alto contraste
]

BACKGROUNDS = [
    "dark_radial",
    "speedlines_manga",
    "manga_halftone",
    "grunge_black",
    "scene_blurred"
]

ANIMATION_PRESETS = [
    "scale_punch",    # 1.35x -> 1.0x com overshoot
    "slam_hit",       # queda rápida com shake
    "rgb_glitch_pop", # aberração cromática no primeiro frame
    "slide_reveal"    # slide rápido lateral
]

PALAVRAS_CHAVE_IMPACTO = [
    # Termos de poder / lore / impacto
    r"\bvingan[çc]a\b", r"\bvingador\b", r"\bsharingan\b", r"\brinnegan\b", r"\bchidori\b",
    r"\bkirin\b", r"\bsusanoo\b", r"\bmorte\b", r"\bmorrer\b", r"\bmonarca\b", r"\btit[ãa]\b",
    r"\bdestrui[çc][ãa]o\b", r"\bdestruidor\b", r"\bpoder\b", r"\bodio\b", r"\bfogo\b",
    r"\bchamas\b", r"\bsangue\b", r"\bliberdade\b", r"\btatakae\b", r"\barise\b", r"\bdeus\b"
]

def identificar_palavra_dominante(frase: str) -> dict:
    """
    Identifica a PRIMARY WORD (dominante), SECONDARY WORDS e SUPPORT TEXT na frase.
    """
    palavras = frase.strip().split()
    if not palavras:
        return {"primary": "", "secondary": "", "support": ""}

    # 1. Procurar por palavra de impacto de lore
    for p in palavras:
        p_clean = normalizar(re.sub(r"[^\w]", "", p))
        if candidatos_semanticos(p_clean):
            sec = " ".join([w for w in palavras if w != p])
            return {"primary": p.upper(), "secondary": sec.upper(), "support": "TRAP GEEK"}
        for pat in PALAVRAS_CHAVE_IMPACTO:
            if re.search(pat, p_clean):
                sec = " ".join([w for w in palavras if w != p])
                return {"primary": p.upper(), "secondary": sec.upper(), "support": "TRAP GEEK"}

    # 2. Se não achou na lore, pegar a palavra mais longa ou a última palavra (punchline)
    palavra_longa = max(palavras, key=lambda w: len(re.sub(r"[^\w]", "", w)))
    sec = " ".join([w for w in palavras if w != palavra_longa])
    return {
        "primary": palavra_longa.upper(),
        "secondary": sec.upper(),
        "support": "VX RAPS"
    }

class CreativeDirector:
    def __init__(self, projeto_dir: Path):
        self.projeto_dir = projeto_dir
        self.memoria_estilos = deque(maxlen=6) # Lembra os últimos 6 estilos para penalizar repetição
        self.memoria_bg = deque(maxlen=4)

    def planejar_cenas_impacto(self, max_cenas: int = 8) -> list:
        """
        Analisa a transcrição e seleciona os momentos que verdadeiramente
        merecem uma cena especial/gráfica de impacto (0.5s a 3.0s).
        """
        transc_file = self.projeto_dir / "entradas" / "transcricao.json"
        if not transc_file.exists():
            return []

        dados_raw = json.loads(transc_file.read_text(encoding="utf-8"))
        # Se for dicionário com lista de 'words', agrupar em frases por pausas
        words = dados_raw.get("words", []) if isinstance(dados_raw, dict) else dados_raw
        
        # Agrupar palavras em frases (pausa > 0.5s ou quebra de fluxo)
        frases = []
        frase_atual = []
        for w in words:
            if not frase_atual:
                frase_atual.append(w)
            else:
                if w.get("start", 0) - frase_atual[-1].get("end", 0) > 0.45 or len(frase_atual) >= 6:
                    frases.append({
                        "text": " ".join([x.get("word", "") for x in frase_atual]),
                        "start": frase_atual[0].get("start", 0),
                        "end": frase_atual[-1].get("end", 0)
                    })
                    frase_atual = [w]
                else:
                    frase_atual.append(w)
        if frase_atual:
            frases.append({
                "text": " ".join([x.get("word", "") for x in frase_atual]),
                "start": frase_atual[0].get("start", 0),
                "end": frase_atual[-1].get("end", 0)
            })

        cenas_planejadas = []

        for verso in frases:
            texto = verso.get("text", "").strip()
            ini = verso.get("start", 0.0)
            fim = verso.get("end", 0.0)
            dur = fim - ini

            # Avaliar se a frase contém uma palavra com peso de impacto
            hierarquia = identificar_palavra_dominante(texto)
            p_dom = hierarquia["primary"]

            eh_impacto = bool(candidatos_semanticos(p_dom))
            for pat in PALAVRAS_CHAVE_IMPACTO:
                if re.search(pat, p_dom.lower()):
                    eh_impacto = True
                    break

            if eh_impacto and dur >= 1.0:
                # Escolher estilo visual penalizando repetição recente
                estilo_escolhido = None
                for st in TIPOS_CENA:
                    if st not in self.memoria_estilos:
                        estilo_escolhido = st
                        break
                if not estilo_escolhido:
                    estilo_escolhido = TIPOS_CENA[len(cenas_planejadas) % len(TIPOS_CENA)]

                self.memoria_estilos.append(estilo_escolhido)

                # Escolher background alternado
                bg_escolhido = None
                for bg in BACKGROUNDS:
                    if bg not in self.memoria_bg:
                        bg_escolhido = bg
                        break
                if not bg_escolhido:
                    bg_escolhido = BACKGROUNDS[len(cenas_planejadas) % len(BACKGROUNDS)]
                self.memoria_bg.append(bg_escolhido)

                # Definir duração ideal do impacto (entre 0.8s e 2.5s)
                dur_cena = min(2.5, max(0.8, dur * 0.75))

                cena_spec = {
                    "id": f"impact_{len(cenas_planejadas)+1:02d}",
                    "tempo_inicio": round(ini, 2),
                    "duracao": round(dur_cena, 2),
                    "tipo_cena": estilo_escolhido,
                    "keyword_dominante": p_dom,
                    "texto_secundario": hierarquia["secondary"],
                    "suporte": hierarquia["support"],
                    "background": bg_escolhido,
                    "animacao": ANIMATION_PRESETS[len(cenas_planejadas) % len(ANIMATION_PRESETS)],
                    "transicao_in": "flash_zoom",
                    "transicao_out": "motion_blur",
                    "font_pairing": {
                        "dominant": "Impact",
                        "secondary": "Bebas Neue",
                        "support": "MS Gothic"
                    }
                }
                cenas_planejadas.append(cena_spec)
                if len(cenas_planejadas) >= max_cenas:
                    break

        return cenas_planejadas

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("Uso: python creative_impact_director.py <slug>")
    p = Path(__file__).resolve().parents[1] / "projetos" / sys.argv[1]
    cd = CreativeDirector(p)
    cenas = cd.planejar_cenas_impacto(6)
    print(f"Diretor Criativo planejou {len(cenas)} cenas de impacto:")
    print(json.dumps(cenas, indent=2, ensure_ascii=False))
