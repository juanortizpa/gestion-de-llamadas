"""Siembra la cache de STT con los resultados del benchmark (evita re-transcribir al desarrollar).

Mapea cada archivo de muestra -> sha256 -> data/cache/<sha16>_stt_medium_b1.json usando el id unico del nombre.
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llamadas.audio import sha256_file  # noqa: E402
from llamadas.config import ROOT, load_settings  # noqa: E402
from llamadas.stt import cache_path  # noqa: E402

s = load_settings()
src_dir = ROOT / "benchmarks" / "results" / f"{s['stt']['model']}_beam{s['stt']['beam_size']}"
n = 0
for folder in ("llamadas no auditadas", "llamadas auditadas"):
    for f in (ROOT / folder).iterdir():
        m = re.search(r"\.(\d+)\.(gsm|mp3)$", f.name)
        if not m or "(1)" in f.name:
            continue
        j = src_dir / f"{m.group(1)}.json"
        if j.exists():
            cp = cache_path(s, sha256_file(f))
            cp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(j, cp)
            n += 1
print("cache sembrada:", n)
