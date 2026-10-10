"""Depuracion: diariza un archivo mostrando tiempos por hablante tras excluir audio grabado."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llamadas.audio import load_audio, sha256_file  # noqa: E402
from llamadas.config import ROOT, load_settings  # noqa: E402
from llamadas.diarize import diarize  # noqa: E402
from llamadas.recorded import detect_recorded  # noqa: E402
from llamadas.stt import transcribe  # noqa: E402

s = load_settings()
f = next(p for d in ("llamadas no auditadas", "llamadas auditadas") for p in (ROOT / d).iterdir() if sys.argv[1] in p.name)
a = load_audio(f)
segs = transcribe(a, s, sha256_file(f))
rec = detect_recorded(segs, s)
print("grabado:", [(r["kind"], round(r["start"]), round(r["end"])) for r in rec])
d, hs = diarize(a, rec, s)
print("audio humano:", round(hs, 1), "s; segmentos:", len(d))
for k in sorted({x["spk"] for x in d}):
    print("spk", k, round(sum(x["end"] - x["start"] for x in d if x["spk"] == k), 1), "s")
print([(x["start"], x["end"], x["spk"]) for x in d][:15])
