"""Import preguicoso de modulos.

Problema que resolve: `estudio.py` importava ~55 modulos no topo. Um import
quebrado (dependencia ausente, erro de sintaxe) derrubava TODOS os comandos,
inclusive as etapas da esteira, e cada etapa (subprocess) pagava o custo de
carregar cv2/librosa/torch mesmo sem usar.

`modulo("nome")` devolve um proxy: o import real acontece no primeiro acesso a
um atributo. O erro, se houver, aparece so no comando que usa o modulo.
"""
from __future__ import annotations

import importlib
import types


class _ModuloPreguicoso(types.ModuleType):
    def __init__(self, nome: str):
        super().__init__(nome)
        self.__dict__["_vx_nome"] = nome
        self.__dict__["_vx_real"] = None

    def _vx_carregar(self):
        real = self.__dict__["_vx_real"]
        if real is None:
            real = importlib.import_module(self.__dict__["_vx_nome"])
            self.__dict__["_vx_real"] = real
        return real

    def __getattr__(self, item):
        return getattr(self._vx_carregar(), item)

    def __setattr__(self, item, valor):
        # patch.object(proxy, "f", ...) precisa valer tambem dentro do modulo real
        setattr(self._vx_carregar(), item, valor)

    def __delattr__(self, item):
        delattr(self._vx_carregar(), item)

    def __dir__(self):
        return dir(self._vx_carregar())

    def __repr__(self):
        estado = "carregado" if self.__dict__["_vx_real"] is not None else "pendente"
        return f"<modulo preguicoso {self.__dict__['_vx_nome']} ({estado})>"


def modulo(nome: str) -> types.ModuleType:
    return _ModuloPreguicoso(nome)


class _Opcional:
    """Dependencia opcional (ex.: rembg). `bool(proxy)` e False se o import falhar.

    Uso: `if not saber_mod: erro...` -> so tenta importar quando o comando roda.
    """

    def __init__(self, nome: str):
        self._nome = nome
        self._real = None
        self._falhou = False

    def _carregar(self):
        if self._real is None and not self._falhou:
            try:
                self._real = importlib.import_module(self._nome)
            except ImportError:
                self._falhou = True
        return self._real

    def __bool__(self):
        return self._carregar() is not None

    def __getattr__(self, item):
        real = self._carregar()
        if real is None:
            raise ImportError(f"dependencia opcional ausente: {self._nome}")
        return getattr(real, item)


def modulo_opcional(nome: str) -> _Opcional:
    return _Opcional(nome)
