"""Metricas por timestamps: huecos entre turnos, esperas (hold) y tiempo muerto.

Un hueco entre dos turnos humanos consecutivos se clasifica como:
  - "grabado":  solapa audio grabado dentro de la llamada (bucle de espera / mensajes de cola)
  - "anunciado": uno de los 2 turnos previos contiene una frase de espera ("permitame un momento"...)
  - "silencio":  tiempo muerto sin anunciar
El IVR/cola ANTERIOR al primer turno humano no cuenta.
"""
from __future__ import annotations

from .config import Settings
from .textutil import fuzzy_has, normalize


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def compute_metrics(tr: dict, settings: Settings) -> dict:
    turns = tr["turns"]
    rules = settings["rules"]
    hold_phr = settings.lex["rules"]["hold_phrases"]
    recorded = [r for r in tr.get("recorded_intervals", []) if r["kind"] == "grabado_en_llamada"]
    duration = tr["call"]["duration_s"]

    def announces(t: dict) -> bool:
        n = normalize(t["text"])
        return any(fuzzy_has(n, p) for p in hold_phr)

    gaps = []
    for i in range(len(turns) - 1):
        a, b = turns[i], turns[i + 1]
        g0, g1 = a["end"], b["start"]
        dur = g1 - g0
        if dur < rules["hold_min_gap_s"]:
            continue
        rec_ov = sum(_overlap(g0, g1, r["start"], r["end"]) for r in recorded)
        ann = announces(a) or (i > 0 and announces(turns[i - 1]))
        kind = "grabado" if rec_ov >= 0.5 * dur else ("anunciado" if ann else "silencio")
        gaps.append({"start": round(g0, 1), "end": round(g1, 1), "duration_s": round(dur, 1), "kind": kind,
                     "turn_before": a["turn_id"], "turn_after": b["turn_id"], "recorded_s": round(rec_ov, 1)})

    # espera final: el audio termina durante un hold (el ultimo turno anuncia espera y no vuelve a hablar nadie)
    if turns and duration - turns[-1]["end"] >= rules["hold_min_gap_s"] and announces(turns[-1]):
        gaps.append({"start": round(turns[-1]["end"], 1), "end": round(duration, 1),
                     "duration_s": round(duration - turns[-1]["end"], 1), "kind": "anunciado",
                     "turn_before": turns[-1]["turn_id"], "turn_after": None, "recorded_s": 0.0})

    holds = [g for g in gaps if g["kind"] in ("grabado", "anunciado")]
    dead = [g for g in gaps if g["kind"] == "silencio" and g["duration_s"] >= rules["g2_gap_s"]]
    words = {"ASESOR": 0, "CLIENTE": 0}
    for t in turns:
        if t["speaker"] in words:
            words[t["speaker"]] += len(t["text"].split())
    tw = sum(words.values()) or 1
    h_start = turns[0]["start"] if turns else 0.0
    h_end = turns[-1]["end"] if turns else 0.0
    return {
        "human_start_s": round(h_start, 1), "human_end_s": round(h_end, 1),
        "human_span_s": round(h_end - h_start, 1),
        "word_share": {k: round(v / tw, 2) for k, v in words.items()},
        "hold_events": holds,
        "longest_hold_s": max((g["duration_s"] for g in holds), default=0.0),
        "dead_air_events": dead,
        "dead_air_total_s": round(sum(g["duration_s"] for g in dead), 1),
        "dead_air_longest_s": max((g["duration_s"] for g in dead), default=0.0),
        "silence_gaps_all": [g for g in gaps if g["kind"] == "silencio"],
    }
