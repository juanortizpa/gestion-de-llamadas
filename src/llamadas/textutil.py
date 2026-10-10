"""Normalizacion de texto compartida por todas las reglas."""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SENT = re.compile(r"(?<=[.?!])\s+")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """minuscula, sin tildes (conserva la n), sin puntuacion, espacios simples."""
    text = text.lower().replace("ñ", "\x00")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("\x00", "n")
    return _WS.sub(" ", _PUNCT.sub(" ", text)).strip()


def fuzzy_has(text_n: str, phrase: str, thr: float = 85) -> bool:
    """Frases cortas (<8 car.): palabra completa exacta. Largas: contenida o coincidencia aproximada."""
    if len(phrase) < 8:
        return f" {phrase} " in f" {text_n} "
    if phrase in text_n:
        return True
    # partial_ratio da 100 si el texto (muy corto) esta DENTRO de la frase: exigir texto de tamano comparable
    return len(text_n) >= 0.6 * len(phrase) and fuzz.partial_ratio(phrase, text_n) >= thr


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def best_sentence(text: str, phrases: list[str], thr: float = 85) -> str | None:
    """Oracion LITERAL del texto que mejor coincide con alguna frase (sirve como cita/evidencia)."""
    best, best_score = None, 0.0
    for s in sentences(text):
        sn = normalize(s)
        for p in phrases:
            if len(p) < 8:
                sc = 100.0 if f" {p} " in f" {sn} " else 0.0
            else:
                sc = 100.0 if p in sn else (fuzz.partial_ratio(p, sn) if len(sn) >= 0.6 * len(p) else 0.0)
            if sc > best_score:
                best, best_score = s, sc
    return best if best_score >= thr else None
