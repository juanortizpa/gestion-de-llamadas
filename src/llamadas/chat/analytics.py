"""Consultas estructuradas sobre las auditorias (conteos, tasas, promedios, rankings, listas) calculadas con codigo, sin IA.

Honestidad de los numeros: siempre se informa el tamano de la base (n) y cuantas llamadas quedaron fuera por estar
pendientes o descartadas; un ranking con pocas llamadas por asesor se marca como poco fiable.
"""
from __future__ import annotations

from collections import defaultdict

from ..audit import NAMES
from ..export import TYPE_ES
from .chunks import fecha_es
from .router import Filters, Parsed

MIN_GROUP_N = 5          # por debajo de esto un porcentaje por asesor se marca "(pocas llamadas)"


def matches(r: dict, f: Filters) -> bool:
    if f.call_ids and r["call_id"] not in f.call_ids:
        return False
    if f.agents and r["agent"] not in f.agents:
        return False
    if f.date_from and (not r["date"] or r["date"] < f.date_from):
        return False
    if f.date_to and (not r["date"] or r["date"] > f.date_to):
        return False
    if f.types and r["type"] not in f.types:
        return False
    for e in f.estados:
        ok = {"aprobada": (r["estado"] or "").startswith("Aprobado"),
              "no_aprobada": (r["estado"] or "").startswith("No aprobado"),
              "pendiente": r["estado_ui"] == "revisar",
              "revisada": bool(r["reviewed"]),
              "descartada": bool(r["discarded"]),
              "e1": r["e1"] in ("confirmed", "candidato")}.get(e, True)
        if not ok:
            return False
    return True


def filter_rows(rows: list[dict], f: Filters) -> list[dict]:
    return [r for r in rows if matches(r, f)]


def allowed_ids(rows: list[dict], f: Filters) -> set[str] | None:
    """Llamadas permitidas por los filtros de nivel llamada; None si no hay ninguno (no restringe)."""
    return None if f.call_level_empty() else {r["call_id"] for r in rows if matches(r, f)}


def _scope(f: Filters) -> str:
    d = f.describe()
    return " (" + "; ".join(d) + ")" if d else ""


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f} %" if b else "—"


def _link(cid: str) -> str:
    return f"[{cid}](call:{cid})"


def _auditables(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not r["discarded"] and r["estado_ui"] not in ("sin_conversacion", "error")]


def _crit_stats(rows: list[dict], code: str) -> dict:
    fail = sum(1 for r in rows if r["criteria"].get(code) == 0)
    ok = sum(1 for r in rows if r["criteria"].get(code) == 1)
    pend = sum(1 for r in rows if r["criteria"].get(code) is None)
    return {"fail": fail, "ok": ok, "pend": pend, "decided": fail + ok}


def _table(head: list[str], body: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(lines)


def _group_key(r: dict, by: str) -> str:
    if by == "type":
        return TYPE_ES.get(r["type"], "") or "sin identificar"
    if by == "day":
        return r["date"] or "sin fecha"
    return r["agent"] or "sin asignar"


def answer(p: Parsed, rows: list[dict], limit: int = 10) -> dict | None:
    """{'text': markdown, 'call_ids': [...], 'rows': n} o None si la consulta no se puede responder estructuradamente."""
    f = p.filters
    sel = filter_rows(rows, f)
    if not sel:
        return {"text": "No hay llamadas que cumplan esos filtros" + _scope(f) + ".", "call_ids": [], "rows": 0}
    aud = _auditables(sel)
    codes = f.criteria
    note = f"\n\n_Calculado directamente de las auditorías, sin IA. Base: {len(sel)} llamada(s)" + \
        (f", {len(sel) - len(aud)} sin auditar (descartadas o sin conversación)" if len(sel) != len(aud) else "") + "._"

    if p.metric == "list":
        sel_sorted = sorted(sel, key=lambda r: (r["date"] or "", r["time"] or ""), reverse=True)
        if codes:
            want = 0 if p.polarity == "fail" else 1
            sel_sorted = [r for r in sel_sorted if all(r["criteria"].get(c) == want for c in codes)]
        shown = sel_sorted[:15]
        if not shown:
            return {"text": "Ninguna llamada coincide" + _scope(f) + ".", "call_ids": [], "rows": 0}
        body = [[_link(r["call_id"]), fecha_es(r["date"].replace("-", "")), r["agent"] or "—",
                 "—" if r["percent"] is None else f"{r['percent']:.0f} %", r["estado"] or ""] for r in shown]
        more = f"\n\nMostrando {len(shown)} de {len(sel_sorted)}." if len(sel_sorted) > len(shown) else ""
        return {"text": f"**{len(sel_sorted)} llamada(s)**" + _scope(f) + ":\n\n" + _table(["Llamada", "Fecha", "Asesor", "Nota", "Estado"], body) + more + note,
                "call_ids": [r["call_id"] for r in shown], "rows": len(sel_sorted)}

    if p.metric == "avg":
        vals = [r["percent"] for r in aud if r["percent"] is not None]
        if not vals:
            return {"text": "Todavía no hay notas definitivas" + _scope(f) + f" ({len(aud)} llamada(s) con criterios pendientes)." + note, "call_ids": [], "rows": len(sel)}
        return {"text": f"Nota promedio{_scope(f)}: **{sum(vals) / len(vals):.1f} %** sobre {len(vals)} llamada(s) con nota definitiva "
                        f"({len(aud) - len(vals)} aún pendientes de decisión)." + note, "call_ids": [], "rows": len(sel)}

    if p.metric in ("count", "rate") and not p.group_by:
        if codes:
            lines = []
            for c in codes:
                s = _crit_stats(aud, c)
                if p.polarity == "fail":
                    lines.append(f"- **{c} {NAMES[c]}**: no cumple en **{s['fail']}** de {s['decided']} llamada(s) con decisión ({_pct(s['fail'], s['decided'])}); {s['pend']} pendiente(s).")
                else:
                    lines.append(f"- **{c} {NAMES[c]}**: cumple en **{s['ok']}** de {s['decided']} llamada(s) con decisión ({_pct(s['ok'], s['decided'])}); {s['pend']} pendiente(s).")
            ids = [r["call_id"] for r in aud if any(r["criteria"].get(c) == (0 if p.polarity == "fail" else 1) for c in codes)][:15]
            return {"text": "Criterios" + _scope(f) + ":\n" + "\n".join(lines) + note, "call_ids": ids, "rows": len(sel)}
        if "aprobada" in f.estados or "no_aprobada" in f.estados or p.metric == "count":
            return {"text": f"**{len(sel)}** llamada(s)" + _scope(f) + "." + note, "call_ids": [r["call_id"] for r in sel][:15], "rows": len(sel)}
        dec = [r for r in aud if r["percent"] is not None]
        ap = sum(1 for r in dec if (r["estado"] or "").startswith("Aprobado"))
        return {"text": f"Aprobación{_scope(f)}: **{_pct(ap, len(dec))}** ({ap} de {len(dec)} con nota definitiva; {len(aud) - len(dec)} pendientes)." + note,
                "call_ids": [], "rows": len(sel)}

    # ranking / agrupado
    by = p.group_by or "agent"
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in aud:
        groups[_group_key(r, by)].append(r)
    label = {"agent": "Asesor", "type": "Motivo", "day": "Día"}[by]
    if codes:
        c = codes[0]
        data = []
        for g, rs in groups.items():
            s = _crit_stats(rs, c)
            val = s["fail"] if p.polarity == "fail" else s["ok"]
            data.append((g, val, s["decided"], rs))
        data.sort(key=lambda x: (-(x[1] / x[2] if x[2] else -1), -x[1]))
        head = [label, "Llamadas con decisión", "No cumple" if p.polarity == "fail" else "Cumple", "Tasa"]
        body = [[g + (" (pocas llamadas)" if by == "agent" and dec < MIN_GROUP_N else ""), dec, val, _pct(val, dec)] for g, val, dec, _ in data[:limit]]
        title = f"**{c} {NAMES[c]}** por {label.lower()}{_scope(f)}"
    else:
        data = []
        for g, rs in groups.items():
            vals = [r["percent"] for r in rs if r["percent"] is not None]
            data.append((g, sum(vals) / len(vals) if vals else None, len(vals), len(rs)))
        low_first = "mejor" not in p.text.lower() and "mas alta" not in p.text.lower()
        data = [d for d in data if d[1] is not None]
        data.sort(key=lambda x: x[1], reverse=not low_first)
        head = [label, "Nota promedio", "Llamadas con nota", "Llamadas"]
        body = [[g + (" (pocas llamadas)" if by == "agent" and n < MIN_GROUP_N else ""), f"{avg:.1f} %", n, tot] for g, avg, n, tot in data[:limit]]
        title = f"**Nota promedio** por {label.lower()}{_scope(f)} ({'menor a mayor' if low_first else 'mayor a menor'})"
    if not body:
        return {"text": "Todavía no hay datos suficientes (criterios pendientes de decisión)" + _scope(f) + "." + note, "call_ids": [], "rows": len(sel)}
    return {"text": title + ":\n\n" + _table(head, body) + note, "call_ids": [], "rows": len(sel)}


def card(call_id: str, rows: list[dict], chunks_text: str) -> dict:
    """Ficha de una llamada (resumen + criterios); el texto viene del fragmento `resumen` ya indexado."""
    r = next((x for x in rows if x["call_id"] == call_id), None)
    if not r:
        return {"text": f"No encuentro la llamada {call_id}.", "call_ids": [], "rows": 0}
    return {"text": f"**Llamada {_link(call_id)}**\n\n{chunks_text}\n\n_Datos de las auditorías, sin IA._", "call_ids": [call_id], "rows": 1}
