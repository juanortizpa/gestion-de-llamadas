"""Speech-to-text con faster-whisper (CPU, int8) y cache por hash de archivo."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

from .config import Settings

_MODEL = {}


def _add_cuda_dlls() -> None:
    """Windows: faster-whisper necesita cuBLAS/cuDNN 12; los wheels nvidia-* los dejan en site-packages/nvidia/*/bin."""
    if not hasattr(os, "add_dll_directory"):
        return
    for p in sys.path:
        for d in Path(p, "nvidia").glob("*/bin") if p else ():
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def _cuda_ok() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _get_model(cfg: dict):
    device = cfg.get("device", "auto")
    if device == "auto":
        _add_cuda_dlls()
        device = "cuda" if _cuda_ok() else "cpu"
    elif device == "cuda":
        _add_cuda_dlls()
    compute = cfg["compute_type_gpu"] if device == "cuda" else cfg["compute_type"]
    key = (cfg["model"], device, compute, cfg["cpu_threads"])
    if key not in _MODEL:
        from faster_whisper import WhisperModel

        try:
            _MODEL[key] = WhisperModel(cfg["model"], device=device, compute_type=compute, cpu_threads=cfg["cpu_threads"])
        except Exception:
            if device != "cuda":
                raise
            # sin GPU utilizable (DLL/VRAM): se cae a CPU en vez de detener la auditoria
            return _get_model({**cfg, "device": "cpu"})
    return _MODEL[key]


def cache_path(settings: Settings, sha: str) -> Path:
    from .vocab import stt_hints

    cfg = settings["stt"]
    return settings.data_dir / "cache" / f"{sha[:16]}_stt_{cfg['model']}_b{cfg['beam_size']}{stt_hints(settings)[1]}.json"


def transcribe(audio: np.ndarray, settings: Settings, sha: str | None = None) -> list[dict]:
    """Devuelve segmentos [{start,end,text,words:[{w,s,e,p}]}]. Usa cache si existe."""
    if sha:
        cp = cache_path(settings, sha)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))
    from .vocab import stt_hints

    cfg = settings["stt"]
    prompt = stt_hints(settings)[0]       # prompt base + vocabulario del dominio (entrevista en Configuracion)
    model = _get_model(cfg)
    segs, _ = model.transcribe(
        audio, language=cfg["language"], beam_size=cfg["beam_size"], vad_filter=True,
        condition_on_previous_text=False, word_timestamps=True, initial_prompt=prompt,
    )
    out = [
        {"start": s.start, "end": s.end, "text": s.text.strip(),
         "words": [{"w": w.word, "s": w.start, "e": w.end, "p": round(w.probability, 3)} for w in (s.words or [])]}
        for s in segs
    ]
    if sha:
        cp = cache_path(settings, sha)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def speech_seconds(audio: np.ndarray) -> float:
    """Segundos de voz segun Silero VAD (el mismo de faster-whisper)."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    ts = get_speech_timestamps(audio, VadOptions(threshold=0.5))
    return sum(t["end"] - t["start"] for t in ts) / 16000
