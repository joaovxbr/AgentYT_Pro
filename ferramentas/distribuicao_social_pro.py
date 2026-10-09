#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
distribuicao_social_pro.py — Gerador Automático de Pacote Multiplataforma (Shorts/TikTok/Reels).
A partir de um projeto concluído:
1. Analisa a curva de energia do áudio para escolher automaticamente os 3 MELHORES momentos:
   - Gancho Inicial (0-30s)
   - O Drop do Refrão (momento de maior energia)
   - O Clímax Final
2. Invoca o módulo POV vertical (9:16) com legendas karaoke (\kf) para cada trecho.
3. Gera o arquivo 'social_pacote.json' contendo títulos magnéticos, copys e hashtags personalizadas
   para YouTube Shorts, TikTok e Instagram Reels.
"""
from pathlib import Path
import json
import librosa
import numpy as np

def encontrar_melhores_momentos(audio_path: str, duracao_trecho: float = 35.0) -> list[dict]:
    """
    Analisa o áudio musical e localiza os 3 trechos de maior retenção/impacto.
    """
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duracao_total = len(y) / sr

    # Energia RMS
    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    tempos = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

    # Janela deslizante
    frames_janela = int(duracao_trecho * sr / hop_length)
    if len(rms) <= frames_janela:
        return [{"nome": "Master Completo", "inicio": 0.0, "duracao": round(duracao_total, 2)}]

    energias_trechos = []
    passo = int(5.0 * sr / hop_length) # a cada 5s
    for i in range(0, len(rms) - frames_janela, passo):
        energia_media = np.mean(rms[i:i + frames_janela])
        t_inicio = tempos[i]
        energias_trechos.append((t_inicio, float(energia_media)))

    # 1. Gancho inicial (primeiros 40s)
    ganchos_iniciais = [e for e in energias_trechos if e[0] < 35.0]
    melhor_inicio = max(ganchos_iniciais, key=lambda x: x[1])[0] if ganchos_iniciais else 0.0

    # 2. Drop / Climax (maior energia global excluindo o início)
    resto = [e for e in energias_trechos if e[0] >= 35.0]
    melhor_drop = max(resto, key=lambda x: x[1])[0] if resto else 40.0

    # 3. Final / Clímax (último terço da música)
    terco_final = [e for e in energias_trechos if e[0] >= (duracao_total * 0.65)]
    melhor_final = max(terco_final, key=lambda x: x[1])[0] if terco_final else (duracao_total - duracao_trecho - 5.0)

    return [
        {"tipo": "gancho_intro", "inicio": round(float(melhor_inicio), 2), "duracao": duracao_trecho},
        {"tipo": "drop_refrao", "inicio": round(float(melhor_drop), 2), "duracao": duracao_trecho},
        {"tipo": "climax_final", "inicio": round(float(melhor_final), 2), "duracao": duracao_trecho}
    ]

def gerar_metadados_sociais(personagem: str, anime: str, musica: str) -> dict:
    """
    Gera copys, títulos e hashtags calibradas para alta retenção.
    """
    p_up = personagem.upper()
    return {
        "youtube_shorts": {
            "titulo": f"{p_up} MOSTROU POR QUE É O MAIS FORTE! 🔥 ({anime}) #Shorts #Anime",
            "descricao": f"A fúria de {personagem} em {anime}. Trecho da faixa '{musica}'.\n\nVídeo completo no canal @VXRaps!\n#VXRaps #{personagem.replace(' ', '')} #{anime.replace(' ', '')} #AnimeTrap"
        },
        "tiktok": {
            "legenda": f"O momento em que o {personagem} perdeu o controle... 💀 Qual seu personagem favorito de {anime}? Comenta aí! @VXRaps #anime #trapgeek #{anime.lower().replace(' ', '')} #{personagem.lower().replace(' ', '')} #amv"
        },
        "instagram_reels": {
            "legenda": f"Quando {personagem} entra na batalha, o fim é inevitável. 🔥\nFaixa: {musica} (VX RAPS)\nAssista ao clipe completo no YouTube!\n.\n.\n#animeedit #vxraps #animetrap #{anime.lower().replace(' ', '')} #{personagem.lower().replace(' ', '')}"
        }
    }

if __name__ == "__main__":
    import sys
    print("Módulo de distribuição social pronto.")


def pacote_lancamento(projeto_dir) -> dict:
    """Consolida o lancamento em saidas/pacote_lancamento.json (porta: estudio.py lancamento <slug>).

    Copy do video principal: projeto.json -> lancamento.{titulo,descricao,tags}; sem isso,
    modelo gerado do manifesto. Verifica que os arquivos existem e respeitam os limites
    do YouTube (thumb 1280x720 < 2 MB, titulo <= 100).
    """
    from PIL import Image
    projeto_dir = Path(projeto_dir)
    slug = projeto_dir.name
    m = json.loads((projeto_dir / "projeto.json").read_text(encoding="utf-8-sig"))
    saidas = projeto_dir / "saidas"
    pers = m.get("personagem", slug)
    anime = str(m.get("anime", "")).split("(")[0].strip()
    faixa = m.get("faixa", slug)
    lanc = m.get("lancamento") or {}
    titulo = lanc.get("titulo") or f"{pers.upper()} \u2013 {faixa} | Rap de {anime} | VX RAPS"
    tags = lanc.get("tags") or [pers, anime, "rap anime", "VX RAPS", faixa, "AMV", "trap geek"]
    descricao = lanc.get("descricao") or (
        f"\u201c{faixa}\u201d \u2014 rap inspirado em {pers} ({anime}).\n\n"
        f"\U0001F525 Se curtiu, deixa o like e se inscreve no canal.\n\U0001F3A7 VX RAPS\n\n"
        + " ".join("#" + "".join(ch for ch in t.title() if ch.isalnum()) for t in tags[:5]))
    master = projeto_dir / m.get("master", f"saidas/{slug}_master.mp4")
    thumb = saidas / f"{slug}_capa_ia.jpg"
    problemas = []
    if not master.is_file():
        problemas.append(f"master ausente: {master}")
    if thumb.is_file():
        with Image.open(thumb) as im:
            if im.size != (1280, 720):
                problemas.append(f"thumb {im.size} != 1280x720")
        if thumb.stat().st_size >= 2 * 1024 * 1024:
            problemas.append("thumb >= 2 MB")
    else:
        problemas.append(f"thumb ausente: {thumb}")
    if len(titulo) > 100:
        problemas.append("titulo > 100 caracteres")
    shorts = {}
    sp = saidas / "shorts" / "pacote.json"
    if sp.is_file():
        shorts = json.loads(sp.read_text(encoding="utf-8"))
    import compositor_master_gpu as comp
    import publicacao_doc
    intro_s = comp.inspecionar_midia(comp.INTRO_OFICIAL)[1]
    dur_master = comp.inspecionar_midia(master)[1] if master.is_file() else intro_s
    doc = publicacao_doc.gerar(projeto_dir, intro_s, dur_master, shorts)
    titulo, descricao, tags = doc["titulo_escolhido"], doc["descricao"], doc["tags"]
    problemas += doc["problemas"]
    pacote = {
        "slug": slug,
        "pronto": not problemas,
        "documento": "saidas/PUBLICACAO.md",
        "problemas": problemas,
        "video_principal": {"arquivo": str(master.relative_to(projeto_dir)).replace("\\", "/"),
                            "titulo": titulo, "titulos_ab": [t["titulo"] for t in doc["titulos"]],
                            "descricao": descricao, "tags": tags, "capitulos": doc["capitulos"],
                            "comentario_fixado": doc["comentario_fixado"],
                            "miniatura": str(thumb.relative_to(projeto_dir)).replace("\\", "/")},
        "artes": sorted(p.name for p in saidas.glob(f"{slug}_*.jpg")),
        "shorts": [{k: s[k] for k in ("arquivo", "titulo", "descricao", "tiktok") if k in s}
                   for s in shorts.get("shorts", [])],
        "publicar": [f"python ferramentas/publicar.py miniatura <VIDEO_ID> projetos/{slug}/"
                     + str(thumb.relative_to(projeto_dir)).replace("\\", "/")],
    }
    (saidas / "pacote_lancamento.json").write_text(json.dumps(pacote, indent=2, ensure_ascii=False),
                                                   encoding="utf-8")
    return pacote
