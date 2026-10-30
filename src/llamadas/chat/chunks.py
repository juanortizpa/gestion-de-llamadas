"""De una llamada auditada a (fila estructurada + fragmentos de texto para buscar).

Tipos de fragmento:
  resumen     una linea de vida de la llamada: fecha, asesor, tipo, nota, criterios que fallan, esperas
  criterio    por criterio: resultado final, explicacion y evidencias (citas con turno y tiempo)
  ventana     tramo de la transcripcion (~window_words palabras, con 1 turno de solape)
  observacion lo que anoto el auditor humano
  e1          candidatos a error critico

Privacidad: numeros largos (documentos, telefonos) se enmascaran ANTES de indexar, asi ni el indice ni el prompt los contienen.
"""
from __future__ import annotations

import hashlib
import json
import re

from ..audit import NAMES
from ..export import TYPE_ES
from ..review import CODES, ui_state
from ..textutil import sentences

CHUNKER_VERSION = "1"
_DIGITS = re.compile(r"\d[\d\s.,]{5,}\d")


def mask_pii(text: str) -> str:
    """Enmascara secuencias de >=7 digitos (incluidas las dictadas con espacios): 1 0 6 2 3 3 1 5 6 5 -> ****6565."""
    def sub(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return f"****{digits[-4:]}" if len(digits) >= 7 else m.group(0)
    return _DIGITS.sub(sub, text)


def mmss(t: float | None) -> str:
    if t is None:
        return ""
    t = int(round(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def fecha_es(yyyymmdd: str | None) -> str:
    d = yyyymmdd or ""
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else ""


def iso_date(yyyymmdd: str | None) -> str:
    d = yyyymmdd or ""
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else ""


def _h(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


def _chunk(kind: str, ctx: str, body: str, **kw) -> dict:
    body = mask_pii(body).strip()
    return {"kind": kind, "ctx": ctx, "body": body, "hash": _h(CHUNKER_VERSION, kind, ctx, body), **kw}


def _val(v) -> str:
    return {1: "cumple", 0: "no cumple", None: "pendiente"}.get(v, "pendiente")


def call_row(audit: dict, review: dict, final: dict, sig: str) -> dict:
    call = audit["call"]
    metrics = audit.get("metrics") or {}
    crit = {c: v["value"] for c, v in (final.get("criteria") or {}).items()}
    return {
        "call_id": call["call_id"], "sig": sig, "date": iso_date(call.get("received_date")),
        "time": (call.get("received_time") or "")[:4], "agent": (review.get("agent") or "").strip(),
        "auditor": (review.get("auditor") or "").strip(), "type": (audit.get("call_type") or {}).get("type") or "",
        "queue": call.get("queue") or "", "duration_s": call.get("duration_s"), "percent": final.get("percent"),
        "points": final.get("points"), "estado": final.get("estado"), "estado_ui": ui_state(audit, final),
        "e1": final.get("e1"), "discarded": final.get("discarded") or "", "reviewed": 1 if final.get("reviewed") else 0,
        "pending": json.dumps(final.get("pending") or []), "criteria": json.dumps(crit),
        "n_holds": len(metrics.get("hold_events") or []), "longest_hold": metrics.get("longest_hold_s") or 0.0,
        "analyzed_at": audit.get("analyzed_at") or "",
    }


def _header(audit: dict, review: dict) -> str:
    c = audit["call"]
    tipo = TYPE_ES.get((audit.get("call_type") or {}).get("type"), "") or "tipo sin identificar"
    ag = (review.get("agent") or "").strip() or "sin asignar"
    return f"Llamada {c['call_id']} · {fecha_es(c.get('received_date'))} · asesor {ag} · {tipo}"


def _summary(audit: dict, review: dict, final: dict, ctx: str) -> dict:
    c = audit["call"]
    parts = [f"Duración {c['duration_s'] / 60:.1f} min."]
    if final.get("discarded"):
        auto = audit.get("auto_discard") or {}
        why = f" Motivo: {auto['reason']}." if auto.get("reason") and final.get("discard_origin") == "automática" else ""
        parts.append(f"No se audita: {final['estado'].split('(')[-1].rstrip(')')}.{why}")
    elif not audit.get("criteria"):
        parts.append("Sin conversación: no se genera nota.")
    else:
        crit = final["criteria"]
        nota = f"nota {final['percent']} %" if final.get("percent") is not None else "nota pendiente"
        parts.append(f"Resultado: {nota} ({final['estado']}).")
        fails = [f"{k} {NAMES[k]}" for k in CODES if crit[k]["value"] == 0]
        pend = [f"{k} {NAMES[k]}" for k in CODES if crit[k]["value"] is None]
        parts.append("Criterios que no cumple: " + (", ".join(fails) if fails else "ninguno") + ".")
        if pend:
            parts.append("Pendientes de decidir: " + ", ".join(pend) + ".")
        if final.get("e1") in ("confirmed", "candidato"):
            parts.append("Error crítico " + ("confirmado" if final["e1"] == "confirmed" else "candidato (por revisar)") + ".")
        m = audit.get("metrics") or {}
        holds = m.get("hold_events") or []
        if holds:
            parts.append(f"Esperas (hold): {len(holds)}, la más larga de {m.get('longest_hold_s', 0):.0f} s.")
        if m.get("dead_air_total_s"):
            parts.append(f"Tiempo muerto total {m['dead_air_total_s']:.0f} s.")
        if not final.get("reviewed"):
            parts.append("Aún sin revisión humana.")
    return _chunk("resumen", ctx, " ".join(parts))


def _criteria_chunks(audit: dict, final: dict, ctx: str, turns_by_id: dict) -> list[dict]:
    out = []
    for code in CODES:
        cr = (audit.get("criteria") or {}).get(code)
        if not cr or not cr.get("applicable", True):
            continue
        f = final["criteria"][code]
        lines = [f"Criterio {code} ({NAMES[code]}): {_val(f['value'])} (decidido por {f['origin']})."]
        if cr.get("explanation"):
            lines.append(f"Explicación: {cr['explanation']}")
        t0 = t1 = None
        for s in cr.get("sub_checks", []):
            ev = s.get("evidence") or {}
            bit = f"- {s['id']}: {_val(1 if s['passed'] is True else 0 if s['passed'] is False else None)}"
            if isinstance(ev, dict) and ev.get("quote"):
                bit += f' — "{ev["quote"]}" (turno {ev.get("turn_id")}, {mmss(ev.get("start"))})'
                if ev.get("start") is not None and t0 is None:
                    t0, t1 = ev["start"], ev.get("end")
            if s.get("note"):
                bit += f" [{s['note'].strip(' |')}]"
            lines.append(bit)
        out.append(_chunk("criterio", ctx, "\n".join(lines), criterion=code, t0=t0, t1=t1))
    return out


def _windows(turns: list[dict], ctx: str, window_words: int) -> list[dict]:
    """Agrupa turnos hasta ~window_words palabras; el ultimo turno de cada ventana abre la siguiente (contexto)."""
    items = []
    for t in turns:                       # un turno enorme se parte por oraciones para no inflar el fragmento
        words = t["text"].split()
        if len(words) <= 2 * window_words:
            items.append(t)
            continue
        buf, n = [], 0
        for s in sentences(t["text"]) or [t["text"]]:
            buf.append(s)
            n += len(s.split())
            if n >= window_words:
                items.append({**t, "text": " ".join(buf)})
                buf, n = [], 0
        if buf:
            items.append({**t, "text": " ".join(buf)})
    nw = lambda x: len(x["text"].split())  # noqa: E731
    out: list[dict] = []
    cur: list[dict] = []
    words = fresh = 0                    # fresh = turnos de `cur` que aun no salieron en ningun fragmento

    def flush():
        body = "\n".join(f"{x['speaker']}: {x['text']}" for x in cur)
        out.append(_chunk("ventana", ctx, body, t0=cur[0]["start"], t1=cur[-1]["end"],
                          turn0=cur[0]["turn_id"], turn1=cur[-1]["turn_id"]))

    for t in items:
        cur.append(t)
        words += nw(t)
        fresh += 1
        if words >= window_words:
            flush()
            cur = [t] if nw(t) < window_words else []     # solape de 1 turno
            words, fresh = sum(nw(x) for x in cur), 0
    if cur and fresh:
        flush()
    return out


def build_call(audit: dict, transcript: dict, review: dict, final: dict, sig: str, window_words: int = 90) -> tuple[dict, list[dict]]:
    """(fila de `calls`, lista de fragmentos). Las llamadas sin conversacion solo aportan el resumen."""
    ctx = _header(audit, review)
    row = call_row(audit, review, final, sig)
    chunks = [_summary(audit, review, final, ctx)]
    if audit.get("criteria") and not final.get("discarded"):
        turns = transcript.get("turns") or []
        chunks += _criteria_chunks(audit, final, ctx, {t["turn_id"]: t for t in turns})
        for f in (audit.get("critical_error") or {}).get("findings", []):
            ev = f.get("evidence") or {}
            q = f' Cita: "{ev["quote"]}" (turno {ev.get("turn_id")}).' if isinstance(ev, dict) and ev.get("quote") else ""
            chunks.append(_chunk("e1", ctx, f"Posible error crítico {f.get('code', '')}: {f.get('description', '')}.{q}",
                                 t0=ev.get("start") if isinstance(ev, dict) else None))
        chunks += _windows(turns, ctx, window_words)
    obs = (review.get("obs") or "").strip()
    motivo = (review.get("motivo") or "").strip()
    if obs or motivo:
        who = review.get("auditor") or "el auditor"
        chunks.append(_chunk("observacion", ctx, (f"Motivo registrado: {motivo}. " if motivo else "") +
                             (f"Observaciones de {who}: {obs}" if obs else "")))
    return row, chunks
