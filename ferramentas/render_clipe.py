"""Prévia curta da timeline com encoder central; áudio e legendas são aplicados uma vez."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import render_dispatch as rd
from timeline_clipe import fonte, validar, duracao
from legenda import filtro_ass
import movimento as mv


# Tipos de segmento com estetica propria (motion/cards/IA) que NAO devem receber
# o lift de sombra do render do corpo; eles ja controlam a propria exposicao.
_TIPOS_SEM_LIFT = {
    "vx_graphics_auto", "vx_manga_auto", "vx_title_card",
    "vx_end_card", "vx_cena_ia", "vx_chroma",
}


def _lift_sombra(segmento: dict) -> str:
    """Lift suave de sombras para cenas de anime genuinamente escuras.

    O porteiro de imagem (`imagem.py`) marca como "quase-morto" frames com
    luz<24 e detalhe<22. Silhuetas escuras de anime (ex.: Gojo em cena noturna)
    encostam nesse piso. Um gamma leve levanta as sombras sem estourar os reais
    ou lavar a arte, mantendo o porteiro intacto (nao mexemos no limiar). Nao se
    aplica a takes com estetica propria (graphics/cards/IA), que ja controlam a
    propria exposicao. Retorna um trecho de filtro pronto para concatenar
    (terminado em virgula) ou string vazia.
    """
    tipo = str(segmento.get("type", ""))
    if tipo in _TIPOS_SEM_LIFT:
        return ""
    if segmento.get("graphics_locked") or segmento.get("preset") == "graphics_locked":
        return ""
    return "eq=gamma=1.08:brightness=0.02:contrast=1.02,"


def intervalos_sem_legenda(timeline: dict) -> list[tuple[float, float]]:
    """Trechos em que o take ja escreve a frase na tela (graphics_auto.oculta_legenda)."""
    return [(float(s["start"]), float(s["end"])) for s in timeline.get("segments") or []
            if (s.get("graphics_auto") or {}).get("oculta_legenda")]


def _ass_tempo(txt: str) -> float:
    h, m, s = txt.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


COBERTURA_MIN_OCULTAR = 0.9


def ass_sem_intervalos(texto: str, intervalos: list[tuple[float, float]]) -> str:
    """Remove os Dialogue que um take de linha cobre QUASE INTEIROS (>= 90% do evento).
    Evento so parcialmente coberto fica: melhor frase duplicada um instante do que
    palavra sumida (incidente 'tormento'). O legenda_ass original nao muda."""
    out = []
    for linha in texto.splitlines(keepends=True):
        if linha.startswith("Dialogue:"):
            campos = linha.split(",", 3)
            try:
                a0, b0 = _ass_tempo(campos[1]), _ass_tempo(campos[2])
            except (IndexError, ValueError):
                out.append(linha)
                continue
            dur = max(1e-6, b0 - a0)
            coberto = max((max(0.0, min(b, b0) - max(a, a0)) for a, b in intervalos), default=0.0)
            if coberto / dur >= COBERTURA_MIN_OCULTAR:
                continue
        out.append(linha)
    return "".join(out)


def _filtros_transicao(shot: dict | None, segmento: dict,
                        a: float, b: float) -> list[str]:
    """Filtros locais e raros. Match/zoom cuts são resolvidos pela câmera, sem FX."""
    if not shot:
        return []
    dur_local = max(0.0, b - a)
    if dur_local <= 0.03:
        return []
    filtros = []
    seg_start = float(segmento["start"])
    seg_end = float(segmento["end"])

    tin = shot.get("transition_in") or {}
    if tin.get("type") == "flash_cut" and abs(a - seg_start) <= 0.02:
        d = min(float(tin.get("duration", 0.08)), dur_local * 0.35)
        if d >= 0.03:
            strength = max(0.0, min(1.0, float(tin.get("strength", 0.56))))
            bright = 0.045 + 0.085 * strength
            filtros.append(
                f"eq=brightness={bright:.4f}:contrast=1.04:saturation=0.90:"
                f"enable='between(t,0,{d:.4f})'"
            )
            filtros.append(
                f"gblur=sigma=1.15:steps=1:enable='between(t,0,{d:.4f})'"
            )
    elif tin.get("type") == "snap_impact" and abs(a - seg_start) <= 0.02:
        d = min(float(tin.get("duration", 0.12)), dur_local * 0.35)
        if d >= 0.03:
            strength = max(0.0, min(1.0, float(tin.get("strength", 0.70))))
            bright = 0.060 + 0.100 * strength
            shift = int(round(4 + 6 * strength))
            filtros.append(
                f"eq=brightness={bright:.4f}:contrast=1.12:saturation=0.95:"
                f"enable='between(t,0,{d:.4f})'"
            )
            filtros.append(
                f"rgbashift=rh={shift}:bh=-{shift}:"
                f"enable='between(t,0,{d:.4f})'"
            )
            filtros.append(
                f"gblur=sigma=1.2:steps=1:enable='between(t,0,{d:.4f})'"
            )

    tout = shot.get("transition_out") or {}
    if tout.get("type") == "flash_cut" and abs(b - seg_end) <= 0.02:
        d = min(float(tout.get("duration", 0.08)), dur_local * 0.35)
        if d >= 0.03:
            st = max(0.0, dur_local - d)
            strength = max(0.0, min(1.0, float(tout.get("strength", 0.56))))
            bright = 0.045 + 0.085 * strength
            filtros.append(
                f"eq=brightness={bright:.4f}:contrast=1.04:saturation=0.90:"
                f"enable='between(t,{st:.4f},{dur_local:.4f})'"
            )
            filtros.append(
                f"gblur=sigma=1.15:steps=1:"
                f"enable='between(t,{st:.4f},{dur_local:.4f})'"
            )
    elif tout.get("type") == "snap_impact" and abs(b - seg_end) <= 0.02:
        d = min(float(tout.get("duration", 0.08)), dur_local * 0.35)
        if d >= 0.03:
            st = max(0.0, dur_local - d)
            strength = max(0.0, min(1.0, float(tout.get("strength", 0.60))))
            bright = 0.050 + 0.080 * strength
            shift = int(round(3 + 5 * strength))
            filtros.append(
                f"eq=brightness={bright:.4f}:contrast=1.08:saturation=0.95:"
                f"enable='between(t,{st:.4f},{dur_local:.4f})'"
            )
            filtros.append(
                f"rgbashift=rh={shift}:bh=-{shift}:"
                f"enable='between(t,{st:.4f},{dur_local:.4f})'"
            )
            filtros.append(
                f"gblur=sigma=1.2:steps=1:"
                f"enable='between(t,{st:.4f},{dur_local:.4f})'"
            )
    return filtros


def _indexar_plano(plano: dict | None) -> dict:
    idx = {}
    for shot in (plano or {}).get("shots", []):
        idx[round(float(shot["start"]), 2)] = shot
    return idx


def _carregar_plano(projeto: Path) -> dict:
    """Le plano_visual.json (movimento por shot). {} se nao existir."""
    p = projeto / "plano_visual.json"
    if not p.is_file():
        return {}
    try:
        plano = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return _indexar_plano(plano)


def previa(projeto: Path, timeline: dict, audio: Path, destino: Path,
           inicio: float, dur: float, ass: Path | None = None,
           com_movimento: bool = True, plano_override: dict | None = None) -> Path:
    erros = validar(projeto, timeline, audio)
    if erros:
        raise ValueError("timeline inválida:\n" + "\n".join(erros))
    if inicio < 0 or dur <= 0 or inicio + dur > duracao(audio) + .001:
        raise ValueError("intervalo da prévia fora da música")
    fim = inicio + dur
    if com_movimento:
        plano = (_indexar_plano(plano_override) if plano_override is not None
                 else _carregar_plano(projeto))
    else:
        plano = {}
    destino.parent.mkdir(parents=True, exist_ok=True)
    import contextlib
    import os
    manter = os.environ.get("VX_MANTER_TMP")      # diagnostico: guarda as partes do render
    ctx = contextlib.nullcontext(manter) if manter else tempfile.TemporaryDirectory(prefix="vx_previa_")
    if manter:
        Path(manter).mkdir(parents=True, exist_ok=True)
    with ctx as pasta:
        tmp = Path(pasta)
        partes = []
        esperados = []
        for i, s in enumerate(timeline["segments"]):
            a, b = max(inicio, float(s["start"])), min(fim, float(s["end"]))
            if b - a < .001:
                continue
            # fluxo H.264 puro (Annex B): sem container, sem timestamp, sem edit list.
            # A junção vira concatenação de bytes e o numero de quadros e exato.
            part = tmp / f"{i:04d}.h264"
            base = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,"
                    + _lift_sombra(s) +
                    "format=yuv420p")
            # motion graphics de camera por shot (zoom/pan continuo)
            shot = plano.get(round(float(s["start"]), 2)) if plano else None
            if shot:
                par = mv.parametros_do_shot(shot)
                zoom = mv.filtro_zoom(b - a, par["z0"], par["z1"],
                                      1920, 1080, 30, par["pan"])
                chain = [base, zoom]
                chain += _filtros_transicao(shot, s, a, b)
                vf = ",".join(chain)
            else:
                vf = base
            frames = round(b * 30) - round(a * 30)
            if frames <= 0:
                # plano menor que meio quadro (ex.: 7 ms): o arredondamento telescopa, entao os
                # vizinhos ja cobrem esse tempo e o total de quadros continua exato
                continue
            src_ini = float(s["src"]) + a - float(s["start"])
            try:
                rd.encode(str(part), ["-ss", str(src_ini), "-i", str(fonte(projeto, s["clip"])),
                                      "-t", str(b-a + 0.5)],
                          # tpad: fonte que acaba antes clona o ultimo quadro
                          filtro_v=vf + ",tpad=stop_mode=clone:stop_duration=1",
                          mapa=["-map", "0:v:0"], args_audio=["-an"],
                          args_extra=["-frames:v", str(frames), "-bsf:v", "h264_mp4toannexb", "-f", "h264"],
                          faststart=False, silencioso=True)
            except RuntimeError as e:
                raise RuntimeError(f"plano {i} {s['clip']}@{src_ini:.3f}s ({a:.3f}-{b:.3f}s, "
                                   f"{frames} quadros) falhou: {e}") from e
            partes.append(part)
            esperados.append({"i": i, "clip": s["clip"], "src": round(src_ini, 3), "de": round(a, 3),
                              "frames": frames, "part": part})
        if not partes:
            raise ValueError("nenhum plano na prévia")
        # cada plano PRECISA ter exatamente os quadros pedidos: plano curto (clipe que acaba
        # antes do src+dur, fonte recortada/limpa) desalinha tudo e o concat corta o video.
        # tpad clona o ultimo quadro se a fonte acabar antes; aqui conferimos.
        falhas = [e for e in esperados if contar_quadros(e["part"]) != e["frames"]]
        if falhas:
            det = "; ".join(f"plano {e['i']} {e['clip']}@{e['src']}s: {contar_quadros(e['part'])}/{e['frames']} quadros"
                            for e in falhas[:6])
            raise RuntimeError(f"planos com quadros faltando ({len(falhas)}): {det}")
        # juncao por BYTES (o concat demuxer estimava duracao pelo container e parava no meio:
        # Douma cortou em 105,8 s e depois em 89,2 s; incidente 2026-09-30-douma-render-cortado)
        fluxo = tmp / "bruto.h264"
        with open(fluxo, "wb") as saida_fluxo:
            for p in partes:
                saida_fluxo.write(Path(p).read_bytes())
        total = sum(e["frames"] for e in esperados)
        obtido = contar_quadros(fluxo)
        if abs(obtido - total) > 2:
            raise RuntimeError(f"juncao entregou {obtido} quadros de {total} esperados "
                               f"({obtido / 30:.2f}s de {total / 30:.2f}s)")
        bruto = tmp / "bruto.mp4"
        rd.encode(str(bruto), ["-framerate", "30", "-f", "h264", "-i", str(fluxo)],
                  mapa=["-map", "0:v:0"], args_audio=["-an"], args_extra=["-r", "30"], silencioso=True)
        # ASS usa o relógio da música; deslocar PTS antes de queimar as legendas.
        vf = None
        if ass is not None:
            if not ass.is_file():
                raise ValueError(f"legenda ausente: {ass}")
            ocultar = intervalos_sem_legenda(timeline)
            if ocultar:
                # takes de motion com a frase na tela: nao repetir a legenda embaixo
                filtrada = tmp / "legenda_render.ass"
                filtrada.write_text(ass_sem_intervalos(ass.read_text(encoding="utf-8-sig"), ocultar),
                                    encoding="utf-8")
                ass = filtrada
            # filtro_ass ja escapa o caminho e aponta fontsdir (Cinzel do repo)
            vf = f"setpts=PTS+{inicio:.5f}/TB,{filtro_ass(ass)},setpts=PTS-{inicio:.5f}/TB"
        rd.encode(str(destino), ["-i", str(bruto), "-ss", str(inicio), "-t", str(dur), "-i", str(audio)],
                  filtro_v=vf, mapa=["-map", "0:v:0", "-map", "1:a:0"],
                  args_extra=["-t", str(dur), "-shortest"])
    return destino

def contar_quadros(video: Path) -> int:
    """Quadros de video realmente gravados (conta pacotes; rapido, sem decodificar)."""
    r = subprocess.run([rd.ffprobe_bin(), "-v", "error", "-select_streams", "v:0", "-count_packets",
                        "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    try:
        return int((r.stdout or "0").strip().split(",")[0])
    except ValueError:
        return 0


def duracoes_streams(video: Path) -> tuple[float, float]:
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,duration',
                        '-of', 'json', str(video)], capture_output=True, text=True, check=True)
    streams = json.loads(r.stdout)['streams']
    return tuple(next(float(x['duration']) for x in streams if x['codec_type'] == tipo)
                 for tipo in ('video', 'audio'))
