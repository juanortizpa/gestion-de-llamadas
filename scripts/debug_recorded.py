"""Depuracion: muestra por segmento el puntaje de coincidencia con las plantillas de audio grabado."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rapidfuzz import fuzz  # noqa: E402
from llamadas.config import ROOT, load_settings  # noqa: E402
from llamadas.textutil import normalize  # noqa: E402

s = load_settings()
corpus = " ".join(normalize(t) for t in s.lex["recorded"]["templates"])
for cid in sys.argv[1:]:
    segs = json.load(open(ROOT / "benchmarks/results/medium_beam1" / f"{cid}.json", encoding="utf-8"))
    print("=====", cid)
    for g in segs[:12]:
        n = normalize(g["text"])
        print(f"[{g['start']:6.1f}] {fuzz.partial_ratio(n, corpus):5.1f} len={len(n):3d} {g['text'][:110]}")
