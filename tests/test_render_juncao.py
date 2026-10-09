"""Regressao: render do corpo cortado no meio (Douma, incidente 2026-09-30-douma-render-cortado).

O concat demuxer parava em 105,8 s / 89,2 s de 179,9 s. A juncao agora e por bytes H.264
(Annex B) com contagem exata de quadros; plano menor que meio quadro e pulado sem perder tempo.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "ferramentas"))

import render_clipe as rc  # noqa: E402


class JuncaoPorBytesTests(unittest.TestCase):
    def _rodar(self, segmentos, quadros_por_arquivo=None):
        encodes = []

        def falso_encode(saida, entradas, **kw):
            encodes.append((saida, entradas, kw))
            extra = kw.get("args_extra") or []
            n = int(extra[extra.index("-frames:v") + 1]) if "-frames:v" in extra else 0
            Path(saida).write_bytes(b"Q" * n)          # 1 byte = 1 quadro no falso fluxo
            return saida

        def falso_contar(p):
            p = Path(p)
            if quadros_por_arquivo and p.name in quadros_por_arquivo:
                return quadros_por_arquivo[p.name]
            return p.stat().st_size

        timeline = {"segments": segmentos}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(rc, "validar", return_value=[]), \
                mock.patch.object(rc, "duracao", return_value=1000.0), \
                mock.patch.object(rc, "fonte", side_effect=lambda d, c: Path(c)), \
                mock.patch.object(rc.rd, "encode", side_effect=falso_encode), \
                mock.patch.object(rc, "contar_quadros", side_effect=falso_contar):
            dur = float(segmentos[-1]["end"])
            rc.previa(Path(tmp), timeline, Path("a.wav"), Path(tmp) / "out.mp4", 0.0, dur, com_movimento=False)
        return encodes

    def test_plano_de_7ms_e_pulado_e_total_fica_exato(self):
        segs = [{"clip": "a.mp4", "src": 0, "start": 0.0, "end": 27.36},
                {"clip": "b.mp4", "src": 0, "start": 27.36, "end": 27.367},
                {"clip": "c.mp4", "src": 0, "start": 27.367, "end": 30.0}]
        encodes = self._rodar(segs)
        planos = [e for e in encodes if str(e[0]).endswith(".h264")]
        self.assertEqual(len(planos), 2)
        juncao = [e for e in encodes if str(e[0]).endswith("bruto.mp4")][0]
        self.assertIn("h264", juncao[1])                      # remontado do fluxo cru, nao do concat demuxer
        fluxo = Path(juncao[1][-1])
        self.assertEqual(fluxo.name, "bruto.h264")

    def test_plano_com_quadros_faltando_reprova(self):
        segs = [{"clip": "a.mp4", "src": 0, "start": 0.0, "end": 2.0},
                {"clip": "b.mp4", "src": 0, "start": 2.0, "end": 4.0}]
        with self.assertRaisesRegex(RuntimeError, "quadros faltando"):
            self._rodar(segs, quadros_por_arquivo={"0001.h264": 30})


if __name__ == "__main__":
    unittest.main()
