"""Fase 1: .gsm -> transcripcion estructurada (turnos asesor/cliente) con audio grabado excluido."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import __version__
from .audio import load_audio, parse_filename, sha256_file
from .config import Settings, load_settings
from .diarize import diarize
from .recorded import detect_recorded, in_intervals
from .roles import assign_roles
from .stt import speech_seconds, transcribe
from .transcript import assign_speakers, build_turns, flatten_words

SCHEMA_VERSION = "0.1-fase1"


def process_file(path: Path, settings: Settings | None = None, log=lambda m: None) -> dict:
    settings = settings or load_settings()
    t0 = time.time()
    meta = parse_filename(path.name)
    sha = sha256_file(path)
    log("decodificando audio")
    audio = load_audio(path, settings["audio"]["sample_rate"])
    duration = len(audio) / settings["audio"]["sample_rate"]
    warnings: list[str] = []

    result = {
        "schema_version": SCHEMA_VERSION,
        "call": {"call_id": meta.get("call_id", sha[:12]), "source_file": meta["masked_name"], "sha256": sha,
                 "duration_s": round(duration, 1), "queue": meta.get("queue"), "caller_masked": meta.get("caller_masked"),
                 "received_date": meta.get("date"), "received_time": meta.get("time")},
        "pipeline": {"llamadas": __version__, "stt_model": settings["stt"]["model"],
                     "stt_beam": settings["stt"]["beam_size"], "diarization": "sherpa-onnx pyannote-seg3.0 + titanet_small",
                     "num_clusters": settings["diarization"]["num_clusters"]},
    }

    speech_s = speech_seconds(audio)
    if speech_s < settings["audio"]["min_speech_s"]:
        result.update(status="no_speech", quality={"speech_s": round(speech_s, 1), "warnings": ["sin_conversacion_detectable"]},
                      recorded_intervals=[], speakers={}, turns=[])
        result["pipeline"]["processing_s"] = round(time.time() - t0, 1)
        return result

    log("transcribiendo")
    segments = transcribe(audio, settings, sha)
    recorded = detect_recorded(segments, settings)
    log(f"audio grabado detectado: {[(r['kind'], round(r['start']), round(r['end'])) for r in recorded]}")

    words_all = flatten_words(segments)
    human_words = [w for w in words_all if not in_intervals((w["s"] + w["e"]) / 2, recorded)]
    rec_text = {}
    for r in recorded:
        rec_text[r["kind"]] = rec_text.get(r["kind"], 0) + 1

    log("diarizando")
    diar, human_s = diarize(audio, recorded, settings)
    if not diar:
        warnings.append("audio_humano_insuficiente_para_diarizar")
        for w in human_words:
            w["spk"] = None
    else:
        assign_speakers(human_words, diar)

    turns = build_turns(human_words, settings["turns"]["merge_gap_s"]) if human_words else []
    roles = assign_roles(turns, settings) if diar else {"roles": {}, "confidence": 0.0, "scores": {}}
    if roles.get("warning"):
        warnings.append(roles["warning"])
    for t in turns:
        t["speaker"] = roles["roles"].get(t["spk"], "DESCONOCIDO") if t["spk"] is not None else "DESCONOCIDO"
    # turnos consecutivos con el mismo ROL (aunque vengan de clusters distintos) se funden en uno
    merged: list[dict] = []
    for t in turns:
        if merged and merged[-1]["speaker"] == t["speaker"] and t["start"] - merged[-1]["end"] <= settings["turns"]["merge_gap_s"]:
            merged[-1]["end"] = t["end"]
            merged[-1]["text"] += " " + t["text"]
        else:
            merged.append(dict(t))
    for i, t in enumerate(merged, 1):
        t["turn_id"] = i
    turns = merged

    share = {"ASESOR": 0, "CLIENTE": 0}
    for t in turns:
        if t["speaker"] in share:
            share[t["speaker"]] += len(t["text"].split())
    tot_w = sum(share.values())
    if tot_w and diar and min(share.values()) / tot_w < settings["turns"]["min_role_share"]:
        warnings.append("diarizacion_sospechosa_un_rol_casi_sin_habla")

    avg_p = round(sum(w["p"] for w in human_words) / len(human_words), 3) if human_words else 0.0
    if avg_p and avg_p < 0.6:
        warnings.append("transcripcion_baja_confianza")
    status = "needs_review" if warnings else "completed"

    result.update(
        status=status,
        quality={"speech_s": round(speech_s, 1), "human_audio_s": round(human_s, 1), "n_words": len(human_words),
                 "avg_word_prob": avg_p, "role_confidence": roles["confidence"], "warnings": warnings},
        recorded_intervals=[{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()} for r in recorded],
        speakers={"clusters_por_rol": {str(k): v for k, v in roles["roles"].items()},
                  "scores": {str(k): v for k, v in roles["scores"].items()}},
        turns=[{"turn_id": t["turn_id"], "speaker": t["speaker"], "start": round(t["start"], 2), "end": round(t["end"], 2),
                "text": t["text"], "avg_prob": t["avg_prob"]} for t in turns],
    )
    result["pipeline"]["processing_s"] = round(time.time() - t0, 1)
    return result


def save_result(result: dict, settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    out = settings.data_dir / "results"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{result['call']['call_id']}.transcript.json"
    p.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
