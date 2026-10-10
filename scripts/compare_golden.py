"""Compara la auditoria por reglas contra la auditoria HUMANA de las 6 llamadas (tests/golden/auditadas.json).
IMPORTANTE: n=6 y 57/60 respuestas humanas son 1 => esto es prueba de humo, NO validacion estadistica."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
gold = json.loads((root / "tests/golden/auditadas.json").read_text())
codes = ["P1", "P2", "V1", "V2", "G1", "G2", "C1", "C2", "Z1", "Z2"]
agree = disagree = pending = 0
fail_detect = fail_total = 0
rows = []
for cid, g in gold.items():
    if cid.startswith("_"):
        continue
    au = json.loads((root / "data/results" / f"{cid}.audit.json").read_text(encoding="utf-8"))
    line = []
    for c in codes:
        cr = au["criteria"][c]
        sysv = cr["score"] if cr["applicable"] else 1
        hv = g[c]
        if sysv is None:
            tag, pending = "?", pending + 1
        elif sysv == hv:
            tag, agree = "=", agree + 1
        else:
            tag, disagree = ("X" if hv == 1 else "!"), disagree + 1
        if hv == 0:
            fail_total += 1
            fail_detect += 1 if sysv == 0 else 0
        line.append(tag)
    m = au["metrics"]
    rows.append((cid, g["aud"], " ".join(f"{c}{t}" for c, t in zip(codes, line)),
                 f"holdMax={m['longest_hold_s']}s muertoTot={m['dead_air_total_s']}s muertoMax={m['dead_air_longest_s']}s"))
print("= acuerdo | X sistema=0 humano=1 (falso fallo) | ! sistema=1 humano=0 (fallo no detectado) | ? pendiente")
for r in rows:
    print(r[0], r[1], r[2], "|", r[3])
tot = agree + disagree
print(f"\nAcuerdo en lo decidido: {agree}/{tot} = {100 * agree / max(tot, 1):.0f}%  | pendientes: {pending} | desacuerdos: {disagree}")
print(f"Fallos humanos detectados por el sistema: {fail_detect}/{fail_total}  (humano=0 en 3 casos: Z1, V1, V2)")
print("Linea base 'todo cumple': 57/60 = 95% de acuerdo con el humano (por eso el % de acuerdo engana)")
