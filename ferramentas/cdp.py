#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cdp.py — helper de navegador via Chrome DevTools Protocol (porta 9222).

O UNICO cliente CDP do estudio. Entre 31/08 e 01/09/2026 nasceram duas copias
proprias disto em assets/tiktok e assets/instagram e ~40 scripts que refaziam a
conexao e quebravam em pontos diferentes.

    🔴 Se algo nao funciona, conserte ESTE arquivo. Nao crie outra copia.

Licoes queimadas embutidas aqui:
- JS mora em string (arquivo), nunca em one-liner de shell (aspas comidas).
- /json/new e /json/close exigem PUT (Chrome >= 111), nao GET.
- envio de arquivo por DOM.setFileInputFiles (o seletor do sistema nao abre).
- clique que submete exige gesto real (Input.dispatchMouseEvent), nao el.click().
- legenda por Input.insertText (execCommand token a token quadruplica a mencao).
- toda aba aberta aqui e fechada no fim (try/finally), menos a obtida por anexar().

Requer o pacote `websocket-client` (pip install websocket-client) para a sessao
WebSocket. Sem ele, `disponivel()` retorna False e o publicar.py explica.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import List, Optional

try:
    import websocket  # type: ignore
    _TEM_WS = True
except ImportError:
    websocket = None
    _TEM_WS = False

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222


def _base() -> str:
    return f"http://{CDP_HOST}:{CDP_PORT}"


def disponivel() -> tuple[bool, str]:
    """(ok, motivo). Verifica biblioteca WS e o endpoint do Chrome de depuracao."""
    if not _TEM_WS:
        return False, ("falta o pacote 'websocket-client' "
                       "(pip install websocket-client)")
    try:
        with urllib.request.urlopen(_base() + "/json/version", timeout=3) as r:
            info = json.loads(r.read())
        return True, info.get("Browser", "Chrome")
    except Exception as e:
        return False, (f"Chrome de depuracao nao respondeu em {_base()} "
                       f"({e}). Suba o Chrome com --remote-debugging-port=9222.")


def _http(metodo: str, caminho: str) -> dict:
    req = urllib.request.Request(_base() + caminho, method=metodo)
    with urllib.request.urlopen(req, timeout=10) as r:
        corpo = r.read()
    return json.loads(corpo) if corpo else {}


class Pagina:
    """Uma aba do Chrome, controlada por WebSocket CDP."""

    def __init__(self, ws_url: str, target_id: str, minha: bool):
        self._ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0
        self.target_id = target_id
        self._minha = minha       # se True, eu fecho no fim
        self._reter = None
        self.enviar("Page.enable")
        self.enviar("Runtime.enable")
        self.enviar("DOM.enable")

    def enviar(self, metodo: str, params: dict = None) -> dict:
        self._id += 1
        mid = self._id
        self._ws.send(json.dumps({"id": mid, "method": metodo,
                                  "params": params or {}}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {metodo}: {msg['error']}")
                return msg.get("result", {})

    def avaliar(self, expr_js: str):
        r = self.enviar("Runtime.evaluate", {
            "expression": expr_js, "returnByValue": True, "awaitPromise": True})
        return r.get("result", {}).get("value")

    def navegar(self, url: str) -> None:
        self.enviar("Page.navigate", {"url": url})

    def esperar(self, seletor: str, timeout: float = 30.0) -> bool:
        import time
        fim = time.time() + timeout
        expr = f"!!document.querySelector({json.dumps(seletor)})"
        while time.time() < fim:
            if self.avaliar(expr):
                return True
            time.sleep(0.4)
        return False

    def enviar_arquivo(self, seletor_input: str, caminho: str) -> None:
        doc = self.enviar("DOM.getDocument", {"depth": -1})
        node = self.enviar("DOM.querySelector", {
            "nodeId": doc["root"]["nodeId"], "selector": seletor_input})
        self.enviar("DOM.setFileInputFiles", {
            "files": [caminho], "nodeId": node["nodeId"]})

    def digitar(self, texto: str) -> None:
        # Input.insertText: nao dispara autocomplete token a token
        self.enviar("Input.insertText", {"text": texto})

    def clicar_real(self, x: float, y: float) -> None:
        for tipo in ("mousePressed", "mouseReleased"):
            self.enviar("Input.dispatchMouseEvent", {
                "type": tipo, "x": x, "y": y, "button": "left",
                "clickCount": 1})

    def clicar_texto(self, texto: str) -> bool:
        js = f"""
        (() => {{
          const alvo = {json.dumps(texto)}.toLowerCase();
          const els = [...document.querySelectorAll('button,a,div[role=button],span')];
          const hit = els.reverse().find(e =>
            (e.textContent||'').trim().toLowerCase() === alvo);
          if (!hit) return null;
          const r = hit.getBoundingClientRect();
          return [r.left + r.width/2, r.top + r.height/2];
        }})()
        """
        pos = self.avaliar(js)
        if not pos:
            return False
        self.clicar_real(pos[0], pos[1])
        return True

    def reter(self, motivo: str) -> None:
        self._reter = motivo

    def fechar(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass
        if self._minha and not self._reter:
            try:
                _http("PUT", f"/json/close/{self.target_id}")
            except Exception:
                pass


class Navegador:
    """Contexto que fecha, no fim, TODA aba que ele proprio abriu."""

    def __init__(self):
        self._paginas: List[Pagina] = []

    def nova_aba(self, url: str = "about:blank") -> Pagina:
        info = _http("PUT", "/json/new?" + urllib.parse.quote(url, safe=""))
        pg = Pagina(info["webSocketDebuggerUrl"], info["id"], minha=True)
        if url and url != "about:blank":
            pg.navegar(url)
        self._paginas.append(pg)
        return pg

    def anexar(self, url_contem: str) -> Optional[Pagina]:
        for alvo in _http("GET", "/json/list"):
            if alvo.get("type") == "page" and url_contem in alvo.get("url", ""):
                pg = Pagina(alvo["webSocketDebuggerUrl"], alvo["id"], minha=False)
                self._paginas.append(pg)
                return pg
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for pg in self._paginas:
            pg.fechar()
        return False
