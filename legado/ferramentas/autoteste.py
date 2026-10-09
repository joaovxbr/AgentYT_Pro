#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autoteste.py — prova de funcionamento da esteira, ponta a ponta, na GPU.

Cria uma faixa de teste sintetica (master via NVENC), roda TODAS as etapas do
estudio e confere o resultado de cada uma. No fim, imprime um placar e limpa
tudo. Nao toca em nenhum projeto real nem publica nada.

    python autoteste.py            # roda e limpa
    python autoteste.py --manter   # roda e NAO apaga (para inspecionar as saidas)

O que ele exercita:
  1. doutor            -> GPU/NVENC ativos?
  2. novo + manifesto  -> cadastro da faixa
  3. master sintetico  -> encode via NVENC (a prova de que a GPU roda)
  4. legenda           -> gera o .ass a partir da LETRA.md
  5. sincronia         -> porteiro de legenda APROVA (onsets casam)
  6. sincronia (ruim)  -> porteiro REPROVA quando a legenda esta adiantada
  7. imagem            -> porteiro de imagem mede o master
  8. imagem (preto)    -> porteiro REPROVA um master com tela morta
  9. ritmo             -> grade de BPM
 10. capa              -> as 3 artes nos tamanhos exatos + card 210px
 11. corte 9:16        -> vertical enquadrado via NVENC, > 30 s
 12. corte <= 30 s     -> a trava RECUSA
 13. porteiro legenda  -> publicar.py recusa copy ruim ANTES do navegador
 14. porteiro audio    -> mede loudness (LUFS) e true peak do master
 15. QA unificado      -> relatorio com todos os porteiros (legenda+imagem+audio)
 16. legenda variada   -> animacao slide funciona no .ass
 17. filtros (catalogo)-> lista efeitos e receitas
 18. filtro no beat    -> receita ritmica renderiza e preserva dimensoes
 19. filtro sem grade  -> efeito ritmico e IGNORADO, nao quebra a cadeia
 20. end card no VIDEO -> o card entra na contagem de QUADROS, nao so na duracao
 21. POV para Shorts   -> gancho + cena + marca, 1080x1920
 22. POV sem gancho    -> RECUSA (POV sem pergunta e corte com moldura)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))

import render_dispatch as rd  # noqa: E402

SLUG = "_autoteste"
DIRP = RAIZ / "projetos" / SLUG


class Placar:
    def __init__(self):
        self.itens = []

    def marca(self, nome, ok, detalhe=""):
        self.itens.append((nome, ok, detalhe))
        simbolo = "OK  " if ok else "FALHA"
        print(f"  [{simbolo}] {nome}" + (f" — {detalhe}" if detalhe else ""))

    def resumo(self):
        n_ok = sum(1 for _, ok, _ in self.itens if ok)
        print("\n" + "=" * 60)
        print(f"PLACAR: {n_ok}/{len(self.itens)} etapas OK")
        print("=" * 60)
        return n_ok == len(self.itens)


def _sonda_video(caminho):
    """(duracao, n_quadros, fps) do stream de video. Conta quadro de verdade.

    Usa -count_frames porque `nb_frames` vem do cabecalho e pode mentir; o que
    interessa aqui e quantos quadros existem MESMO no arquivo.
    """
    r = subprocess.run(
        [rd.ffprobe_bin(), "-v", "error", "-count_frames",
         "-select_streams", "v:0",
         "-show_entries", "stream=duration,nb_read_frames,avg_frame_rate",
         "-of", "default=nw=1", str(caminho)],
        capture_output=True, text=True)
    # o ffprobe devolve os campos na ordem do STREAM, nao na ordem pedida:
    # le por NOME (chave=valor), senao duracao e fps trocam de lugar.
    campos = {}
    for linha in (r.stdout or "").splitlines():
        chave, _, valor = linha.strip().partition("=")
        if chave:
            campos[chave] = valor
    try:
        dur = float(campos.get("duration", 0))
        num, _, den = campos.get("avg_frame_rate", "0/1").partition("/")
        fps = float(num) / float(den or 1)
        n = int(campos.get("nb_read_frames", 0))
        return (dur, n, round(fps, 3))
    except (ValueError, ZeroDivisionError):
        return (0.0, 0, 0.0)


def _sonda_audio(caminho):
    """Duracao do stream de audio."""
    r = subprocess.run(
        [rd.ffprobe_bin(), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=duration", "-of", "csv=p=0", str(caminho)],
        capture_output=True, text=True)
    try:
        return float((r.stdout or "0").strip())
    except ValueError:
        return 0.0


def _est(*args):
    """Roda estudio.py com args e devolve (rc, saida)."""
    r = subprocess.run([sys.executable, str(AQUI / "estudio.py"), *args],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def _pub(*args):
    r = subprocess.run([sys.executable, str(AQUI / "publicar.py"), *args],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def _gerar_master(destino: Path, duracao=40, preto=False):
    destino.parent.mkdir(parents=True, exist_ok=True)
    ff = rd.ffmpeg_bin()
    if preto:
        entrada = ["-f", "lavfi", "-i", f"color=c=black:s=1920x1080:r=30:d={duracao}"]
    else:
        entrada = ["-f", "lavfi", "-i",
                   f"testsrc2=size=1920x1080:rate=30:duration={duracao}"]
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", *entrada,
           "-f", "lavfi", "-i",
           f"sine=frequency=220:sample_rate=48000:duration={duracao}",
           *rd.video_args(preferir_gpu=True), "-c:a", "aac", "-b:a", "192k",
           "-shortest", str(destino)]
    subprocess.run(cmd, check=True)


def _escrever_projeto():
    DIRP.mkdir(parents=True, exist_ok=True)
    (DIRP / "frames_capa" / "hd").mkdir(parents=True, exist_ok=True)
    manifesto = {
        "faixa": "AUTOTESTE",
        "personagem": "Prova", "anime": "ESTEIRA",
        "titulo_linhas": ["PROVA DA", "ESTEIRA"],
        "cor": {"destaque": "#00F0A0", "destaque_claro": ""},
        "arte": {"frames_dir": "frames_capa/hd", "frame_capa": "12.0",
                 "frame_banner": "20.0", "video_fonte": "master.mp4"},
        "master": "master.mp4", "letra": "LETRA.md",
        "palavras_vocal": "palavras_vocal.json",
        "cortes": [{"de": 2.0, "dur": 34.0, "tema": "PROVA"}],
        "publicado": {"estado": "nao"},
    }
    (DIRP / "projeto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    (DIRP / "LETRA.md").write_text(
        "# Letra autoteste\n\n```\n"
        " 12,000  PRIMEIRA LINHA DE TESTE\n"
        " 15,000  SEGUNDA LINHA AGORA\n"
        " 18,500  TERCEIRA LINHA VEM AQUI\n"
        " 22,000  QUARTA LINHA FECHA\n```\n", encoding="utf-8")
    # onsets casados (legenda alinhada)
    (DIRP / "palavras_vocal.json").write_text(json.dumps([
        {"word": "primeira", "start": 12.05}, {"word": "segunda", "start": 15.10},
        {"word": "terceira", "start": 18.60}, {"word": "quarta", "start": 22.08},
    ]), encoding="utf-8")
    # onsets deslocados (legenda 1,5 s adiantada -> deve reprovar)
    (DIRP / "palavras_vocal_ruim.json").write_text(json.dumps([
        {"word": "primeira", "start": 13.5}, {"word": "segunda", "start": 16.6},
        {"word": "terceira", "start": 20.0}, {"word": "quarta", "start": 23.6},
    ]), encoding="utf-8")


def rodar(manter: bool) -> int:
    pl = Placar()
    print("### AUTOTESTE DA ESTEIRA (GPU) ###\n")

    # 1. doutor / GPU
    print("1) ambiente")
    gpu = rd.tem_nvenc() and rd.tem_gpu_nvidia()
    pl.marca("GPU NVENC ativo", gpu, rd.nome_gpu() if gpu else "sem NVENC — cairia p/ CPU")

    # 2/3. projeto + master
    print("\n2) cadastro + master (NVENC)")
    if DIRP.exists():
        shutil.rmtree(DIRP, ignore_errors=True)
    _escrever_projeto()
    _gerar_master(DIRP / "master.mp4", 40)
    master_ok = (DIRP / "master.mp4").exists()
    pl.marca("master sintetico gerado via GPU", master_ok)

    # 4. legenda
    print("\n3) legenda")
    rc, out = _est("legenda", SLUG)
    ass = DIRP / "legendas" / f"{SLUG}.ass"
    pl.marca("gera .ass", rc == 0 and ass.exists(), ass.name)

    # 5. sincronia aprova
    print("\n4) porteiro de legenda")
    rc, out = _est("sincronia", SLUG)
    pl.marca("sincronia APROVA (onsets casam)", rc == 0 and "APROVADO" in out)

    # 6. sincronia reprova (onsets ruins)
    m = json.loads((DIRP / "projeto.json").read_text(encoding="utf-8"))
    m["palavras_vocal"] = "palavras_vocal_ruim.json"
    (DIRP / "projeto.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    rc, out = _est("sincronia", SLUG)
    pl.marca("sincronia REPROVA legenda adiantada", rc != 0 and "REPROVADO" in out)
    # restaura o bom
    m["palavras_vocal"] = "palavras_vocal.json"
    (DIRP / "projeto.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                       encoding="utf-8")

    # 7. imagem aprova
    print("\n5) porteiro de imagem")
    rc, out = _est("imagem", SLUG)
    pl.marca("imagem mede o master", rc == 0 and "APROVADO" in out)

    # 8. imagem reprova (master preto)
    _gerar_master(DIRP / "master_preto.mp4", 6, preto=True)
    m["master"] = "master_preto.mp4"
    (DIRP / "projeto.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    rc, out = _est("imagem", SLUG)
    pl.marca("imagem REPROVA tela preta", rc != 0 and "REPROVADO" in out)
    m["master"] = "master.mp4"
    (DIRP / "projeto.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                       encoding="utf-8")

    # 9. ritmo
    print("\n6) ritmo")
    rc, out = _est("ritmo", SLUG)
    pl.marca("mede a grade de BPM", rc == 0 and "BPM=" in out)

    # 10. capa
    print("\n7) artes")
    rc, out = _est("capa", SLUG)
    saidas = DIRP / "saidas"
    from PIL import Image
    tam_ok = False
    if (saidas / f"{SLUG}_capa_youtube.jpg").exists():
        tam_ok = (
            Image.open(saidas / f"{SLUG}_capa_youtube.jpg").size == (1280, 720)
            and Image.open(saidas / f"{SLUG}_banner_canal.jpg").size == (2560, 1440)
            and Image.open(saidas / f"{SLUG}_capa_streaming_3000.jpg").size == (3000, 3000)
        )
    pl.marca("3 artes nos tamanhos exatos", rc == 0 and tam_ok)
    pl.marca("previa do card 210px", (saidas / "previa_card_210.jpg").exists())

    # 11. corte 9:16
    print("\n8) corte vertical (NVENC)")
    rc, out = _est("corte", SLUG, "--de", "2.0", "--dur", "34.0", "--tema", "PROVA")
    corte = saidas / f"{SLUG}_corte_2s_9x16.mp4"
    dims_ok = False
    if corte.exists():
        pr = subprocess.run(
            [rd.ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(corte)],
            capture_output=True, text=True)
        dims_ok = "1080,1920" in pr.stdout.replace(" ", "")
    pl.marca("corte 9:16 1080x1920 gerado", rc == 0 and dims_ok)

    # 12. trava de 30 s
    rc, out = _est("corte", SLUG, "--de", "2.0", "--dur", "28.0", "--tema", "CURTO")
    pl.marca("trava recusa corte <= 30 s", rc != 0 and "RECUSADO" in out)

    # 13. porteiro de legenda do publicar
    print("\n9) porteiro de publicacao (sem navegador)")
    rc, out = _pub("tiktok", str(corte), "--legenda", "curto demais")
    pl.marca("publicar recusa copy ruim antes do navegador",
             rc != 0 and "PORTEIRO REPROVOU" in out)

    # 14. porteiro de audio (master sintetico = sine wave, sem vocal -> reprovado)
    print("\n10) porteiro de audio")
    rc, out = _est("audio", SLUG)
    pl.marca("audio mede loudness e true peak",
             "loudness" in out.lower() or "APROVADO" in out or "REPROVADO" in out)

    # 15. QA unificado (relatorio) — master sintetico reprovado no audio, mas roda
    print("\n11) QA unificado")
    rc, out = _est("relatorio", SLUG)
    pl.marca("relatorio QA roda e mostra resultado",
             "APROVADO" in out or "REPROVADO" in out)

    # 16. legenda com animacao variada
    print("\n12) legenda com --animacao slide")
    rc, out = _est("legenda", SLUG, "--animacao", "slide")
    ass_slide = DIRP / "legendas" / f"{SLUG}.ass"
    pl.marca("legenda com animacao slide", rc == 0 and ass_slide.exists())

    # 17. catalogo de filtros
    print("\n13) filtros e VFX")
    rc, out = _est("filtros")
    pl.marca("catalogo de filtros lista efeitos e receitas",
             rc == 0 and "zoom_pulse" in out and "amv" in out)

    # 18. filtro ritmico renderiza e preserva o enquadramento do corte 9:16
    rc, out = _est("filtrar", SLUG, "--efeitos", "short", "--alvo",
                   f"saidas/{SLUG}_corte_2s_9x16.mp4")
    fx = saidas / f"{SLUG}_corte_2s_9x16_fx_short.mp4"
    fx_dims_ok = False
    if fx.exists():
        pr = subprocess.run(
            [rd.ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(fx)],
            capture_output=True, text=True)
        fx_dims_ok = "1080,1920" in pr.stdout.replace(" ", "")
    pl.marca("filtro no beat renderiza e mantem 1080x1920",
             rc == 0 and fx_dims_ok)

    # 19. sem grade confiavel, o efeito ritmico sai de fininho (nao quebra)
    sys.path.insert(0, str(AQUI))
    import filtros as flt
    cadeia = flt.montar(["amv"], grade=None, cor="#00F0A0")
    pl.marca("efeito ritmico ignorado sem grade",
             "zoom_pulse" in cadeia.ignorados and "bloom" in cadeia.aplicados)

    # 20. o end card entra no VIDEO, nao so no audio.
    # O bug: o concat demuxer descarta em silencio a parte cujo fps nao casa,
    # entao o card somava 3 s de duracao SEM somar um unico quadro. Contar
    # duracao nao pega isso — tem de contar QUADRO.
    print("\n14) end card no fluxo de video")
    dur_v, n_frames, fps = _sonda_video(corte)
    dur_a = _sonda_audio(corte)
    frames_esperados = dur_v * fps if fps else 0
    card_no_video = (
        n_frames > 0 and frames_esperados > 0
        and abs(n_frames - frames_esperados) <= fps      # 1 s de tolerancia
        and abs(dur_v - dur_a) <= 0.5                    # video e audio juntos
    )
    pl.marca("end card entra no video (quadros == duracao)", card_no_video,
             f"dur_v={dur_v:.1f}s dur_a={dur_a:.1f}s frames={n_frames} fps={fps:g}")

    # 21. POV para Shorts
    print("\n15) corte POV para Shorts")
    rc, out = _est("pov", SLUG, "--de", "2.0", "--dur", "34.0",
                   "--gancho", "Voce se achava um Deus ate encontrar o Yoriichi...")
    pov_mp4 = saidas / f"{SLUG}_pov_2s_9x16.mp4"
    pov_ok = False
    if pov_mp4.exists():
        pr = subprocess.run(
            [rd.ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0",
             str(pov_mp4)], capture_output=True, text=True)
        pov_ok = "1080,1920" in pr.stdout.replace(" ", "")
    pl.marca("POV 9:16 1080x1920 gerado", rc == 0 and pov_ok)

    # 22. POV sem gancho: a trava RECUSA
    rc, out = _est("pov", SLUG, "--de", "2.0", "--dur", "34.0", "--gancho", "   ")
    pl.marca("POV sem gancho e RECUSADO", rc != 0 and "RECUSADO" in out)

    # 23. karaoke fill-sweep: gera .ass com \kf por palavra
    print("\n16) legenda karaoke fill-sweep")
    rc, out = _est("karaoke", SLUG)
    ass_kar = DIRP / "legendas" / f"{SLUG}.ass"
    tem_kf = False
    if ass_kar.exists():
        conteudo = ass_kar.read_text(encoding="utf-8")
        tem_kf = "\\kf" in conteudo and "Style: Karaoke" in conteudo
    pl.marca("karaoke gera .ass com \\kf por palavra", rc == 0 and tem_kf)

    ok = pl.resumo()

    if manter:
        print(f"\n(--manter) saidas preservadas em: {DIRP}")
    else:
        shutil.rmtree(DIRP, ignore_errors=True)
        for cache in RAIZ.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        print("\nlimpo (nenhum projeto real foi tocado).")

    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manter", action="store_true")
    a = ap.parse_args()
    sys.exit(rodar(a.manter))
