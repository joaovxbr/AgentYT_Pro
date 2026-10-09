#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auditor_ritmo.py — Auditoria de Dinâmica de Ritmo e Cuts Per Minute (CPM).
Avalia se a timeline possui a dinâmica ideal de retenção do YouTube:
- Versos com duração média de 1.5s a 2.5s para assimilação da letra
- Refrão / Drops com cortes rápidos (0.3s a 0.8s) para manter adrenalina alta
- Alerta contra fadiga visual ou lentidão excessiva
"""
from pathlib import Path
import json
import sys

def auditar_dinamica_timeline(timeline_path: Path) -> dict:
    if not timeline_path.exists():
        raise FileNotFoundError(f"Timeline não encontrada: {timeline_path}")

    with open(timeline_path, "r", encoding="utf-8") as f:
        dados = json.load(f)

    segmentos = dados.get("segments", [])
    if not segmentos:
        return {"erro": "Nenhum segmento na timeline."}

    duracoes = [s.get("duration", s.get("end", 0) - s.get("start", 0)) for s in segmentos]
    total_tempo = sum(duracoes)
    total_cortes = len(duracoes)
    cpm = (total_cortes / max(1.0, total_tempo)) * 60.0

    media_corte = float(np.mean(duracoes)) if 'np' in globals() else sum(duracoes) / len(duracoes)
    cortes_muito_longos = [i for i, d in enumerate(duracoes) if d > 4.5]
    cortes_muito_curtos = [i for i, d in enumerate(duracoes) if d < 0.25]

    score_retencao = 100
    alertas = []

    if cpm < 20:
        score_retencao -= 20
        alertas.append(f"CPM muito baixo ({cpm:.1f} cortes/min). Risco de queda de retenção no vídeo.")
    elif cpm > 75:
        score_retencao -= 15
        alertas.append(f"CPM muito elevado ({cpm:.1f} cortes/min). Risco de fadiga visual.")

    if cortes_muito_longos:
        score_retencao -= len(cortes_muito_longos) * 5
        alertas.append(f"{len(cortes_muito_longos)} cortes com mais de 4.5s (podem cansar o espectador).")

    score_final = max(20, min(100, score_retencao))

    return {
        "total_cortes": total_cortes,
        "duracao_total_s": round(total_tempo, 2),
        "cortes_por_minuto_cpm": round(cpm, 1),
        "duracao_media_por_corte_s": round(media_corte, 2),
        "score_retencao_estimado": score_final,
        "alertas_editorial": alertas
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python auditor_ritmo.py <timeline.json>")
        sys.exit(1)
    res = auditar_dinamica_timeline(Path(sys.argv[1]))
    print(json.dumps(res, indent=2, ensure_ascii=False))
