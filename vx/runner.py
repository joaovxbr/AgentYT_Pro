"""Executor de etapas — in-process por padrao, subprocess como escape.

O problema que este modulo resolve: a esteira chamava `estudio.py` por
`subprocess` (71 pontos em `ferramentas/*.py`). Cada etapa custava um processo
Python novo — ~1-2 s so de import (numpy, torch, cv2 entram por import
preguicoso em `vx/lazy.py`) — e o erro voltava como `CalledProcessError` com um
`exit code`, sem o traceback real: `vx/metrics.py` registrava "exit 1" e o
operador tinha que abrir o log para saber o que morreu.

Aqui a etapa roda DENTRO do processo da esteira, chamando `estudio.main(argv)`.
O que isso muda:

- **erro tem contexto**: a excecao original sobe com traceback, `metrics`
  registra `origem_erro` com o tipo real em vez de "exit 1";
- **o processo nao e recriado**: o que ja foi importado fica importado;
- **o log continua existindo**: stdout/stderr da etapa vao para o MESMO arquivo
  `qa/esteira/<run_id>/NN_<etapa>.log` que o operador ja sabe abrir.

A pegadinha que isso cria, e que este modulo trata: `estudio.py` levanta
`SystemExit` em 28 pontos para sinalizar erro de entrada (letra ausente, ASS
faltando...). Em subprocess isso era so o exit code. In-process, `SystemExit`
NAO pode atravessar a esteira — ela morreria com um `SystemExit` cru, sem passar
pelo `finally` do pipeline. Todo `SystemExit` que nao seja 0 vira
`ErroDeEtapa`.

Falha fechada: qualquer saida que nao seja exatamente `0` reprova a etapa. Um
`main()` que devolve `None` (caminho nao tratado no dispatcher) conta como 0,
porque e o contrato de `estudio.main` — para reprovar precisa devolver != 0 or
levantar.

**Quando NAO usar in-process (`--isolado`):** etapa que suja estado global do
processo (le do `os.environ`, mexe em `sys.modules` de forma irreversivel) ou
que precisa morrer sozinha. O custo e voltar a pagar 1-2 s de import.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import ambiente

__all__ = ["ErroDeEtapa", "Resultado", "executar", "executar_isolado", "preparar_processo"]

RAIZ = Path(__file__).resolve().parents[1]
FERRAMENTAS = RAIZ / "ferramentas"


class ErroDeEtapa(RuntimeError):
    """Etapa reprovou. `codigo` e o que o subprocess teria devolvido (nunca 0)."""

    def __init__(self, mensagem: str, *, codigo: int | None = 1, etapa: str = "",
                 log: Path | None = None):
        super().__init__(mensagem)
        # Uma etapa que reprovou nunca tem codigo 0 (0 e sucesso); None vira 1.
        try:
            self.codigo = int(codigo) if codigo is not None else 1
        except (TypeError, ValueError):
            self.codigo = 1
        if self.codigo == 0:
            self.codigo = 1
        self.etapa = etapa
        self.log = log

    @property
    def origem(self) -> str:
        return "ErroDeEtapa"


@dataclass
class Resultado:
    """O que uma etapa entregou. `isolado` diz se pagou o custo do subprocess."""

    nome: str
    codigo: int
    duracao_s: float
    log: Path | None = None
    isolado: bool = False
    saida_vazia: bool = False

    @property
    def ok(self) -> bool:
        return self.codigo == 0


class _chdir_ctx:
    """Contexto de `os.chdir` com restauracao — `contextlib.chdir` so existe no 3.11+.

    A esteira roda em Python 3.10 (`.venv`), entao este e o caminho normal.
    """

    def __init__(self, alvo: Path):
        self.alvo = alvo
        self.antes: Path | None = None

    def __enter__(self):
        self.antes = Path.cwd()
        os.chdir(self.alvo)
        return self

    def __exit__(self, *exc):
        if self.antes is not None:
            os.chdir(self.antes)
        return False


def _cwd_seguro():
    """Garante que estamos na raiz do projeto durante a etapa.

    As etapas usam caminhos relativos (`RAIZ / ...` e `projetos/<slug>`); se o
    processo da esteira tiver sido iniciado de outro diretorio, um `chdir`
    acidental de qualquer etapa vazaria para as seguintes. Aqui o cwd e
    fixado antes e restaurado depois, exatamente como um subprocess faria
    (`cwd=RAIZ` em `executar_passo`).
    """
    return _chdir_ctx(RAIZ)


def _log_duplo(log_path: Path | None):
    """Devolve (contexto, buffer) que espelha stdout/stderr no log E no console.

    O operador ve a etapa acontecendo (nao fica mudo como no subprocess, que
    mandava tudo direto pro arquivo) e o log continua completo para depois.
    """
    return _Tee(log_path)


class _Tee:
    """Escreve no stream original E no arquivo. Erro de I/O nunca derruba a etapa."""

    def __init__(self, log_path: Path | None):
        self.log_path = log_path
        self._arquivo = None
        self._originais: dict[str, object] = {}

    def __enter__(self):
        if self.log_path is not None:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._arquivo = self.log_path.open("w", encoding="utf-8", errors="replace")
            except OSError:
                self._arquivo = None
        for nome in ("stdout", "stderr"):
            original = getattr(sys, nome)
            self._originais[nome] = original
            setattr(sys, nome, _FluxoTee(original, self._arquivo))
        return self

    def __exit__(self, *exc):
        for nome, original in self._originais.items():
            setattr(sys, nome, original)
        # stderr foi reconfigurado por `estudio.main`; restaurar o objeto de volta
        # e suficiente, mas o flush garante que nada ficou no buffer do arquivo.
        if self._arquivo is not None:
            try:
                self._arquivo.flush()
                self._arquivo.close()
            except OSError:
                pass
        return False


class _FluxoTee:
    """Delegua para o stream real; espelha no arquivo se houver."""

    def __init__(self, original, arquivo):
        self._original = original
        self._arquivo = arquivo

    def write(self, texto):
        if self._arquivo is not None:
            try:
                self._arquivo.write(texto)
            except (OSError, ValueError):
                self._arquivo = None
        return self._original.write(texto)

    def flush(self):
        if self._arquivo is not None:
            try:
                self._arquivo.flush()
            except (OSError, ValueError):
                pass
        try:
            self._original.flush()
        except (OSError, ValueError):
            pass

    def isatty(self):
        return getattr(self._original, "isatty", lambda: False)()

    def fileno(self):
        return self._original.fileno()

    def __getattr__(self, nome):
        return getattr(self._original, nome)


def preparar_processo():
    """Ambiente minimo para uma etapa rodar in-process.

    Equivale ao que o subprocess garantia de graca: ffmpeg/ffprobe no PATH e
    `ferramentas/` importavel (`estudio` importa irmaos por nome curto).
    """
    ambiente.garantir_path()
    for caminho in (str(RAIZ), str(FERRAMENTAS)):
        if caminho not in sys.path:
            sys.path.insert(0, caminho)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _argumentos(etapa: str, args, slug: str | None) -> list[str]:
    """Monta o argv que `estudio.main` espera, na mesma forma de antes."""
    argv = [str(a) for a in args]
    if slug:
        try:
            if slug not in argv:
                argv.insert(1, slug)
        except IndexError:
            argv = [etapa, slug]
    return argv


def executar(etapa: str, args, log_path: Path | None = None, *,
             slug: str | None = None, bloqueante: bool = True,
             isolado: bool = False) -> Resultado:
    """Roda a etapa DENTRO deste processo, com a saida espelhada no log.

    `isolado=True` delega para `executar_isolado` (subprocess) — mesma interface,
    mesmo log, mesmo contrato de erro. Usar quando a etapa precisar de processo
    limpo (estado global sujo, `os.environ` mexido, etc.).

    Levanta `ErroDeEtapa` quando o codigo de saida nao e 0 — o chamador decide
    se reprova a esteira (bloqueante) ou so registra aviso.
    """
    if isolado:
        return executar_isolado(etapa, args, log_path=log_path, slug=slug)
    if not etapa:
        raise ValueError("executar() precisa do nome da etapa")
    preparar_processo()
    argv = _argumentos(etapa, args, slug)
    log_path = Path(log_path) if log_path is not None else None
    t0 = time.perf_counter()
    saida = None
    try:
        import estudio  # import tardio: cada etapa paga so o que usa
        with _cwd_seguro():
            with _log_duplo(log_path):
                buffer = io.StringIO()
                saida = buffer
                codigo = estudio.main(argv)
    except SystemExit as exc:
        # Contrato do estudio.py: erro de entrada e SystemExit(str) -> 1.
        # In-process isso NAO pode atravessar a esteira (mataria o processo e o
        # `finally` do pipeline nunca fecharia as metricas).
        if isinstance(exc.code, int):
            codigo = exc.code
        else:
            codigo = 0 if exc.code is None else 1
        if codigo != 0:
            duracao = time.perf_counter() - t0
            raise ErroDeEtapa(f"{etapa}: {exc.code or 'falhou'}", codigo=codigo,
                              etapa=etapa, log=log_path) from None
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        duracao = time.perf_counter() - t0
        raise ErroDeEtapa(f"{etapa}: {type(exc).__name__}: {exc}", codigo=1,
                          etapa=etapa, log=log_path) from exc
    duracao = time.perf_counter() - t0
    codigo = 0 if codigo is None else int(codigo)
    if codigo != 0:
        raise ErroDeEtapa(f"{etapa}: exit {codigo}", codigo=codigo, etapa=etapa, log=log_path)
    return Resultado(nome=etapa, codigo=codigo, duracao_s=duracao, log=log_path,
                     saida_vazia=bool(saida is not None and not saida.getvalue()))


def executar_isolado(etapa: str, args, log_path: Path | None = None, *,
                     slug: str | None = None) -> Resultado:
    """Mesma interface, mas em subprocess — para etapa que exige processo limpo."""
    preparar_processo()
    argv = _argumentos(etapa, args, slug)
    cmd = [sys.executable, str(FERRAMENTAS / "estudio.py"), *argv]
    log_path = Path(log_path) if log_path is not None else None
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    t0 = time.perf_counter()
    if log_path is None:
        proc = subprocess.run(cmd, cwd=RAIZ, env=env)
    else:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, cwd=RAIZ, env=env, stdout=log,
                                  stderr=subprocess.STDOUT)
    duracao = time.perf_counter() - t0
    if proc.returncode != 0:
        raise ErroDeEtapa(f"{etapa}: exit {proc.returncode}", codigo=proc.returncode,
                          etapa=etapa, log=log_path)
    return Resultado(nome=etapa, codigo=0, duracao_s=duracao, log=log_path, isolado=True)
