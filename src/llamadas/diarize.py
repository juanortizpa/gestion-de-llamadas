"""Diarizacion a 2 hablantes con sherpa-onnx (segmentacion pyannote-3.0 ONNX + titanet_small).

El audio grabado (IVR/hold) se EXCLUYE antes de agrupar: un bucle de hold secuestra un cluster (B2).
"""
from __future__ import annotations

import numpy as np

from .config import Settings

SR = 16000
_SD = {}


def _get_sd(settings: Settings):
    cfg = settings["diarization"]
    key = (cfg["segmentation_model"], cfg["embedding_model"], cfg["num_clusters"])
    if key not in _SD:
        import sherpa_onnx as so

        md = settings.models_dir
        _SD[key] = so.OfflineSpeakerDiarization(so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(
                pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(md / cfg["segmentation_model"])),
                num_threads=4),
            embedding=so.SpeakerEmbeddingExtractorConfig(model=str(md / cfg["embedding_model"]), num_threads=4),
            clustering=so.FastClusteringConfig(num_clusters=cfg["num_clusters"]),
            min_duration_on=0.3, min_duration_off=0.5))
    return _SD[key]


def keep_intervals(duration: float, recorded: list[dict]) -> list[tuple[float, float]]:
    """Complemento de los intervalos grabados dentro de [0, duration]."""
    keep, cur = [], 0.0
    for iv in sorted(recorded, key=lambda x: x["start"]):
        if iv["start"] > cur:
            keep.append((cur, iv["start"]))
        cur = max(cur, iv["end"])
    if cur < duration:
        keep.append((cur, duration))
    return [(a, b) for a, b in keep if b - a > 0.2]


def diarize(audio: np.ndarray, recorded: list[dict], settings: Settings) -> tuple[list[dict], float]:
    """Devuelve (segmentos [{start,end,spk}] en tiempo ORIGINAL, segundos de audio humano analizado)."""
    keep = keep_intervals(len(audio) / SR, recorded)
    human_s = sum(b - a for a, b in keep)
    if human_s < settings["diarization"]["min_audio_s"]:
        return [], human_s
    chunks = [audio[int(a * SR):int(b * SR)] for a, b in keep]
    cat = np.concatenate(chunks)
    # mapa tiempo concatenado -> original
    offs, acc = [], 0.0
    for a, b in keep:
        offs.append((acc, acc + (b - a), a))
        acc += b - a

    def to_orig(t: float) -> float:
        for c0, c1, o in offs:
            if c0 <= t <= c1:
                return o + (t - c0)
        c0, c1, o = offs[-1]
        return o + (c1 - c0)

    # Silencio al final: si el ultimo segmento de habla toca el borde del audio, sherpa-onnx 1.13 recorta su
    # embedding y aborta el proceso entero en C++ ("This segment is too short"); Python no lo puede capturar.
    cat = np.concatenate([cat, np.zeros(2 * SR, dtype=cat.dtype)])
    res = _get_sd(settings).process(cat).sort_by_start_time()
    segs: list[dict] = []
    for r in res:
        # un segmento puede cruzar un corte: se parte por tramo
        for c0, c1, o in offs:
            s, e = max(r.start, c0), min(r.end, c1)
            if e - s > 0.05:
                segs.append({"start": round(o + (s - c0), 2), "end": round(o + (e - c0), 2), "spk": int(r.speaker)})
    return segs, human_s
