"""Fase 2: transcripcion estructurada -> auditoria PARCIAL por reglas/timestamps (sin LLM)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Settings, load_settings
from .metrics import compute_metrics
from .rules.calltype import classify
from .rules.closing import z1, z2
from .rules.context import Ctx, roles_reliable
from .rules.critical import e1
from .rules.flow import c1, c2, g1, g2
from .rules.identity import p1, p2, v1, v2

SCHEMA_VERSION = "0.2-fase2"
ORDER = ["P1", "P2", "V1", "V2", "G1", "G2", "C1", "C2", "Z1", "Z2"]
NAMES = {"P1": "Saludo guion", "P2": "Nombre cliente", "V1": "Conf. documento", "V2": "Valida datos/hist", "G1": "Control hold",
         "G2": "Agilidad sistema", "C1": "Escucha activa", "C2": "Tono y lenguaje", "Z1": "Conf. cita/solucion", "Z2": "Despedida guion"}
RUNNERS = {"P1": p1, "P2": p2, "V1": v1, "V2": v2, "G1": g1, "G2": g2, "C1": c1, "C2": c2, "Z1": z1, "Z2": z2}


def audit_transcript(tr: dict, settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    out = {"schema_version": SCHEMA_VERSION, "call": tr["call"], "synthetic": tr.get("synthetic", False),
           "pipeline": {**tr.get("pipeline", {}), "rules_version": "0.2"}, "source_status": tr.get("status")}
    min_s = settings["rules"].get("min_call_seconds", 20)
    dur = tr["call"].get("duration_s") or 0
    if 0 < dur < min_s:   # regla determinista: no hay llamada que evaluar
        out["auto_discard"] = {"value": "cortada", "source": "regla", "reason": f"Duración de {round(dur)} s: menos de {min_s} s"}
    if tr.get("status") == "no_speech" or not tr.get("turns"):
        out.update(status="no_speech" if tr.get("status") == "no_speech" else "failed",
                   criteria={}, critical_error={"status": "none", "findings": []},
                   score={"points_confirmed": None, "percent_final": None},
                   human_review={"required": False, "reasons": ["sin conversacion: no se genera nota"]})
        return out

    metrics = compute_metrics(tr, settings)
    ctx = Ctx(tr=tr, settings=settings, metrics=metrics, turns=tr["turns"], roles_ok=roles_reliable(tr, settings))
    ct = classify(ctx)
    ctx.call_type = ct["type"]
    na = set(settings.rubric.get("not_applicable", {}).get(ct["type"], []))

    criteria = {}
    for code in ORDER:
        if code in na:
            criteria[code] = {"code": code, "name": NAMES[code], "score": 1, "applicable": False, "method": "n/a",
                              "confidence": 0.5, "sub_checks": [],
                              "explanation": f"No aplica para llamadas de tipo '{ct['type']}' (se cuenta como cumplido; ver P-06)."}
        else:
            criteria[code] = RUNNERS[code](ctx)
    crit_err = e1(ctx, criteria)

    pts = sum(1 for c in criteria.values() if c["score"] == 1)
    fails = [k for k, c in criteria.items() if c["score"] == 0]
    pend = [k for k, c in criteria.items() if c["score"] is None]
    reasons = []
    if not ctx.roles_ok:
        reasons.append("roles asesor/cliente poco fiables: la evidencia puede estar mal atribuida")
    if pend:
        reasons.append(f"criterios pendientes de LLM/humano: {', '.join(pend)}")
    if crit_err["status"] != "none":
        reasons.append("posible error critico E1 (requiere revision humana)")
    if tr.get("status") == "needs_review":
        reasons.append("la transcripcion se marco needs_review: " + ", ".join(tr["quality"]["warnings"]))
    out.update(
        status="partial" if pend else ("needs_review" if reasons else "completed"),
        call_type=ct, metrics=metrics, criteria=criteria, critical_error=crit_err,
        score={"points_confirmed": pts, "failed": fails, "pending": pend, "max_points": 10,
               "percent_min": pts * 10, "percent_max": (pts + len(pend)) * 10,
               "percent_final": None if pend else pts * 10,
               "e1_note": "si E1 se confirma, la nota final es 0 %" if crit_err["status"] != "none" else None},
        human_review={"required": bool(reasons), "reasons": reasons},
    )
    return out


def save_audit(audit: dict, settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    out = settings.data_dir / "results"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{audit['call']['call_id']}.audit.json"
    p.write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
