"""Registra las muestras ya procesadas (copia el audio a data/audio_store para poder escucharlas en la interfaz)."""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llamadas.audio import sha256_file  # noqa: E402
from llamadas.config import ROOT, load_settings  # noqa: E402
from llamadas.jobs import _register, store_dir  # noqa: E402

s = load_settings()
n = 0
for folder in ("llamadas no auditadas", "llamadas auditadas"):
    for f in sorted((ROOT / folder).iterdir()):
        m = re.search(r"\.(\d+)\.(gsm|mp3)$", f.name)
        if not m or "(1)" in f.name:
            continue
        cid = m.group(1)
        if (s.data_dir / "results" / f"{cid}.audit.json").exists():
            shutil.copy(f, store_dir(s) / f"{cid}{f.suffix.lower()}")
            _register(s, sha256_file(f), cid)
            n += 1
print("audios registrados:", n)
