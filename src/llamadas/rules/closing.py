"""Z1 confirmacion de cita/solucion (slots) y Z2 despedida."""
from __future__ import annotations

from ..catalog import Catalog, get_catalog
from ..textutil import best_sentence, fuzzy_has, normalize, sentences
from .context import Ctx, Hit, criterion, find, sc

_SOPORTE_VERBS = ["presentar", "llevar", "traer", "debe", "necesita", "tiene que", "recuerde", "lleve", "presente", "traiga", "anexar"]


def _agent_turns(ctx: Ctx, turns: list) -> list:
    return [t for t in turns if t["speaker"] == "ASESOR" or not ctx.roles_ok]


def _first_hit(ctx: Ctx, turns: list, phrases: list[str]) -> Hit | None:
    for t in turns:
        s = best_sentence(t["text"], phrases)
        if s:
            return Hit(t, s)
    return None


def _prep_check(prep, prep_req, exam) -> dict:
    if exam is None:
        return sc("preparacion", True if prep else None, prep, optional=True,
                  note="examen no encontrado en la base maestra: no se sabe si requiere preparacion")
    if prep_req:
        return sc("preparacion", bool(prep), prep, note=f"'{exam['procedimiento']}' REQUIERE preparacion segun la base maestra")
    return sc("preparacion", True, prep, optional=True, note=f"'{exam['procedimiento']}' no requiere preparacion (base maestra)")


def z1(ctx: Ctx) -> dict:
    lex, m = ctx.lex, ctx.metrics
    start = m["human_start_s"] + ctx.rules["z1_from_fraction"] * m["human_span_s"]
    window = _agent_turns(ctx, [t for t in ctx.turns if t["end"] >= start])
    typ = ctx.call_type

    if typ == "cancelacion":
        h = _first_hit(ctx, window, lex["cancel_confirm"])
        return criterion("Z1", "Conf. cita/solucion", [sc("cancelacion_confirmada", bool(h), h)], ctx,
                         "El asesor confirma la cancelacion." if h else "No se encontro confirmacion de la cancelacion.")

    agenda = _first_hit(ctx, window, lex["agenda_confirm"])
    fecha = _first_hit(ctx, window, lex["fecha_words"])
    hora = _first_hit(ctx, window, lex["hora_words"])
    sede = _first_hit(ctx, window, lex["sede_words"])
    medico = _first_hit(ctx, window, lex["medico_words"])
    soporte = None
    for t in window:
        for s in sentences(t["text"]):
            sn = normalize(s)
            if any(fuzzy_has(sn, w) for w in lex["soportes_words"]) and any(fuzzy_has(sn, v) for v in _SOPORTE_VERBS):
                soporte = Hit(t, s)
                break
        if soporte:
            break
    prep = _first_hit(ctx, window, lex["prep_words"])
    # Base maestra del usuario: sede por nombre (IPS/clinicas) y preparacion segun el examen
    cat = get_catalog()
    whole_n = normalize(" ".join(t["text"] for t in ctx.turns))
    exam = cat.match_exam(whole_n) if cat.loaded else None
    if cat.loaded:
        sede_cat = _first_hit(ctx, window, cat.sede_names())
        sede = sede_cat or sede
    prep_req = Catalog.prep_required(exam["rows"]) if exam else None
    ctx.extra["exam"] = exam["procedimiento"] if exam else None
    ctx.extra["prep_required"] = prep_req
    # El medico solo se exige si la cita es una CONSULTA (una radiografia/ecografia no tiene medico asignado)
    whole = normalize(" ".join(t["text"] for t in ctx.turns))
    consulta = any(fuzzy_has(whole, w) for w in lex["consulta_words"])
    subs = [sc("cita_agendada", bool(agenda), agenda), sc("fecha", bool(fecha), fecha), sc("hora", bool(hora), hora),
            sc("direccion_sede", bool(sede), sede),
            sc("medico_especialista", bool(medico), medico, optional=not consulta,
               note=None if consulta else "no exigido: no parece una consulta medica"),
            sc("soportes_a_llevar", bool(soporte), soporte),
            _prep_check(prep, prep_req, exam)]
    c = criterion("Z1", "Conf. cita/solucion", subs, ctx, "Slots de confirmacion: agendada, fecha, hora, sede, medico y soportes.")
    return c


def z2(ctx: Ctx) -> dict:
    lex, m = ctx.lex, ctx.metrics
    start = m["human_end_s"] - ctx.rules["z2_window_s"]
    window = _agent_turns(ctx, [t for t in ctx.turns if t["end"] >= start])
    algo = _first_hit(ctx, window, lex["algo_mas"])
    desp = None
    for t in reversed(window):
        s = best_sentence(t["text"], lex["despedida"])
        if s:
            desp = Hit(t, s)
            break
    req_algo = ctx.rules["z2_algo_mas_required"]
    subs = [sc("pregunta_si_requiere_algo_mas", bool(algo), algo, optional=not req_algo,
               note=None if req_algo else "informativo: la regla literal no se exige (P-23)"),
            sc("despedida_cordial", bool(desp), desp)]
    return criterion("Z2", "Despedida guion", subs, ctx, "Pregunta si requiere algo mas y se despide en el tramo final.")
