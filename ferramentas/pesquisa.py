#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pesquisa.py — ferramenta de PESQUISA DE CONTEUDO para o canal VX RAPS.

Analisa o que esta funcionando no nicho de anime rap/AMV para guiar decisoes
de conteudo: qual personagem, qual anime, qual tema.

Comandos:
    python pesquisa.py tendencias                   # o que esta em alta no nicho
    python pesquisa.py concorrentes [CANAL_ID]       # analisa canais concorrentes
    python pesquisa.py personagem NOME               # pesquisa sobre um personagem
    python pesquisa.py avaliar <slug>                 # avalia o projeto atual vs tendencias
    python pesquisa.py relatorio                      # relatorio completo de pesquisa

Dados de entrada: busca web (yt-dlp --flat-playlist, trending) + projeto.json.
Saida: relatorio em texto com scores e recomendacoes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"
sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------------------
# Canais de referencia do nicho (anime rap / AMV / geek)
# ---------------------------------------------------------------------------

CANAIS_NICHO = [
    {"nome": "CellBit", "id": "UC02wQ_C5kYbTJ6FyN91cRgQ", "genero": "rap geek"},
    {"nome": "7 Minutoz", "id": "UC0n9xzCOzZVowhE3ZoNnm4w", "genero": "rap geek"},
    {"nome": "Enaldinho", "id": "UCG6APUsS6eOzd1mS8MKyPYg", "genero": "anime/youtube"},
    {"nome": "Igor 3K", "id": "UCY9V2L8n6Z9qT7uN6Q3mY5g", "genero": "rap geek"},
    {"nome": "Bolacha", "id": "UC0Oz8nHgq2wD5dS5t3pR5BQ", "genero": "rap geek"},
    {"nome": "VX RAPS (nos)", "id": "", "genero": "rap geek AMV"},
]

# Personagens com mais potencial visual para AMV (baseado em tendencia)
PERSONAGENS_TRENDING = {
    "one_piece": [
        "Luffy", "Shanks", "Zoro", "Nami", "Sanji", "Kaido", "Big Mom",
        "Blackbeard", "Law", "Kid", "Yamato", "Ace", "Robin",
    ],
    "jujutsu_kaisen": [
        "Gojo", "Sukuna", "Itadori", "Megumi", "Nobara", "Todo",
        "Toji", "Nanami", "Yuta", "Maki",
    ],
    "demon_slayer": [
        "Tanjiro", "Zenitsu", "Inosuke", "Rengoku", "Akaza", "Muzan",
        "Giyu", "Shinobu", "Mitsuri", "Tengen",
    ],
    "attack_on_titan": [
        "Eren", "Levi", "Mikasa", "Armin", "Reiner", "Annie",
        "Zeke", "Erwin", "Hange", "Historia",
    ],
    "naruto": [
        "Naruto", "Sasuke", "Sakura", "Kakashi", "Madara", "Itachi",
        "Pain", "Obito", "Minato", "Hashirama",
    ],
    "chainsaw_man": [
        "Denji", "Makima", "Power", "Aki", "Reze", "Quanxi",
        "Aldo", "Beam", "Violence", "Darkness",
    ],
    "solo_leveling": [
        "Sung Jin-Woo", "Cha Hae-In", "Thomas Andre", "Goto",
        "Igris", "Beru", "Kargalgan",
    ],
    "hunter_x_hunter": [
        "Gon", "Killua", "Kurapika", "Leorio", "Hisoka", "Chrollo",
        "Meruem", "Netero", "Illumi", "Feitan",
    ],
}

# Temas que mais performam (combinacoes de titulo que pegam)
TEMAS_ALTA = [
    "haki", "dominio", "poder", "vinganca", "traição",
    "forma final", "transformação", "raiva", "despertar",
    "top 10", "morte", "lenda", "rei", "rei supremo",
    "frase icônica", "melhor cena", "cena épica",
    "vs", "batalha", "final boss",
]


# ---------------------------------------------------------------------------
# YtDlp helpers
# ---------------------------------------------------------------------------

def _ytdlp_bin() -> str:
    import shutil
    return shutil.which("yt-dlp") or "yt-dlp"


def _ytdlp_flat(url: str, max_results: int = 15) -> list[dict]:
    """Roda yt-dlp --flat-playlist e devolve lista de metadados basicos."""
    cmd = [
        _ytdlp_bin(), "--flat-playlist", "--dump-json",
        "--playlist-end", str(max_results),
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        resultados = []
        for linha in r.stdout.strip().splitlines():
            if not linha.strip():
                continue
            try:
                resultados.append(json.loads(linha))
            except json.JSONDecodeError:
                continue
        return resultados
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _ytdlp_info(url: str) -> Optional[dict]:
    """Metadados detalhados de um unico video."""
    cmd = [_ytdlp_bin(), "--dump-json", "--no-download", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip().splitlines()[0])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


# ---------------------------------------------------------------------------
# Analise de tendencias
# ---------------------------------------------------------------------------

@dataclass
class Tendencia:
    termo: str
    fonte: str
    rank: int
    motivo: str


def tendencias_nicho() -> List[Tendencia]:
    """Busca videos recentes dos canais de referencia e extrai temas quentes."""
    tendencias: List[Tendencia] = []
    # busca por "rap geek 2026" e "AMV edit" no YouTube
    queries = [
        "site:youtube.com rap geek 2026",
        "site:youtube.com anime edit AMV 2026",
        "site:youtube.com one piece rap",
        "site:youtube.com jujutsu kaisen edit",
    ]
    for q in queries:
        url = f"ytsearch10:{q.replace('site:youtube.com ', '')}"
        videos = _ytdlp_flat(url, max_results=10)
        for i, v in enumerate(videos):
            titulo = (v.get("title") or "").lower()
            canal = (v.get("channel") or v.get("uploader") or "").lower()
            views = v.get("view_count") or 0
            # extrair personagens/temas do titulo
            for anime, personagens in PERSONAGENS_TRENDING.items():
                for p in personagens:
                    if p.lower() in titulo:
                        tendencias.append(Tendencia(
                            termo=p, fonte=f"youtube/{canal[:20]}",
                            rank=i + 1,
                            motivo=f"video '{v.get('title', '')[:50]}' com {views} views",
                        ))
            # temas genericos
            for tema in TEMAS_ALTA:
                if tema in titulo:
                    tendencias.append(Tendencia(
                        termo=tema, fonte=f"youtube/{canal[:20]}",
                        rank=i + 1,
                        motivo=f"video '{v.get('title', '')[:50]}' com {views} views",
                    ))
    return tendencias


def _score_tendencia(termo: str, tendencias: List[Tendencia]) -> int:
    """Conta quantas vezes um termo aparece nas tendencias (0-100)."""
    hits = sum(1 for t in tendencias if t.termo.lower() == termo.lower())
    return min(hits * 15, 100)


# ---------------------------------------------------------------------------
# Analise de concorrentes
# ---------------------------------------------------------------------------

@dataclass
class AnaliseConcorrente:
    canal: str
    genero: str
    n_videos: int
    views_medias: float
    temas_frequentes: List[str]
    estilo: str


def analisar_concorrentes(Canal_id: str = None) -> List[AnaliseConcorrente]:
    """Analisa canais de referencia do nicho."""
    canais = CANAIS_NICHO
    if Canal_id:
        canais = [c for c in canais if Canal_id in c.get("id", "")]
        if not canais:
            canais = CANAIS_NICHO

    resultados = []
    for canal in canais[:5]:  # limita a 5 para nao demorar
        url = f"https://www.youtube.com/@{canal['nome'].replace(' ', '')}/videos"
        videos = _ytdlp_flat(url, max_results=10)
        if not videos:
            continue
        views = [v.get("view_count") or 0 for v in videos]
        views_medias = sum(views) / max(len(views), 1)
        # temas frequentes nos titulos
        todos_titulos = " ".join((v.get("title") or "").lower() for v in videos)
        temas = []
        for t in TEMAS_ALTA + ["one piece", "jujutsu", "demon slayer",
                                "naruto", "attack on titan", "chainsaw man",
                                "solo leveling", "hunter x hunter"]:
            if t in todos_titulos:
                temas.append(t)
        resultados.append(AnaliseConcorrente(
            canal=canal["nome"], genero=canal["genero"],
            n_videos=len(videos), views_medias=round(views_medias),
            temas_frequentes=temas[:5],
            estilo="rap geek AMV",
        ))
    return resultados


# ---------------------------------------------------------------------------
# Analise de personagem
# ---------------------------------------------------------------------------

@dataclass
class RelatorioPersonagem:
    nome: str
    anime: str
    score_tendencia: int  # 0-100
    tem_amv: bool
    videos_encontrados: int
    views_medias: float
    cor_sugerida: str
    temas_sugeridos: List[str]


# cores por personagem/tema
CORES_PERSONAGEM = {
    "luffy": "#FFD700", "shanks": "#CC0000", "zoro": "#00CC66",
    "gojo": "#4169E1", "sukuna": "#CC0066", "itadori": "#FF4500",
    "tanjiro": "#00AA00", "zenitsu": "#FFD700", "inosuke": "#4682B4",
    "rengoku": "#FF4500", "akaza": "#CC00CC",
    "eren": "#006400", "levi": "#2F4F4F", "mikasa": "#B22222",
    "naruto": "#FF8C00", "sasuke": "#6A0DAD", "itachi": "#8B0000",
    "madara": "#800080", "pain": "#C71585",
    "denji": "#DC143C", "makima": "#FFD700", "power": "#FF69B4",
    "sung jin-woo": "#4B0082", "igris": "#B22222",
    "gon": "#228B22", "killua": "#191970", "hisoka": "#FF1493",
}


def pesquisar_personagem(nome: str) -> RelatorioPersonagem:
    """Pesquisa um personagem no YouTube e retorna analise."""
    # descobrir anime
    anime = ""
    for a, ps in PERSONAGENS_TRENDING.items():
        for p in ps:
            if p.lower() == nome.lower():
                anime = a.replace("_", " ").title()
                break
        if anime:
            break

    url = f"ytsearch15:{nome} anime edit AMV"
    videos = _ytdlp_flat(url, max_results=15)
    views = [v.get("view_count") or 0 for v in videos]
    views_medias = sum(views) / max(len(views), 1)

    # cor sugerida
    cor = CORES_PERSONAGEM.get(nome.lower(), "#00F0A0")

    # temas sugeridos
    temas = []
    for v in videos[:10]:
        titulo = (v.get("title") or "").lower()
        for t in TEMAS_ALTA:
            if t in titulo and t not in temas:
                temas.append(t)

    # score de tendencia derivado da propria busca: volume de AMVs + views
    # medias. Evita uma segunda chamada de rede so para pontuar.
    score = min(len(videos) * 5, 60) + min(int(views_medias / 100_000) * 8, 40)
    score_tendencia = min(score, 100)

    return RelatorioPersonagem(
        nome=nome, anime=anime,
        score_tendencia=score_tendencia,
        tem_amv=len(videos) > 3,
        videos_encontrados=len(videos),
        views_medias=round(views_medias),
        cor_sugerida=cor,
        temas_sugeridos=temas[:5],
    )


# ---------------------------------------------------------------------------
# Avaliacao de projeto vs tendencias
# ---------------------------------------------------------------------------

@dataclass
class RelatorioAvaliacao:
    slug: str
    score_conteudo: int  # 0-100
    score_visual: int    # 0-100
    score_titulo: int    # 0-100
    score_geral: int     # 0-100
    pontos_fortes: List[str]
    pontos_fracos: List[str]
    recomendacoes: List[str]


def avaliar_projeto(slug: str) -> RelatorioAvaliacao:
    """Avalia um projeto existente contra as tendencias do nicho."""
    from estudio import carregar_manifesto, dir_projeto
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)

    pontos_fortes = []
    pontos_fracos = []
    recomendacoes = []

    # 1. Score de conteudo (personagem + anime)
    personagem = m.get("personagem", "")
    anime = m.get("anime", "")
    score_conteudo = 50  # base

    for a, ps in PERSONAGENS_TRENDING.items():
        if a.replace("_", " ") in anime.lower():
            if personagem.lower() in [p.lower() for p in ps]:
                score_conteudo += 30  # personagem do anime certo
                pontos_fortes.append(f"{personagem} ({anime}) esta no radar do nicho")
            else:
                score_conteudo += 10
                recomendacoes.append(f"Considere personagens mais icônicos de {anime}")
            break

    # 2. Score visual (tem frame, tem cor, tem titulo)
    score_visual = 0
    arte = m.get("arte", {})
    if arte.get("frame_capa"):
        score_visual += 30
    if arte.get("frame_banner"):
        score_visual += 20
    if m.get("cor", {}).get("destaque"):
        score_visual += 25
        pontos_fortes.append(f"Cor de destaque definida: {m['cor']['destaque']}")
    else:
        pontos_fracos.append("Sem cor de destaque definida")
        recomendacoes.append("Defina uma cor de destaque no manifesto")

    # 3. Score de titulo
    score_titulo = 0
    titulo_linhas = m.get("titulo_linhas", [])
    if titulo_linhas:
        titulo_completo = " ".join(titulo_linhas).lower()
        score_titulo += 30
        # verificar se tem palavras de alta
        for tema in TEMAS_ALTA[:10]:
            if tema in titulo_completo:
                score_titulo += 15
                pontos_fortes.append(f"Titulo usa tema quente: '{tema}'")
                break
        if len(titulo_linhas) <= 3:
            score_titulo += 20
            pontos_fortes.append("Titulo curto e direto")
        else:
            recomendacoes.append("Titulo pode ser mais curto (max 3 linhas)")
    else:
        pontos_fracos.append("Sem titulo definido")
        recomendacoes.append("Adicione titulo_linhas ao manifesto")

    # 4. Score geral
    score_geral = round(score_conteudo * 0.35 + score_visual * 0.35 + score_titulo * 0.30)

    # recomendacoes gerais
    if not m.get("cortes"):
        recomendacoes.append("Adicione cortes para TikTok/Shorts (duplica alcance)")
    if not m.get("master"):
        recomendacoes.append("Registre o master no manifesto")
    if not pontos_fortes:
        pontos_fortes.append("Projeto em andamento")

    return RelatorioAvaliacao(
        slug=slug, score_conteudo=min(score_conteudo, 100),
        score_visual=min(score_visual, 100),
        score_titulo=min(score_titulo, 100),
        score_geral=min(score_geral, 100),
        pontos_fortes=pontos_fortes,
        pontos_fracos=pontos_fracos,
        recomendacoes=recomendacoes,
    )


# ---------------------------------------------------------------------------
# Relatorio completo
# ---------------------------------------------------------------------------

def gerar_relatorio() -> str:
    """Gera relatorio completo de pesquisa do nicho."""
    linhas = ["=" * 60, "RELATORIO DE PESQUISA — VX RAPS", "=" * 60, ""]

    # Tendencias
    linhas.append("--- TENDENCIAS DO NICHO ---")
    tendencias = tendencias_nicho()
    if tendencias:
        # agrupar por termo
        contagem: dict[str, int] = {}
        for t in tendencias:
            contagem[t.termo] = contagem.get(t.termo, 0) + 1
        for termo, cnt in sorted(contagem.items(), key=lambda x: -x[1])[:10]:
            linhas.append(f"  {termo:25s}  x{cnt} menções")
    else:
        linhas.append("  (nenhum resultado — sem internet ou limite atingido)")
    linhas.append("")

    # Concorrentes
    linhas.append("--- CONCORRENTES ---")
    concorrentes = analisar_concorrentes()
    for c in concorrentes:
        linhas.append(f"  {c.canal:20s}  views_media={c.views_medias:>10}  "
                      f"temas={', '.join(c.temas_frequentes[:3])}")
    linhas.append("")

    # Projetos existentes
    linhas.append("--- PROJETOS EXISTENTES ---")
    projetos = sorted(p.parent for p in PROJETOS.glob("*/projeto.json"))
    for d in projetos:
        try:
            m = json.loads((d / "projeto.json").read_text(encoding="utf-8"))
            pub = m.get("publicado", {}).get("estado", "nao")
            linhas.append(f"  {d.name:25s}  {m.get('personagem','?'):15s}  "
                          f"{m.get('anime','?'):20s}  pub={pub}")
        except Exception:
            linhas.append(f"  {d.name:25s}  (manifesto ilegivel)")
    linhas.append("")

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pesquisa.py")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tendencias")
    sub.add_parser("concorrentes")
    pm = sub.add_parser("personagem")
    pm.add_argument("nome")
    av = sub.add_parser("avaliar")
    av.add_argument("slug")
    sub.add_parser("relatorio")

    a = p.parse_args(argv)
    if not a.cmd:
        print(__doc__)
        return 0

    if a.cmd == "tendencias":
        tendencias = tendencias_nicho()
        if not tendencias:
            print("Nenhuma tendencia encontrada (sem internet?)")
            return 1
        contagem = {}
        for t in tendencias:
            contagem.setdefault(t.termo, []).append(t)
        print("== tendencias do nicho ==")
        for termo, lista in sorted(contagem.items(), key=lambda x: -len(x[1]))[:15]:
            print(f"  {termo:25s}  x{len(lista)}  (ex: {lista[0].motivo[:60]})")
        return 0

    if a.cmd == "concorrentes":
        concorrentes = analisar_concorrentes()
        print("== concorrentes do nicho ==")
        for c in concorrentes:
            print(f"\n  {c.canal} ({c.genero})")
            print(f"    videos analisados: {c.n_videos}")
            print(f"    views media: {c.views_medias}")
            print(f"    temas: {', '.join(c.temas_frequentes)}")
        return 0

    if a.cmd == "personagem":
        rel = pesquisar_personagem(a.nome)
        print(f"== personagem: {rel.nome} ==")
        print(f"  anime: {rel.anime or '?'}")
        print(f"  videos encontrados: {rel.videos_encontrados}")
        print(f"  views media: {rel.views_medias}")
        print(f"  cor sugerida: {rel.cor_sugerida}")
        print(f"  temas: {', '.join(rel.temas_sugeridos)}")
        if not rel.tem_amv:
            print("  ⚠️ Poucos AMVs encontrados — personagem pode ter baixa demanda visual")
        return 0

    if a.cmd == "avaliar":
        rel = avaliar_projeto(a.slug)
        print(f"== avaliacao: {rel.slug} ==")
        print(f"  conteudo:  {rel.score_conteudo}/100")
        print(f"  visual:    {rel.score_visual}/100")
        print(f"  titulo:    {rel.score_titulo}/100")
        print(f"  GERAL:     {rel.score_geral}/100")
        if rel.pontos_fortes:
            print("\n  Pontos fortes:")
            for pf in rel.pontos_fortes:
                print(f"    + {pf}")
        if rel.pontos_fracos:
            print("\n  Pontos fracos:")
            for pf in rel.pontos_fracos:
                print(f"    - {pf}")
        if rel.recomendacoes:
            print("\n  Recomendacoes:")
            for r in rel.recomendacoes:
                print(f"    -> {r}")
        return 0

    if a.cmd == "relatorio":
        print(gerar_relatorio())
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
