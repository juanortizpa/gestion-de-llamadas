"""P1 saludo/entidad/nombre, P2 nombre del cliente, V1 documento, V2 validacion de datos/examen."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from ..textutil import best_sentence, fuzzy_has, normalize, sentences
from .context import Ctx, Hit, criterion, ev, find, find_all, sc

_CAP = r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ]{2,}"
_NAME_AFTER_PRES = re.compile(
    r"(?:mi nombre es|me llamo|le habla|habla con|habla|le atiende|lo atiende|la atiende|le saluda|soy)\s+(?:la |el )?"
    rf"({_CAP}(?:\s+(?:de\s+|del\s+)?{_CAP})*)", re.IGNORECASE)
_NAME_STOP = {"que", "con", "en", "una", "un", "el", "la", "los", "las", "usted", "ustedes", "para", "por", "como", "cual",
              "buenas", "buenos", "tardes", "dias", "noches", "gracias", "senor", "senora", "senorita", "angiografia", "occidente",
              "nueva", "eps"}
_ADDRESS = re.compile(rf"\b(?:se[ñn]or[a]?|se[ñn]orita|do[ñn]a|don|paciente)\s+(?!que\b)({_CAP})", re.IGNORECASE)
_SPOKEN_NUM = {"cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "veinte",
               "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa", "cien", "ciento"}


_ASK_VERBS = ["me confirma", "me regala", "me da", "me indica", "me suministra", "permitame el", "digame", "cual es", "validamos",
              "necesito su", "me colabora", "me puede dar", "me brinda", "indiqueme"]


def _digits(text: str) -> int:
    return len(re.findall(r"\d", text))


def _spoken_numbers(text: str) -> int:
    return sum(1 for w in normalize(text).split() if w in _SPOKEN_NUM)


def _clean_name(raw: str) -> str | None:
    toks = [t for t in raw.split() if normalize(t) not in _NAME_STOP]
    return " ".join(toks) if toks else None


def _early(ctx: Ctx) -> list:
    return ctx.turns[: ctx.rules["p1_first_turns"]]


def p1(ctx: Ctx) -> dict:
    lex, early = ctx.lex, _early(ctx)
    if not early:
        return criterion("P1", "Saludo guion", [sc("saludo", None, note="sin_turnos")], ctx, "No hay conversacion humana.")
    saludo = find(ctx, lex["saludo"], turns=early)
    entidad = find(ctx, lex["entidad"], turns=early)

    # nombre del asesor: 1) patron de presentacion 2) roster 3) inferencia por sobrante del saludo
    nombre_hit, nombre_note = None, None
    agent_early = [t for t in early if t["speaker"] == "ASESOR"] if ctx.roles_ok else early
    for t in agent_early:
        for s in sentences(t["text"]):
            m = _NAME_AFTER_PRES.search(s)
            if m and _clean_name(m.group(1)):
                nombre_hit, nombre_note = Hit(t, s), f"patron_presentacion:{_clean_name(m.group(1))}"
                break
        if nombre_hit:
            break
    if not nombre_hit:
        for t in agent_early:
            n = normalize(t["text"])
            for full in ctx.settings.agents:
                first = normalize(full).split()[0]
                if len(first) >= 4 and (f" {first} " in f" {n} " or any(fuzz.ratio(first, w) >= 85 for w in n.split() if len(w) >= 4)):
                    nombre_hit, nombre_note = Hit(t, best_sentence(t["text"], [first], 80) or t["text"]), "roster"
                    break
            if nombre_hit:
                break
    if not nombre_hit and entidad and not entidad.wrong_side:
        # sobrante del saludo: "9PS, buenas tardes. Ana, Stéphane y Peña, ¿en qué le puedo servir?"
        for t in agent_early:
            n = normalize(t["text"])
            for p in lex["saludo"] + lex["entidad"] + ["en que le puedo servir", "en que le puedo colaborar", "en que le puedo ayudar"]:
                n = n.replace(p, " ")
            rest = [w for w in n.split() if w not in _NAME_STOP and len(w) > 2]
            if len(rest) >= 2 and fuzzy_has(normalize(t["text"]), "en que le puedo"):
                nombre_hit, nombre_note = Hit(t, t["text"][:160]), "inferido_por_sobrante_del_saludo"
                break

    # Si el saludo del asesor se transcribio con baja confianza, NO encontrar la entidad/nombre no prueba que falten
    low = [t for t in agent_early if t["avg_prob"] < ctx.rules["greeting_min_prob"]]
    garbled = bool(agent_early) and len(low) == len(agent_early)

    def verdict(found: bool):
        return True if found else (None if garbled else False)

    subs = [
        sc("saludo", bool(saludo and not saludo.wrong_side), saludo),
        sc("entidad", verdict(bool(entidad and not entidad.wrong_side)), entidad,
           note="stt_baja_confianza_en_el_saludo" if garbled and not (entidad and not entidad.wrong_side) else None),
        sc("nombre_asesor", verdict(bool(nombre_hit)), nombre_hit,
           note=nombre_note or ("stt_baja_confianza_en_el_saludo" if garbled else None)),
    ]
    c = criterion("P1", "Saludo guion", subs, ctx, "Saludo, entidad y presentacion con nombre en los primeros turnos del asesor.")
    if nombre_note and nombre_note.startswith("inferido"):
        c["confidence"] = min(c["confidence"], 0.55)
    return c


def _client_names(ctx: Ctx) -> list[str]:
    names = []
    for t in ctx.turns:
        if ctx.roles_ok and t["speaker"] != "CLIENTE":
            continue
        for s in sentences(t["text"]):
            m = _NAME_AFTER_PRES.search(s)
            if m:
                n = _clean_name(m.group(1))
                if n:
                    names.append(n)
    return names


def p2(ctx: Ctx) -> dict:
    agent_turns = [t for t in ctx.turns if t["speaker"] == "ASESOR"] if ctx.roles_ok else ctx.turns
    names = _client_names(ctx)
    hits: list[Hit] = []
    for t in agent_turns:
        for s in sentences(t["text"]):
            if _ADDRESS.search(s):
                hits.append(Hit(t, s))
                continue
            sn = normalize(s)
            if any(len(tok) >= 4 and any(fuzz.ratio(tok, w) >= 88 for w in sn.split()) for nm in names for tok in normalize(nm).split()):
                hits.append(Hit(t, s))
    ok = len(hits) >= ctx.rules["p2_min_mentions"]
    subs = [sc("menciona_nombre_cliente", ok, hits[0] if hits else None,
               note=f"menciones={len(hits)}; nombre_cliente_detectado={'si' if names else 'no'}")]
    return criterion("P2", "Nombre cliente", subs, ctx,
                     "El asesor usa el nombre/apellido del cliente o paciente." if ok else
                     "No se encontro evidencia de que el asesor use el nombre del cliente (puede deberse a errores del STT).")


def v1(ctx: Ctx) -> dict:
    lex = ctx.lex
    req_phr = lex["doc_request"]
    req = None
    req_idx = None
    for i, t in enumerate(ctx.turns):
        if ctx.roles_ok and t["speaker"] != "ASESOR":
            continue
        # solo cuenta como PETICION una oracion que pregunta/pide (no "presentese con su cedula")
        for s in sentences(t["text"]):
            sn = normalize(s)
            asks = "?" in s or any(fuzzy_has(sn, v) for v in _ASK_VERBS)
            if asks and best_sentence(s, req_phr):
                req, req_idx = Hit(t, s), i
                break
        if req:
            break
    if not req:
        return criterion("V1", "Conf. documento", [sc("solicita_documento", False)], ctx,
                         "No se encontro solicitud de documento/cedula por parte del asesor.")
    window = ctx.turns[req_idx: req_idx + 1 + ctx.rules["v1_reply_turns"]]
    reply = None
    for t in window:
        if ctx.roles_ok and t["speaker"] == "ASESOR" and t is not req.turn:
            continue
        if _digits(t["text"]) >= 6 or _spoken_numbers(t["text"]) >= 5:
            reply = Hit(t, t["text"][:120])
            break
    # confirmacion posterior del asesor (informativa)
    conf = None
    if reply:
        j = ctx.turns.index(reply.turn)
        for t in ctx.turns[j: j + 3]:
            if (t["speaker"] == "ASESOR" or not ctx.roles_ok) and (_digits(t["text"]) >= 3 or fuzzy_has(normalize(t["text"]), "correcto")
                                                                   or fuzzy_has(normalize(t["text"]), "validamos") or fuzzy_has(normalize(t["text"]), "paciente")):
                conf = Hit(t, t["text"][:120])
                break
    next_is_client = len(window) > 1 and window[1]["speaker"] != "ASESOR"
    if reply:
        resp_pass = True
    elif next_is_client:
        resp_pass = None   # el cliente respondio pero el STT no transcribio los digitos
    else:
        resp_pass = False
    subs = [sc("solicita_documento", True, req),
            sc("cliente_responde_numero", resp_pass, reply,
               note=None if reply else "sin_digitos_transcritos" if resp_pass is None else "sin_respuesta_con_numero"),
            sc("asesor_valida_o_repite", bool(conf), conf, optional=True)]
    return criterion("V1", "Conf. documento", subs, ctx,
                     "El asesor pide el documento y el cliente lo da." if resp_pass else
                     "Se pidio el documento pero no se pudo confirmar la respuesta con numero.")


def v2(ctx: Ctx) -> dict:
    hits = find_all(ctx, ctx.lex["exam_hints"], who="ASESOR")
    if hits:
        return criterion("V2", "Valida datos/hist", [sc("pregunta_examen_orden_requisitos", True, hits[0], note=f"coincidencias={len(hits)}")],
                         ctx, "El asesor pregunta por examen/orden/requisitos.", conf=0.7)
    return criterion("V2", "Valida datos/hist", [sc("pregunta_examen_orden_requisitos", None, note="sin_palabras_clave")], ctx,
                     "Sin palabras clave de validacion; requiere confirmacion semantica.")
