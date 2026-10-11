#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""entrega.py — PACOTE DE ENTREGA completo de uma musica (regra: nunca entregar so o video).

Portas:
    estudio.py promover <slug> <run_id>   # candidato aprovado pelo usuario -> master (com backup)
    estudio.py entrega  <slug>            # gera o que falta e confere TUDO; 'pronto' so se nada faltar

O pacote (cerebro/entrega.md) e sempre:
  1. video completo (master promovido)            5. comentario fixado
  2. thumbnail 1280x720 < 2 MB                     6. Shorts (MP4 9:16)
  3. titulo(s) + descricao + tags + capitulos      7. titulo/descricao/legenda TikTok de cada Short
  4. artes extras (banner do canal, capa 3000 px)  8. saidas/ENTREGA.md com tudo pronto para copiar
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"

ITENS = [
    ("master", "Vídeo completo (master promovido)"),
    ("thumb", "Thumbnail YouTube 1280x720 < 2 MB"),
    ("titulo", "Título do vídeo (≤ 100)"),
    ("descricao", "Descrição (≤ 5000, com capítulos)"),
    ("tags", "Tags (≤ 500 caracteres)"),
    ("capitulos", "Capítulos (≥ 3, 1º em 0:00)"),
    ("comentario", "Comentário fixado"),
    ("shorts", "Shorts 9:16 (MP4)"),
    ("shorts_textos", "Título, descrição e legenda TikTok de cada Short"),
    ("artes_extras", "Banner do canal + capa 3000 px"),
]

# Dois nomes para a MESMA miniatura 1280x720, cada um escrito por uma porta diferente:
#   estudio.py capa      -> <slug>_capa_youtube.jpg   (artes_base.compor_capa_youtube)
#   estudio.py artes-ia  -> <slug>_capa_ia.jpg        (gerador_artes_ia, ComfyUI)
# Antes cada consumidor cravava um nome: quem tinha a capa pronta mas rodou so a porta
# `capa` era reprovado com "thumb ausente", e o lancamento publicava um caminho que nao
# existia. Um resolvedor so, na ordem canonica: primeiro o nome que o pacote sempre usou,
# depois o nome novo. Tamanho e peso continuam sendo conferidos depois (nao afrouxa nada).
NOMES_THUMB = ("{slug}_capa_ia.jpg", "{slug}_capa_youtube.jpg")


def _thumb(d: Path) -> Path:
    """Caminho da miniatura deste projeto (existe um dos nomes aceitos).

    Sem arquivo nenhum, devolve o nome canonico (`_capa_ia.jpg`) para que a mensagem de
    erro e o `publicar.py miniatura` continuem apontando o lugar esperado.
    """
    d, slug = Path(d), Path(d).name
    saidas = d / "saidas"
    for modelo in NOMES_THUMB:
        p = saidas / modelo.format(slug=slug)
        if p.is_file():
            return p
    return saidas / NOMES_THUMB[0].format(slug=slug)



def _json(p: Path, padrao=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return padrao


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()[:16]


def promover(slug: str, run_id: str) -> dict:
    """Copia o candidato aprovado da esteira para o master do manifesto.
    O master anterior (se houver) vai para backups/masters/. Registro em qa/promocoes.json."""
    d = PROJETOS / slug
    m = _json(d / "projeto.json", {}) or {}
    exe = _json(d / "qa" / "esteira" / run_id / "execucao.json", {}) or {}
    if exe.get("status") != "aprovado_qa_automatico":
        raise ValueError(f"execucao {run_id} nao esta aprovada no QA automatico (status={exe.get('status')})")
    candidato = Path(exe.get("saida") or d / "saidas" / "esteira" / run_id / f"{slug}_master_final_com_intro.mp4")
    if not candidato.is_file():
        raise FileNotFoundError(candidato)
    rel_master = m.get("master") or f"saidas/{slug}_master.mp4"
    master = d / rel_master
    master.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if master.is_file():
        bdir = d / "backups" / "masters"
        bdir.mkdir(parents=True, exist_ok=True)
        backup = bdir / f"{master.stem}_{datetime.now():%Y%m%dT%H%M%S}{master.suffix}"
        shutil.copy2(master, backup)
    shutil.copy2(candidato, master)
    # Se o manifesto estava sem master definido, atualiza para o master promovido
    if not m.get("master"):
        m["master"] = str(master.relative_to(d)).replace("\\", "/")
        (d / "projeto.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    reg = {"quando": datetime.now().isoformat(timespec="seconds"), "run_id": run_id,
           "candidato": str(candidato), "master": str(master.relative_to(d)), "sha": _sha(master),
           "backup_anterior": str(backup.relative_to(d)) if backup else None}
    hist = _json(d / "qa" / "promocoes.json", []) or []
    hist.append(reg)
    (d / "qa" / "promocoes.json").write_text(json.dumps(hist, indent=2, ensure_ascii=False), encoding="utf-8")
    return reg


def conferir(d: Path, pacote: dict | None) -> dict[str, str]:
    """Checklist puro: item -> '' (ok) ou motivo do que falta."""
    from PIL import Image
    d = Path(d)
    slug = d.name
    m = _json(d / "projeto.json", {}) or {}
    saidas = d / "saidas"
    falta: dict[str, str] = {}
    rel_master = m.get("master") or f"saidas/{slug}_master.mp4"
    master = d / rel_master
    falta["master"] = "" if master.is_file() else f"master ausente ({master.relative_to(d)}): rode estudio.py promover"
    thumb = _thumb(d)
    if not thumb.is_file():
        falta["thumb"] = "thumb ausente: estudio.py artes-ia"
    else:
        with Image.open(thumb) as im:
            tam = im.size
        falta["thumb"] = "" if tam == (1280, 720) and thumb.stat().st_size < 2 * 1024 * 1024 else \
            f"thumb fora do padrao ({tam}, {thumb.stat().st_size // 1024} KB)"
    vp = (pacote or {}).get("video_principal") or {}
    titulo = vp.get("titulo") or ""
    falta["titulo"] = "" if 0 < len(titulo) <= 100 else "titulo vazio ou > 100"
    desc = vp.get("descricao") or ""
    falta["descricao"] = "" if 0 < len(desc) <= 5000 else "descricao vazia ou > 5000"
    tags = vp.get("tags") or []
    falta["tags"] = "" if tags and sum(len(t) for t in tags) + len(tags) - 1 <= 500 else "tags vazias ou > 500"
    caps = vp.get("capitulos") or []
    falta["capitulos"] = "" if len(caps) >= 3 and float(caps[0].get("t", 1)) == 0 else "menos de 3 capitulos ou 1o != 0:00"
    falta["comentario"] = "" if vp.get("comentario_fixado") else "comentario fixado vazio"
    sp = _json(saidas / "shorts" / "pacote.json", {}) or {}
    lista = sp.get("shorts") or []
    arquivos = [saidas / "shorts" / s.get("arquivo", "") for s in lista]
    falta["shorts"] = "" if lista and all(a.is_file() for a in arquivos) else "shorts ausentes: estudio.py shorts"
    falta["shorts_textos"] = "" if lista and all(s.get("titulo") and s.get("descricao") and s.get("tiktok")
                                                 for s in lista) else "texto de short faltando"
    extras = [saidas / f"{slug}_banner_canal.jpg", saidas / f"{slug}_capa_streaming_3000.jpg"]
    falta["artes_extras"] = "" if all(p.is_file() for p in extras) else "banner/capa 3000 ausentes: estudio.py artes-ia"
    return falta


def _desatualizado(arquivo: Path, referencia: Path) -> bool:
    return not arquivo.is_file() or (referencia.is_file() and arquivo.stat().st_mtime < referencia.stat().st_mtime)


def _rodar_folha(slug: str, master: Path, log: list[str]) -> None:
    """Folha por quadro do master, so se ela estiver velha. Diagnostico: nunca derruba a entrega.

    E o QA visual que os porteiros nao cobrem (motion escrevendo a linha errada, take
    escondendo a legenda, cartao duplicado). Varre TODOS os quadros e escreve uma folha por
    take de motion. O pedido para rodar sempre mora aqui, na porta da entrega.
    """
    destino = PROJETOS / slug / "qa" / "folha_por_quadro" / f"{slug}_folha.csv"
    if not _desatualizado(destino, master):
        return
    print("  [entrega] folha por quadro do master (TODOS os quadros)...", flush=True)
    try:
        import folha_por_quadro as fq
        res = fq.auditar(slug)
        log.append(f"folha por quadro: {res['amostras']} quadros, {len(res['folhas'])} folhas, "
                   f"achados {sorted(res['cobertura']) or 'nenhum'}")
    except Exception as exc:
        log.append(f"AVISO: folha por quadro nao rodou ({exc})")


def executar(slug: str, n_shorts: int = 3, forcar_artes: bool = False) -> dict:
    """Gera o que falta (ou ficou mais velho que o master) e confere o pacote inteiro."""
    import distribuicao_social_pro as soc
    import shorts_pipeline as shorts_mod
    d = PROJETOS / slug
    m = _json(d / "projeto.json", {}) or {}
    master = d / m.get("master", f"saidas/{slug}_master.mp4")
    saidas = d / "saidas"
    log = []
    if not master.is_file():
        raise FileNotFoundError(f"master ausente ({master}). Primeiro: estudio.py promover {slug} <run_id>")
    # shorts saem da timeline (mesma edicao do master): refaz so se a timeline mudou depois deles
    if _desatualizado(saidas / "shorts" / "pacote.json", d / "timeline.json"):
        print("  [entrega] Shorts...")
        shorts_mod.executar(slug, n=n_shorts)
        log.append("shorts gerados")
    thumb = _thumb(d)
    if forcar_artes or not thumb.is_file() or not (saidas / f"{slug}_banner_canal.jpg").is_file():
        print("  [entrega] thumbnail, banner e capa (ComfyUI)...")
        import gerador_artes_ia as art
        art.gerar_pacote_artes(d, forcar=forcar_artes)
        log.append("artes geradas")
    print("  [entrega] titulo, descricao, tags, capitulos, comentario (PUBLICACAO.md)...")
    pacote = soc.pacote_lancamento(d)
    # Folha por quadro: QA visual do master inteiro, uma folha por take de motion.
    _rodar_folha(slug, master, log)
    falta = conferir(d, pacote)
    pronto = not any(falta.values())
    (saidas / "ENTREGA.md").write_text(markdown(d, pacote, falta, log), encoding="utf-8")
    return {"slug": slug, "pronto": pronto, "faltando": {k: v for k, v in falta.items() if v},
            "entrega": str(saidas / "ENTREGA.md"), "publicacao": str(saidas / "PUBLICACAO.md"), "log": log}


def markdown(d: Path, pacote: dict, falta: dict, log: list[str]) -> str:
    """ENTREGA.md: o checklist do pacote + onde achar cada coisa (inclusive a folha por quadro)."""
    slug = d.name
    vp = pacote.get("video_principal") or {}
    ok, fail = "\u2705", "\u274c "
    L = [f"# Entrega \u2014 {slug}", "",
         "Pacote completo para postar. Textos prontos para copiar em `PUBLICACAO.md` (mesma pasta).", "",
         "## Checklist", "", "| item | status |", "|---|---|"]
    for chave, nome in ITENS:
        L.append("| " + nome + " | " + (ok if not falta.get(chave) else fail + falta[chave]) + " |")
    arte = [f"- Arte: `saidas/{a}`" for a in (pacote.get("artes") or [])]
    shorts = [f"- **Short:** `saidas/shorts/{s.get('arquivo')}`" for s in (pacote.get("shorts") or [])]
    alternativos = " \u00b7 ".join(
        f"`{t}`" for t in (vp.get("titulos_ab") or [])[1:])
    L += ["", "## Arquivos", "",
          f"- **V\u00eddeo completo:** `{vp.get('arquivo')}`",
          f"- **Thumbnail:** `{vp.get('miniatura')}`",
          *arte, *shorts,
          "", "## V\u00eddeo completo", "", f"**T\u00edtulo:** `{vp.get('titulo', '')}`", "",
          "T\u00edtulos alternativos (teste A/B): " + alternativos,
          "", "Descri\u00e7\u00e3o, tags, cap\u00edtulos e coment\u00e1rio fixado: ver `PUBLICACAO.md`.",
          "", "## QA visual \u2014 folha por quadro", "",
          "Auditoria de **todos** os quadros do master, em `qa/folha_por_quadro/`. N\u00e3o \u00e9 porteiro: "
          "n\u00e3o reprova nada, \u00e9 o olhar de QA que os porteiros n\u00e3o cobrem (motion escrevendo a linha "
          "errada, take escondendo a legenda, cart\u00e3o duplicado, cor, flicker).",
          "",
          "- `<slug>_folha.csv` \u2014 uma linha por quadro",
          "- `<slug>_take_NN.jpg` \u2014 uma folha por take de motion (todos os quadros da janela)",
          "- `<slug>_achados.md` \u2014 achados agrupados por classe", ""]
    if log:
        L += ["## Gerado nesta entrega", ""] + [f"- {x}" for x in log] + [""]
    return "\n".join(L)
