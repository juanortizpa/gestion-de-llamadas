"""G1 control de hold, G2 agilidad, C1 escucha activa, C2 tono y lenguaje."""
from __future__ import annotations

from ..textutil import fuzzy_has, normalize
from .context import Ctx, Hit, criterion, ev, find, find_all, sc


def g1(ctx: Ctx) -> dict:
    limit = ctx.rules["hold_limit_s"]
    holds = ctx.metrics["hold_events"]
    unannounced_long = [g for g in ctx.metrics["silence_gaps_all"] if g["duration_s"] >= limit]
    viol = [g for g in holds if g["duration_s"] >= limit]
    worst = max(viol, key=lambda g: g["duration_s"]) if viol else None
    if worst:
        evid = {"start": worst["start"], "end": worst["end"], "duration_s": worst["duration_s"], "kind": worst["kind"],
                "turn_before": worst["turn_before"], "turn_after": worst["turn_after"]}
        subs = [sc("hold_menor_al_limite", False, evidence=evid, note=f"limite={limit:.0f}s; eventos_de_espera={len(holds)}")]
        return criterion("G1", "Control hold", subs, ctx,
                         f"Espera de {worst['duration_s']:.0f} s (>= {limit:.0f} s), segun timestamps.", conf=0.85,
                         method="time", extra={"hold_events": holds})
    if unannounced_long:
        g = max(unannounced_long, key=lambda g: g["duration_s"])
        subs = [sc("hold_menor_al_limite", False, evidence={"start": g["start"], "end": g["end"], "duration_s": g["duration_s"],
                                                           "kind": "silencio_sin_anuncio"}, note="silencio largo sin anunciar espera")]
        return criterion("G1", "Control hold", subs, ctx, f"Silencio de {g['duration_s']:.0f} s sin anunciar espera.",
                         conf=0.5, method="time", extra={"hold_events": holds})
    note = f"esperas={len(holds)}; mas_larga={ctx.metrics['longest_hold_s']}s"
    return criterion("G1", "Control hold", [sc("hold_menor_al_limite", True, note=note)], ctx,
                     "Ninguna espera alcanza el limite.", conf=0.8, method="time", extra={"hold_events": holds})


def g2(ctx: Ctx) -> dict:
    m, r = ctx.metrics, ctx.rules
    single_ok = m["dead_air_longest_s"] <= r["g2_max_single_gap_s"]
    total_ok = m["dead_air_total_s"] <= r["g2_max_total_s"]
    subs = [sc("sin_tiempo_muerto_largo", single_ok, evidence={"longest_s": m["dead_air_longest_s"]}),
            sc("tiempo_muerto_total_aceptable", total_ok, evidence={"total_s": m["dead_air_total_s"]})]
    c = criterion("G2", "Agilidad sistema", subs, ctx,
                  "Tiempo muerto sin anunciar dentro de umbrales (UMBRALES SIN CALIBRAR con auditores humanos).",
                  conf=0.45, method="time", extra={"calibration_pending": True})
    return c


def c1(ctx: Ctx) -> dict:
    reps = find_all(ctx, ["me repite", "puede repetir", "como dice", "perdon", "disculpe", "no le escuche", "repitame"], who="ASESOR")
    many = len(reps) >= 3
    subs = [sc("pocas_peticiones_de_repeticion", not many, reps[0] if reps else None, note=f"peticiones={len(reps)}"),
            sc("comprende_la_necesidad", None, note="requiere_LLM")]
    return criterion("C1", "Escucha activa", subs, ctx, "Parcial: faltan interrupciones (requieren solapes fiables) y comprension (LLM).",
                     conf=0.4, method="hybrid")


def c2(ctx: Ctx) -> dict:
    lex = ctx.lex
    strong = find_all(ctx, lex["inadecuado_fuerte"], who="ASESOR")
    weak = find_all(ctx, lex["inadecuado_debil"], who="ASESOR")
    courtesy = {p for p in lex["cortesia"] for t in ctx.turns
                if (t["speaker"] == "ASESOR" or not ctx.roles_ok) and fuzzy_has(normalize(t["text"]), p)}
    if strong:
        subs = [sc("sin_lenguaje_inadecuado", False, strong[0])]
        return criterion("C2", "Tono y lenguaje", subs, ctx, "Lenguaje inadecuado detectado.", conf=0.8)
    polite = len(courtesy) >= 3 and len(weak) < 2
    subs = [sc("sin_lenguaje_inadecuado", True, note=f"banderas_debiles={len(weak)}"),
            sc("uso_de_cortesia", True if polite else None, note=f"marcadores_de_cortesia={len(courtesy)}")]
    return criterion("C2", "Tono y lenguaje", subs, ctx,
                     "Sin lenguaje inadecuado y con marcadores de cortesia (solo texto: el tono de voz NO se evalua).",
                     conf=0.55, method="hybrid")
