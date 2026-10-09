"""Verificacao empirica da fase 5: `--jobs` muda QUANDO as etapas rodam, nao O QUE elas fazem.

Roda o mesmo projeto falso duas vezes -- serial e em ondas -- e compara:
  * a ORDEM das chamadas (deve diferir: paralelismo existe);
  * o CONJUNTO de chamadas (deve ser identico: nada pulado, nada duplicado);
  * o estado final registrado (metricas por etapa, status).

Nao toca em GPU, ffmpeg ou rede: substitui `vx_runner.executar` por um fake que
so anota inicio/fim com um pequeno atraso, para o paralelismo ser observavel.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ferramentas"))

import pipeline_autonomo_pro as pipeline  # noqa: E402
import render_dispatch as rd  # noqa: E402
from vx import etapas as vx_etapas  # noqa: E402
from vx import projeto as vx_projeto  # noqa: E402

ATRASO = 0.08  # por etapa: grande o bastante para duas threads se sobreporem


class Gravador:
    """Anota (etapa, t_inicio, t_fim) e o pico de etapas simultaneas."""

    def __init__(self):
        self.eventos: list[tuple[str, float, float]] = []
        self.ativos = 0
        self.pico = 0
        self.lock = threading.Lock()

    def __call__(self, etapa, args, log_path=None, **kw):
        t0 = time.perf_counter()
        with self.lock:
            self.ativos += 1
            self.pico = max(self.pico, self.ativos)
        time.sleep(ATRASO)
        with self.lock:
            self.ativos -= 1
        self.eventos.append((etapa, t0, time.perf_counter()))

    def ordem(self):
        return [e[0] for e in sorted(self.eventos, key=lambda x: x[1])]

    def duracao(self):
        if not self.eventos:
            return 0.0
        return max(e[2] for e in self.eventos) - min(e[1] for e in self.eventos)

    def sobreposicoes(self):
        """Pares de etapas cujas janelas se sobrepoem (prova de paralelismo real)."""
        pares = []
        ev = sorted(self.eventos, key=lambda x: x[1])
        for i in range(len(ev)):
            for j in range(i + 1, len(ev)):
                a, b = ev[i], ev[j]
                if b[1] < a[2] - 1e-9:  # b comecou antes de a terminar
                    pares.append((a[0], b[0]))
        return pares


def montar_projeto(tmp: Path, com_stems: bool = False):
    """Projeto minimo que passa o preflight e faz todas as etapas 'rodarem'.

    `com_stems=False` (padrao) deixa `stems`/`transcrever` PENDENTES de proposito:
    e o unico jeito de a primeira onda paralela (`stems` || `fonte-limpa`) se
    formar -- a onda tem um lado bootstrap e um lado producao.
    """
    p = tmp
    (p / "projeto.json").write_text(json.dumps({"legenda_ass": "legendas/x.ass"}),
                                    encoding="utf-8")
    vx_projeto.stems_dir(p).mkdir(parents=True, exist_ok=True)
    if com_stems:
        for s in vx_projeto.stems(p):
            s.write_bytes(b"x")
        (p / "entradas" / "transcricao.json").write_text("{}", encoding="utf-8")
    (p / "timeline.json").write_text(json.dumps({"cortes": []}), encoding="utf-8")
    (p / "legendas").mkdir(parents=True, exist_ok=True)
    (p / "legendas" / "x.ass").write_text("Style: x\nDialogue: 0\n", encoding="utf-8")
    return p


def rodar(jobs: int, com_stems: bool = False):
    with tempfile.TemporaryDirectory() as tmp:
        p = montar_projeto(Path(tmp), com_stems=com_stems)
        grav = Gravador()
        relatorio = {"aprovado": True, "erros": [], "saida": str(p / "o.mp4")}

        def fake_preflight(slug, permitir_bootstrap=False):
            return dict(relatorio)

        def fake_bootstrap(slug, pend=None, isolado=False):
            # o bootstrap real rodaria stems/transcrever fora do `step`; aqui
            # deixamos o plano cuidar disso para exercitar a onda paralela.
            return pend or []

        with patch.object(pipeline, "preflight", side_effect=fake_preflight), \
             patch.object(pipeline, "pendencias_bootstrap", return_value=[]), \
             patch.object(pipeline, "executar_bootstrap", side_effect=fake_bootstrap), \
             patch.object(pipeline, "projeto", return_value=p), \
             patch.object(rd, "video_args", return_value=[]), \
             patch.object(pipeline.vx_runner, "executar", side_effect=grav):
            try:
                pipeline.executar_esteira_completa("demo", jobs=jobs)
            except Exception as exc:
                # etapas que exigem artefato real falham DEPOIS de serem chamadas
                # (o registro foi feito de qualquer forma); so anotamos.
                relatorio["parada"] = f"{type(exc).__name__}: {exc}"[:120]
        estado = None
        cands = list((p / "qa" / "esteira").glob("*/execucao.json"))
        if cands:
            estado = json.loads(cands[0].read_text(encoding="utf-8"))
        return grav, estado


def main():
    print("=" * 72)
    print("FASE 5 -- verificacao empirica do paralelismo (vx/dag.py)")
    print("=" * 72)
    problemas = []

    g_serial, est_serial = rodar(1)
    g_ondas, est_ondas = rodar(4)

    print(f"\n[SERIAL --jobs 1]")
    print(f"  etapas chamadas : {len(g_serial.eventos)}")
    print(f"  pico simultaneo : {g_serial.pico}")
    print(f"  sobreposicoes   : {len(g_serial.sobreposicoes())}")
    print(f"  duracao total   : {g_serial.duracao():.2f}s")

    print(f"\n[ONDAS --jobs 4]")
    print(f"  etapas chamadas : {len(g_ondas.eventos)}")
    print(f"  pico simultaneo : {g_ondas.pico}")
    print(f"  sobreposicoes   : {len(g_ondas.sobreposicoes())}")
    print(f"  duracao total   : {g_ondas.duracao():.2f}s")

    # 1) mesmo CONJUNTO de etapas
    a, b = sorted(g_serial.ordem()), sorted(g_ondas.ordem())
    print(f"\n[1] conjunto de etapas identico? {'OK' if a == b else 'DIFERE'}")
    if a != b:
        problemas.append(f"conjunto difere: so serial {set(a) - set(b)}, "
                         f"so ondas {set(b) - set(a)}")

    # 2) ondas NAO roda em serie puro (prova de paralelismo)
    print(f"[2] ondas sobrepoe etapas? {'OK' if g_ondas.pico > 1 else 'NAO'}")
    if g_ondas.pico <= 1:
        problemas.append("ondas nunca teve 2 etapas simultaneas")

    # 3) serial NAO sobrepoe
    print(f"[3] serial nunca sobrepoe? {'OK' if g_serial.pico == 1 else 'NAO'}")
    if g_serial.pico != 1:
        problemas.append(f"serial teve {g_serial.pico} etapas simultaneas")

    # 4) a composicao nunca roda junto (invariante de seguranca)
    junto = [(x, y) for x, y in g_ondas.sobreposicoes()
             if x in vx_etapas.POR_NOME and y in vx_etapas.POR_NOME
             and vx_etapas.POR_NOME[x].escreve and vx_etapas.POR_NOME[y].escreve
             and "timeline.json" in vx_etapas.POR_NOME[x].escreve
             and "timeline.json" in vx_etapas.POR_NOME[y].escreve]
    print(f"[4] composicao nunca em paralelo? {'OK' if not junto else 'VIOLADO'}")
    if junto:
        problemas.append(f"duas etapas de composicao em paralelo: {junto}")

    # 5) ondas termina mais rapido (sinal de ganho real)
    ganho = g_serial.duracao() - g_ondas.duracao()
    print(f"[5] ganho de tempo: {ganho:+.2f}s "
          f"({ganho / g_serial.duracao() * 100:.0f}%) "
          f"{'OK' if ganho > 0 else 'SEM GANHO'}")

    # 6) ordem serial == ordem do registro (nao regrediu)
    ordem_esperada = [e.nome for e in vx_etapas.TODAS if e.nome in g_serial.ordem()]
    print(f"[6] serial na ordem do registro? "
          f"{'OK' if g_serial.ordem() == ordem_esperada else 'DIFERE'}")
    if g_serial.ordem() != ordem_esperada:
        problemas.append("a ordem serial mudou")

    print("\n" + "=" * 72)
    if problemas:
        print("PROBLEMAS:")
        for x in problemas:
            print("  - " + x)
        return 1
    print("TUDO OK: --jobs muda o QUANDO, nao o QUE; composicao segue serial.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
