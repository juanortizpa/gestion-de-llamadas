"""Revision humana: el auditor confirma/corrige criterios y E1. La nota FINAL sale de aqui (D-07)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import Settings, load_settings

CODES = ["P1", "P2", "V1", "V2", "G1", "G2", "C1", "C2", "Z1", "Z2"]
DISCARD = {"cortada": "llamada cortada", "incompleta": "llamada incompleta"}


def _dir(settings: Settings) -> Path:
    d = settings.data_dir / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_review(call_id: str, settings: Settings | None = None) -> dict:
    p = _dir(settings or load_settings()) / f"{call_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_review(call_id: str, review: dict, settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    clean = {
        "auditor": str(review.get("auditor", ""))[:80], "agent": str(review.get("agent", ""))[:80],
        "motivo": str(review.get("motivo", ""))[:120], "obs": str(review.get("obs", ""))[:1500],
        "e1": review.get("e1") if review.get("e1") in ("confirmed", "dismissed") else None,
        "criteria": {k: int(v) for k, v in (review.get("criteria") or {}).items() if k in CODES and v in (0, 1)},
        "discard": review.get("discard") if review.get("discard") in (*DISCARD, "ninguna") else None,
        "reviewed": bool(review.get("reviewed", True)), "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (_dir(settings) / f"{call_id}.json").write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    return clean


def effective_discard(audit: dict, review: dict | None) -> tuple[str | None, str | None]:
    """(motivo, origen). El auditor manda: 'ninguna' anula una marca automática (regla de 20 s o IA)."""
    rd = (review or {}).get("discard")
    if rd == "ninguna":
        return None, None
    if rd in DISCARD:
        return rd, "auditor"
    auto = audit.get("auto_discard") or {}
    if auto.get("value") in DISCARD:
        return auto["value"], "automática"
    return None, None


def final_view(audit: dict, review: dict | None, settings: Settings | None = None) -> dict:
    """Combina sistema + humano. Un criterio humano siempre gana. E1 confirmado => nota 0."""
    settings = settings or load_settings()
    review = review or {}
    discard, origin = effective_discard(audit, review)
    if discard:  # cortada/incompleta: no se audita, no cuenta en notas ni pendientes
        crit = {c: {"value": None, "origin": "descartada"} for c in CODES}
        return {"status": audit.get("status"), "criteria": crit, "points": None, "pending": [], "percent": None,
                "estado": f"No se audita ({DISCARD[discard]})", "e1": "none", "reviewed": True, "discarded": discard,
                "discard_origin": origin}
    if not audit.get("criteria"):
        return {"status": audit.get("status"), "criteria": {}, "points": None, "percent": None, "estado": "Sin conversación",
                "e1": "none"}
    crit = {}
    for code in CODES:
        c = audit["criteria"][code]
        human = review.get("criteria", {}).get(code)
        if human is not None:
            crit[code] = {"value": human, "origin": "humano"}
        elif c["score"] is not None:
            crit[code] = {"value": c["score"], "origin": "n/a" if not c.get("applicable", True) else "sistema"}
        else:
            crit[code] = {"value": None, "origin": "pendiente"}
    cand = audit["critical_error"]["status"] != "none"
    e1 = review.get("e1") or ("candidato" if cand else "none")
    pending = [k for k, v in crit.items() if v["value"] is None]
    points = sum(1 for v in crit.values() if v["value"] == 1)
    if e1 == "confirmed":
        percent, pend_flag = 0, False
    elif pending:
        percent, pend_flag = None, True
    else:
        percent, pend_flag = points * 10, False
    thr = settings["review"]["pass_percent"]
    if e1 == "confirmed":
        estado = "No aprobado (error crítico)"
    elif pend_flag:
        estado = "Pendiente de revisión"
    else:
        estado = "Aprobado" if percent >= thr else "No aprobado"
    if e1 == "candidato" and not review.get("reviewed"):
        estado = "Revisar posible error crítico" if not pend_flag else estado
    return {"criteria": crit, "points": points, "pending": pending, "percent": percent, "estado": estado, "e1": e1,
            "reviewed": bool(review.get("reviewed"))}
