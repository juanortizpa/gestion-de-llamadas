"""Compara num_clusters (2..6) con metricas proxy (sin ground truth): reparto de palabras por rol y cambios de turno."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llamadas.config import ROOT, Settings, load_settings  # noqa: E402
from llamadas.pipeline import process_file  # noqa: E402

base = load_settings()
ids = sys.argv[1:] or ["2072716", "2072690", "2090657", "2091752", "1870590", "1870634", "1870686", "1870600", "2091790"]
files = {}
for d in ("llamadas no auditadas", "llamadas auditadas"):
    for p in (ROOT / d).iterdir():
        for i in ids:
            if f".{i}." in p.name and "(1)" not in p.name:
                files[i] = p
print(f"{'id':8} {'k':>2} {'%palabras asesor':>17} {'cambios/min':>12} {'turnos':>7} avisos")
for i in ids:
    for k in (2, 3, 4, 5, 6):
        raw = copy.deepcopy(base.raw)
        raw["diarization"]["num_clusters"] = k
        r = process_file(files[i], Settings(raw=raw, lex=base.lex))
        turns = r["turns"]
        w = {"ASESOR": 0, "CLIENTE": 0}
        for t in turns:
            if t["speaker"] in w:
                w[t["speaker"]] += len(t["text"].split())
        tot = sum(w.values()) or 1
        sw = sum(1 for a, b in zip(turns, turns[1:]) if a["speaker"] != b["speaker"])
        dur = r["call"]["duration_s"] / 60
        print(f"{i:8} {k:>2} {100 * w['ASESOR'] / tot:>16.0f}% {sw / dur:>12.1f} {len(turns):>7} {r['quality']['warnings']}", flush=True)
