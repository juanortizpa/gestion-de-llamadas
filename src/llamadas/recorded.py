"""Deteccion de audio grabado (IVR inicial y bucle de espera/hold), que NO es el asesor ni el cliente.

Se detecta por texto (plantillas fijas + coincidencia aproximada), no por energia: la musica/mensajes
confunden al VAD. Estos intervalos se excluyen antes de la diarizacion (D-21) y sirven luego para G1.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from .config import Settings
from .textutil import normalize


def _matches(seg_text: str, corpus: str, thr: float, min_chars: int) -> bool:
    n = normalize(seg_text)
    if len(n) < min_chars:
        # frases cortas: solo si estan literalmente dentro de las plantillas
        return len(n) >= 8 and n in corpus
    return fuzz.partial_ratio(n, corpus) >= thr


def detect_recorded(segments: list[dict], settings: Settings) -> list[dict]:
    cfg = settings["recorded"]
    corpus = " ".join(normalize(t) for t in settings.lex["recorded"]["templates"])
    thr, minc = cfg["match_threshold"], cfg["min_chars"]
    flags = [_matches(s["text"], corpus, thr, minc) for s in segments]

    out: list[dict] = []
    # 1) IVR inicial: racha de coincidencias desde el principio (se toleran segmentos muy cortos sueltos)
    last = -1
    for i, (s, f) in enumerate(zip(segments, flags)):
        if f:
            last = i
            continue
        n = normalize(s["text"])
        if not any(ch.isalpha() for ch in n) or len(n.split()) < 4:
            continue  # solo digitos (telefono del WhatsApp) o fragmento muy corto: se absorbe
        # texto del IVR mal transcrito: se absorbe solo si PARECE IVR (ratio >= 60) y pronto vuelve a haber coincidencias.
        # (si no, la voz del asesor seria absorbida por una coincidencia posterior del bucle de hold)
        ahead = [j for j in range(i + 1, min(i + 4, len(segments)))
                 if flags[j] and segments[j]["start"] - s["end"] <= 15.0]
        # "emparedado" entre coincidencias y corto (p. ej. telefono de WhatsApp mal transcrito) tambien se absorbe
        sandwiched = last >= 0 and s["start"] - segments[last]["end"] <= 15.0 and len(n.split()) <= 10
        if not ahead or (fuzz.partial_ratio(n, corpus) < 60 and not sandwiched):
            break
    if last >= 0:
        out.append({"kind": "ivr_inicial", "start": 0.0, "end": segments[last]["end"],
                    "segments": last + 1})
    first_free = last + 1

    # 2) bucle de hold: coincidencias posteriores, agrupadas si estan cerca; exigen >= N coincidencias
    run: list[int] = []

    def close_run():
        if len(run) >= cfg["hold_loop_min_matches"]:
            # OJO: es audio grabado dentro de la llamada (bucle de espera o mensajes de cola). Que sea un HOLD
            # (G1) lo decide la Fase 2 mirando si el asesor lo anuncio antes.
            out.append({"kind": "grabado_en_llamada", "start": segments[run[0]]["start"],
                        "end": segments[run[-1]]["end"], "segments": len(run)})
        run.clear()

    for i in range(first_free, len(segments)):
        if not flags[i]:
            continue
        if run and segments[i]["start"] - segments[run[-1]]["end"] > cfg["hold_loop_max_gap_s"]:
            close_run()
        run.append(i)
    close_run()
    return out


def in_intervals(t: float, intervals: list[dict]) -> bool:
    return any(iv["start"] <= t < iv["end"] for iv in intervals)
