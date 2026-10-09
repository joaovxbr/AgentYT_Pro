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
import time
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
from vx import metrics as vx_metrics  # noqa: E402
from vx import checkpoint as vx_checkpoint  # noqa: E402
from vx import runner as vx_runner  # noqa: E402
from vx import cache as vx_cache  # noqa: E402
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


def executar_bootstrap(slug, pend=None, isolado=False):
    """Roda, na ordem oficial, so as etapas de bootstrap que faltam."""
    p = projeto(slug)
    pend = pendencias_bootstrap(slug) if pend is None else pend
    audio = vx_projeto.audio(p)
    # `args` ja comeca pelo subcomando: mesma forma que o registro usa em
    # `vx/etapas.py -> args` (nome da etapa primeiro, extras depois).
    comandos = {
        "stems": ["stems", str(audio), "--saida", str(p / "entradas" / "stems")],
        "transcrever": ["transcrever", slug, "--modelo", "large-v3"],
        "sincronizar": ["sincronizar", slug],
        "timeline": ["timeline", slug],
    }
    for nome in ("stems", "transcrever", "sincronizar", "timeline"):
        if nome in pend:
            print(f"[ESTEIRA] bootstrap: {nome}", flush=True)
            vx_runner.executar(nome, comandos[nome], isolado=isolado)
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

def executar_esteira_completa(slug, planejar=False, clean_rebuild=False, resume=None,
                              isolado=False, cache=True):
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
        # --resume: mostra o que seria retomado, sem executar nada
        if resume:
            res = _planejar_resume(slug, resume, clean_rebuild)
            check["resume"] = res
            if res.get("run_id"):
                check["etapas"] = res.get("a_pular", []) + check.get("etapas", [])
        print(json.dumps(check, ensure_ascii=False, indent=2))
        return 0 if check["aprovado"] else 1

    # Lock ANTES de qualquer escrita: bootstrap e clean-rebuild tambem regravam
    # timeline.json/estados e antes rodavam sem protecao. Lock orfao (PID morto)
    # e retomado sozinho; lock vivo ou ilegivel falha fechado.
    p = projeto(slug)
    # --resume: reaproveita o run_id anterior (o checkpoint vive na pasta dele).
    # Sem isso, cada execucao teria um run_id novo e o checkpoint nunca seria lido.
    if resume:
        run_id = _resolver_resume(p, resume, clean_rebuild)
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    lock = p / ".esteira.lock"
    lock_info = vx_lock.adquirir(lock, run_id)
    if lock_info.get("lock_orfao_removido"):
        print(f"[ESTEIRA] lock orfao removido (pid {lock_info['lock_orfao_removido'].get('pid')} "
              "nao existe mais)", flush=True)
    try:
        return _executar_com_lock(slug, clean_rebuild, p, run_id, lock_info, resume=resume,
                                  isolado=isolado, cache=cache)
    finally:
        vx_lock.liberar(lock, run_id)


def _resolver_resume(p, resume, clean_rebuild) -> str:
    """Decide o run_id de retomada. `auto` = checkpoint mais recente do projeto.

    Falha fechada: sem checkpoint para retomar, avisa e comeca uma execucao nova
    (nunca inventa um run_id que nao tem checkpoint, senao o resume nao faria nada).
    """
    if clean_rebuild:
        print("[ESTEIRA] --resume ignorado: rebuild-clean recomeca do zero", flush=True)
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    alvo = vx_checkpoint.mais_recente(p) if str(resume).lower() == "auto" else str(resume)
    if not alvo or not (p / "qa" / "esteira" / alvo / vx_checkpoint.ARQ).is_file():
        disponiveis = vx_checkpoint.run_ids_disponiveis(p)
        aviso = ("nenhum checkpoint disponivel" if not disponiveis
                 else "disponiveis: " + ", ".join(disponiveis[:5]))
        print(f"[ESTEIRA] --resume {resume}: {aviso}; iniciando execucao nova", flush=True)
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    print(f"[ESTEIRA] RETOMANDO execucao {alvo}", flush=True)
    return alvo


def _planejar_resume(slug, resume, clean_rebuild) -> dict:
    """Previa do resume (para --planejar): o que pularia e o que rodaria."""
    if clean_rebuild:
        return {"run_id": None, "motivo": "rebuild-clean recomeca do zero"}
    p = projeto(slug)
    alvo = vx_checkpoint.mais_recente(p) if str(resume).lower() == "auto" else str(resume)
    caminho = p / "qa" / "esteira" / str(alvo) / vx_checkpoint.ARQ
    if not alvo or not caminho.is_file():
        return {"run_id": None, "motivo": "nenhum checkpoint para retomar",
                "disponiveis": vx_checkpoint.run_ids_disponiveis(p)}
    cp = vx_checkpoint.Checkpoint.ler(caminho, projeto=p, slug=slug)
    pular, rodar = [], []
    for nome in vx_etapas.nomes():
        reg = vx_etapas.POR_NOME.get(nome)
        if reg is None:
            continue
        d = cp.pode_pular(nome, reg.le, reg.escreve)
        (pular if d.pular else rodar).append(nome)
    return {"run_id": alvo, "a_pular": pular, "a_rodar": rodar,
            "motivo": "checkpoint valido para as etapas listadas em a_pular"}


def _executar_com_lock(slug, clean_rebuild, p, run_id, lock_info, resume=None,
                       isolado=False, cache=True):
    # Cache por hash de entrada (vx/cache.py) -- escopo do PROJETO, sobrevive entre
    # execucoes. `--rebuild-clean` desliga: o pedido explicito e refazer tudo do zero,
    # e reaproveitar por baixo dos panos contradiria a intencao do operador.
    cache_ativo = bool(cache) and not clean_rebuild
    clean_report = None
    if clean_rebuild:
        from clean_rebuild import preparar
        print("[ESTEIRA] clean-rebuild", flush=True)
        clean_report = preparar(slug)
        print(f"[ESTEIRA] backup clean: {clean_report['backup']}", flush=True)
        # Reconstroi tambem a sincronizacao oficial: timeline-base nunca depende
        # de um arquivo velho que por acaso existia no projeto anterior.
        print("[ESTEIRA] sincronizacao limpa", flush=True)
        vx_runner.executar("sincronizar", ["sincronizar", slug], isolado=isolado)
        print("[ESTEIRA] timeline-base limpa", flush=True)
        vx_runner.executar("timeline", ["timeline", slug], isolado=isolado)
    else:
        pend = pendencias_bootstrap(slug)
        if pend:
            # falha rapido em problemas que o bootstrap nao resolve, antes de gastar GPU
            parcial = preflight(slug, permitir_bootstrap=True)
            if not parcial["aprovado"]:
                raise ValueError("\n".join(parcial["erros"]))
            executar_bootstrap(slug, pend, isolado=isolado)

    # Composicao: a timeline e remontada da base limpa em toda execucao, entao
    # mudar letra/parametro nunca deixa takes antigos "presos" (vx/composicao.py).
    composicao = {"modo": "clean_rebuild"} if clean_rebuild else None
    if not clean_rebuild:
        if vx_composicao.base_desatualizada(p):
            print("[ESTEIRA] timeline-base (letra sincronizada mudou)", flush=True)
            vx_runner.executar("timeline", ["timeline", slug], isolado=isolado)
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
    # Metricas por etapa (vx/metrics.py): tempo, cache, tamanho de saida e motivo
    # de falha estruturado. Grava em qa/esteira/<run_id>/_metricas.json, ao lado do
    # execucao.json -- o formato antigo do execucao.json NAO muda (so ganha campos).
    metricas = vx_metrics.Relatorio(run_id, projeto=p)
    metricas_path = qa / "_metricas.json"
    # Checkpoint de retomada (vx/checkpoint.py): permite `--resume` pular etapa que ja
    # rodou com as MESMAS entradas e cujas saidas continuam no lugar. Falha fechada:
    # sem prova, roda de novo.
    checkpoint = vx_checkpoint.Checkpoint.ler(qa / vx_checkpoint.ARQ, projeto=p, slug=slug)
    checkpoint_path = qa / vx_checkpoint.ARQ
    if resume:
        print(f"[ESTEIRA] resume ativo ({len(checkpoint.etapas)} etapa(s) no checkpoint)",
              flush=True)

    def _saidas_da_etapa(nome):
        """Caminhos que a etapa declarou em vx/etapas.py, resolvidos no projeto."""
        reg = vx_etapas.POR_NOME.get(nome)
        if reg is None:
            return []
        return [str(p / rel.replace("{slug}", slug)) for rel in reg.escreve]

    def _registrar_checkpoint(nome):
        reg = vx_etapas.POR_NOME.get(nome)
        if reg is None:
            return
        checkpoint.registrar(nome, padroes_le=reg.le, padroes_escreve=reg.escreve)
        checkpoint.gravar(checkpoint_path)

    try:
        salvar_json(report_path, report)
        def step(name, args, bloqueante=True):
            # --resume: pula a etapa so se o checkpoint PROVAR que ela ja rodou com
            # as mesmas entradas e que as saidas estao no lugar (vx/checkpoint.py).
            if resume:
                reg = vx_etapas.POR_NOME.get(name)
                if reg is not None:
                    decisao = checkpoint.pode_pular(name, reg.le, reg.escreve)
                    if decisao.pular:
                        item = {"nome": name, "status": vx_metrics.STATUS_PULADA,
                                "resume": decisao.motivo}
                        report["etapas"].append(item)
                        metricas.etapa_inicio(name)
                        metricas.etapa_pulada(name, motivo=decisao.motivo)
                        metricas.gravar(metricas_path)
                        report["metricas"] = metricas.resumo()
                        salvar_json(report_path, report)
                        checkpoint.registrar_pulado(name, decisao.motivo)
                        checkpoint.gravar(checkpoint_path)
                        print(f"[ESTEIRA] {name}: PULADA ({decisao.motivo})", flush=True)
                        return
                    print(f"[ESTEIRA] {name}: roda de novo ({decisao.motivo})", flush=True)
            # Cache por hash (vx/cache.py): diferente do --resume, aqui o escopo e o
            # PROJETO, nao a execucao. Se alguma execucao ANTERIOR processou estas
            # mesmas entradas e produziu saidas que ainda estao no lugar, a etapa nem
            # e chamada. So vale para etapas `cacheavel` do registro: as de composicao
            # reaplicam sobre a base limpa de proposito (vx/composicao.py).
            if cache_ativo:
                reg = vx_etapas.POR_NOME.get(name)
                if reg is not None and reg.cacheavel:
                    decisao_cache = vx_cache.pode_reaproveitar(
                        name, reg.le, reg.escreve, p, slug)
                    if decisao_cache.reaproveitar:
                        evento = {"nome": name, "status": vx_metrics.STATUS_CACHE,
                                  "cache": decisao_cache.motivo}
                        report["etapas"].append(evento)
                        metricas.etapa_inicio(name)
                        metricas.etapa_cache(name, motivo=decisao_cache.motivo,
                                             bytes_=decisao_cache.bytes)
                        metricas.gravar(metricas_path)
                        report["metricas"] = metricas.resumo()
                        salvar_json(report_path, report)
                        vx_cache.confirmar_uso(name, reg.le, p, slug)
                        # A etapa esta "feita" nesta execucao: registra no checkpoint
                        # tambem, para um --resume posterior nao a reavaliar a toa.
                        checkpoint.registrar(name, padroes_le=reg.le,
                                             padroes_escreve=reg.escreve,
                                             status="concluido")
                        checkpoint.gravar(checkpoint_path)
                        print(f"[ESTEIRA] {name}: CACHE ({decisao_cache.motivo})", flush=True)
                        return
            item = {"nome": name, "status": "executando"}
            report["etapas"].append(item)
            salvar_json(report_path, report)
            metricas.etapa_inicio(name)
            t0 = time.perf_counter()
            log_etapa = qa / f"{len(report['etapas']):02}_{name}.log"
            try:
                # In-process (vx/runner.py): a etapa roda neste processo em vez de um
                # subprocess novo. Ganha-se o traceback real (metrics registra o tipo
                # da excecao, nao "exit 1") e o custo de import deixa de ser pago por
                # etapa. `--isolado` volta ao subprocess quando a etapa exigir.
                vx_runner.executar(name, args, log_path=log_etapa, slug=slug,
                                   isolado=isolado)
            except vx_runner.ErroDeEtapa as exc:
                # Era o unico erro tratado de etapa: reprovacao da etapa (exit != 0
                # ou SystemExit do estudio.py). Aqui se decide reprovar ou so avisar.
                duracao = time.perf_counter() - t0
                if bloqueante:
                    item["status"] = "falhou"
                    metricas.etapa_fim(name, status=vx_metrics.STATUS_FALHOU,
                                       duracao_s=duracao,
                                       erro=f"exit {exc.codigo}",
                                       origem_erro="vx_runner.ErroDeEtapa")
                    metricas.gravar(metricas_path)
                    report["metricas"] = metricas.resumo()
                    salvar_json(report_path, report)
                    raise
                # etapa informativa: registra e segue (contrato do registro)
                item["status"] = "aviso"
                metricas.etapa_fim(name, status=vx_metrics.STATUS_AVISO,
                                   duracao_s=duracao,
                                   erro=f"exit {exc.codigo}",
                                   origem_erro="vx_runner.ErroDeEtapa")
                metricas.gravar(metricas_path)
                report["metricas"] = metricas.resumo()
                salvar_json(report_path, report)
                return
            except BaseException as exc:
                duracao = time.perf_counter() - t0
                item["status"] = "falhou"
                metricas.etapa_fim(name, status=vx_metrics.STATUS_FALHOU,
                                   duracao_s=duracao, erro=exc,
                                   origem_erro=type(exc).__name__)
                metricas.gravar(metricas_path)
                report["metricas"] = metricas.resumo()
                salvar_json(report_path, report)
                raise
            item["status"] = "concluido"
            metricas.etapa_fim(name, status=vx_metrics.STATUS_CONCLUIDO,
                               duracao_s=time.perf_counter() - t0,
                               saidas=_saidas_da_etapa(name))
            metricas.gravar(metricas_path)
            # checkpoint: a etapa terminou OK -- guarda entradas/saidas do momento para
            # que um `--resume` futuro saiba se ainda pode pular esta etapa.
            _registrar_checkpoint(name)
            # cache: guarda entradas/saidas com escopo de PROJETO, para que uma
            # execucao FUTURA (outro run_id) reaproveite sem nem chamar a etapa.
            reg = vx_etapas.POR_NOME.get(name)
            if cache_ativo and reg is not None and reg.cacheavel:
                vx_cache.registrar(name, reg.le, reg.escreve, p, slug)
            report["metricas"] = metricas.resumo()
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
        # fecha as metricas: etapas iniciadas e nao finalizadas viram "interrompida"
        for e in metricas.etapas.values():
            if e.status == "executando":
                e.status = vx_metrics.STATUS_FALHOU
                e.fim = report["fim"]
        metricas.gravar(metricas_path)
        report["metricas"] = metricas.resumo()
        # checkpoint: fecha mesmo em falha, registrando o que ficou concluido --
        # e o que permite o `--resume` retomar daqui em vez de recomecar.
        checkpoint.gravar(checkpoint_path)
        report["resume"] = {"run_id": run_id, "ativo": bool(resume),
                            "etapas_no_checkpoint": len(checkpoint.etapas)}
        salvar_json(report_path, report)
        # resumo legivel no console: gargalo e falhas sem abrir log nenhum
        try:
            print(f"[ESTEIRA] metricas em {metricas_path}", flush=True)
            print(metricas.tabela(), flush=True)
            if not resume and checkpoint.etapas:
                print("[ESTEIRA] para retomar desta execucao: "
                      f"estudio.py esteira {slug} --resume {run_id}", flush=True)
        except Exception:
            pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--planejar", action="store_true")
    parser.add_argument("--rebuild-clean", action="store_true")
    parser.add_argument("--resume", nargs="?", const="auto", default=None,
                        help="retoma do checkpoint (sem valor = mais recente) pulando "
                             "etapas ja concluidas com as mesmas entradas")
    parser.add_argument("--isolado", action="store_true",
                        help="roda cada etapa em subprocess (comportamento antigo); por "
                             "padrao as etapas rodam in-process, com traceback real")
    parser.add_argument("--sem-cache", action="store_true",
                        help="ignora o cache por hash entre execucoes (refaz toda etapa "
                             "cacheavel); --rebuild-clean ja implica isso")
    args = parser.parse_args()
    sys.exit(executar_esteira_completa(args.slug, args.planejar, args.rebuild_clean,
                                      resume=args.resume, isolado=args.isolado,
                                      cache=not args.sem_cache))
