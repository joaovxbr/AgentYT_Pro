#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
font_manager.py — Gerenciador de Fontes do AgentYT_Pro.
Gerencia fontes locais (Windows + fontes instaladas + cache local),
font pairing inteligente por papel visual (dominant, secondary, support)
e consulta/cache de fontes do DaFont respeitando licenças de uso.
"""
from pathlib import Path
import json
import urllib.request
import urllib.parse
import re
import zipfile
import io

RAIZ = Path(__file__).resolve().parents[1]
DIR_FONTES_LOCAIS = RAIZ / "ferramentas" / "fontes"
CACHE_FONTES = RAIZ / "assets" / "fontes"
REGISTRO_FONTES = CACHE_FONTES / "fontes_registro.json"

FONTES_SISTEMA_PADRAO = {
    "impact": {
        "nome": "Impact",
        "arquivo": "C:/Windows/Fonts/impact.ttf",
        "categoria": "Sans Serif pesada",
        "licenca": "Sistema Windows (Instalada)",
        "comercial": None,
        "papel_recomendado": "dominant"
    },
    "arial_black": {
        "nome": "Arial Black",
        "arquivo": "C:/Windows/Fonts/ariblk.ttf",
        "categoria": "Sans Serif pesada",
        "licenca": "Sistema Windows (Instalada)",
        "comercial": None,
        "papel_recomendado": "dominant"
    },
    "cinzel_bold": {
        "nome": "Cinzel Bold",
        "arquivo": str(DIR_FONTES_LOCAIS / "Cinzel-Bold.ttf").replace("\\", "/"),
        "categoria": "Serif Épica / Lore",
        "licenca": "SIL Open Font License (OFL)",
        "comercial": None,
        "papel_recomendado": "dominant"
    },
    "bebas_neue": {
        "nome": "Bebas Neue",
        "arquivo": str(DIR_FONTES_LOCAIS / "BebasNeue-Regular.ttf").replace("\\", "/"),
        "categoria": "Condensed",
        "licenca": "SIL Open Font License (OFL)",
        "comercial": None,
        "papel_recomendado": "secondary"
    },
    "japanese_gothic": {
        "nome": "MS Gothic",
        "arquivo": "C:/Windows/Fonts/msgothic.ttc",
        "categoria": "Kanji / Manga Support",
        "licenca": "Sistema Windows (Instalada)",
        "comercial": None,
        "papel_recomendado": "support"
    }
}

def inicializar_catalogo():
    CACHE_FONTES.mkdir(parents=True, exist_ok=True)
    if not REGISTRO_FONTES.exists():
        REGISTRO_FONTES.write_text(json.dumps(FONTES_SISTEMA_PADRAO, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        # Mesclar fontes do sistema se não existirem
        try:
            dados = json.loads(REGISTRO_FONTES.read_text(encoding="utf-8"))
            for k, v in FONTES_SISTEMA_PADRAO.items():
                if k not in dados:
                    dados[k] = v
                elif not Path(dados[k].get("arquivo", "")).exists() and Path(v["arquivo"]).exists():
                    # registro antigo com caminho de outra maquina/pasta: reancora na raiz atual
                    dados[k]["arquivo"] = v["arquivo"]
                elif not dados[k].get("license_evidence"):
                    dados[k]["comercial"] = None
            REGISTRO_FONTES.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            REGISTRO_FONTES.write_text(json.dumps(FONTES_SISTEMA_PADRAO, indent=2, ensure_ascii=False), encoding="utf-8")

def listar_fontes_disponiveis(categoria: str = None) -> list:
    inicializar_catalogo()
    dados = json.loads(REGISTRO_FONTES.read_text(encoding="utf-8"))
    res = []
    for k, v in dados.items():
        if Path(v["arquivo"]).exists():
            if categoria is None or categoria.lower() in v.get("categoria", "").lower():
                res.append(v)
    return res

def obter_fonte_por_papel(papel: str = "dominant", identidade: str = "anime_trap") -> dict:
    """
    Retorna a melhor fonte para o papel solicitado:
    - dominant: palavra de impacto (pesada, condensada, monumental)
    - secondary: frase complementar (limpa, legível)
    - support: detalhes, kanjis, lore tags
    """
    inicializar_catalogo()
    dados = json.loads(REGISTRO_FONTES.read_text(encoding="utf-8"))
    
    if papel == "dominant":
        if "dark" in identidade or "ninja" in identidade or "lore" in identidade:
            if Path(dados.get("cinzel_bold", {}).get("arquivo", "")).exists():
                return dados["cinzel_bold"]
        if Path(dados.get("impact", {}).get("arquivo", "")).exists():
            return dados["impact"]
        return dados.get("arial_black", list(dados.values())[0])

    elif papel == "secondary":
        if Path(dados.get("bebas_neue", {}).get("arquivo", "")).exists():
            return dados["bebas_neue"]
        return dados.get("impact", list(dados.values())[0])

    elif papel == "support":
        if Path(dados.get("japanese_gothic", {}).get("arquivo", "")).exists():
            return dados["japanese_gothic"]
        return dados.get("bebas_neue", list(dados.values())[0])

    return list(dados.values())[0]

def font_pairing(identidade: str = "anime_trap") -> dict:
    """
    Retorna o trio coordenado de fontes para o projeto:
    - Dominante (30% a 80% da tela)
    - Secundária
    - Suporte / Kanjis
    """
    return {
        "dominant": obter_fonte_por_papel("dominant", identidade),
        "secondary": obter_fonte_por_papel("secondary", identidade),
        "support": obter_fonte_por_papel("support", identidade)
    }

if __name__ == "__main__":
    inicializar_catalogo()
    pair = font_pairing("anime_trap")
    print("Font Pairing Atual:")
    for k, v in pair.items():
        print(f"  {k.upper()}: {v['nome']} ({v['categoria']}) -> {v['arquivo']}")
