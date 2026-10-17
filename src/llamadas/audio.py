"""Entrada de audio: .gsm (GSM 06.10 crudo), .mp3, .wav -> float32 mono 16 kHz via ffmpeg."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np


def find_ffmpeg() -> str:
    """ffmpeg del sistema si existe; si no, el que trae el paquete pip `imageio-ffmpeg` (binario propio de cada SO)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for cand in base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
        return str(cand)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("ffmpeg no encontrado: ejecute iniciar.py de nuevo (lo instala) o instale ffmpeg en el sistema") from None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_audio(path: Path, sample_rate: int = 16000) -> np.ndarray:
    """Decodifica a float32 mono. Los .gsm crudos se declaran a 8 kHz."""
    cmd = [find_ffmpeg(), "-v", "error", "-nostdin"]
    if path.suffix.lower() == ".gsm":
        cmd += ["-f", "gsm", "-ar", "8000"]
    cmd += ["-i", str(path), "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1"]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError(f"ffmpeg fallo con {path.name}: {res.stderr.decode(errors='replace')[:300]}")
    return np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0


_NAME_RE = re.compile(r"^q-(?P<cola>\d+)-(?P<tel>\d+)-(?P<fecha>\d{8})-(?P<hora>\d{6})-(?P<epoch>\d+)\.(?P<uid>\d+)")


def parse_filename(name: str) -> dict:
    """Metadatos del nombre Asterisk de cola. El telefono (PII) se devuelve ya enmascarado."""
    m = _NAME_RE.match(name)
    if not m:
        return {"masked_name": name}
    tel = m["tel"]
    masked = tel[:3] + "*" * max(len(tel) - 6, 0) + tel[-3:] if len(tel) > 6 else "***"
    return {
        "call_id": m["uid"],
        "queue": m["cola"],
        "caller_masked": masked,
        "date": m["fecha"],
        "time": m["hora"],
        "masked_name": name.replace(tel, masked),
    }
