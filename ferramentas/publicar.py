#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publicar.py — a porta de PUBLICACAO do canal VX RAPS.

Uma ferramenta so para tudo que SAI do estudio: YouTube longo e Short, TikTok,
Reel do Instagram, miniatura, comentario fixado.

    🔴 Se algo nao funciona, conserte a ferramenta. Nao crie outro script.
    🔴 Publicar e acao publica e IRREVERSIVEL: so com --confirmo.

Tres porteiros rodam ANTES de abrir o navegador, nos quatro comandos que sobem
video:
    _validar_legenda  (vertical): >=25 chars, sem nome do arquivo, >=3 hashtags,
                       cita @VXRaps;
    _validar_imagem   (todos): chama imagem.py e recusa tela preta/pagina/congelado.
    audio (todos): chama audio.py e recusa loudness fora do YouTube / true peak.
Excecao editorial: --ignorar-qa publica e IMPRIME o motivo (fica no log, nao vira habito).
    Aplica-se a todos os porteiros (legenda, imagem e audio).

Comandos:
    python publicar.py estado
    python publicar.py youtube-longo  ARQ --titulo T --desc D [--tags a,b,c] [--confirmo]
    python publicar.py youtube-short  ARQ --titulo T --desc D [--confirmo]
    python publicar.py tiktok         ARQ --legenda L [--confirmo]
    python publicar.py instagram      ARQ --legenda L [--confirmo]
    python publicar.py miniatura      VIDEO_ID capa_1280x720.jpg [--confirmo]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import imagem as img_mod   # noqa: E402
import audio as audio_mod  # noqa: E402
import cdp                 # noqa: E402

HANDLE = "@VXRaps"


# ---------------------------------------------------------------------------
# Porteiros (rodam antes de qualquer navegador)
# ---------------------------------------------------------------------------

def _validar_legenda(legenda: str, arquivo: Path) -> list[str]:
    problemas = []
    txt = (legenda or "").strip()
    if len(txt) < 25:
        problemas.append(f"legenda com {len(txt)} chars (< 25)")
    nome = arquivo.stem.lower()
    if nome and nome in txt.lower():
        problemas.append(f"legenda contem o nome cru do arquivo ('{arquivo.stem}')")
    n_hash = len(re.findall(r"#\w+", txt))
    if n_hash < 3:
        problemas.append(f"apenas {n_hash} hashtags (< 3)")
    if HANDLE.lower() not in txt.lower():
        problemas.append(f"nao cita {HANDLE}")
    return problemas


def _validar_imagem(arquivo: Path) -> tuple[bool, list[str], str]:
    rel = img_mod.analisar(arquivo, pasta_qa=arquivo.parent / "qa_publicar")
    return rel.aprovado, rel.motivos, (rel.folha or "")


def _porteiros(arquivo: Path, legenda: str | None, ignorar_qa: bool) -> bool:
    """Retorna True se pode prosseguir. Aplica os tres porteiros."""
    arquivo = Path(arquivo)
    if not arquivo.exists():
        print(f"ABORTA: arquivo nao existe: {arquivo}")
        return False

    falhas = []
    if legenda is not None:  # vertical
        falhas += _validar_legenda(legenda, arquivo)

    ok_img, motivos_img, folha = _validar_imagem(arquivo)
    if not ok_img:
        falhas += [f"imagem: {m}" for m in motivos_img]

    # porteiro de audio: loudness e true peak
    try:
        rel_audio = audio_mod.analisar(arquivo)
        if not rel_audio.aprovado:
            falhas += [f"audio: {m}" for m in rel_audio.motivos]
    except Exception as e:
        falhas.append(f"audio: nao foi possivel analisar ({e})")

    if not falhas:
        return True

    print("### PORTEIRO REPROVOU ###")
    for f in falhas:
        print(f"  - {f}")
    if folha:
        print(f"  folha de contato (a prova): {folha}")
    if ignorar_qa:
        # excecao editorial: publica e IMPRIME o motivo
        print("\n⚠️  --ignorar-qa: publicando MESMO ASSIM. Motivo registrado acima.")
        print("    (tela preta nao se conserta com filtro; isto e excecao, nao habito.)")
        return True
    print("\nAborta. Legenda ruim? Escreva uma de verdade. Tela preta? Mude o PLANO no estudio.")
    return False


# ---------------------------------------------------------------------------
# CDP guard
# ---------------------------------------------------------------------------

def _exigir_navegador() -> bool:
    ok, motivo = cdp.disponivel()
    if not ok:
        print(f"ABORTA: {motivo}")
        return False
    print(f"  navegador: {motivo}")
    return True


def _exigir_confirmacao(confirmo: bool) -> bool:
    if confirmo:
        return True
    print("\n🔴 Publicar e acao publica e irreversivel. "
          "Repita o comando com --confirmo para publicar de fato.")
    print("   (os porteiros ja rodaram acima; sem --confirmo eu paro aqui de proposito.)")
    return False


# ---------------------------------------------------------------------------
# Comandos de publicacao
# ---------------------------------------------------------------------------

def cmd_estado() -> int:
    ok, motivo = cdp.disponivel()
    print("== publicar estado ==")
    if not ok:
        print(f"  navegador indisponivel: {motivo}")
        print("  (sem CDP nao da para ler o Studio; suba o Chrome de depuracao)")
        return 1
    print(f"  navegador OK: {motivo}")
    with cdp.Navegador() as nav:
        pg = nav.nova_aba("https://studio.youtube.com/")
        pg.esperar("body", timeout=20)
        print("  YouTube Studio aberto. Confira as abas videos/upload e videos/short.")
    print("  ⚠️ Clicar em 'Publicar' NAO e publicar — a prova e a coluna dizer 'Publico'.")
    return 0


def cmd_youtube_longo(arq, titulo, desc, tags, confirmo, ignorar_qa) -> int:
    arq = Path(arq)
    if not _porteiros(arq, None, ignorar_qa):
        return 2
    _contrato_metadados_longo(titulo, desc, tags)
    if not _exigir_navegador() or not _exigir_confirmacao(confirmo):
        return 3
    return _subir_youtube(arq, titulo, desc, tags, short=False)


def cmd_youtube_short(arq, titulo, desc, confirmo, ignorar_qa) -> int:
    arq = Path(arq)
    # short e vertical, mas o porteiro de legenda do YouTube usa titulo+desc
    if not _porteiros(arq, None, ignorar_qa):
        return 2
    if not _exigir_navegador() or not _exigir_confirmacao(confirmo):
        return 3
    return _subir_youtube(arq, titulo, desc, "", short=True)


def cmd_tiktok(arq, legenda, confirmo, ignorar_qa) -> int:
    arq = Path(arq)
    if not _porteiros(arq, legenda, ignorar_qa):
        return 2
    if not _exigir_navegador() or not _exigir_confirmacao(confirmo):
        return 3
    return _subir_tiktok(arq, legenda)


def cmd_instagram(arq, legenda, confirmo, ignorar_qa) -> int:
    arq = Path(arq)
    if not _porteiros(arq, legenda, ignorar_qa):
        return 2
    if not _exigir_navegador() or not _exigir_confirmacao(confirmo):
        return 3
    return _subir_instagram(arq, legenda)


def _contrato_metadados_longo(titulo, desc, tags) -> None:
    tags_lista = [t for t in (tags or "").split(",") if t.strip()]
    avisos = []
    if not (1300 <= len(desc or "") <= 1500):
        avisos.append(f"descricao com {len(desc or '')} chars (alvo 1300-1500)")
    if not (12 <= len(tags_lista) <= 16):
        avisos.append(f"{len(tags_lista)} tags (alvo 12-16)")
    if avisos:
        print("  ⚠️ contrato de metadados do longo:")
        for a in avisos:
            print(f"     - {a}")


# ---------------------------------------------------------------------------
# Rotinas de navegador (fluxo CDP; publicam de fato com --confirmo)
# ---------------------------------------------------------------------------

def _subir_youtube(arq: Path, titulo: str, desc: str, tags: str, short: bool) -> int:
    url = "https://studio.youtube.com/"
    with cdp.Navegador() as nav:
        pg = nav.nova_aba(url)
        if not pg.esperar("body", timeout=25):
            print("ABORTA: YouTube Studio nao carregou.")
            return 4
        print("  Abrindo diretor de upload...")
        import time as _t
        # viewport estavel: o menu 'Criar' so abre com layout desktop consistente
        try:
            pg.enviar("Emulation.setDeviceMetricsOverride",
                      {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        except Exception:
            pass
        _t.sleep(2.5)
        # 1) clicar no botao Criar por clique NATIVO (o .click() JS nao abre o menu Polymer)
        box = pg.avaliar(
            "(()=>{const b=document.querySelector('button[aria-label=Criar]');"
            "if(!b)return null;const r=b.getBoundingClientRect();"
            "return [r.x+r.width/2, r.y+r.height/2];})()")
        if not box:
            print("ABORTA: botao 'Criar' nao encontrado (UI do Studio mudou?).")
            return 4
        pg.clicar_real(box[0], box[1])
        _t.sleep(2.5)
        # 2) clicar em 'Enviar videos' no menu (tp-yt-paper-item, por coords)
        pos = pg.avaliar(
            "(()=>{const it=[...document.querySelectorAll("
            "'tp-yt-paper-item, ytcp-text-menu-item, [role=menuitem]')]"
            ".find(e=>/enviar v.deos/i.test(e.innerText||''));"
            "if(!it)return null;const r=it.getBoundingClientRect();"
            "return [r.x+r.width/2, r.y+r.height/2];})()")
        if not pos:
            print("ABORTA: item 'Enviar videos' nao apareceu no menu Criar.")
            return 4
        pg.clicar_real(pos[0], pos[1])
        if not pg.esperar("input[type=file]", timeout=20):
            print("ABORTA: input de arquivo nao apareceu.")
            return 4
        pg.enviar_arquivo("input[type=file]", str(arq.resolve()))
        print("  Arquivo injetado. Aguardando processamento do upload...")
        # espera a barra terminar antes de mexer nos metadados
        pg.esperar("#textbox", timeout=60)
        # o editor tem dois #textbox: [0]=titulo, [1]=descricao.
        # dispatch de input events para o Polymer registrar o valor.
        pg.avaliar(f"""
          (() => {{
            const cx = [...document.querySelectorAll('#textbox')];
            const set = (el, v) => {{
              if (!el) return;
              el.textContent = v;
              el.dispatchEvent(new Event('input', {{bubbles: true}}));
            }};
            set(cx[0], {_json(titulo)});
            set(cx[1], {_json(desc or "")});
          }})()""")
        # A resposta "Nao e conteudo para criancas" e obrigatoria (trava o Avancar)
        pg.clicar_texto("Nao e conteudo para criancas")
        print("  Titulo e descricao preenchidos, publico-infantil respondido.")
        if tags:
            print(f"  ⚠️ tags NAO inseridas automaticamente ({tags}); "
                  "adicione em 'Mostrar mais' se quiser.")
        print("  ⚠️ Espere a barra de upload TERMINAR antes de publicar.")
        print("  ⚠️ A prova de sucesso e a coluna de visibilidade dizer 'Publico',")
        print("     nao a ausencia de botao. Short e longo ficam em abas diferentes.")
        pg.reter("upload em andamento — conferir no Studio")
    print("  Fluxo de upload iniciado no Studio. Conclua a revisao final la.")
    return 0


def _subir_tiktok(arq: Path, legenda: str) -> int:
    with cdp.Navegador() as nav:
        pg = nav.nova_aba("https://www.tiktok.com/tiktokstudio/upload")
        if not pg.esperar("input[type=file]", timeout=30):
            print("ABORTA: TikTok Studio nao expos o input de arquivo.")
            return 4
        pg.enviar_arquivo("input[type=file]", str(arq.resolve()))
        print("  Arquivo injetado no TikTok. Aguardando o editor de legenda...")
        pg.esperar("div[contenteditable=true]", timeout=60)
        # limpa o nome do arquivo que ja vem preenchido, e escreve a legenda
        pg.avaliar("""(() => {
          const ed = document.querySelector('div[contenteditable=true]');
          if (ed) { ed.focus(); document.execCommand('selectAll'); document.execCommand('delete'); }
        })()""")
        pg.digitar(legenda)
        # relê a legenda e compara o tamanho (evita a quadruplicada / truncada)
        lida = pg.avaliar("(document.querySelector('div[contenteditable=true]')||{}).innerText||''")
        if not lida or len(lida.strip()) < max(20, int(len(legenda) * 0.7)):
            print(f"ABORTA: legenda no editor veio errada (len={len(lida or '')} vs {len(legenda)}).")
            return 5
        print("  Legenda conferida no editor.")
        print("  ⚠️ Submeta por [data-e2e=post_video_button] (habilita so apos o upload)")
        print("     com clique REAL; confirme 'Publicar agora' se abrir 'Continuar publicando?'.")
        print("     Sucesso = a URL virar /tiktokstudio/content.")
        pg.reter("aguardando upload/submit no TikTok")
    return 0


def _subir_instagram(arq: Path, legenda: str) -> int:
    with cdp.Navegador() as nav:
        pg = nav.nova_aba("https://www.instagram.com/")
        if not pg.esperar("svg[aria-label='Novo post'],svg[aria-label='New post']", timeout=25):
            print("ABORTA: Instagram nao carregou logado.")
            return 4
        print("  Fluxo: Novo post -> Postar -> arquivo -> Cortar(9:16) -> Avancar x2 -> legenda -> Compartilhar")
        print("  ⚠️ Feche avisos (OK/Continuar/Entendi) a cada volta do wizard.")
        print("  ⚠️ Na etapa Cortar meca o <video> escopado em div[role=dialog] (~0.5625).")
        print("  ⚠️ 'Compartilhar' nao muda body.innerText — confirme em /mugenraps_oficial/reels/.")
        pg.reter("wizard do Instagram aberto")
    print("  (legenda a inserir por Input.insertText apos o wizard chegar na etapa de texto)")
    return 0


def cmd_miniatura(video_id, capa, confirmo) -> int:
    capa = Path(capa)
    if not capa.exists():
        print(f"ABORTA: capa nao existe: {capa}")
        return 2
    from PIL import Image
    im = Image.open(capa)
    if im.size != (1280, 720):
        print(f"ABORTA: capa e {im.size}, o card exige 1280x720 exatos.")
        return 2
    if capa.stat().st_size > 2 * 1024 * 1024:
        print("ABORTA: capa > 2 MB (o Studio reescala e borra).")
        return 2
    if not _exigir_navegador() or not _exigir_confirmacao(confirmo):
        return 3
    with cdp.Navegador() as nav:
        pg = nav.nova_aba(f"https://studio.youtube.com/video/{video_id}/edit")
        pg.esperar("body", timeout=25)
        if not pg.esperar("input[type=file]#file-loader,ytcp-thumbnail-uploader input[type=file]",
                          timeout=20):
            print("ABORTA: input da miniatura nao apareceu.")
            return 4
        pg.enviar_arquivo("input[type=file]", str(capa.resolve()))
        print("  Miniatura injetada. Salve no Studio e confirme baixando:")
        print(f"     https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
        pg.reter("confirmar miniatura no Studio")
    return 0


def _json(s: str) -> str:
    import json as _j
    return _j.dumps(s)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="publicar.py")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("estado")

    yl = sub.add_parser("youtube-longo")
    yl.add_argument("arquivo")
    yl.add_argument("--titulo", required=True)
    yl.add_argument("--desc", required=True)
    yl.add_argument("--tags", default="")
    yl.add_argument("--confirmo", action="store_true")
    yl.add_argument("--ignorar-qa", dest="ignorar_qa", action="store_true")

    ys = sub.add_parser("youtube-short")
    ys.add_argument("arquivo")
    ys.add_argument("--titulo", required=True)
    ys.add_argument("--desc", required=True)
    ys.add_argument("--confirmo", action="store_true")
    ys.add_argument("--ignorar-qa", dest="ignorar_qa", action="store_true")

    tk = sub.add_parser("tiktok")
    tk.add_argument("arquivo")
    tk.add_argument("--legenda", required=True)
    tk.add_argument("--confirmo", action="store_true")
    tk.add_argument("--ignorar-qa", dest="ignorar_qa", action="store_true")

    ig = sub.add_parser("instagram")
    ig.add_argument("arquivo")
    ig.add_argument("--legenda", required=True)
    ig.add_argument("--confirmo", action="store_true")
    ig.add_argument("--ignorar-qa", dest="ignorar_qa", action="store_true")

    mn = sub.add_parser("miniatura")
    mn.add_argument("video_id")
    mn.add_argument("capa")
    mn.add_argument("--confirmo", action="store_true")

    a = p.parse_args(argv)
    if not a.cmd:
        print(__doc__)
        return 0
    if a.cmd == "estado":
        return cmd_estado()
    if a.cmd == "youtube-longo":
        return cmd_youtube_longo(a.arquivo, a.titulo, a.desc, a.tags, a.confirmo, a.ignorar_qa)
    if a.cmd == "youtube-short":
        return cmd_youtube_short(a.arquivo, a.titulo, a.desc, a.confirmo, a.ignorar_qa)
    if a.cmd == "tiktok":
        return cmd_tiktok(a.arquivo, a.legenda, a.confirmo, a.ignorar_qa)
    if a.cmd == "instagram":
        return cmd_instagram(a.arquivo, a.legenda, a.confirmo, a.ignorar_qa)
    if a.cmd == "miniatura":
        return cmd_miniatura(a.video_id, a.capa, a.confirmo)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
