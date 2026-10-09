#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""estudio.py — a porta de CRIACAO do canal VX RAPS.

Uma ferramenta so para tudo que acontece DENTRO do estudio: capa, banner, capa
quadrada, corte vertical, e os dois porteiros (legenda e imagem).

    🔴 Se algo nao funciona, conserte a ferramenta. Nao escreva outro script.

Comandos:
    python estudio.py estado [slug]
    python estudio.py doutor
    python estudio.py novo <slug>
    python estudio.py capa <slug> [--quais capa|banner|quadrada|todas] [--saida-dir DIR]
    python estudio.py corte <slug> --de S [--dur D | --ate S2] --tema "TEXTO"
    python estudio.py cortes <slug>
    python estudio.py ritmo <slug> [--gravar]
    python estudio.py legenda <slug> [--animacao auto|fade|slide|pop|mix]
    python estudio.py pov <slug> --de S --dur D --gancho "TEXTO"
    python estudio.py filtros                  # lista efeitos e receitas
    python estudio.py filtrar <slug> --efeitos amv|impacto|suave|cru|short
    python estudio.py sincronia <slug>        # porteiro: a legenda bate com a voz?
    python estudio.py sincronizar <slug>      # alinhamento word-level + gera .ass
    python estudio.py karaoke <slug>          # legenda karaoke fill-sweep (\kf)
    python estudio.py imagem <slug>           # porteiro: tem imagem no quadro?
    python estudio.py qa <slug>               # os dois porteiros num comando
    python estudio.py audio <slug>            # porteiro de audio (LUFS, true peak)
    python estudio.py relatorio <slug>        # QA unificado com todos os porteiros
    python estudio.py pesquisar tendencias    # o que esta em alta no nicho
    python estudio.py pesquisar personagem N  # pesquisa um personagem
    python estudio.py avaliar <slug>          # avalia o projeto vs tendencias
    python estudio.py comfy-status [--iniciar] # VX Image Local: ComfyUI + checkpoint
    python estudio.py comfy-parar             # encerra o ComfyUI que o estudio subiu
    python estudio.py esteira <slug> --resume [run_id]  # retoma do ponto que falhou
    python estudio.py cenas-ia <slug> [--planejar]  # cenas novas via ComfyUI (esteira ja chama)
    python estudio.py gerar-imagem <slug> --tipo capa|fundo|vertical|quadrado
    python estudio.py capa-ia <slug> [--motor local|remoto]

Lista completa: python estudio.py -h
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

# raiz do estudio = pasta acima de ferramentas/
RAIZ = Path(__file__).resolve().parents[1]
PROJETOS = RAIZ / "projetos"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RAIZ))
from vx import ambiente as vx_ambiente  # noqa: E402
vx_ambiente.garantir_path()  # ffmpeg/ffprobe de ferramentas/bin, sem depender do PATH do usuario

# Imports preguicosos (vx/lazy.py): o modulo so carrega no primeiro uso.
# Um import quebrado afeta so o comando que o usa, nao o estudio inteiro.
from vx import lazy as _vx_lazy  # noqa: E402
rd = _vx_lazy.modulo("render_dispatch")
leg_mod = _vx_lazy.modulo("legenda")
img_mod = _vx_lazy.modulo("imagem")
ritmo_mod = _vx_lazy.modulo("ritmo")
audio_mod = _vx_lazy.modulo("audio")
qa_mod = _vx_lazy.modulo("qa")
pesq_mod = _vx_lazy.modulo("pesquisa")
sl_mod = _vx_lazy.modulo("sincronizar_letra")
flt_mod = _vx_lazy.modulo("filtros")
pov_mod = _vx_lazy.modulo("pov")
tl_mod = _vx_lazy.modulo("timeline_clipe")
dir_mod = _vx_lazy.modulo("direcao_clipe")
rc_mod = _vx_lazy.modulo("render_clipe")
tr_mod = _vx_lazy.modulo("transcrever")
dl_mod = _vx_lazy.modulo("baixar_clipes")
mt_mod = _vx_lazy.modulo("montar_timeline")
mov_mod = _vx_lazy.modulo("analisador_movimento")
bass_mod = _vx_lazy.modulo("bass_shake")
imp_mod = _vx_lazy.modulo("impact_frames")
cur_mod = _vx_lazy.modulo("curadoria_ia")
col_mod = _vx_lazy.modulo("color_grade_pro")
cine_mod = _vx_lazy.modulo("cinemascope_fx")
spd_mod = _vx_lazy.modulo("speedlines_manga")
soc_mod = _vx_lazy.modulo("distribuicao_social_pro")
stem_mod = _vx_lazy.modulo("stems_ia_gpu")
mb_mod = _vx_lazy.modulo("motion_blur_pro")
tab_mod = _vx_lazy.modulo("gerador_tumbas_ab")
art_ia_mod = _vx_lazy.modulo("gerador_artes_ia")
img_local_mod = _vx_lazy.modulo("gerador_imagem_local")
cenas_ia_mod = _vx_lazy.modulo("cenas_ia_pipeline")
leg_pro_mod = _vx_lazy.modulo("legendas_mugen_pro")
snap_mod = _vx_lazy.modulo("snap_impact_transition")
ghost_mod = _vx_lazy.modulo("ghosting_fx")
crop_mod = _vx_lazy.modulo("smart_crop_916")
comp_mod = _vx_lazy.modulo("compositor_master_gpu")
rit_aud_mod = _vx_lazy.modulo("auditor_ritmo")
lww_mod = _vx_lazy.modulo("legendas_word_by_word")
neon_leg_mod = _vx_lazy.modulo("legendas_neon_motion")
loop_mod = _vx_lazy.modulo("loop_infinito_916")
pan_mod = _vx_lazy.modulo("paineis_manga")
splash_mod = _vx_lazy.modulo("color_splash")
hook_mod = _vx_lazy.modulo("hook_retencao_shorts")
px_mod = _vx_lazy.modulo("pixel_sort_glitch")
impact_pro_mod = _vx_lazy.modulo("impact_scene_orchestrator")
gfx_auto_mod = _vx_lazy.modulo("graphic_auto_pipeline")
manga_auto_mod = _vx_lazy.modulo("manga_auto_pipeline")
scene_intel_mod = _vx_lazy.modulo("scene_intelligence")
scene_match_mod = _vx_lazy.modulo("semantic_scene_matcher")
# dependencia opcional (rembg): None se ausente; checado no comando card-saber
saber_mod = _vx_lazy.modulo_opcional("card_apresentacao_saber")



# ---------------------------------------------------------------------------
# Manifesto
# ---------------------------------------------------------------------------

MANIFESTO_MODELO = {
    "faixa": "",
    "personagem": "",
    "anime": "",
    "titulo_linhas": [],
    "cor": {"destaque": "", "destaque_claro": ""},
    "arte": {
        "frames_dir": "frames_capa/hd",
        "frame_capa": "",       # ex.: "t_78.jpg" ou segundo "78.5"
        "frame_banner": "",
        "video_fonte": "",      # mp4 de onde tirar frames se nao houver jpg
    },
    "master": "",
    "letra": "LETRA.md",
    "palavras_vocal": "palavras_vocal.json",
    "cortes": [],               # [{"de":63.5,"dur":34.5,"tema":"..."}]
    "publicado": {"estado": "nao", "youtube": "", "tiktok": "", "instagram": ""},
}

CAMPOS_OBRIGATORIOS_CAPA = [
    ("faixa", lambda m: m.get("faixa")),
    ("personagem", lambda m: m.get("personagem")),
    ("anime", lambda m: m.get("anime")),
    ("titulo_linhas", lambda m: m.get("titulo_linhas")),
    ("cor.destaque", lambda m: m.get("cor", {}).get("destaque")),
    ("arte.frame_capa", lambda m: m.get("arte", {}).get("frame_capa")),
    ("arte.frame_banner", lambda m: m.get("arte", {}).get("frame_banner")),
]


def dir_projeto(slug: str) -> Path:
    return PROJETOS / slug


def caminho_manifesto(slug: str) -> Path:
    return dir_projeto(slug) / "projeto.json"


def carregar_manifesto(slug: str) -> dict:
    p = caminho_manifesto(slug)
    if not p.exists():
        raise SystemExit(f"faixa '{slug}' sem manifesto. Rode: estudio.py novo {slug}")
    return json.loads(p.read_text(encoding="utf-8"))


def salvar_manifesto(slug: str, m: dict) -> None:
    caminho_manifesto(slug).write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolver(base: Path, valor: str) -> Path:
    p = Path(valor)
    return p if p.is_absolute() else (base / valor)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_novo(slug: str) -> int:
    d = dir_projeto(slug)
    if caminho_manifesto(slug).exists():
        print(f"ja existe: {caminho_manifesto(slug)}")
        return 1
    d.mkdir(parents=True, exist_ok=True)
    (d / "frames_capa" / "hd").mkdir(parents=True, exist_ok=True)
    salvar_manifesto(slug, copy.deepcopy(MANIFESTO_MODELO))
    print(f"criado {caminho_manifesto(slug)}")
    print("preencha: faixa, personagem, anime, titulo_linhas, cor.destaque,")
    print("          arte.frame_capa, arte.frame_banner, master")
    return 0


def cmd_doutor() -> int:
    print("== estudio doutor ==")
    ok = rd.doutor() == 0
    print()
    # integridade dos masters
    print("Masters registrados:")
    achou = False
    for pj in sorted(PROJETOS.glob("*/projeto.json")):
        try:
            m = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            print(f"  {pj.parent.name}: projeto.json ILEGIVEL")
            continue
        master = m.get("master", "")
        if not master:
            continue
        achou = True
        p = _resolver(pj.parent, master)
        if not p.exists():
            print(f"  {pj.parent.name}: master AUSENTE ({master})")
            continue
        dur = _ffprobe_duracao(p)
        marca = "OK" if dur and dur > 0 else "ILEGIVEL (sem moov?)"
        print(f"  {pj.parent.name}: {p.name}  dur={dur}  [{marca}]")
    if not achou:
        print("  (nenhum master registrado ainda)")
    return 0 if ok else 1


def _ffprobe_duracao(caminho: Path):
    import subprocess
    exe = rd.ffprobe_bin()
    r = subprocess.run(
        [exe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(caminho)],
        capture_output=True, text=True,
    )
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return None


def cmd_estado(slug: str = None) -> int:
    projetos = ([dir_projeto(slug)] if slug
                else sorted(p.parent for p in PROJETOS.glob("*/projeto.json")))
    if not projetos:
        print("nenhuma faixa cadastrada. Rode: estudio.py novo <slug>")
        return 0
    print(f"{'FAIXA':<18}{'PERSONAGEM':<16}{'MASTER':<8}{'PUBLICADO'}")
    print("-" * 60)
    for d in projetos:
        pj = d / "projeto.json"
        if not pj.exists():
            print(f"{d.name:<18}(sem manifesto)")
            continue
        m = json.loads(pj.read_text(encoding="utf-8"))
        master = _resolver(d, m.get("master", "")) if m.get("master") else None
        tem_master = "sim" if master and master.exists() else "nao"
        pub = m.get("publicado", {}).get("estado", "nao")
        print(f"{d.name:<18}{m.get('personagem',''):<16}{tem_master:<8}{pub}")
    return 0


def _faltando_para_capa(m: dict):
    return [nome for nome, get in CAMPOS_OBRIGATORIOS_CAPA if not get(m)]


def _carregar_frame(slug: str, m: dict, chave: str):
    from PIL import Image
    d = dir_projeto(slug)
    arte = m.get("arte", {})
    valor = arte.get(chave, "")
    frames_dir = _resolver(d, arte.get("frames_dir", "frames_capa/hd"))
    # 1) arquivo jpg existente
    cand = frames_dir / valor if valor else None
    if cand and cand.exists():
        return Image.open(cand).convert("RGB")
    if valor and _resolver(d, valor).exists():
        return Image.open(_resolver(d, valor)).convert("RGB")
    # 2) extrair do video fonte num segundo
    video = arte.get("video_fonte") or m.get("master", "")
    if video and valor:
        try:
            seg = float(str(valor).replace("t_", "").replace(".jpg", "").replace(",", "."))
        except ValueError:
            seg = None
        if seg is not None:
            vp = _resolver(d, video)
            if vp.exists():
                import artes_base as ab
                dest = frames_dir / f"t_{seg}.jpg"
                ab.extrair_frame(vp, seg, dest)
                return Image.open(dest).convert("RGB")
    raise SystemExit(f"frame '{chave}'={valor!r} nao encontrado e sem como extrair.")


def cmd_capa(slug: str, quais: str, saida_dir: str = None) -> int:
    import artes_base as ab
    m = carregar_manifesto(slug)
    faltando = _faltando_para_capa(m)
    if faltando:
        print("RECUSADO: manifesto incompleto. Faltam:")
        for f in faltando:
            print(f"  - {f}")
        print("Arte feita com dado chutado sai errada e vai ao ar. Preencha e repita.")
        return 2

    frame_capa = _carregar_frame(slug, m, "frame_capa")
    frame_banner = _carregar_frame(slug, m, "frame_banner")
    dados = ab.DadosArte(
        slug=slug,
        titulo_linhas=m["titulo_linhas"],
        personagem=m["personagem"].upper(),
        anime=m["anime"].upper(),
        cor_destaque=m["cor"]["destaque"],
        frame_capa=frame_capa,
        frame_banner=frame_banner,
        palavra_destaque=(m["titulo_linhas"][-1].split()[-1]
                          if m["titulo_linhas"] else None),
    )

    saida = Path(saida_dir) if saida_dir else (dir_projeto(slug) / "saidas")
    saida.mkdir(parents=True, exist_ok=True)

    feitas = []
    if quais in ("todas", "capa"):
        capa = ab.compor_capa_youtube(dados)
        p = saida / f"{slug}_capa_youtube.jpg"
        capa.save(p, quality=92)
        feitas.append(p)
        prev = ab.previa_card_210(capa, Path(saida) / "previa_card_210.jpg")
        print(f"  previa do card 210px: {prev}  <- ABRA E OLHE (titulo legivel?)")
    if quais in ("todas", "banner"):
        p = saida / f"{slug}_banner_canal.jpg"
        ab.compor_banner(dados).save(p, quality=92)
        feitas.append(p)
    if quais in ("todas", "quadrada"):
        p = saida / f"{slug}_capa_streaming_3000.jpg"
        ab.compor_capa_streaming(dados).save(p, quality=92)
        feitas.append(p)

    print("\nArtes geradas:")
    for f in feitas:
        print(f"  {f}")
    print("\nConferencia obrigatoria (a ferramenta cobra, voce confirma):")
    print(f"  1. E o {m['personagem']} MESMO no frame? (o erro da Lua Superior)")
    print("  2. O titulo se le no card de 210px? (abra a previa)")
    print("  3. A coluna de texto caiu FORA do rosto?")
    return 0


def _dur_do_corte(args):
    if args.ate is not None:
        return round(args.ate - args.de, 3)
    return args.dur


def cmd_corte(slug: str, de: float, dur: float, tema: str) -> int:
    m = carregar_manifesto(slug)
    master = _resolver(dir_projeto(slug), m.get("master", ""))
    if not master.exists():
        raise SystemExit(f"master ausente: {master}")
    sys.path.insert(0, str(RAIZ / "assets" / "tiktok"))
    import gerar_corte_marcado as gcm
    saida = dir_projeto(slug) / "saidas" / f"{slug}_corte_{int(de)}s_9x16.mp4"
    titulo = f"VX RAPS - {tema.upper()}"
    subtitulo = f"{m['personagem'].upper()} ({m['anime'].upper()})"
    cor = m.get("cor", {}).get("destaque", "#00ffcc")
    cor_0x = cor.lstrip("#")
    gcm.gerar(master, de, dur, saida, titulo, subtitulo,
              cor_titulo=f"0x{cor_0x}",
              com_intro=True,
              personagem=m.get("personagem", ""),
              anime=m.get("anime", ""),
              cor_hex=cor)
    print(f"corte pronto: {saida}")
    return 0


def cmd_cortes(slug: str) -> int:
    m = carregar_manifesto(slug)
    cortes = m.get("cortes", [])
    if not cortes:
        print("nenhum corte no manifesto (cortes[]). Use: estudio.py corte ...")
        return 1
    for c in cortes:
        cmd_corte(slug, float(c["de"]), float(c.get("dur", 0) or (c["ate"] - c["de"])),
                  c.get("tema", m["faixa"]))
    return 0


def cmd_legenda(slug: str, estilo_animacao: str = "auto") -> int:
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    # letra pode ser string ("LETRA.md") ou dict {arquivo, linhas}
    letra_cfg = m.get("letra", "LETRA.md")
    letra_arq = letra_cfg.get("arquivo", "LETRA.md") if isinstance(letra_cfg, dict) else letra_cfg
    letra = _resolver(d, letra_arq)
    if not letra.exists():
        raise SystemExit(f"letra ausente: {letra}")
    leg = leg_mod.ler_letra(letra)
    if not leg.eventos:
        raise SystemExit("nenhum evento lido da letra (formato: '<segundo>  TEXTO').")
    saida = _ass_ativo(d, m, slug)
    saida.parent.mkdir(parents=True, exist_ok=True)
    leg_mod.gerar_ass(leg, saida, m.get("cor", {}).get("destaque", "#FFFFFF"),
                      estilo_animacao=estilo_animacao)
    print(f"gerado {saida}  ({len(leg.eventos)} eventos, animacao={estilo_animacao})")
    return 0


def _ass_ativo(d: Path, m: dict, slug: str) -> Path:
    """Legenda ATIVA (a que o render queima): sempre projeto.json -> legenda_ass.

    Todo comando que gera a legenda do master grava aqui; variantes de estilo
    (mugen, word_by_word, neon) gravam em arquivo proprio e nao sao queimadas.
    """
    return _resolver(d, m.get("legenda_ass") or f"legendas/{slug}.ass")


def _ass_e_onsets(slug: str, m: dict):
    d = dir_projeto(slug)
    ass = _ass_ativo(d, m, slug)
    if not ass.exists():
        raise SystemExit(f"nao existe {ass}. Rode: estudio.py sincronizar {slug}")
    # Se existe transcricao canonica, ela e a melhor fonte para o gate:
    # preserva grafia autoral e ja carrega word-level alinhado ao audio.
    canon = d / "transcricao_canonica.json"
    onsets = canon if canon.exists() else _resolver(
        d, m.get("palavras_vocal", "palavras_vocal.json"))
    if not onsets.exists():
        raise SystemExit(f"onsets ausentes: {onsets} (Whisper word_timestamps do vocal).")
    return ass, onsets


def _excecoes_sincronia(projeto: Path, slug: str, fora: list, palavras_err: list[str]):
    """Separa os problemas de sincronia em perdoados (registrados em qa/excecao_sincronia.json)
    e sobras. Um 'fora de 0,30 s' e perdoado so se tempo (±0,6 s) e texto batem com o registro.
    Um 'volta no tempo' e perdoado so se a linha e a palavra batem. Sem arquivo: nada e perdoado."""
    arq = Path(projeto) / "qa" / "excecao_sincronia.json"
    reg = {}
    if arq.is_file():
        reg = json.loads(arq.read_text(encoding="utf-8"))
        if reg.get("projeto") != slug:
            reg = {}
    pontos = reg.get("pontos") or []
    fora_reg = [p for p in pontos if p.get("tipo") == "fora_de_0_30s"]
    pal_reg = [p for p in pontos if p.get("tipo") == "palavra_volta_no_tempo"]

    perdoados_fora, sobra_fora = [], []
    for t, txt, _dv in fora:
        ok = any(abs(float(t) - float(p["t"])) <= 0.6 and str(p["texto"])[:20].lower() in str(txt).lower()
                 for p in fora_reg)
        (perdoados_fora if ok else sobra_fora).append((t, txt))

    perdoados_pal, sobra_pal = [], []
    for msg in palavras_err:
        ok = any(f"'{p.get('palavra')}' volta no tempo" in msg and str(p["texto"])[:20] in msg
                 for p in pal_reg)
        (perdoados_pal if ok else sobra_pal).append(msg)
    return perdoados_fora, perdoados_pal, sobra_fora, sobra_pal


def cmd_sincronia(slug: str) -> int:
    m = carregar_manifesto(slug)
    ass, onsets = _ass_e_onsets(slug, m)
    rel = leg_mod.medir_sincronia(ass, onsets)
    print(f"== sincronia {slug} ==")
    print(f"  medidos {rel.n_medidos}/{rel.n_total} eventos")
    print(f"  mediana={rel.mediana:+.3f}s  p90={rel.p90:.3f}s")
    if rel.motivo:
        print(f"  ! {rel.motivo}")
    if rel.fora:
        print(f"  {len(rel.fora)} linhas fora de +-0,30s (primeiras 8):")
        for t, txt, dv in rel.fora[:8]:
            print(f"    {t:7.2f}s  {dv:+.3f}s  {txt[:40]}")
    # prova independente do ASR: legenda na tela enquanto a voz esta em silencio
    from vx import projeto as vx_projeto
    vocal = vx_projeto.stem(dir_projeto(slug), "vocals", m)
    silencio = []
    if vocal.exists():
        silencio = leg_mod.eventos_sobre_silencio(
            leg_mod._eventos_do_ass(ass), tr_mod.energia_vocal(vocal))
        print(f"  legenda x voz (stem vocal): {len(silencio)} linha(s) sobre silencio")
        for x in silencio[:8]:
            print(f"    {x['inicio']:7.2f}s  {x['silencio']:.0%} silencio  {x['texto'][:40]}")
    else:
        print("  aviso: stem vocal ausente; checagem legenda x voz nao executada")
    # POV/karaoke acendem PALAVRA a palavra: cada palavra no tempo dela, em ordem
    # (incidente 2026-10-01-douma-pov-fora-de-ordem)
    palavras_err = []
    sync_path = dir_projeto(slug) / "letra_sincronizada.json"
    if sync_path.exists() and onsets.exists():
        dados = json.loads(onsets.read_text(encoding="utf-8"))
        ws = dados.get("words", []) if isinstance(dados, dict) else dados
        palavras_err = sl_mod.validar_palavras(json.loads(sync_path.read_text(encoding="utf-8")), ws)
        print(f"  palavra a palavra (POV): {len(palavras_err)} problema(s)")
        for p_ in palavras_err[:8]:
            print(f"    {p_}")
    # excecao humana restrita (projetos/<slug>/qa/excecao_sincronia.json): so os pontos
    # listados saem; mediana/p90/limiar e qualquer outro defeito continuam reprovando
    perdoados_fora, perdoados_pal, sobra_fora, sobra_pal = _excecoes_sincronia(
        dir_projeto(slug), slug, rel.fora, palavras_err)
    if perdoados_fora or perdoados_pal:
        print(f"  excecao registrada: {len(perdoados_fora) + len(perdoados_pal)} ponto(s) aceito(s) "
              f"(qa/excecao_sincronia.json)")
    if rel.aprovado and not silencio and not sobra_pal and not sobra_fora:
        print("  APROVADO" + (" (com excecao registrada)" if perdoados_fora or perdoados_pal else ""))
        return 0
    print("  REPROVADO -> rode: estudio.py auditar-letra", slug, "e estudio.py sincronizar", slug)
    return 1


def _gerar_sync_word_level(slug: str, m: dict):
    """Gera letra_sincronizada priorizando a transcricao canonica quando existe.

    Retorna (sync, palavras, onsets_path). A letra autoral/canonica sempre vence
    sobre grafias antigas do Whisper/LETRA_LINHAS.
    """
    d = dir_projeto(slug)

    canonical_path = d / "transcricao_canonica.json"
    if canonical_path.exists():
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        if isinstance(canonical, dict) and canonical.get("lines"):
            sync = []
            palavras = []
            for line in canonical["lines"]:
                words = []
                for w in line.get("words") or []:
                    token = str(w.get("word", w.get("text", ""))).strip()
                    if not token:
                        continue
                    try:
                        ws = float(w.get("start"))
                        we = float(w.get("end"))
                    except (TypeError, ValueError):
                        continue
                    words.append({"text": token, "start": ws, "end": we})
                    palavras.append({"word": token, "start": ws, "end": we})
                try:
                    ini = float(line["start"])
                    fim = float(line["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                texto = str(line.get("text", "")).strip()
                if not texto or fim <= ini:
                    continue
                sync.append({
                    "start": ini, "end": fim, "text": texto,
                    "keyword": None, "words": words,
                })
            if sync:
                saida = d / "letra_sincronizada.json"
                saida.write_text(
                    json.dumps(sync, ensure_ascii=False, indent=1),
                    encoding="utf-8")
                print(
                    f"sincronizacao canonica: {len(sync)} linhas -> {saida}")
                print("fonte: transcricao_canonica.json (letra autoral + timing de audio)")
                return sync, palavras, canonical_path

    onsets_path = _resolver(d, m.get("palavras_vocal", "palavras_vocal.json"))
    if not onsets_path.exists():
        raise SystemExit(f"palavras_vocal.json ausente: {onsets_path}")

    whisper_data = json.loads(onsets_path.read_text(encoding="utf-8"))
    if isinstance(whisper_data, dict) and "words" in whisper_data:
        palavras = whisper_data["words"]
    elif isinstance(whisper_data, list):
        palavras = whisper_data
    else:
        raise SystemExit("formato de palavras_vocal.json invalido")

    for w in palavras:
        if "end" not in w:
            w["end"] = w.get("start", 0) + 0.3

    # letra pode ser string (LETRA.md) ou dict {arquivo, linhas}
    letra_cfg_raw = m.get("letra", "LETRA.md")
    letra_arquivo = (letra_cfg_raw.get("arquivo", "LETRA.md")
                     if isinstance(letra_cfg_raw, dict) else letra_cfg_raw)
    letra_path = _resolver(d, letra_arquivo)

    # prioriza letra.linhas (LETRA_LINHAS.txt: uma frase cantada por linha, sem
    # timestamp). Se ausente, cai na letra com formato "SEGUNDO TEXTO".
    letra_cfg = m.get("letra")
    linhas_path = None
    if isinstance(letra_cfg, dict) and letra_cfg.get("linhas"):
        linhas_path = _resolver(d, letra_cfg["linhas"])

    if linhas_path and linhas_path.exists():
        # frase por linha, texto cru — o alinhar() casa contra o Whisper
        linhas_texto = [l.strip() for l in linhas_path.read_text(
            encoding="utf-8").splitlines() if l.strip()]
    else:
        linhas_txt = [l.strip() for l in letra_path.read_text(
            encoding="utf-8").splitlines() if l.strip()]
        import re
        re_ts = re.compile(r"^\s*\d+(?:[.,]\d+)?\s+")
        linhas_ts = [l for l in linhas_txt if re_ts.match(l)]
        linhas_texto = [re_ts.sub("", l).strip() for l in linhas_ts]

    # Marcadores de secao ([Intro], [Verso 1], [Refrao]...) sao direcoes do Suno,
    # nao sao cantados: nunca podem virar legenda nem linha da timeline.
    linhas_texto = sl_mod.extrair_linhas_suno("\n".join(linhas_texto))

    if not linhas_texto:
        raise SystemExit("nenhuma linha de letra: nem letra.linhas nem formato 'SEGUNDO TEXTO'")

    sync = sl_mod.alinhar(linhas_texto, palavras)
    sync = sl_mod.corrigir_sobreposicao(sync)

    saida = d / "letra_sincronizada.json"
    json.dump(sync, open(saida, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"alinhamento word-level: {len(sync)} linhas -> {saida}")

    buracos = sl_mod.validar_cobertura(sync, palavras)
    print(f"cobertura: {len(buracos)} palavras sem legenda por perto")
    if buracos:
        print("  buracos:")
        for t, w in buracos[:10]:
            print(f"    {t}s: {w}")
    else:
        print("  100% coberto")

    return sync, palavras, onsets_path


def cmd_sincronizar(slug: str) -> int:
    """Sincroniza a legenda usando alinhamento WORD-LEVEL (metodo novo)."""
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)

    sync, palavras, onsets_path = _gerar_sync_word_level(slug, m)

    cor = m.get("cor", {}).get("destaque", "#FFFFFF")
    ass_saida = _ass_ativo(d, m, slug)
    ass_saida.parent.mkdir(parents=True, exist_ok=True)
    if ass_saida.exists():
        backup = ass_saida.with_suffix(ass_saida.suffix + ".pre-canonical-sync.bak")
        if not backup.exists():
            import shutil
            shutil.copy2(ass_saida, backup)
    leg_mod.gerar_ass_de_sync(sync, ass_saida, cor, perfil="master")
    # legenda dedicada da cena do Short (1080x608): px fixo, quebra propria.
    ass_pov = d / "legendas" / f"{slug}_pov.ass"
    leg_mod.gerar_ass_de_sync(sync, ass_pov, cor, perfil="pov_cena")
    print(f"gerado {ass_saida}  ({len(sync)} eventos, word-level, perfil master)")
    print(f"gerado {ass_pov}  (perfil pov_cena, para Shorts)")

    ass, _ = _ass_e_onsets(slug, m)
    rel = leg_mod.medir_sincronia(ass, onsets_path)
    if rel.aprovado:
        print(f"  sincronia APROVADO (mediana={rel.mediana:+.3f}s, p90={rel.p90:.3f}s)")
    else:
        print(f"  sincronia REPROVADO (mediana={rel.mediana:+.3f}s, p90={rel.p90:.3f}s)")

    print("AVISO: so vale depois de um render NOVO; o master atual tem a legenda antiga queimada.")
    return 0


def cmd_karaoke(slug: str) -> int:
    """Gera legenda KARAOKE fill-sweep (\\kf): cada palavra varre a cor no tempo."""
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)

    sync, _palavras, _onsets = _gerar_sync_word_level(slug, m)

    cor = m.get("cor", {}).get("destaque", "#FFFFFF")
    ass_saida = _ass_ativo(d, m, slug)
    ass_saida.parent.mkdir(parents=True, exist_ok=True)
    leg_mod.gerar_ass_karaoke(sync, ass_saida, cor, perfil="master")
    # legenda karaoke dedicada da cena do Short (1080x608): NAO reaproveita o
    # master; PlayRes = tamanho da cena, entao a linha nunca vaza pelas bordas.
    ass_pov = d / "legendas" / f"{slug}_pov.ass"
    leg_mod.gerar_ass_karaoke(sync, ass_pov, cor, perfil="pov_cena")
    n_words = sum(len(item.get("words") or []) for item in sync)
    print(f"gerado {ass_saida}  ({len(sync)} linhas, {n_words} palavras \\kf, perfil master)")
    print(f"gerado {ass_pov}  (perfil pov_cena, para Shorts)")
    print("So vale depois de um render NOVO - o master atual tem o antigo queimado.")
    return 0


def cmd_ritmo(slug: str, gravar: bool) -> int:
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    # mede no audio FINAL (o master), nao no original
    fonte = _resolver(d, m.get("master", ""))
    if not fonte.exists():
        raise SystemExit(f"master ausente para medir o ritmo: {fonte}")
    g = ritmo_mod.medir_grade(fonte)
    print(f"== ritmo {slug} ==")
    print(f"  BPM={g.bpm}  periodo={g.periodo}s  fase={g.fase}s  "
          f"confianca={g.confianca}  dur={g.duracao}s")
    if g.confianca < 0.25:
        print("  confianca < 0,25: NAO encaixo nada (grade errada e pior que nenhuma).")
        return 1
    # propoe grade de corte pela letra
    letra = _resolver(d, m.get("letra", "LETRA.md"))
    if letra.exists():
        leg = leg_mod.ler_letra(letra)
        tempos = [e.inicio for e in leg.eventos]
        encaixados = ritmo_mod.encaixar(tempos, g)
        casados = sum(1 for x in encaixados if x is not None)
        print(f"  grade de corte: {casados}/{len(tempos)} linhas encaixam no beat (+-110ms)")
        if gravar:
            saida = d / "grade_corte.json"
            saida.write_text(json.dumps(
                {"bpm": g.bpm, "periodo": g.periodo, "fase": g.fase,
                 "confianca": g.confianca,
                 "fronteiras": [{"linha": t, "beat": b}
                                for t, b in zip(tempos, encaixados)]},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  gravado {saida}")
    return 0


def cmd_imagem(slug: str) -> int:
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    master = _resolver(d, m.get("master", ""))
    if not master.exists():
        raise SystemExit(f"master ausente: {master}")
    # Exclui os primeiros 10 segundos da intro do canal (onde pode haver fade-in/abertura escura)
    rel = img_mod.analisar(master, pasta_qa=d / "qa", excluir_intro=10.0)
    print(f"== imagem {slug} ==  (dur {rel.duracao}s)")
    print(f"  morto     {rel.seg_morto}s ({rel.pct_morto}%)  maior bloco {rel.maior_bloco_morto}s")
    print(f"  quase     {rel.seg_quase}s ({rel.pct_quase}%)")
    print(f"  congelado {rel.seg_congelado}s ({rel.pct_congelado}%)")
    print(f"  pagina    {rel.seg_pagina}s")
    if rel.folha:
        print(f"  folha de contato (a PROVA): {rel.folha}")
    if rel.aprovado:
        print("  APROVADO")
        return 0
    print("  REPROVADO:")
    for mot in rel.motivos:
        print(f"    - {mot}")
    print("  🔴 Tela preta nao se conserta com filtro — o PLANO tem de mudar.")
    return 1


def cmd_qa(slug: str) -> int:
    print("### QA — os dois porteiros ###\n")
    r1 = cmd_sincronia(slug)
    print()
    r2 = cmd_imagem(slug)
    print()
    if r1 == 0 and r2 == 0:
        print("APROVADO nos dois porteiros. Pode entregar.")
        return 0
    print("REPROVADO. Nada sai daqui sem os dois porteiros verdes.")
    return 1


def cmd_audio(slug: str) -> int:
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    master = _resolver(d, m.get("master", ""))
    if not master.exists():
        raise SystemExit(f"master ausente: {master}")
    rel = audio_mod.analisar(master)
    print(f"== audio {slug} ==")
    print(f"  loudness:    {rel.lufs:.1f} LUFS  (alvo: -14.0)")
    print(f"  true peak:   {rel.true_peak_dbtp:.1f} dBTP  (max: -1.0)")
    print(f"  sample rate: {rel.sample_rate} Hz")
    print(f"  duracao:     {rel.duracao}s")
    print(f"  clareza vocal: {rel.clareza_vocal:.2f}  (min: 0.30)")
    if rel.aprovado:
        print("  APROVADO")
        return 0
    print("  REPROVADO:")
    for m_ in rel.motivos:
        print(f"    - {m_}")
    return 1


def cmd_relatorio(slug: str) -> int:
    """QA unificado — todos os porteiros num relatorio so."""
    rel = qa_mod.rodar_qa(slug)
    print(qa_mod.formatar_relatorio(rel))
    return 0 if rel.aprovado else 1


def cmd_pesquisar(assunto: str, arg: str = None) -> int:
    if assunto == "tendencias":
        tendencias = pesq_mod.tendencias_nicho()
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
    if assunto == "personagem" and arg:
        rel = pesq_mod.pesquisar_personagem(arg)
        print(f"== personagem: {rel.nome} ==")
        print(f"  anime: {rel.anime or '?'}")
        print(f"  videos encontrados: {rel.videos_encontrados}")
        print(f"  views media: {rel.views_medias}")
        print(f"  cor sugerida: {rel.cor_sugerida}")
        print(f"  temas: {', '.join(rel.temas_sugeridos)}")
        return 0
    print("Uso: estudio.py pesquisar tendencias | estudio.py pesquisar personagem NOME")
    return 1


def _rebase_ass(ass_origem: Path, de: float, dur: float, destino: Path) -> Path:
    """Recorta o .ass ao trecho [de, de+dur] e rebaseia os tempos para 0.

    O -ss de output reseta o PTS do corte para 0; a legenda queimada precisa dos
    tempos rebaseados, senao aparece fora (ou nunca) no trecho.
    """
    import re as _re
    fim = de + dur
    re_dlg = _re.compile(
        r"^(Dialogue:\s*\d+,)(\d+:\d\d:\d\d\.\d\d),(\d+:\d\d:\d\d\.\d\d),(.*)$")

    def tc_seg(tc):
        h, m_, s = tc.split(":")
        return int(h) * 3600 + int(m_) * 60 + float(s)

    def seg_tc(seg):
        seg = max(0.0, seg)
        h = int(seg // 3600); m_ = int((seg % 3600) // 60); s = seg % 60
        return f"{h:d}:{m_:02d}:{s:05.2f}"

    saida_linhas = []
    for linha in ass_origem.read_text(encoding="utf-8").splitlines():
        m = re_dlg.match(linha)
        if not m:
            saida_linhas.append(linha)
            continue
        ini, end = tc_seg(m.group(2)), tc_seg(m.group(3))
        if end <= de or ini >= fim:
            continue  # fora do trecho
        ini2 = max(0.0, ini - de)
        end2 = min(dur, end - de)
        saida_linhas.append(
            f"{m.group(1)}{seg_tc(ini2)},{seg_tc(end2)},{m.group(4)}")
    destino.write_text("\n".join(saida_linhas) + "\n", encoding="utf-8")
    return destino


def _quadro_rgb(caminho: Path, t: float = 0.10, largura: int = 64, altura: int = 36):
    """Um frame do video como array RGB; None se nao der pra ler."""
    import shutil as _sh
    import subprocess as _sp

    import numpy as _np
    ff = _sh.which("ffmpeg") or "ffmpeg"
    try:
        p = _sp.run([ff, "-hide_banner", "-loglevel", "error", "-ss", f"{t}", "-i", str(caminho),
                     "-frames:v", "1", "-vf", f"scale={largura}:{altura}",
                     "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                    capture_output=True, timeout=60)
    except Exception:
        return None
    fb = largura * altura * 3
    if len(p.stdout) < fb:
        return None
    return _np.frombuffer(p.stdout[:fb], dtype=_np.uint8).reshape(altura, largura, 3).astype(_np.int16)


def _comeca_com_intro(a, b, limiar: float = 12.0) -> bool:
    """True quando o frame de `a` e o mesmo frame de `b` (mesmo instante, imagens iguais)."""
    import numpy as np
    if a is None or b is None or getattr(a, "shape", None) != getattr(b, "shape", None):
        return False
    return float(np.abs(a - b).mean()) < limiar


def _dur_intro(master: Path) -> float:
    """Duracao da intro oficial quando o MASTER comeca com ela; 0.0 caso contrario.

    O `.ass` da letra e do CORPO (tempo 0 = primeiro frame depois da intro), mas o
    corte do POV e no MASTER, que tem a intro oficial de ~10 s na frente. Sem este
    ajuste o `pov --karaoke` rebaseia a legenda com o tempo do master: as primeiras
    linhas do trecho sao descartadas e o resto acende 10 s adiantado (Asta, 05/10/2026).
    Masters antigos sem intro devolvem 0.0 e o comportamento antigo continua igual.
    """
    try:
        import compositor_master_gpu as comp
        intro = Path(comp.INTRO_OFICIAL)
        if not intro.exists():
            return 0.0
        _, dur = comp.inspecionar_midia(intro)
        if not _comeca_com_intro(_quadro_rgb(master), _quadro_rgb(intro)):
            return 0.0
        return float(dur)
    except Exception:
        return 0.0


def _de_ass_corpo(de_master: float, master: Path) -> float:
    """`de` do corte (linha do tempo do master) traduzido para a linha do tempo do .ass."""
    return max(0.0, float(de_master) - _dur_intro(master))


def cmd_pov(slug: str, de: float, dur: float, gancho: str,
            tema: str = None, handle: str = "@VXRaps",
            marca: str = "VX RAPS", com_intro: bool = False,
            karaoke: bool = False) -> int:
    """Gera o corte POV para Shorts: gancho no alto, cena no meio, marca embaixo.

    Anime, personagem e cor vem do manifesto — o gancho e a unica coisa que
    voce escreve, porque e a unica que o manifesto nao sabe.

    Com --karaoke, queima a legenda karaoke (\\kf) do slug na cena. Requer que
    `estudio.py karaoke <slug>` ja tenha rodado (gera legendas/<slug>.ass).
    """
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    master = _resolver(d, m.get("master", ""))
    if not master.exists():
        raise SystemExit(f"master ausente: {master}")

    ass_trecho = None
    if karaoke:
        # usa a legenda DEDICADA da cena (perfil pov_cena, 1080x608), nunca o
        # master 1920x1080 — reaproveitar o master faz a linha vazar no Short.
        ass_full = d / "legendas" / f"{slug}_pov.ass"
        if not ass_full.exists():
            ass_master = _ass_ativo(d, m, slug)
            if ass_master.exists():
                raise SystemExit(
                    f"{ass_full} nao existe (so o master {ass_master.name}). "
                    f"Rode de novo: estudio.py karaoke {slug} "
                    f"(agora gera tambem o perfil pov_cena).")
            raise SystemExit(
                f"karaoke pedido mas {ass_full} nao existe. "
                f"Rode antes: estudio.py karaoke {slug}")
        ass_trecho = d / "legendas" / f"{slug}_pov_{int(de)}s.ass"
        # `de` e tempo do MASTER (corte); o .ass e tempo do CORPO — subtrai a intro
        _rebase_ass(ass_full, _de_ass_corpo(de, master), dur, ass_trecho)

    saida = d / "saidas" / f"{slug}_pov_{int(de)}s_9x16.mp4"
    pov_mod.gerar_pov(
        master=master, inicio=de, dur=dur, saida=saida,
        gancho=gancho,
        anime=m.get("anime", ""),
        tema=tema or m.get("faixa", ""),
        cor=m.get("cor", {}).get("destaque", "#FF8C00"),
        marca=marca, handle=handle,
        personagem=m.get("personagem", ""),
        com_intro=com_intro,
        ass=ass_trecho,
    )
    print(f"POV pronto: {saida}")
    return 0



def _audio_clipe(d: Path, t: dict, m: dict) -> Path:
    valor = t.get("audio") or m.get("audio_fonte")
    if not valor:
        raise SystemExit("Defina audio em timeline.json ou audio_fonte no projeto.json")
    return _resolver(d, valor)


def cmd_clipes(slug: str) -> int:
    """Baixa o material bruto listado em projeto.json -> clips_fontes."""
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    fontes = m.get("clips_fontes") or []
    if not fontes:
        raise SystemExit("Defina 'clips_fontes' no projeto.json "
                         "([{nome,url,de,ate,nota}, ...]).")
    destino = _resolver(d, m.get("clips_dir", "clips_raw"))
    print(f"baixando {len(fontes)} fonte(s) -> {destino}")
    resultados = dl_mod.baixar(fontes, destino)

    ok = [r for r in resultados if not r["erro"] and not r.get("pulado")]
    falhas = [r for r in resultados if r["erro"]]
    for r in resultados:
        if r["erro"]:
            print(f"  FALHA {r['nome']}: {r['erro'][:160]}")
        elif r.get("pulado"):
            print(f"  PULA  {r['nome']}.mp4  {r.get('dur',0):.1f}s (ja existe)")
        else:
            print(f"  OK    {r['nome']}.mp4  {r.get('dur',0):.1f}s")

    # auditoria de imagem por clipe — limiar de FONTE (tolera slow-mo do AMV,
    # reprova so tela morta real ou clipe estatico).
    print("\n== auditoria de imagem dos clipes (limiar de fonte) ==")
    reprovados = []
    for r in [x for x in resultados if not x["erro"]]:
        rel = img_mod.auditar_fonte(r["arquivo"], r["nome"])
        estado = "OK" if rel.aprovado else "REPROVA"
        print(f"  [{estado}] {r['nome']}  dur={rel.duracao}s  "
              f"morto={rel.pct_morto}%  congelado={rel.pct_congelado}%  pagina={rel.seg_pagina}s")
        if not rel.aprovado:
            reprovados.append((r["nome"], rel.motivos))
    # porteiro de fonte: marca d'agua/logo (corrige na hora) e legenda queimada (marca cenas)
    print("\n== fonte limpa: marca d'agua e legenda queimada ==")
    fonte_ok = cmd_fonte_limpa(slug, corrigir=True) == 0
    if falhas or reprovados or not fonte_ok:
        print("\nAUDITORIA REPROVADA:")
        for r in falhas:
            print(f"  - download {r['nome']}: {r['erro'][:120]}")
        for nome, motivos in reprovados:
            print(f"  - imagem {nome}: {'; '.join(motivos)}")
        if not fonte_ok:
            print("  - fonte: marca d'agua que a limpeza nao removeu (ver qa/fonte_limpa.md)")
        return 1
    print(f"\nauditoria dos clipes: OK ({len(ok)} clipes)")
    return 0


def _energia_db_em(energia: list) -> "callable | None":
    """Medidor (a, b) -> dBFS a partir da lista [(inicio_s, db)] de `energia_vocal` (janelas de
    0,5 s). Devolve o MENOR nivel das janelas cobertas (um trecho com voz em qualquer parte nao
    e silencio). Sem energia (stem vocal ausente) devolve None: regra desligada."""
    if not energia:
        return None

    def medir(a: float, b: float) -> float:
        cobertas = [db for t, db in energia if t < b and t + 0.5 > a]
        return min(cobertas) if cobertas else -200.0

    return medir


def cmd_transcrever(slug: str, modelo: str = None) -> int:
    """Gera entradas/transcricao.json (onset word-level da voz, via Whisper)."""
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    audio = _resolver(d, m.get("audio_fonte", ""))
    if not audio.exists():
        raise SystemExit(f"audio ausente: {audio} (defina audio_fonte no projeto.json)")

    destino = _resolver(d, m.get("palavras_vocal", "entradas/transcricao.json"))

    # letra oficial como initial_prompt: ancora nomes proprios (Eren, titan...)
    letra_cfg = m.get("letra", "LETRA.txt")
    letra_arq = letra_cfg.get("linhas") or letra_cfg.get("arquivo") \
        if isinstance(letra_cfg, dict) else letra_cfg
    letra_path = _resolver(d, letra_arq) if letra_arq else None
    prompt = None
    if letra_path and letra_path.exists():
        prompt = letra_path.read_text(encoding="utf-8")[:900]

    linhas_letra = []
    if letra_path and letra_path.exists():
        linhas_letra = sl_mod.extrair_linhas_suno(letra_path.read_text(encoding="utf-8"))
    if prompt:
        # marcadores [Intro]/[Refrao] nao sao cantados; nao ancoram o Whisper
        prompt = " ".join(sl_mod.extrair_linhas_suno(prompt))[:900]

    # Fonte preferida: stem vocal (sem beat, menos alucinacao). Transcricao em
    # blocos independentes com sobreposicao: o Whisper em passada unica pula
    # dezenas de segundos cantados (visto no Gojo: 31-58 s sem nenhuma palavra).
    from vx import projeto as vx_projeto
    vocal = vx_projeto.stem(d, "vocals", m)
    fonte = vocal if vocal.exists() else audio
    mdl = modelo or "large-v3"
    if destino.exists():
        bak = destino.with_suffix(".json.bak")
        bak.write_bytes(destino.read_bytes())
    print(f"transcrevendo {fonte.name} com Whisper '{mdl}' em blocos de 30 s...")
    energia = tr_mod.energia_vocal(vocal) if vocal.exists() else []
    try:
        modelo_w = tr_mod.carregar_modelo(mdl)
        dados = tr_mod.transcrever_chunked(fonte, modelo=mdl, prompt=prompt,
                                           chunk_seconds=30, overlap=4, model=modelo_w)
        # palavra que cai em silencio do stem vocal com baixa confianca e alucinacao (ver
        # transcrever.palavra_em_silencio): medida na mesma energia que a lacuna usa
        n_lixo = tr_mod.limpar_alucinacoes(dados, _energia_db_em(energia))
        if n_lixo:
            print(f"  removidas {n_lixo} palavras de alucinacao/degeneradas do Whisper")
        if energia:
            # 2a passada so nos trechos com voz e sem palavras, sem prompt
            restantes = tr_mod.preencher_lacunas(fonte, dados, energia, modelo=mdl, model=modelo_w)
            for x in dados.get("lacunas_preenchidas", []):
                print(f"  lacuna {x['inicio']}-{x['fim']}s preenchida: {x['palavras']} palavras")
            # 3a passada: lacunas que ainda tem LETRA pendente, com so essas frases de prompt
            if linhas_letra:
                tr_mod.passada_guiada(fonte, dados, energia, linhas_letra, modelo=mdl, model=modelo_w)
                for x in dados.get("passada_guiada", []):
                    print(f"  3a passada lacuna {x['inicio']}-{x['fim']}s (janela {x['janela'][0]}-{x['janela'][1]}s): "
                          f"{x['palavras']} palavras ({x['pendentes']} tokens pendentes) -> "
                          f"{'ACEITA' if x['aceita'] else 'rejeitada'}{' (com prompt)' if x['com_prompt'] else ''}")
    except Exception as exc:  # modelo nao baixado localmente etc.
        print(f"  aviso: transcricao em blocos falhou ({exc}); usando passada unica")
        dados = tr_mod.transcrever(fonte, destino, modelo=mdl, initial_prompt=prompt)
    dados["fonte"] = str(fonte.relative_to(d)) if fonte.is_relative_to(d) else str(fonte)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

    dur = tl_mod.duracao(audio)
    erros = tr_mod.auditar(dados, dur)
    if energia and dados.get("words"):
        primeira = min(float(w["start"]) for w in dados["words"])
        lacunas = [x for x in tr_mod.lacunas_vocais(dados["words"], energia)
                   if x["fim"] > primeira + 0.5]          # vocalise antes do 1o verso: nao tem letra
        if linhas_letra:
            # so reprova lacuna com LETRA pendente; voz sem letra (vocalise/ad-lib/outro) nao
            lacunas, vocalises = tr_mod.classificar_lacunas(lacunas, dados["words"],
                                                            tr_mod.tokens_da_letra(linhas_letra))
            for v in vocalises:
                print(f"  voz sem letra pendente {v['inicio']}-{v['fim']}s: vocalise/ad-lib (ok)")
        for lac in lacunas:
            pend = " ".join(lac.get("letra_pendente") or [])[:70]
            erros.append(f"voz sem transcricao de {lac['inicio']}s a {lac['fim']}s "
                         f"({lac['voz_s']}s cantados sem palavras)" + (f"; letra pendente: {pend}" if pend else ""))
    print(f"transcrito: {len(dados['words'])} palavras, "
          f"{len(dados['segments'])} segmentos -> {destino}")
    print(f"audio {dur:.2f}s | ultima palavra {dados['words'][-1]['end']:.2f}s")
    if erros:
        print("AUDITORIA REPROVADA:")
        for e in erros[:12]:
            print("  - " + e)
        return 1
    print("auditoria da transcricao: OK")
    return 0


def cmd_etapas(slug: str | None) -> int:
    """Lista a ordem da esteira (registro vx/etapas.py) e, com slug, entradas ausentes."""
    from vx import etapas as vx_etapas
    d = dir_projeto(slug) if slug else None
    m = carregar_manifesto(slug) if slug else {}
    for e in vx_etapas.TODAS:
        faltam = []
        if d is not None:
            for rel in e.le:
                if "*" in rel or "<run_id>" in rel:
                    continue
                if rel.startswith("<projeto.json:"):
                    rel = m.get(rel[len("<projeto.json:"):-1], "")
                    if not rel:
                        faltam.append("(campo legenda_ass vazio no manifesto)")
                        continue
                alvo = (RAIZ / rel) if rel.startswith("assets/") else d / rel.format(slug=slug)
                if not alvo.exists() and not rel.endswith("transcricao_canonica.json"):
                    faltam.append(rel.format(slug=slug))
        marca = "bloqueia" if e.bloqueante else "info"
        linha = f"  {e.fase:<9} {e.nome:<15} [{marca}] {e.descricao}"
        print(linha)
        for f in faltam:
            print(f"               falta: {f}")
    return 0


def cmd_cache(slug: str | None, limpar: bool = False) -> int:
    """Mostra (ou limpa) o cache por hash de entrada de um projeto.

    Responde a pergunta operacional: "o que ja esta pronto e pode ser reaproveitado,
    e o cache esta realmente pagando o proprio custo?". `usos` e o dado-chave --
    uma entrada com usos alto e uma etapa que repete; usos 0/1 nao compensa.
    """
    from vx import cache as vx_cache
    from vx import etapas as vx_etapas

    if not slug:
        print("informe o slug: estudio.py cache <slug> [--limpar]")
        return 2
    p = dir_projeto(slug)

    if limpar:
        removidos = vx_cache.invalidar(p)
        print(f"cache limpo: {removidos} arquivo(s) removido(s) de {vx_cache.cache_dir(p)}")
        return 0

    dados = vx_cache.resumo(p)
    cacheaveis = [e.nome for e in vx_etapas.TODAS if e.cacheavel]
    print(f"cache de '{slug}' em {dados['diretorio']}")
    print(f"  {'ETAPA':<18} {'VARIACOES':>9} {'USOS':>6} {'TAMANHO':>9}")
    print("  " + "-" * 46)
    for nome in cacheaveis:
        info = dados["etapas"].get(nome)
        if not info:
            print(f"  {nome:<18} {'-':>9} {'-':>6} {'-':>9}")
            continue
        tam = info["bytes"]
        for unidade in ("B", "KB", "MB", "GB"):
            if tam < 1024 or unidade == "GB":
                texto = f"{tam:.0f}{unidade}" if unidade == "B" else f"{tam:.1f}{unidade}"
                break
            tam /= 1024
        print(f"  {nome:<18} {info['variacoes']:>9} {info['usos']:>6} {texto:>9}")
    print(f"\n  {dados['total_variacoes']} variacao(oes) guardada(s); "
          f"etapas nao cacheaveis (composicao/master) nao aparecem aqui.")
    return 0


def cmd_cerebro() -> int:
    """Regenera cerebro/etapas.md a partir do registro de etapas."""
    from vx import etapas as vx_etapas
    alvo = RAIZ / "cerebro" / "etapas.md"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(vx_etapas.documentacao() + "\n", encoding="utf-8")
    print(f"gerado {alvo}")
    import motion_lab as ml_mod
    alvo2 = RAIZ / "cerebro" / "biblioteca_motion.md"
    alvo2.write_text(ml_mod.documentacao_biblioteca() + "\n", encoding="utf-8")
    print(f"gerado {alvo2}")
    return 0


def cmd_auditar_letra(slug: str) -> int:
    """Porteiro letra x audio: o que esta na letra foi cantado, na ordem, e vice-versa."""
    import auditor_letra as al_mod
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    rel = al_mod.executar(d, m, slug)
    print(f"== auditar-letra {slug} ==")
    print(f"  letra {rel['palavras_letra']} palavras | audio {rel['palavras_audio']} "
          f"| casadas {rel['palavras_audio_casadas']}")
    for x in rel["lacunas_voz"]:
        print(f"  VOZ SEM TRANSCRICAO {x['inicio']}s-{x['fim']}s")
    for x in rel["cantado_fora_da_letra"]:
        print(f"  CANTADO FORA DA LETRA {x['inicio']}s-{x['fim']}s: {x['ouvido'][:70]}")
    for l in rel["linhas_sem_audio"] + rel["linhas_fracas"]:
        print(f"  LINHA NAO ACHADA [{l['cobertura']:.0%}] {l['texto'][:60]}")
    print(f"  relatorio: {d / 'qa' / 'auditoria_letra.md'}")
    print("  APROVADO" if rel["aprovado"] else "  REPROVADO: " + "; ".join(rel["motivos"]))
    return 0 if rel["aprovado"] else 1


def cmd_fonte_limpa(slug: str, corrigir: bool = False) -> int:
    """Porteiro de fonte: marca d'agua/logo (corrige) + legenda queimada (cena poluida)."""
    import fonte_limpa as fl_mod
    carregar_manifesto(slug)
    d = dir_projeto(slug)
    print(f"== fonte-limpa {slug} ==")
    rel = fl_mod.auditar_projeto(d, corrigir=corrigir)
    for nome, it in rel["clipes"].items():
        marca = f"marca {len(it['marca'])}" if it["marca"] else "sem marca"
        limp = (it.get("limpeza") or {}).get("acao", "")
        print(f"  {nome:<34} {marca:<10} {limp:<28} legenda {it['legenda_fracao']:.0%}")
    if (d / "scene_intelligence.json").is_file():
        import scene_intelligence as si_mod
        cat = json.loads((d / "scene_intelligence.json").read_text(encoding="utf-8"))
        n = si_mod.marcar_cenas_poluidas(d, cat)
        si_mod._write_catalog(d / "scene_intelligence.json", cat)
        print(f"  catalogo: {n} cena(s) com legenda queimada marcadas como poluidas")
    print(f"  relatorio: {d / 'qa' / 'fonte_limpa.md'}")
    for aviso in rel.get("avisos") or []:
        print(f"  aviso: {aviso}")
    print("  APROVADO" if rel["aprovado"] else "  REPROVADO: " + "; ".join(rel["motivos"]))
    return 0 if rel["aprovado"] else 1


def cmd_motion_lab(slug: str, de: float | None, dur: float, estilos: str = "") -> int:
    """LAB em teste: previas de tipografia em movimento sobre a cena real (nao entra no master)."""
    import motion_lab as ml_mod
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    lista = [e.strip() for e in estilos.split(",") if e.strip()] or None
    print(f"== motion-lab {slug} ==")
    try:
        rel = ml_mod.executar(d, m, slug, de=de, dur=dur, estilos=lista)
    except ValueError as exc:
        print(f"  ERRO: {exc}")
        return 1
    print(f"  janela {rel['de']:g}s +{rel['dur']:g}s | cor da cena {rel['acento']}")
    rc = rel["recorte"]
    print(f"  recorte do personagem: media {rc['media']:.0%} (min {rc['min']:.0%}, max {rc['max']:.0%})"
          + (f"  AVISO: {rc['aviso']}" if rc["aviso"] else ""))
    print(f"  {len(rel['previas'])} previa(s) em {d / 'lab' / 'motion'} (assistir e aprovar)")
    return 0


def cmd_transcricao_canonica(slug: str) -> int:
    """Offline large-v3 mix+vocal ASR, monotonically aligned to author lyrics."""
    m=carregar_manifesto(slug); d=dir_projeto(slug)
    letra=d/'suno_lyrics.txt'
    if not letra.exists(): raise SystemExit(f'letra autoral ausente: {letra}')
    # vocabulario canonico vem do manifesto (projeto.json -> vocabulario), nao do codigo
    voc=sl_mod.vocabulario_do_manifesto(m)
    linhas=[sl_mod.corrigir_vocabulario_canonico(x, voc) for x in sl_mod.extrair_linhas_suno(letra.read_text(encoding='utf-8'))]
    vocab=(', '.join(sorted(set(voc.values())))+'. ') if voc else ''
    prompt=(vocab+' '.join(linhas))[:4000]
    from vx import projeto as vx_projeto
    sources=[('mix',vx_projeto.audio(d,m)),('demucs_vocal',vx_projeto.stem(d,'vocals',m))]
    observations=[]
    for name,audio in sources:
        if not audio.exists(): raise SystemExit(f'fonte ASR ausente: {audio}')
        raw_path=d/'entradas'/f'asr_chunked_{name}_large-v3.json'
        if raw_path.exists():
            raw=json.loads(raw_path.read_text(encoding='utf-8'))
        else:
            raw=tr_mod.transcrever_chunked(audio,modelo='large-v3',prompt=prompt,chunk_seconds=30,overlap=4)
            raw_path.write_text(json.dumps(raw,ensure_ascii=False,indent=1),encoding='utf-8')
        observations.append({'source':name,'words':raw['words']})
        print(f'ASR {name}: {len(raw["words"])} palavras -> {raw_path}',flush=True)
    # Existing independent passes are timing evidence only; their misspellings never
    # replace canonical lyrics. The preview-vocal pass covers the disputed intro.
    for name,rel in [('prior_full_mix','entradas/transcricao.json'),('prior_preview_vocal','entradas/previa_asr.json')]:
        aux=d/rel
        if aux.exists(): observations.append({'source':name,'words':json.loads(aux.read_text(encoding='utf-8')).get('words',[])})
    result=sl_mod.construir_transcricao_canonica(linhas,observations)
    result.update({'model':'faster-whisper large-v3 local','lyrics_source':'suno_lyrics.txt',
                   'method':'overlapping 30s chunks; condition_on_previous_text=False; mix + Demucs vocal; monotonic expected-lyrics alignment'})
    out=d/'transcricao_canonica.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    audit=d/'qa'/'transcricao_canonica.md';audit.parent.mkdir(parents=True,exist_ok=True)
    lows=[w for w in result['words'] if w['confidence'] in {'low','gap'}]
    rows=['# Auditoria da transcrição canônica','',f'- Linhas: {len(result["lines"])}',f'- Palavras esperadas: {len(result["words"])}',f'- Identificadas no áudio: {result["audit"]["identified_words"]}',f'- Baixa confiança/lacunas: {len(lows)}','', '| Início | Fim | Confiança | Texto |','|---:|---:|---|---|']
    for line in result['lines']: rows.append(f'| {line["start"]} | {line["end"]} | {line["confidence"]} | {line["text"]} |')
    rows += ['', '## Palavras de baixa confiança ou lacunas']+[f'- `{w["word"]}`: {w["confidence"]}; evidência={w["evidence"]}' for w in lows]
    audit.write_text('\n'.join(rows)+'\n',encoding='utf-8')
    print(f'canônica: {out}\nauditoria: {audit}\nlacunas/baixa confiança: {len(lows)}')
    return 0


def cmd_timeline(slug: str) -> int:
    """Gera timeline.json cobrindo a musica (letra sincronizada + clipes) e audita."""
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)
    sync_path = d / "letra_sincronizada.json"
    if not sync_path.exists():
        raise SystemExit(f"{sync_path} ausente. Rode antes: estudio.py sincronizar {slug}")
    sync = json.loads(sync_path.read_text(encoding="utf-8"))
    audio = _resolver(d, m.get("audio_fonte", ""))
    if not audio.exists():
        raise SystemExit(f"audio ausente: {audio}")

    # ritmo de edicao: planos longos sao quebrados nos picos reais de 808
    from audio_reactive_fx import carregar_picos
    batidas = [float(e["tempo"]) for e in carregar_picos(d, m) if "tempo" in e]
    from vx import config as vx_config
    # ritmo: codigo < config/estudio.json[edicao] < projeto.json[edicao]
    edicao = vx_config.secao("edicao", mt_mod.EDICAO_PADRAO, m)
    tl = mt_mod.montar(d, sync, audio, batidas=batidas, edicao=edicao)
    # grava o caminho relativo do audio (o validador usa a timeline["audio"])
    tl["audio"] = m.get("audio_fonte")
    out = d / "timeline.json"
    out.write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"timeline: {out}  ({len(tl['segments'])} segmentos, "
          f"{tl['audio_duration']:.2f}s)")

    # auditoria: cobertura sem lacuna, fontes, limites
    erros = tl_mod.validar(d, tl, audio)
    if erros:
        print("AUDITORIA REPROVADA:")
        for e in erros[:15]:
            print("  - " + e)
        return 1
    n_lyric = sum(1 for s in tl["segments"] if s["type"] == "lyric")
    print(f"auditoria da timeline: OK  "
          f"({n_lyric} linhas cantadas, cobertura 0..{tl['audio_duration']:.2f}s sem lacuna)")
    # base limpa para a esteira recompor sempre do zero (vx/composicao.py)
    from vx import composicao as vx_comp
    vx_comp.registrar_base(d)
    print(f"timeline-base registrada: {d / vx_comp.ARQ_BASE}")
    return 0


def cmd_planejar(slug: str) -> int:
    d = dir_projeto(slug)
    t = tl_mod.carregar(d)
    erros = tl_mod.validar(d, t, _audio_clipe(d, t, carregar_manifesto(slug)))
    if erros:
        print("Timeline reprovada:\n" + "\n".join("- " + e for e in erros))
        return 1
    p = d / "entradas" / "transcricao.json"
    tr = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    t = dict(t, audio_duration=tl_mod.duracao(_audio_clipe(d, t, carregar_manifesto(slug))))
    plano = dir_mod.criar(t, tr)
    out = d / "plano_visual.json"
    out.write_text(json.dumps(plano, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Plano visual: {out} ({len(plano['shots'])} planos)")
    return 0


def cmd_renderizar_clipe(slug: str, inicio: float, dur: float,
                         legenda: bool, completo: bool = False, saida_path: str = None) -> int:
    d = dir_projeto(slug)
    t = tl_mod.carregar(d)
    m = carregar_manifesto(slug)
    audio = _audio_clipe(d, t, m)
    if completo:
        inicio, dur = 0, tl_mod.duracao(audio)
    if legenda and not m.get("legenda_ass"):
        raise SystemExit("Defina legenda_ass no projeto.json")
    ass = _resolver(d, m["legenda_ass"]) if legenda else None
    saida = d / "saidas" / (f"{slug}_novo_master.mp4" if completo
                            else f"{slug}_previa_{inicio:g}s.mp4")
    if saida_path:
        saida = Path(saida_path).resolve()
        if saida == _resolver(d, m.get("master", "")).resolve():
            raise ValueError("Saida explicita nao pode substituir o master aprovado")
        saida.parent.mkdir(parents=True, exist_ok=True)
    rc_mod.previa(d, t, audio, saida, inicio, dur, ass)
    if completo:
        vd, ad = rc_mod.duracoes_streams(saida)
        if abs(vd - ad) > .05 or abs(vd - tl_mod.duracao(audio)) > .5:
            raise RuntimeError(f"duração divergente: vídeo={vd:.3f}s áudio={ad:.3f}s")
    print(f"Render: {saida}")
    return 0

def cmd_filtros() -> int:
    flt_mod.listar()
    return 0


def cmd_filtrar(slug: str, efeitos: str, intensidade: float,
                alvo: str, saida: str = None) -> int:
    """Aplica uma cadeia de efeitos no master ou num corte do projeto.

    A cor de destaque vem do manifesto, entao `grade_cor` puxa a paleta do
    personagem sem precisar informar nada a mao.
    """
    m = carregar_manifesto(slug)
    d = dir_projeto(slug)

    if alvo == "master":
        entrada = _resolver(d, m.get("master", ""))
    else:
        entrada = Path(alvo) if Path(alvo).is_absolute() else (d / alvo)
    if not entrada.exists():
        raise SystemExit(f"entrada ausente: {entrada}")

    if saida:
        destino = Path(saida) if Path(saida).is_absolute() else (d / saida)
    else:
        sufixo = efeitos.replace(",", "-")
        destino = d / "saidas" / f"{entrada.stem}_fx_{sufixo}{entrada.suffix}"

    cor = m.get("cor", {}).get("destaque", "#FFFFFF")
    lista = [s for s in efeitos.split(",") if s.strip()]
    flt_mod.aplicar(entrada, destino, lista, cor=cor, intensidade=intensidade)
    print(f"pronto: {destino}")
    return 0


def cmd_avaliar(slug: str) -> int:
    rel = pesq_mod.avaliar_projeto(slug)
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    # console do Windows (cp1252) nao pode derrubar um comando por causa de um acento/kanji
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="estudio.py", add_help=True)
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("doutor")
    e = sub.add_parser("estado"); e.add_argument("slug", nargs="?")
    n = sub.add_parser("novo"); n.add_argument("slug")

    c = sub.add_parser("capa")
    c.add_argument("slug")
    c.add_argument("--quais", default="todas",
                   choices=["todas", "capa", "banner", "quadrada"])
    c.add_argument("--saida-dir", dest="saida_dir", default=None)

    ct = sub.add_parser("corte")
    ct.add_argument("slug")
    ct.add_argument("--de", type=float, required=True)
    ct.add_argument("--dur", type=float, default=None)
    ct.add_argument("--ate", type=float, default=None)
    ct.add_argument("--tema", required=True)

    cs = sub.add_parser("cortes"); cs.add_argument("slug")

    lg = sub.add_parser("legenda"); lg.add_argument("slug")
    lg.add_argument("--animacao", default="auto",
                    choices=["auto", "fade", "slide", "pop", "mix"],
                    help="estilo de animacao das legendas")
    sc = sub.add_parser("sincronia"); sc.add_argument("slug")
    al = sub.add_parser("auditar-letra", help="porteiro letra x audio (ordem, lacunas, trechos sem legenda)")
    al.add_argument("slug")
    et = sub.add_parser("etapas", help="ordem da esteira e, com slug, o que falta em cada etapa")
    et.add_argument("slug", nargs="?")
    ca = sub.add_parser("cache", help="cache por hash entre execucoes: o que esta guardado e quanto ja foi reaproveitado")
    ca.add_argument("slug", nargs="?")
    ca.add_argument("--limpar", action="store_true", help="apaga o cache do projeto")
    sub.add_parser("cerebro", help="regenera cerebro/etapas.md (vx/etapas.py) e cerebro/biblioteca_motion.md (biblioteca_motion.json)")
    sz = sub.add_parser("sincronizar"); sz.add_argument("slug")
    kk = sub.add_parser("karaoke", help="legenda karaoke fill-sweep word-level")
    kk.add_argument("slug")

    rt = sub.add_parser("ritmo")
    rt.add_argument("slug")
    rt.add_argument("--gravar", action="store_true")

    im = sub.add_parser("imagem"); im.add_argument("slug")
    qa = sub.add_parser("qa"); qa.add_argument("slug")

    au = sub.add_parser("audio"); au.add_argument("slug")
    rl = sub.add_parser("relatorio"); rl.add_argument("slug")

    ps = sub.add_parser("pesquisar")
    ps.add_argument("assunto", choices=["tendencias", "personagem"])
    ps.add_argument("arg", nargs="?")

    av = sub.add_parser("avaliar"); av.add_argument("slug")

    pv = sub.add_parser("pov", help="corte POV 9:16 para Shorts")
    pv.add_argument("slug")
    pv.add_argument("--de", type=float, required=True)
    pv.add_argument("--dur", type=float, default=None)
    pv.add_argument("--ate", type=float, default=None)
    pv.add_argument("--gancho", required=True,
                    help="a frase que faz a pergunta no primeiro frame")
    pv.add_argument("--tema", default=None)
    pv.add_argument("--marca", default="VX RAPS")
    pv.add_argument("--handle", default="@VXRaps")
    pv.add_argument("--com-intro", dest="com_intro", action="store_true",
                    help="cola a intro antes do gancho (desligado de proposito)")
    pv.add_argument("--karaoke", action="store_true",
                    help="queima a legenda karaoke (\\kf) do slug na cena")

    sub.add_parser("filtros", help="lista efeitos e receitas de VFX")
    tc = sub.add_parser("transcrever", help="gera transcricao.json (Whisper word-level)")
    tc.add_argument("slug")
    tc.add_argument("--modelo", default=None,
                    help="modelo Whisper (tiny/base/small/medium/large-v3)")
    tcc = sub.add_parser("transcricao-canonica", help="alinha letra autoral ao ASR local mix+vocal")
    tcc.add_argument("slug")
    cl = sub.add_parser("clipes", help="baixa material bruto (clips_fontes do manifesto)")
    cl.add_argument("slug")
    tm = sub.add_parser("timeline", help="gera timeline.json cobrindo a musica")
    tm.add_argument("slug")
    sci = sub.add_parser("catalogar-cenas", help="VX Scene Intelligence: indexa o conteudo visual real dos clips")
    sci.add_argument("slug")
    sci.add_argument("--force", action="store_true", help="reanalisar mesmo clips sem mudanca")
    sci.add_argument("--interval", type=float, default=scene_intel_mod.DEFAULT_SAMPLE_INTERVAL)
    scm = sub.add_parser("cenas-auto", help="casa automaticamente letra/narrativa com cenas do anime")
    scm.add_argument("slug")
    scm.add_argument("--planejar", action="store_true", help="mostra decisoes sem alterar timeline")
    scm.add_argument("--force-catalog", action="store_true", help="reanalisar catalogo visual antes do matching")
    pl = sub.add_parser("planejar"); pl.add_argument("slug")
    sub.add_parser("chroma-auto", help="tela verde vira cena composta (fundo + recorte + aura pulsando)").add_argument("slug")
    fl_p = sub.add_parser("fonte-limpa", help="porteiro de fonte: marca d'agua/logo e legenda queimada nos clipes")
    fl_p.add_argument("slug")
    fl_p.add_argument("--corrigir", action="store_true", help="esconde a marca (recorte/delogo); original em _originais/")
    rf = sub.add_parser("referencia", help="raio-x de video de referencia (url ou mp4) -> referencias/<id>/analise.md")
    rf.add_argument("fonte")
    rf.add_argument("--comparar", default=None, help="mp4 nosso para comparar lado a lado")
    ml = sub.add_parser("motion-lab", help="LAB (em teste): tipografia em movimento sobre a cena real -> lab/motion/")
    ml.add_argument("slug")
    ml.add_argument("--de", type=float, default=None, help="inicio em segundos (padrao: 1o refrao)")
    ml.add_argument("--dur", type=float, default=4.0)
    ml.add_argument("--estilos", default="", help="lista separada por virgula (padrao: todos)")
    pr = sub.add_parser("previa-clipe"); pr.add_argument("slug")
    pr.add_argument("--de", type=float, required=True)
    pr.add_argument("--dur", type=float, required=True)
    pr.add_argument("--legenda", action="store_true")
    rc = sub.add_parser("render-clipe"); rc.add_argument("slug")
    rc.add_argument("--legenda", action="store_true")
    rc.add_argument("--saida", default=None, help="destino explicito do candidato")
    
    # Novos módulos PRO
    sub.add_parser("movimento", help="analisa optical flow e picos de impacto de clipes").add_argument("video")
    sub.add_parser("subgrave", help="detecta impactos de 808/subgrave no audio").add_argument("audio")
    sub.add_parser("curadoria", help="audita clipe contra watermarks e CapCut").add_argument("video")
    ip = sub.add_parser("impacto", help="gera tipografia cinematografica anime")
    ip.add_argument("palavra")
    ip.add_argument("--sub", default="")
    ip.add_argument("--aura", default="#FF4500")

    ipp = sub.add_parser("impacto-pro", help="VX Graphics Pro: motion design premium automatico")
    ipp.add_argument("slug")
    ipp.add_argument("--word", default=None, help="palavra manual; sem ela o diretor escolhe punchlines")
    ipp.add_argument("--sub", default="", help="texto secundario da cena manual")
    ipp.add_argument("--preset", default="auto", help="auto ou preset do catalogo VX Graphics")
    ipp.add_argument("--layout", default="auto", help="auto, hero_center, lyric_punchline, energy_ring, impact_fullscreen")
    ipp.add_argument("--dur", type=float, default=1.8)
    ipp.add_argument("--tempo", type=float, default=None, help="tempo da faixa para reatividade real ao 808")
    ipp.add_argument("--energia", type=float, default=0.88)
    ipp.add_argument("--max-cenas", type=int, default=6)
    ipp.add_argument("--saida", default=None, help="saida da cena manual relativa ao projeto ou absoluta")
    ipp.add_argument("--planejar", action="store_true", help="gera somente o plano visual JSON")

    tit_p = sub.add_parser("titulos", help="VX Titulos: Title Card de abertura + End Card no corpo do AMV")
    tit_p.add_argument("slug")
    tit_p.add_argument("--planejar", action="store_true")
    cia_p = sub.add_parser("cenas-ia", help="VX Cenas IA: gera cenas no ComfyUI onde o material real ficou fraco")
    cia_p.add_argument("slug")
    cia_p.add_argument("--planejar", action="store_true", help="mostra trechos/prompts sem gerar nem alterar a timeline")

    map_auto = sub.add_parser("manga-auto", help="VX Manga Auto: insere raros manga panels em climax da letra")
    map_auto.add_argument("slug")
    map_auto.add_argument("--planejar", action="store_true", help="analisa candidatos sem alterar a timeline")

    gap = sub.add_parser("graficos-auto", help="VX Graphics Auto: escolhe textos pela letra e injeta na timeline")
    gap.add_argument("slug")
    gap.add_argument("--planejar", action="store_true", help="analisa letra/audio sem alterar a timeline")

    fq = sub.add_parser("folha-quadro",
                        help="auditoria quadro a quadro do master (motion, legenda, cartao, cor)")
    fq.add_argument("slug")
    fq.add_argument("--fps", type=float, default=None,
                    help="quadros por segundo; padrao e TODOS os quadros do master (nao perder nenhum)")
    fq.add_argument("--geral", action="store_true",
                    help="so a folha geral do video inteiro, sem as folhas por take")
    sub.add_parser("cinemascope", help="gera filtro de barras pretas de cinema").add_argument("--altura", type=int, default=140)
    sub.add_parser("colorgrade", help="retorna filtro de cor por arquétipo").add_argument("estilo", choices=list(col_mod.RECEITAS_COLOR_GRADE.keys()))
    sub.add_parser("speedlines", help="gera frames de linhas de açao anime").add_argument("--pasta", default="speedlines_fx")
    soc = sub.add_parser("social", help="gera pacote 3x shorts + copys do master")
    soc.add_argument("slug")
    
    # Módulos Ultra Pro
    stem_p = sub.add_parser("stems", help="separa stems (voz/bateria/808) via IA na GPU")
    stem_p.add_argument("audio")
    stem_p.add_argument("--saida", default="stems_saida")

    mb_p = sub.add_parser("motionblur", help="aplica motion blur cinemático via optical flow")
    mb_p.add_argument("video")
    mb_p.add_argument("saida")
    mb_p.add_argument("--intensidade", type=float, default=1.2)

    tab_p = sub.add_parser("tumbas-ab", help="gera conjunto de miniaturas A/B de alto CTR")
    tab_p.add_argument("frame")
    tab_p.add_argument("slug")

    capa_ia_p = sub.add_parser("capa-ia", help="gera miniatura com IA (local ComfyUI/SDXL por padrao)")
    capa_ia_p.add_argument("slug")
    capa_ia_p.add_argument("--motor", choices=["local", "remoto"], default="local")
    capa_ia_p.add_argument("--prompt", default=None, help="local: tags extras; remoto: prompt completo")
    capa_ia_p.add_argument("--seed", type=int, default=None)
    capa_ia_p.add_argument("--ref", default=None, help="frame de referencia (img2img, so local)")
    capa_ia_p.add_argument("--denoise", type=float, default=0.6)
    capa_ia_p.add_argument("--forcar", action="store_true", help="ignora o cache")
    capa_ia_p.add_argument("--variacoes", type=int, default=4, help="VX Image Critic escolhe a melhor")

    gi_p = sub.add_parser("gerar-imagem", help="VX Image Local: gera imagens SDXL na GPU via ComfyUI")
    gi_p.add_argument("slug")
    gi_p.add_argument("--tipo", choices=["capa", "fundo", "vertical", "quadrado", "cena"], default="capa")
    gi_p.add_argument("--cena", default=None, help="tags extras da cena (ingles, estilo danbooru)")
    gi_p.add_argument("--seed", type=int, default=None)
    gi_p.add_argument("--variacoes", type=int, default=1)
    gi_p.add_argument("--ref", default=None, help="imagem de referencia para img2img")
    gi_p.add_argument("--denoise", type=float, default=0.6)
    gi_p.add_argument("--forcar", action="store_true", help="ignora o cache")

    cst_p = sub.add_parser("comfy-status", help="checa ComfyUI local, GPU e checkpoint do VX Image Local")
    cst_p.add_argument("--iniciar", action="store_true", help="sobe o ComfyUI automaticamente se estiver offline")
    sub.add_parser("comfy-parar", help="encerra o ComfyUI que o estudio subiu (libera a GPU)")
    sh_p = sub.add_parser("shorts", help="VX Shorts: pacote vertical automatico (trechos, gancho, letra, metadados)")
    sh_p.add_argument("slug")
    sh_p.add_argument("--n", type=int, default=3)
    sh_p.add_argument("--dur", type=float, default=30.0)
    sh_p.add_argument("--planejar", action="store_true")
    sub.add_parser("lancamento", help="consolida master+artes+shorts+copy em saidas/pacote_lancamento.json").add_argument("slug")
    pm_p = sub.add_parser("promover", help="candidato aprovado pelo usuario -> master (backup do anterior)")
    pm_p.add_argument("slug")
    pm_p.add_argument("run_id")
    en_p = sub.add_parser("entrega", help="PACOTE COMPLETO: video+thumb+titulo/descricao/tags+shorts+textos (confere tudo)")
    en_p.add_argument("slug")
    en_p.add_argument("--n", type=int, default=3, help="quantidade de shorts")
    en_p.add_argument("--forcar-artes", action="store_true")
    art_p = sub.add_parser("artes-ia", help="pacote de lancamento IA: thumb YouTube + banner + capa 3000px")
    art_p.add_argument("slug")
    art_p.add_argument("--forcar", action="store_true", help="ignora o cache de imagens")

    # Novos Módulos Masterclass (Referência Jiraiya)
    sb_p = sub.add_parser("card-saber", help="gera take de apresentaçao com efeito saber neon")
    sb_p.add_argument("frame")
    sb_p.add_argument("nome")
    sb_p.add_argument("saida")

    sub.add_parser("legendas-mugen", help="converte LETRA.txt para ASS com destaques ciano/vermelho").add_argument("slug")
    sub.add_parser("snap-impact", help="gera filtro de snap zoom punch + flash").add_argument("tempo", type=float)
    sub.add_parser("ghosting", help="gera filtro de eco visual / frame ghosting").add_argument("tempo", type=float)

    # Módulos de Elite Final
    sc_p = sub.add_parser("smartcrop", help="auto-reframing 9:16 com rastreamento de açao")
    sc_p.add_argument("video")
    sc_p.add_argument("saida")

    sub.add_parser("auditar-ritmo", help="avalia cuts per minute e dinamica de retençao").add_argument("slug")

    # Legendas dinâmicas
    sub.add_parser("legenda-palavra", help="gera legenda word-by-word (palavra a palavra)").add_argument("slug")
    sub.add_parser("legenda-neon", help="gera legenda word-by-word com motion graphics de neon").add_argument("slug")

    # Módulos de Viralização Máxima
    lp_p = sub.add_parser("loop-infinito", help="cria loop perfeito sem corte para shorts")
    lp_p.add_argument("video")
    lp_p.add_argument("saida")

    pan_p = sub.add_parser("paineis", help="gera split screen de mangá")
    pan_p.add_argument("--modo", default="2_paineis_h", choices=["2_paineis_h", "2_paineis_v"])

    spl_p = sub.add_parser("color-splash", help="isola uma cor e deixa o resto em PB")
    spl_p.add_argument("cor", choices=["vermelho", "verde", "azul_ciano", "amarelo"])
    spl_p.add_argument("--inicio", type=float, default=0.0)
    spl_p.add_argument("--dur", type=float, default=2.0)

    hk_p = sub.add_parser("hook-retencao", help="gera card de gancho de alta retençao nos 3s")
    hk_p.add_argument("texto")
    hk_p.add_argument("saida")

    px_p = sub.add_parser("pixel-sort", help="transiçao de pixel sort / datamosh")
    px_p.add_argument("tempo", type=float)

    fl = sub.add_parser("filtrar", help="aplica efeitos num video do projeto")
    fl.add_argument("slug")
    fl.add_argument("--efeitos", required=True,
                    help="nomes separados por virgula, ou uma receita "
                         "(amv, impacto, suave, cru, short)")
    fl.add_argument("--intensidade", type=float,
                    default=flt_mod.INTENSIDADE_PADRAO)
    fl.add_argument("--alvo", default="master",
                    help="'master' ou caminho relativo ao projeto")
    fl.add_argument("--saida", default=None)

    rev = sub.add_parser("revisao", help="render manifest-driven revision with technical QA")
    rev.add_argument("slug")
    rev.add_argument("--previa", action="store_true", help="Render only the explicit preview manifest, never a master")
    mm = sub.add_parser("motion-manga", help="render offline layered manga take, not a master")
    mm.add_argument("slug")
    mm.add_argument("--config", default="motion_manga.json")
    mm.add_argument("--prepare-only", action="store_true")
    ep = sub.add_parser("esteira", help="pipeline com preflight, logs e QA da saida nova")
    ep.add_argument("slug")
    ep.add_argument("--planejar", action="store_true", help="somente validar entradas e mostrar etapas")
    ep.add_argument("--rebuild-clean", action="store_true",
                    help="backup + remove derivados/legado + recria timeline e todos os efeitos novos")
    ep.add_argument("--resume", nargs="?", const="auto", default=None,
                    help="retoma do checkpoint (sem valor = mais recente): pula etapa ja concluida "
                         "com as mesmas entradas e saidas no lugar")
    ep.add_argument("--isolado", action="store_true",
                    help="roda cada etapa em subprocess (comportamento antigo); por padrao as "
                         "etapas rodam in-process, com traceback real no log e nas metricas")
    ep.add_argument("--sem-cache", action="store_true",
                    help="ignora o cache por hash entre execucoes e refaz toda etapa cacheavel "
                         "(--rebuild-clean ja implica isso)")
    rb = sub.add_parser("rebuild-total", help="alias de producao limpa: equivale a esteira --rebuild-clean")
    rb.add_argument("slug")
    rb.add_argument("--planejar", action="store_true")
    a = p.parse_args(argv)
    if a.cmd in ("esteira", "rebuild-total"):
        from pipeline_autonomo_pro import executar_esteira_completa
        try:
            clean = bool(getattr(a, "rebuild_clean", False) or a.cmd == "rebuild-total")
            return executar_esteira_completa(a.slug, a.planejar, clean_rebuild=clean,
                                             resume=getattr(a, "resume", None),
                                             isolado=getattr(a, "isolado", False),
                                             cache=not getattr(a, "sem_cache", False))
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 1
    if a.cmd == "motion-manga":
        from motion_manga import executar
        return executar(a.slug, a.config, a.prepare_only)
    if a.cmd == "revisao":
        from pipeline_autonomo_pro import executar_revisao
        return executar_revisao(a.slug, previa=a.previa)
    if not a.cmd:
        print(__doc__)
        return 0

    if a.cmd == "doutor":
        return cmd_doutor()
    if a.cmd == "estado":
        return cmd_estado(a.slug)
    if a.cmd == "novo":
        return cmd_novo(a.slug)
    if a.cmd == "capa":
        return cmd_capa(a.slug, a.quais, a.saida_dir)
    if a.cmd == "corte":
        dur = _dur_do_corte(a)
        if dur is None:
            raise SystemExit("informe --dur ou --ate")
        return cmd_corte(a.slug, a.de, dur, a.tema)
    if a.cmd == "cortes":
        return cmd_cortes(a.slug)
    if a.cmd == "legenda":
        return cmd_legenda(a.slug, a.animacao)
    if a.cmd == "auditar-letra":
        return cmd_auditar_letra(a.slug)
    if a.cmd == "etapas":
        return cmd_etapas(a.slug)
    if a.cmd == "cache":
        return cmd_cache(a.slug, getattr(a, "limpar", False))
    if a.cmd == "cerebro":
        return cmd_cerebro()
    if a.cmd == "sincronia":
        return cmd_sincronia(a.slug)
    if a.cmd == "sincronizar":
        return cmd_sincronizar(a.slug)
    if a.cmd == "karaoke":
        return cmd_karaoke(a.slug)
    if a.cmd == "ritmo":
        return cmd_ritmo(a.slug, a.gravar)
    if a.cmd == "imagem":
        return cmd_imagem(a.slug)
    if a.cmd == "qa":
        return cmd_qa(a.slug)
    if a.cmd == "audio":
        return cmd_audio(a.slug)
    if a.cmd == "relatorio":
        return cmd_relatorio(a.slug)
    if a.cmd == "pesquisar":
        return cmd_pesquisar(a.assunto, getattr(a, "arg", None))
    if a.cmd == "avaliar":
        return cmd_avaliar(a.slug)
    if a.cmd == "pov":
        dur = _dur_do_corte(a)
        if dur is None:
            raise SystemExit("informe --dur ou --ate")
        return cmd_pov(a.slug, a.de, dur, a.gancho, a.tema,
                       a.handle, a.marca, a.com_intro, a.karaoke)
    if a.cmd == "filtros":
        return cmd_filtros()
    if a.cmd == "transcrever":
        return cmd_transcrever(a.slug, a.modelo)
    if a.cmd == "transcricao-canonica":
        return cmd_transcricao_canonica(a.slug)
    if a.cmd == "clipes":
        return cmd_clipes(a.slug)
    if a.cmd == "timeline":
        return cmd_timeline(a.slug)
    if a.cmd == "catalogar-cenas":
        res = scene_intel_mod.catalogar_projeto(
            dir_projeto(a.slug), force=a.force, sample_interval=a.interval)
        resumo = {
            "engine": "vx_scene_intelligence",
            "slug": a.slug,
            "clips_total": res.get("clips_total", 0),
            "eligible_clips": res.get("eligible_clips", 0),
            "scenes_total": res.get("scenes_total", 0),
            "cache": res.get("cache", {}),
            "errors": res.get("errors", []),
        }
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0 if not res.get("errors") else 1
    if a.cmd == "cenas-auto":
        res = scene_match_mod.executar(
            dir_projeto(a.slug), somente_planejar=a.planejar,
            force_catalog=a.force_catalog)
        resumo = {
            "engine": "vx_semantic_scene_matcher",
            "slug": a.slug,
            "status": res.get("status"),
            "applied": res.get("applied", False),
            "matched_segments": res.get("matched_segments", 0),
            "catalog": res.get("catalog", {}),
            "sample_decisions": [{
                "index": d.get("index"), "type": d.get("type"),
                "text": d.get("text", ""), "clip": d.get("clip"),
                "src": d.get("src"), "score": d.get("score"),
                "concepts": d.get("concepts", []),
                "scene_tags": d.get("scene_tags", [])
            } for d in res.get("decisions", []) if d.get("status") == "matched"][:12],
        }
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "planejar":
        return cmd_planejar(a.slug)
    if a.cmd == "chroma-auto":
        import chroma_auto as ch_mod
        carregar_manifesto(a.slug)
        res = ch_mod.executar(a.slug)
        print(f"== chroma-auto {a.slug} == {res['status']}: {res['takes']} take(s) de tela verde recompostos")
        for x in res.get("itens", []):
            print(f"  {x['start']:.2f}-{x['end']:.2f}s  {x['fonte']}@{float(x['src']):.1f}s -> {x['take']}")
        return 0
    if a.cmd == "fonte-limpa":
        return cmd_fonte_limpa(a.slug, a.corrigir)
    if a.cmd == "referencia":
        import analisar_referencia as ref_mod
        ref_mod.executar(a.fonte, a.comparar)
        return 0
    if a.cmd == "motion-lab":
        return cmd_motion_lab(a.slug, a.de, a.dur, a.estilos)
    if a.cmd == "previa-clipe":
        return cmd_renderizar_clipe(a.slug, a.de, a.dur, a.legenda)
    if a.cmd == "render-clipe":
        return cmd_renderizar_clipe(a.slug, 0, 0, a.legenda, True, a.saida)
    if a.cmd == "filtrar":
        return cmd_filtrar(a.slug, a.efeitos, a.intensidade, a.alvo, a.saida)
    if a.cmd == "movimento":
        res = mov_mod.analisar_fluxo_movimento(a.video)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "subgrave":
        evs = bass_mod.extrair_picos_subgrave(a.audio)
        print(f"Total de impactos 808/sub-grave detectados: {len(evs)}")
        print(json.dumps(evs[:10], indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "curadoria":
        rel = cur_mod.auditar_clipe_completo(a.video)
        print(json.dumps(rel, indent=2, ensure_ascii=False))
        return 0 if rel.get("aprovado_para_esteira") else 1
    if a.cmd == "impacto":
        p = Path(f"artes_impacto_{a.palavra.lower()}")
        frames = imp_mod.gerar_sequencia_animacao_impacto(a.palavra, p, subtexto=a.sub, cor_aura=a.aura)
        print(f"Gerados {len(frames)} frames de impacto em: {p}")
        return 0
    if a.cmd == "manga-auto":
        res = manga_auto_mod.executar(a.slug, somente_planejar=a.planejar)
        resumo = {
            "engine": "vx_manga_auto",
            "slug": a.slug,
            "status": res.get("status"),
            "applied": res.get("applied", False),
            "candidate_count": res.get("candidate_count", 0),
            "selected": [{
                "start": c.get("start"), "end": c.get("end"),
                "text": c.get("text"), "score": c.get("score"),
                "concepts": c.get("concepts", []),
                "beat_score": c.get("beat_score"),
                "visual_score": c.get("visual_score")
            } for c in res.get("selected", [])],
            "timeline": res.get("timeline"),
        }
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "graficos-auto":
        res = gfx_auto_mod.executar(a.slug, somente_planejar=a.planejar)
        resumo = {
            "engine": "vx_graphics_auto",
            "slug": a.slug,
            "applied": res.get("applied", False),
            "candidate_count": res.get("candidate_count", 0),
            "selected": [{
                "start": c["start"], "end": c["end"], "word": c["word"],
                "preset": c["preset"], "layout": c["layout"],
                "score": c["score"], "beat_score": c["beat_score"]
            } for c in res.get("selected", [])],
            "timeline": res.get("timeline"),
        }
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "folha-quadro":
        import folha_por_quadro as fq_mod
        res = fq_mod.auditar(a.slug, fps=a.fps, por_take=not a.geral)
        print(res["relatorio"])
        print(json.dumps({k: v for k, v in res.items() if k != "relatorio"},
                         ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "impacto-pro":
        res = impact_pro_mod.executar(
            a.slug, palavra=a.word, subtexto=a.sub, preset=a.preset,
            layout=a.layout, duracao=a.dur, energia=a.energia,
            max_cenas=a.max_cenas, saida=a.saida, somente_planejar=a.planejar,
            tempo_inicio=a.tempo)
        resumo = {
            "engine": res["engine"], "plano": res["plano"],
            "renderizados": res["renderizados"],
            "cenas": [{"word": c["keyword_dominante"], "preset": c["preset"],
                       "layout": c["layout"], "background": c["background"],
                       "beats": c.get("audio_reactive", {}).get("beat_count", 0),
                       "reactive": c.get("audio_reactive", {}).get("source", "curve_only")}
                      for c in res["cenas"]],
        }
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "cinemascope":
        print(cine_mod.gerar_filtro_cinemascope(a.altura))
        return 0
    if a.cmd == "colorgrade":
        print(col_mod.obter_filtro_color_grade(a.estilo))
        return 0
    if a.cmd == "speedlines":
        p = Path(a.pasta)
        frames = spd_mod.gerar_pacote_speedlines_animadas(p)
        print(f"Gerados {len(frames)} frames de speedlines em: {p}")
        return 0
    if a.cmd == "social":
        m = carregar_manifesto(a.slug)
        p_dir = dir_projeto(a.slug)
        from vx import projeto as vx_projeto
        audio_file = vx_projeto.audio(p_dir, m)
        if not audio_file.exists():
            audio_file = p_dir / "audio.wav"
        momentos = soc_mod.encontrar_melhores_momentos(str(audio_file))
        metas = soc_mod.gerar_metadados_sociais(m.get("personagem", a.slug), m.get("anime", ""), m.get("faixa", a.slug))
        res = {"momentos_shorts": momentos, "metadados": metas}
        out_file = p_dir / "social_pacote.json"
        out_file.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Pacote social gerado com sucesso em: {out_file}")
        return 0
    if a.cmd == "stems":
        res = stem_mod.separar_stems_gpu(a.audio, Path(a.saida))
        print("Stems separados:", json.dumps(res, indent=2))
        return 0
    if a.cmd == "motionblur":
        res = mb_mod.aplicar_motion_blur_video(a.video, a.saida, a.intensidade)
        print("Motion blur aplicado:", res)
        return 0
    if a.cmd == "tumbas-ab":
        m = carregar_manifesto(a.slug)
        p_dir = dir_projeto(a.slug) / "capas_ab"
        p = m.get("personagem", a.slug)
        fx = m.get("faixa", a.slug)
        aura = m.get("cor", {}).get("destaque", "#FF4500")
        caps = tab_mod.gerar_suite_ab(a.frame, p_dir, p, fx, aura)
        print(f"Geradas {len(caps)} opções de capa para teste A/B em: {p_dir}")
        return 0
    if a.cmd == "capa-ia":
        carregar_manifesto(a.slug)
        try:
            out = art_ia_mod.gerar_miniatura_completa(
                dir_projeto(a.slug), motor=a.motor, prompt_customizado=a.prompt, seed=a.seed,
                ref=a.ref, denoise=a.denoise, forcar=a.forcar, variacoes=a.variacoes)
        except img_local_mod.ComfyIndisponivel as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2
        print(f"Capa IA ({a.motor}) gerada: {out}")
        return 0
    if a.cmd == "gerar-imagem":
        carregar_manifesto(a.slug)
        try:
            outs = img_local_mod.gerar(dir_projeto(a.slug), a.tipo, cena=a.cena, seed=a.seed,
                                       variacoes=a.variacoes, ref=a.ref, denoise=a.denoise,
                                       forcar=a.forcar)
        except img_local_mod.ComfyIndisponivel as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2
        print(json.dumps([str(o) for o in outs], indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "promover":
        import entrega as ent_mod
        reg = ent_mod.promover(a.slug, a.run_id)
        print(json.dumps(reg, indent=2, ensure_ascii=False))
        print(f"proximo passo obrigatorio: estudio.py entrega {a.slug}")
        return 0
    if a.cmd == "entrega":
        import entrega as ent_mod
        carregar_manifesto(a.slug)
        res = ent_mod.executar(a.slug, n_shorts=a.n, forcar_artes=a.forcar_artes)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        print("PACOTE COMPLETO" if res["pronto"] else "PACOTE INCOMPLETO: " + "; ".join(res["faltando"].values()))
        return 0 if res["pronto"] else 1
    if a.cmd == "lancamento":
        carregar_manifesto(a.slug)
        res = soc_mod.pacote_lancamento(dir_projeto(a.slug))
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["pronto"] else 1
    if a.cmd == "shorts":
        import shorts_pipeline as shorts_mod
        carregar_manifesto(a.slug)
        res = shorts_mod.executar(a.slug, n=a.n, dur=a.dur, somente_planejar=a.planejar)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "artes-ia":
        carregar_manifesto(a.slug)
        try:
            res = art_ia_mod.gerar_pacote_artes(dir_projeto(a.slug), forcar=a.forcar)
        except img_local_mod.ComfyIndisponivel as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "comfy-parar":
        print("ComfyUI encerrado." if img_local_mod.parar_comfy()
              else "Nenhum ComfyUI iniciado pelo estudio (pid ausente); nada a fazer.")
        return 0
    if a.cmd == "titulos":
        import titulos_pipeline as tit_mod
        print(json.dumps(tit_mod.executar(a.slug, somente_planejar=a.planejar), indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "cenas-ia":
        res = cenas_ia_mod.executar(a.slug, somente_planejar=a.planejar)
        print(json.dumps({k: v for k, v in res.items() if k != "config"}, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "comfy-status":
        st = img_local_mod.status(iniciar=a.iniciar)
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return 0 if st.get("online") and st.get("checkpoint_ok") else 1
    if a.cmd == "card-saber":
        if not saber_mod:
            print("ERRO: card-saber precisa do rembg (pip install rembg[gpu]==2.0.67).", file=sys.stderr)
            return 2
        saber_mod.renderizar_video_apresentacao_saber(a.frame, a.nome, a.saida)
        return 0
    if a.cmd == "legendas-mugen":
        p_dir = dir_projeto(a.slug)
        letra_txt = p_dir / "LETRA.txt"
        out_ass = p_dir / "legendas" / f"{a.slug}_mugen.ass"
        leg_pro_mod.converter_letra_para_ass_mugen(letra_txt, out_ass)
        return 0
    if a.cmd == "snap-impact":
        print(snap_mod.gerar_filtro_snap_impact(a.tempo))
        return 0
    if a.cmd == "ghosting":
        print(ghost_mod.gerar_filtro_ghosting(a.tempo))
        return 0
    if a.cmd == "smartcrop":
        out = crop_mod.renderizar_smart_crop_916(a.video, a.saida)
        return 0
    if a.cmd == "auditar-ritmo":
        p_dir = dir_projeto(a.slug)
        tl_path = p_dir / "timeline.json"
        res = rit_aud_mod.auditar_dinamica_timeline(tl_path)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "legenda-palavra":
        p_dir = dir_projeto(a.slug)
        transc = p_dir / "entradas" / "transcricao.json"
        out_ass = p_dir / "legendas" / f"{a.slug}_word_by_word.ass"
        lww_mod.gerar_ass_word_by_word(transc, out_ass)
        return 0
    if a.cmd == "legenda-neon":
        p_dir = dir_projeto(a.slug)
        transc = p_dir / "entradas" / "transcricao.json"
        out_ass = p_dir / "legendas" / f"{a.slug}_neon.ass"
        neon_leg_mod.gerar_ass_neon_motion(transc, out_ass)
        return 0
    if a.cmd == "loop-infinito":
        out = loop_mod.criar_short_loop_infinito(a.video, a.saida)
        return 0
    if a.cmd == "paineis":
        print(pan_mod.gerar_filtro_paineis_manga(a.modo))
        return 0
    if a.cmd == "color-splash":
        print(splash_mod.gerar_filtro_color_splash(a.cor, a.inicio, a.dur))
        return 0
    if a.cmd == "hook-retencao":
        out = hook_mod.salvar_overlay_hook(a.texto, Path(a.saida))
        return 0
    if a.cmd == "pixel-sort":
        print(px_mod.gerar_filtro_pixel_sort_glitch(a.tempo))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
