"""Alineacion palabra<->hablante y construccion de turnos."""
from __future__ import annotations


def flatten_words(segments: list[dict]) -> list[dict]:
    words = []
    for s in segments:
        ws = s.get("words") or []
        if ws:
            words.extend({"w": w["w"], "s": w["s"], "e": w["e"], "p": w.get("p", 1.0)} for w in ws)
        elif s["text"]:  # sin timestamps por palabra: repartir el segmento
            toks = s["text"].split()
            dur = (s["end"] - s["start"]) / max(len(toks), 1)
            words.extend({"w": " " + t, "s": s["start"] + i * dur, "e": s["start"] + (i + 1) * dur, "p": 1.0}
                         for i, t in enumerate(toks))
    return words


def assign_speakers(words: list[dict], diar: list[dict], max_snap_s: float = 1.0) -> None:
    """Asigna 'spk' a cada palabra por maximo solapamiento; si no hay, el segmento mas cercano; si no, el previo."""
    prev = None
    for w in words:
        best, best_ov = None, 0.0
        for d in diar:
            ov = min(w["e"], d["end"]) - max(w["s"], d["start"])
            if ov > best_ov:
                best, best_ov = d["spk"], ov
        if best is None and diar:
            mid = (w["s"] + w["e"]) / 2
            near = min(diar, key=lambda d: 0 if d["start"] <= mid <= d["end"] else min(abs(mid - d["start"]), abs(mid - d["end"])))
            dist = 0 if near["start"] <= mid <= near["end"] else min(abs(mid - near["start"]), abs(mid - near["end"]))
            best = near["spk"] if dist <= max_snap_s else prev
        w["spk"] = best if best is not None else prev
        prev = w["spk"]


def build_turns(words: list[dict], merge_gap_s: float) -> list[dict]:
    """Agrupa palabras consecutivas del mismo hablante (pausa < merge_gap_s) en turnos."""
    turns: list[dict] = []
    for w in words:
        if turns and turns[-1]["spk"] == w["spk"] and w["s"] - turns[-1]["end"] <= merge_gap_s:
            t = turns[-1]
            t["end"] = w["e"]
            t["text"] += w["w"] if w["w"].startswith(" ") else " " + w["w"]
            t["probs"].append(w["p"])
        else:
            turns.append({"spk": w["spk"], "start": w["s"], "end": w["e"], "text": w["w"].strip(), "probs": [w["p"]]})
    for i, t in enumerate(turns, 1):
        t["turn_id"] = i
        t["text"] = " ".join(t["text"].split())
        t["avg_prob"] = round(sum(t["probs"]) / len(t["probs"]), 3)
        del t["probs"]
    return turns
