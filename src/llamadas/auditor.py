"""Fase 3: el LLM responde SOLO los sub-checks que las reglas dejaron pendientes (None).

Reglas de seguridad (D-06, D-07, D-22):
  - El LLM no da puntajes: responde sí/no por sub-check con cita literal.
  - Una respuesta "sí" solo vale si la cita aparece (aprox.) en la transcripcion: si no, se descarta y queda pendiente.
  - Una respuesta "no" del LLM se acepta pero se marca para revision humana.
  - El LLM NUNCA decide E1.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from .config import Settings, load_settings
from .llm import LlamaServer
from .textutil import normalize

QUESTIONS = {
    ("P1", "saludo"): "¿El ASESOR saluda cordialmente (buenos días/tardes/noches o similar)?",
    ("P1", "entidad"): "¿El ASESOR dice el nombre de la entidad (Angiografía de Occidente o Nueva EPS)? El texto puede estar mal transcrito; acepta variantes fonéticas.",
    ("P1", "nombre_asesor"): "¿El ASESOR dice su propio nombre al presentarse?",
    ("P2", "menciona_nombre_cliente"): "¿El ASESOR llama al cliente o paciente por su nombre o apellido (o 'señor/señora + apellido') en algún momento?",
    ("V1", "cliente_responde_numero"): "¿El cliente entrega un número de documento/cédula al asesor (aunque los dígitos no aparezcan en el texto)?",
    ("V2", "pregunta_examen_orden_requisitos"): "¿El ASESOR pregunta o verifica el examen, la orden médica, la autorización/EPS u otros requisitos previos del paciente?",
    ("C1", "comprende_la_necesidad"): "¿El ASESOR entiende lo que pide el cliente y responde a esa necesidad sin hacerle repetir lo mismo innecesariamente ni interrumpirlo?",
    ("C2", "uso_de_cortesia"): "¿El ASESOR usa un lenguaje respetuoso, claro y cortés (usted, por favor, gracias, con gusto)?",
    ("Z1", "preparacion"): "¿El ASESOR informa la preparación que debe hacer el paciente para el examen (ayuno u otra)?",
    ("Z2", "pregunta_si_requiere_algo_mas"): "¿El ASESOR pregunta al cliente si necesita algo más antes de terminar?",
}
SCHEMA = {"type": "object", "properties": {"checks": {"type": "array", "items": {
    "type": "object",
    "properties": {"id": {"type": "string"}, "passed": {"type": "boolean"}, "turn_id": {"type": "integer"},
                   "quote": {"type": "string"}},
    "required": ["id", "passed", "turn_id", "quote"]}}}, "required": ["checks"]}
SYSTEM = ("Eres un auditor de calidad de llamadas de un centro de atención en español. Respondes SOLO con JSON. "
          "Para cada pregunta devuelve passed=true únicamente si hay evidencia clara, con el turn_id y una CITA LITERAL "
          "copiada de ese turno (máximo 15 palabras). Si no hay evidencia: passed=false, turn_id=0, quote=\"\". "
          "La transcripción puede tener errores de reconocimiento de voz y los roles ASESOR/CLIENTE pueden estar mal asignados "
          "en algunos turnos; no inventes citas.")


def schema_for(ids: list[str]) -> dict:
    """Esquema que OBLIGA a responder exactamente una entrada por pregunta, con los ids pedidos (los modelos
    pequenos inventaban ids como 'C1.0'..'C1.8' con un esquema abierto)."""
    return {"type": "object", "properties": {"checks": {
        "type": "array", "minItems": len(ids), "maxItems": len(ids),
        "items": {"type": "object",
                  "properties": {"id": {"enum": ids}, "passed": {"type": "boolean"}, "turn_id": {"type": "integer"},
                                 "quote": {"type": "string", "maxLength": 160}},
                  "required": ["id", "passed", "turn_id", "quote"]}}}, "required": ["checks"]}


def pending_items(audit: dict) -> list[tuple[str, str]]:
    out = []
    for code, c in audit.get("criteria", {}).items():
        if not c.get("applicable", True):
            continue
        for s in c["sub_checks"]:
            if s["passed"] is None and (code, s["id"]) in QUESTIONS and not s.get("optional"):
                out.append((code, s["id"]))
    return out


def verify_quote(quote: str, turns: list[dict], turn_id: int, min_ratio: float) -> dict | None:
    """Devuelve el turno donde la cita aparece (aprox.) o None. Prefiere el turno indicado por el LLM."""
    q = normalize(quote)
    if len(q.split()) < 3:      # "Sí señora" no prueba nada: la cita debe tener al menos 3 palabras
        return None
    ordered = sorted(turns, key=lambda t: 0 if t["turn_id"] == turn_id else 1)
    for t in ordered:
        tn = normalize(t["text"])
        if q in tn or (len(tn) >= 0.6 * len(q) and fuzz.partial_ratio(q, tn) >= min_ratio):
            return t
    return None


def _recompute(c: dict) -> None:
    req = [s for s in c["sub_checks"] if not s.get("optional")]
    if any(s["passed"] is False for s in req):
        c["score"] = 0
    elif any(s["passed"] is None for s in req):
        c["score"] = None
    else:
        c["score"] = 1
        c.pop("pending", None)
    if c["score"] is not None:
        c.pop("pending", None)
        if c["method"] == "rule":
            c["method"] = "hybrid"


def _refresh_totals(audit: dict) -> None:
    crit = audit["criteria"]
    pts = sum(1 for c in crit.values() if c["score"] == 1)
    fails = [k for k, c in crit.items() if c["score"] == 0]
    pend = [k for k, c in crit.items() if c["score"] is None]
    audit["score"].update(points_confirmed=pts, failed=fails, pending=pend, percent_min=pts * 10,
                          percent_max=(pts + len(pend)) * 10, percent_final=None if pend else pts * 10)
    reasons = [r for r in audit["human_review"]["reasons"] if not r.startswith("criterios pendientes")]
    if pend:
        reasons.insert(0, f"criterios pendientes de LLM/humano: {', '.join(pend)}")
    hints = [f"{c}.{s['id']}" for c, cr in crit.items() for s in cr["sub_checks"] if s.get("ai_hint") is False and s["passed"] is None]
    if hints:
        reasons.append("la IA no encontró evidencia (solo una pista, decide el humano): " + ", ".join(hints))
    audit["human_review"] = {"required": bool(reasons), "reasons": reasons}
    if audit["status"] == "partial" and not pend:
        audit["status"] = "needs_review" if reasons else "completed"


COMPLETION_SYSTEM = (
    "Eres un auditor de calidad de llamadas de un centro de atención en español. Respondes SOLO con JSON. "
    "Decides cómo terminó la llamada:\n"
    "- finalizada: la conversación llegó a un cierre natural (despedida, agradecimiento final o el cliente da por terminada la atención).\n"
    "- cortada: la conversación se interrumpe de forma abrupta (frase a medias, sin despedida, se cae la línea) aunque antes fuera normal. "
    "Si te avisan de que la última frase termina sin punto final y no hay despedida, es una señal fuerte de corte.\n"
    "- incompleta: falta una parte esencial para evaluarla (solo se oye a una de las partes, no se llega a atender la necesidad, "
    "casi no hay conversación).\n"
    "Si eliges cortada o incompleta debes dar turn_id y una CITA LITERAL (máx. 15 palabras) de la transcripción que lo justifique "
    "(por ejemplo la última frase). Si no puedes citarla, elige finalizada. La transcripción puede tener errores de "
    "reconocimiento de voz y roles mal asignados; no inventes citas. En motivo explica en una frase corta."
)


def completion_schema() -> dict:
    return {"type": "object", "properties": {
        "estado": {"enum": ["finalizada", "cortada", "incompleta"]}, "turn_id": {"type": "integer"},
        "quote": {"type": "string", "maxLength": 160}, "motivo": {"type": "string", "maxLength": 200}},
        "required": ["estado", "turn_id", "quote", "motivo"]}


def _ends_open(turns: list[dict]) -> bool:
    """La última frase termina sin signo de cierre: la transcripción lleva puntuación final, así que su ausencia indica corte."""
    last = (turns[-1]["text"] if turns else "").rstrip()
    return bool(last) and last[-1] not in '.?!…»")'


def _farewell_detected(audit: dict, turns: list[dict] | None = None) -> bool:
    """¿Hay despedida? Con `turns`, solo vale si está entre los últimos 3 turnos (un «con gusto» a mitad de llamada no es un cierre)."""
    z2 = (audit.get("criteria") or {}).get("Z2") or {}
    last = turns[-1]["turn_id"] if turns else None
    return any(s.get("id") == "despedida_cordial" and s.get("passed") is True
               and (last is None or ((s.get("evidence") or {}).get("turn_id") or 0) >= last - 2) for s in z2.get("sub_checks", []))


def classify_completion(audit: dict, tr: dict, server: LlamaServer, settings: Settings | None = None) -> dict:
    """La IA clasifica si la llamada finalizó, se cortó o quedó incompleta y, si es cortada/incompleta con cita verificada,
    la marca sola (`auto_discard`). El auditor puede revertirla siempre. Modifica y devuelve `audit`."""
    settings = settings or load_settings()
    turns = tr.get("turns") or []
    if audit.get("auto_discard") or not turns:
        return audit
    speakers = {t["speaker"] for t in turns}
    if _farewell_detected(audit, turns) and {"ASESOR", "CLIENTE"} <= speakers and not _ends_open(turns):   # cierre normal: hay despedida y la llamada no acaba a media frase
        audit["completion"] = {"estado": "finalizada", "source": "regla", "applied": False,
                               "motivo": "Hay despedida y se oyen las dos partes"}
        return audit
    fmt = lambda ts: [f"[{t['turn_id']}] {t['speaker']}: {t['text']}" for t in ts]  # noqa: E731
    lines = fmt(turns) if len(turns) <= 14 else fmt(turns[:3]) + ["[... turnos intermedios omitidos ...]"] + fmt(turns[-11:])
    head = (f"Duración de la llamada: {round(audit['call']['duration_s'])} s. Turnos: {len(turns)}. "
            f"Partes que se oyen: {', '.join(sorted(speakers))}. Despedida detectada por reglas: "
            f"{'sí' if _farewell_detected(audit, turns) else 'no'}. "
            f"La última frase termina sin punto final: {'sí' if _ends_open(turns) else 'no'}.")
    user = f"{head}\n\nTRANSCRIPCIÓN:\n" + "\n".join(lines) + "\n\n¿La llamada finalizó, se cortó o está incompleta?"
    try:
        ans, meta = server.chat_json(COMPLETION_SYSTEM, user, completion_schema())
    except (ValueError, KeyError) as e:
        audit["completion"] = {"estado": None, "source": "ia", "applied": False, "error": f"respuesta inválida: {e}"}
        return audit
    estado = ans.get("estado")
    comp = {"estado": estado, "source": "ia", "applied": False, "motivo": (ans.get("motivo") or "")[:200], "secs": meta.get("secs")}
    if estado in ("cortada", "incompleta"):
        t = verify_quote(ans.get("quote", ""), turns, ans.get("turn_id", 0), settings["llm"]["quote_min_ratio"])
        if t:
            comp.update(applied=True, quote=ans["quote"][:220], turn_id=t["turn_id"], start=t["start"])
            audit["auto_discard"] = {"value": estado, "source": "ia", "reason": comp["motivo"] or f"La IA indica que la llamada está {estado}",
                                     "quote": comp["quote"], "turn_id": t["turn_id"], "start": t["start"]}
        else:
            comp["nota"] = "la IA dijo que no terminó bien pero su cita no está en la transcripción: no se marcó"
    audit["completion"] = comp
    return audit


def resolve_with_llm(audit: dict, tr: dict, server: LlamaServer, settings: Settings | None = None) -> dict:
    """Completa los sub-checks pendientes. Modifica y devuelve `audit` (con bloque `llm` de trazabilidad)."""
    settings = settings or load_settings()
    items = pending_items(audit)
    if not items or not tr.get("turns"):
        return audit
    min_ratio = settings["llm"]["quote_min_ratio"]
    convo = "\n".join(f"[{t['turn_id']}] {t['speaker']}: {t['text']}" for t in tr["turns"])
    # Lotes de <= 4 preguntas: respuestas cortas => JSON completo y ids correctos (un lote largo fue truncado en pruebas)
    by_id: dict = {}
    meta = {"secs": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "batches": 0, "invalid_batches": 0}
    for i in range(0, len(items), 4):
        chunk = items[i:i + 4]
        qs = "\n".join(f"- {code}.{sid}: {QUESTIONS[(code, sid)]}" for code, sid in chunk)
        user = (f"TRANSCRIPCIÓN:\n{convo}\n\nPREGUNTAS:\n{qs}\n\n"
                'Devuelve {"checks":[...]} con una entrada por pregunta; usa como id exactamente "CODIGO.sub_id" (por ejemplo "P1.entidad").')
        meta["batches"] += 1
        try:
            answers, m = server.chat_json(SYSTEM, user, schema_for([f"{c}.{s}" for c, s in chunk]))
            for k in ("secs", "prompt_tokens", "completion_tokens"):
                meta[k] = round(meta[k] + (m.get(k) or 0), 1)
            by_id.update({a["id"]: a for a in answers.get("checks", []) if isinstance(a, dict) and "id" in a})
        except (ValueError, KeyError):   # JSON truncado/invalido: esas preguntas quedan pendientes para el humano
            meta["invalid_batches"] += 1
    log = []
    norm_ids = {str(k).strip().lower(): v for k, v in by_id.items()}

    def lookup(code: str, sid: str):
        # los modelos pequenos a veces devuelven solo "sub_id" o solo "CODIGO": se acepta si no es ambiguo
        for key in (f"{code}.{sid}".lower(), sid.lower()):
            if key in norm_ids:
                return norm_ids[key]
        same_code = [s for c, s in items if c == code]
        return norm_ids.get(code.lower()) if len(same_code) == 1 else None

    for code, sid in items:
        a = lookup(code, sid)
        sub = next(s for s in audit["criteria"][code]["sub_checks"] if s["id"] == sid)
        if not a:
            log.append({"id": f"{code}.{sid}", "result": "sin_respuesta"})
            continue
        if a["passed"]:
            t = verify_quote(a.get("quote", ""), tr["turns"], a.get("turn_id", 0), min_ratio)
            if t:
                sub.update(passed=True, source="llm", evidence={"turn_id": t["turn_id"], "quote": a["quote"][:220],
                                                                 "start": t["start"], "end": t["end"]})
                log.append({"id": f"{code}.{sid}", "result": "si_verificado"})
            else:
                sub["note"] = (sub.get("note") or "") + " | LLM dijo 'sí' pero su cita no está en la transcripción: descartado"
                log.append({"id": f"{code}.{sid}", "result": "cita_inventada_descartada"})
        else:
            # Un "no" del LLM pequeno no es evidencia (en pruebas dijo "no" a casi todo): NO fija 0, solo deja una pista.
            sub["ai_hint"] = False
            sub["note"] = (sub.get("note") or "") + " | LLM: sin evidencia (confirmar)"
            log.append({"id": f"{code}.{sid}", "result": "no_sin_evidencia"})
    for c in audit["criteria"].values():
        if c.get("applicable", True):
            _recompute(c)
    audit["llm"] = {"mode": server.mode, "model": server.model.name, "log": log, **meta}
    _refresh_totals(audit)
    return audit
