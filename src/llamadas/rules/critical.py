"""E1: catalogo CERRADO de errores criticos (D-07). Las reglas solo generan CANDIDATOS: ninguna ausencia de evidencia
(que puede ser un error del STT) fija un 0 % por si sola; siempre pasa a revision humana."""
from __future__ import annotations

from ..textutil import fuzzy_has, normalize
from .context import Ctx

_NO_DISPONIBILIDAD = ["no hay disponibilidad", "no hay agenda", "sin disponibilidad", "no tenemos agenda", "no hay citas", "no hay cupo"]


def _crit(criteria: dict, code: str, sub_id: str):
    c = criteria.get(code)
    if not c:
        return None
    return next((s for s in c["sub_checks"] if s["id"] == sub_id), None)


def e1(ctx: Ctx, criteria: dict) -> dict:
    findings = []
    typ = ctx.call_type
    doc = _crit(criteria, "V1", "solicita_documento")
    agenda = _crit(criteria, "Z1", "cita_agendada")
    cancel = _crit(criteria, "Z1", "cancelacion_confirmada")
    acted = (agenda and agenda["passed"]) or (cancel and cancel["passed"])
    if typ in ("nueva_cita", "confirmacion", "cancelacion") and doc and doc["passed"] is False and acted:
        findings.append({"code": "E1.a", "source": "rule", "confidence": 0.5,
                         "description": "Se agendo/cancelo sin evidencia de validacion de identidad (solicitud de documento)",
                         "evidence": (agenda or cancel)["evidence"]})
    if typ == "nueva_cita" and agenda and agenda["passed"] is False:
        text = normalize(" ".join(t["text"] for t in ctx.turns))
        if not any(fuzzy_has(text, p) for p in _NO_DISPONIBILIDAD):
            findings.append({"code": "E1.c", "source": "rule", "confidence": 0.4,
                             "description": "Llamada de agendamiento sin confirmacion de que la cita quedo agendada",
                             "evidence": None})
    return {"status": "candidate_pending_review" if findings else "none", "findings": findings,
            "note": "Reglas solo proponen candidatos; E1 definitivo requiere revision humana (D-07)."}
