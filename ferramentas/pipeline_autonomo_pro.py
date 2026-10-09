"""Pipeline de producao com preflight, logs e QA da saida real.

Porta publica: estudio.py esteira <slug> [--planejar].
Nao publica, nao altera o master aprovado e nao chama APIs de imagem.
"""
import sys
import subprocess
import json
import re
import shutil
import os
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
from uuid import uuid4

RAIZ = Path(__file__).resolve().parents[1]
FERRAMENTAS = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from vx import ambiente  # noqa: E402
from vx import lock as vx_lock  # noqa: E402
from vx import etapas as vx_etapas  # noqa: E402
from vx import composicao as vx_composicao  # noqa: E402
from vx import projeto as vx_projeto  # noqa: E402
ambiente.garantir_path()

def quantizar_cortes(tempos, fps=30):
    return [round(float(t) * fps) for t in tempos]

def executar_revisao(slug, previa=False):
    if previa:
        from revisao_master import executar_previa
        return executar_previa(slug)
    from revisao_master import executar
    return executar(slug)

def projeto(slug):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", slug):
        raise ValueError("Slug invalido: use letras, numeros, _ ou -")
    base = (RAIZ / "projetos").resolve()
    path = (base / slug).resolve()
    if path.parent != base or not path.is_dir():
        raise ValueError(f"Projeto inexistente ou fora da raiz: {slug}")
    return path

def _ass_do_manifesto(p, manifest):
    ass = manifest.get("legenda_ass")
    if not isinstance(ass, str) or not ass.strip():
        return None
    path = Path(ass)
    return path if path.is_absolute() else p / path


def pendencias_bootstrap(slug):
    """Etapas que um projeto novo ainda precisa antes do preflight completo.

    So devolve etapas que a esteira sabe produzir sozinha a partir de audio + letra.
    """
    try:
        p = projeto(slug)
        manifest = json.loads((p / "projeto.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    audio = vx_projeto.audio(p)
    if not audio.is_file():
        return []
    pend = []
    if not all(x.is_file() for x in vx_projeto.stems(p)):
        pend.append("stems")
    if not (p / "entradas" / "transcricao.json").is_file():
        pend.append("transcrever")
    ass_path = _ass_do_manifesto(p, manifest)
    if ass_path is not None and not ass_path.is_file():
        pend.append("sincronizar")
    if not (p / "timeline.json").is_file():
        pend.append("timeline")
    return pend


def executar_bootstrap(slug, pend=None):
    """Roda, na ordem oficial, so as etapas de bootstrap que faltam."""
    p = projeto(slug)
    pend = pendencias_bootstrap(slug) if pend is None else pend
    audio = vx_projeto.audio(p)
    comandos = {
        "stems": ["stems", str(audio), "--saida", str(p / "entradas" / "stems")],
        "transcrever": ["transcrever", slug, "--modelo", "large-v3"],
        "sincronizar": ["sincronizar", slug],
        "timeline": ["timeline", slug],
    }
    for nome in ("stems", "transcrever", "sincronizar", "timeline"):
        if nome in pend:
            executar_passo([sys.executable, str(FERRAMENTAS / "estudio.py"), *comandos[nome]],
                           f"bootstrap: {nome}")
    return pend


def preflight(slug, permitir_bootstrap=False):
    p = projeto(slug)
    errors = []
    try:
        manifest = json.loads((p / "projeto.json").read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifesto deve ser um objeto JSON")
    except (OSError, ValueError) as exc:
        return {"aprovado": False, "erros": [str(exc)], "etapas": []}
    pend = pendencias_bootstrap(slug) if permitir_bootstrap else []
    audio = vx_projeto.audio(p)
    required = [audio, RAIZ / "assets/intro/Eu_preciso_criar_INTRO_para_o.mp4"]
    # Render-clipe uses this exact ASS; never generate another ASS and QA the old one.
    ass_path = _ass_do_manifesto(p, manifest)
    if ass_path is None:
        errors.append("Defina legenda_ass no projeto.json e sincronize antes da esteira")
    else:
        if "sincronizar" not in pend:
            required.append(ass_path)
        if ass_path.is_file():
            content = ass_path.read_text(encoding="utf-8-sig")
            if "Style:" not in content or "Dialogue:" not in content:
                errors.append("ASS precisa de estilos e eventos Dialogue")
    for file in required:
        if not file.is_file() or not file.stat().st_size:
            errors.append(f"Arquivo obrigatorio ausente/vazio: {file}")
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            errors.append(f"{exe} nao encontrado no PATH")
    timeline_path = p / "timeline.json"
    if "timeline" not in pend:
        try:
            timeline = json.loads(timeline_path.read_text(encoding="utf-8-sig"))
            if not isinstance(timeline, dict):
                raise ValueError("Timeline deve ser um objeto")
            if audio.is_file() and shutil.which("ffprobe"):
                from timeline_clipe import validar
                errors.extend(validar(p, timeline, audio))
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"Timeline invalida: {exc}")
    # ordem vem do registro unico (vx/etapas.py); sincronizar/timeline aparecem
    # como "bootstrap:<nome>" quando pendentes
    steps = [n for n in vx_etapas.nomes() if n not in ("sincronizar", "timeline")]
    return {"aprovado": not errors, "erros": errors, "etapas": steps,
            "saida": str(p / "saidas" / "esteira" / "<execucao>" / f"{slug}_master_final_com_intro.mp4"),
            "observacoes": [
                "VX Scene Intelligence escolhe cenas reais pela letra antes dos efeitos especiais.",
                "VX Cenas IA gera cenas novas no ComfyUI (auto-inicia) so onde o material real ficou fraco.",
                "VX Manga Auto pode inserir 1-2 takes raros de climax quando houver candidato forte.",
                "VX Graphics Auto analisa letra/audio e injeta alguns takes tipograficos antes do render.",
                "VX Titulos injeta Title Card (abertura) e End Card (encerramento); audio com fade no master.",
                "Nao promove o candidato a master publicado.",
                "Shorts e capa continuam nas portas explicitas do estudio."]}

def salvar_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)

def executar_passo(cmd, titulo, log_path=None):
    print(f"[ESTEIRA] {titulo}", flush=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if log_path is None:
        subprocess.run(cmd, cwd=RAIZ, env=env, check=True)
    else:
        with log_path.open("w", encoding="utf-8") as log:
            subprocess.run(cmd, cwd=RAIZ, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)

def executar_esteira_completa(slug, planejar=False, clean_rebuild=False):
    if planejar:
        check = preflight(slug, permitir_bootstrap=not clean_rebuild)
        pend = pendencias_bootstrap(slug) if not clean_rebuild else []
        if pend:
            check["bootstrap"] = pend
            check["etapas"] = [f"bootstrap:{x}" for x in pend] + check.get("etapas", [])
            check.setdefault("observacoes", []).insert(
                0, "PROJETO NOVO: a esteira gera sozinha " + ", ".join(pend) + " antes do preflight completo.")
        if clean_rebuild:
            check["etapas"] = ["clean-rebuild", "timeline-base"] + check.get("etapas", [])
            check.setdefault("observacoes", []).insert(
                0, "REBUILD CLEAN: derivados/legado seriam isolados em backup e a timeline seria recriada do zero.")
        print(json.dumps(check, ensure_ascii=False, indent=2))
        return 0 if check["aprovado"] else 1

    # Lock ANTES de qualquer escrita: bootstrap e clean-rebuild tambem regravam
    # timeline.json/estados e antes rodavam sem protecao. Lock orfao (PID morto)
    # e retomado sozinho; lock vivo ou ilegivel falha fechado.
    p = projeto(slug)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    lock = p / ".esteira.lock"
    lock_info = vx_lock.adquirir(lock, run_id)
    if lock_info.get("lock_orfao_removido"):
        print(f"[ESTEIRA] lock orfao removido (pid {lock_info['lock_orfao_removido'].get('pid')} "
              "nao existe mais)", flush=True)
    try:
        return _executar_com_lock(slug, clean_rebuild, p, run_id, lock_info)
    finally:
        vx_lock.liberar(lock, run_id)


def _executar_com_lock(slug, clean_rebuild, p, run_id, lock_info):
    clean_report = None
    if clean_rebuild:
        from clean_rebuild import preparar
        print("[ESTEIRA] clean-rebuild", flush=True)
        clean_report = preparar(slug)
        print(f"[ESTEIRA] backup clean: {clean_report['backup']}", flush=True)
        # Reconstroi tambem a sincronizacao oficial: timeline-base nunca depende
        # de um arquivo velho que por acaso existia no projeto anterior.
        executar_passo(
            [sys.executable, str(FERRAMENTAS / "estudio.py"), "sincronizar", slug],
            "sincronizacao limpa",
        )
        executar_passo(
            [sys.executable, str(FERRAMENTAS / "estudio.py"), "timeline", slug],
            "timeline-base limpa",
        )
    else:
        pend = pendencias_bootstrap(slug)
        if pend:
            # falha rapido em problemas que o bootstrap nao resolve, antes de gastar GPU
            parcial = preflight(slug, permitir_bootstrap=True)
            if not parcial["aprovado"]:
                raise ValueError("\n".join(parcial["erros"]))
            executar_bootstrap(slug, pend)

    # Composicao: a timeline e remontada da base limpa em toda execucao, entao
    # mudar letra/parametro nunca deixa takes antigos "presos" (vx/composicao.py).
    composicao = {"modo": "clean_rebuild"} if clean_rebuild else None
    if not clean_rebuild:
        if vx_composicao.base_desatualizada(p):
            executar_passo([sys.executable, str(FERRAMENTAS / "estudio.py"), "timeline", slug],
                           "timeline-base (letra sincronizada mudou)")
        composicao = vx_composicao.recompor(p, p / "qa" / "esteira" / run_id / "recomposicao")
        print(f"[ESTEIRA] composicao: {composicao['modo']}"
              + (f" (base adotada de {composicao['base_adotada']})" if composicao.get("base_adotada") else ""),
              flush=True)

    check = preflight(slug)
    if not check["aprovado"]:
        raise ValueError("\n".join(check["erros"]))
    import render_dispatch as rd
    rd.video_args()
    from compositor_master_gpu import concatenar_intro
    qa = p / "qa" / "esteira" / run_id
    qa.mkdir(parents=True, exist_ok=True)
    candidate_dir = p / "saidas" / "esteira" / run_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    check["saida"] = str(candidate_dir / f"{slug}_master_final_com_intro.mp4")
    report = {"run_id": run_id, "status": "executando", "inicio": datetime.now(timezone.utc).isoformat(),
              "etapas": [], "saida": check["saida"],
              "clean_rebuild": bool(clean_rebuild),
              "clean_backup": clean_report.get("backup") if clean_report else None,
              "lock_orfao_removido": lock_info.get("lock_orfao_removido"),
              "composicao": composicao}
    report_path = qa / "execucao.json"
    try:
        salvar_json(report_path, report)
        def step(name, args, bloqueante=True):
            item = {"nome": name, "status": "executando"}
            report["etapas"].append(item)
            salvar_json(report_path, report)
            try:
                executar_passo([sys.executable, str(FERRAMENTAS / "estudio.py"), *args],
                              name, qa / f"{len(report['etapas']):02}_{name}.log")
            except subprocess.CalledProcessError:
                if bloqueante:
                    item["status"] = "falhou"
                    raise
                # etapa informativa: registra e segue (contrato do registro)
                item["status"] = "aviso"
                salvar_json(report_path, report)
                return
            except BaseException:
                item["status"] = "falhou"
                raise
            item["status"] = "concluido"
            salvar_json(report_path, report)

        audio = vx_projeto.audio(p)
        stems_dir = vx_projeto.stems_dir(p)
        stems = vx_projeto.stems(p)
        if not all(x.is_file() and x.stat().st_size for x in stems):
            step("stems", ["stems", str(audio), "--saida", str(stems_dir)])
            if not all(x.is_file() and x.stat().st_size for x in stems):
                raise RuntimeError("Demucs nao entregou os quatro stems")
        transcription = p / "entradas" / "transcricao.json"
        if not transcription.is_file():
            step("transcrever", ["transcrever", slug, "--modelo", "large-v3"])
        # auditar-letra primeiro: letra que nao bate com o audio (verso pulado,
        # bloco reordenado, voz sem transcricao) falha ANTES de gastar render.
        for etapa in vx_etapas.PRODUCAO:
            step(etapa.nome, [etapa.nome, slug, *etapa.args], bloqueante=etapa.bloqueante)
        if composicao and composicao.get("modo") != "legado":
            vx_composicao.registrar_composicao(p)
        body = candidate_dir / f"{slug}_corpo.mp4"
        render = vx_etapas.POR_NOME["render-clipe"]
        step(render.nome, [render.nome, slug, *render.args, "--saida", str(body)])
        if not body.is_file() or not body.stat().st_size:
            raise RuntimeError(f"Render nao entregou o corpo esperado: {body}")
        report["fase"] = "intro"
        salvar_json(report_path, report)
        final = concatenar_intro(body, Path(check["saida"]))
        report["fase"] = "qa-master"
        salvar_json(report_path, report)
        executar_passo([rd.ffmpeg_bin(), "-v", "error", "-xerror", "-i",
                       str(final), "-f", "null", "-"], "decode", qa / "decode.log")
        import imagem
        gate = imagem.analisar(final, pasta_qa=qa, excluir_intro=10.0)
        salvar_json(qa / "imagem.json", asdict(gate))
        if not gate.aprovado:
            raise RuntimeError(f"QA da saida nova reprovado: {gate.motivos}")
        # porteiro de texto no render: logo/legenda/cartela de terceiros que escapou da fonte
        import fonte_limpa
        texto = fonte_limpa.auditar_texto_render(body, p)
        salvar_json(qa / "texto_render.json", texto)
        if not texto["aprovado"]:
            amostra = "; ".join(f"{i['t']:.1f}s '{i['texto']}'" for i in texto["intrusos"][:8])
            raise RuntimeError(f"QA de texto do render reprovado ({len(texto['intrusos'])}): {amostra}")
        import audio as audio_gate
        rel_audio = audio_gate.analisar(final)
        salvar_json(qa / "audio.json", asdict(rel_audio))
        # clareza vocal no mix completo e so indicativa; loudness/true peak bloqueiam.
        bloqueios = [m for m in rel_audio.motivos if not m.startswith("clareza")]
        report["audio"] = {"lufs": rel_audio.lufs, "true_peak_dbtp": rel_audio.true_peak_dbtp,
                           "avisos": [m for m in rel_audio.motivos if m not in bloqueios]}
        if bloqueios:
            raise RuntimeError(f"QA de audio do master reprovado: {bloqueios}")
        report["status"] = "aprovado_qa_automatico"
        print(f"Candidato com intro verificado: {final}")
        print("Revisao visual/editorial ainda necessaria; master do manifesto preservado.")
        return 0
    except BaseException as exc:
        report["status"] = "falhou"
        report["erro"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["fim"] = datetime.now(timezone.utc).isoformat()
        salvar_json(report_path, report)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--planejar", action="store_true")
    parser.add_argument("--rebuild-clean", action="store_true")
    args = parser.parse_args()
    sys.exit(executar_esteira_completa(args.slug, args.planejar, args.rebuild_clean))
