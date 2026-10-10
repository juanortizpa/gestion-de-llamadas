"""Speech-to-text con faster-whisper (CPU, int8) y cache por hash de archivo."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import Settings

_MODEL = {}


def _get_model(cfg: dict):
    key = (cfg["model"], cfg["compute_type"], cfg["cpu_threads"])
    if key not in _MODEL:
        from faster_whisper import WhisperModel

        _MODEL[key] = WhisperModel(cfg["model"], device="cpu", compute_type=cfg["compute_type"],
                                   cpu_threads=cfg["cpu_threads"])
    return _MODEL[key]


def cache_path(settings: Settings, sha: str) -> Path:
    cfg = settings["stt"]
    return settings.data_dir / "cache" / f"{sha[:16]}_stt_{cfg['model']}_b{cfg['beam_size']}.json"


def transcribe(audio: np.ndarray, settings: Settings, sha: str | None = None) -> list[dict]:
    """Devuelve segmentos [{start,end,text,words:[{w,s,e,p}]}]. Usa cache si existe."""
    if sha:
        cp = cache_path(settings, sha)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))
    cfg = settings["stt"]
    model = _get_model(cfg)
    segs, _ = model.transcribe(
        audio, language=cfg["language"], beam_size=cfg["beam_size"], vad_filter=True,
        condition_on_previous_text=False, word_timestamps=True, initial_prompt=cfg["initial_prompt"],
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
