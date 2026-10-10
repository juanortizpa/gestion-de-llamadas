"""Clasificacion del motivo de la llamada (decide la aplicabilidad de criterios, D-15)."""
from __future__ import annotations

from ..textutil import fuzzy_has, normalize
from .context import Ctx


def classify(ctx: Ctx) -> dict:
    lex = ctx.lex
    text_all = normalize(" ".join(t["text"] for t in ctx.turns))
    text_client = normalize(" ".join(t["text"] for t in ctx.turns if t["speaker"] == "CLIENTE")) if ctx.roles_ok else text_all

    def score(words, text):
        return sum(1 for w in words if fuzzy_has(text, w))

    s = {
        "cancelacion": 3 * score(lex["t_cancelacion"], text_client) + score(lex["t_cancelacion"], text_all),
        "confirmacion": 2 * score(lex["t_confirmacion"], text_client) + score(lex["t_confirmacion"], text_all),
        "nueva_cita": 2 * score(lex["t_nueva"], text_client) + score(lex["t_nueva"], text_all),
        "informacion": score(lex["t_info"], text_client) + score(lex["t_info"], text_all) * 0.5,
    }
    # cancelacion/confirmacion explicitas ganan: "cancelar una cita" tambien contiene "una cita" (nueva_cita)
    if s["cancelacion"] >= 3:
        return {"type": "cancelacion", "scores": s}
    if s["confirmacion"] >= 3:
        return {"type": "confirmacion", "scores": s}
    best = max(s, key=s.get)
    if s[best] < 2:
        return {"type": "desconocido", "scores": s}
    return {"type": best, "scores": s}
