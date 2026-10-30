"""Entiende la pregunta SIN IA: filtros (fechas, asesor, criterio, estado, tipo, llamada) e intencion.

Principio del proyecto: lo que se puede calcular no se le pregunta a un LLM. Contar, promediar, ordenar y listar llamadas son
consultas sobre datos estructurados; solo las preguntas abiertas ("¿por que...?", "¿que dicen...?") necesitan la IA.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from ..textutil import normalize

MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
          "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}

CRITERIA_WORDS = {
    "P1": ["saludo", "saludar", "presentacion", "presentarse", "bienvenida", "p1"],
    "P2": ["nombre del cliente", "nombre del paciente", "por su nombre", "p2"],
    "V1": ["documento", "cedula", "identificacion", "v1"],
    "V2": ["valida datos", "validacion de datos", "antecedentes", "historial", "requisitos previos", "v2"],
    "G1": ["espera", "esperas", "hold", "retencion", "g1"],
    "G2": ["agilidad", "lentitud", "g2"],
    "C1": ["escucha activa", "interrumpe", "interrupciones", "c1"],
    "C2": ["tono", "lenguaje", "cortesia", "trato", "c2"],
    "Z1": ["confirma la cita", "confirmacion de la cita", "preparacion", "resumen de la cita", "z1"],
    "Z2": ["despedida", "despide", "algo mas", "cierre", "z2"],
}
TYPE_WORDS = {"cancelacion": ["cancelacion", "cancelaciones"], "nueva_cita": ["solicitud de cita", "solicitudes de cita", "nueva cita", "nuevas citas"],
              "confirmacion": ["confirmacion de cita", "confirmaciones"], "informacion": ["llamadas de informacion", "tipo informacion"]}
ESTADO_WORDS = {"no_aprobada": ["no aprobad", "reprobad", "desaprobad", "no pasa", "no pasaron"], "aprobada": ["aprobad", "pasan", "pasaron"],
                "pendiente": ["pendiente", "por revisar", "sin revisar", "falta revisar"], "revisada": ["revisada", "revisadas"],
                "descartada": ["descartad", "cortada", "cortadas", "incompleta", "incompletas"], "e1": ["error critico", "errores criticos", " e1 "]}

STOP = set("""a al algo algunas algunos ante antes aqui asi aun cada como con cual cuales cuando de del desde donde dos el ella ellas ellos en
entre era eran es esa esas ese eso esos esta estan estas este esto estos ha han hay la las le les lo los mas me mi mis muy ni no nos o
otra otro para pero por porque que quien quienes se sea segun ser si sin sobre su sus tambien te tiene tienen todo todos tu un una uno
unas unos y ya yo""".split())
# palabras que ya explican una pregunta estructurada (no cuentan como "tema" libre)
AGG_WORDS = set("""cuantas cuantos cuanta cuanto numero cantidad total porcentaje tasa proporcion promedio media nota notas ranking mejor peor
mejores peores quien asesor asesora asesores agente agentes llamada llamadas lista listame muestrame dame enumera cuales fallan falla fallo
cumple cumplen cumplio incumple incumplen aprobadas aprobada pasan semana mes dia dias hoy ayer ultimos ultimas pasada pasado este esta
criterio criterios mas menos por cada tuvieron tuvo tiene tienen hubo""".split())

AGG_PATTERNS = {
    "count": r"\bcuant[oa]s?\b|\bnumero de\b|\bcantidad\b|\btotal de\b",
    "rate": r"\bporcentaje\b|%|\btasa\b|\bproporcion\b",
    "avg": r"\bpromedio\b|\bnota media\b|\ben media\b|\bmedia de\b",
    "rank": r"\bquien\b|\bquienes\b|\bque asesor\w*|\bcual asesor\w*|\bcuales asesor\w*|\branking\b|\bmejor(es)?\b|\bpeor(es)?\b|\bmas (falla|fallan|incumple|incumplen)\b",
    "list": r"\bcuales\b|\blista\b|\blistame\b|\bmuestrame\b|\bdame\b|\benumera\b|\bque llamadas\b",
}
OPEN_PAT = r"\bpor que\b|\bpara que\b|\bexplica\w*|\bque dijo\b|\bque dicen\b|\bque dice\b|\bcomo (se|saluda|se despide|responde)\b|\bejemplos?\b|\breclam\w*|\bmotivo\b|\bqueja\w*|\bresum\w+ (de )?(lo que|los temas)\b"
FAIL_PAT = r"\bfall\w*|\bincumpl\w*|\bno cumpl\w*|\bmal\b|\breprob\w*|\bno pasa\w*"
PASS_PAT = r"\bcumplen?\b|\bcumplio\b|\bbien\b|\bpasan\b|\bcumpliendo\b"
FOLLOW_PAT = r"^y\b|\b(esa|ese|esas|esos|ella|el mismo|la misma|mismo|misma)\b|\bademas\b"
CARD_PAT = r"\bresumen\b|\bresultado\b|\bdetalle\b|\bcomo le fue\b|\bnota\b|\bficha\b"


@dataclass
class Filters:
    call_ids: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None
    types: list[str] = field(default_factory=list)
    estados: list[str] = field(default_factory=list)
    criteria: list[str] = field(default_factory=list)

    def empty(self) -> bool:
        return not any((self.call_ids, self.agents, self.date_from, self.date_to, self.types, self.estados, self.criteria))

    def call_level_empty(self) -> bool:
        """Sin filtros que reduzcan el conjunto de llamadas (criterio solo orienta, no filtra llamadas)."""
        return not any((self.call_ids, self.agents, self.date_from, self.date_to, self.types, self.estados))

    def describe(self) -> list[str]:
        out = []
        if self.call_ids:
            out.append("llamada " + ", ".join(self.call_ids))
        if self.agents:
            out.append("asesor " + ", ".join(self.agents))
        if self.date_from or self.date_to:
            out.append("del " + (self.date_from or "…") + " al " + (self.date_to or "…") if self.date_from != self.date_to else "el " + self.date_from)
        if self.types:
            out.append("tipo " + ", ".join(self.types))
        if self.estados:
            out.append("estado " + ", ".join(self.estados))
        if self.criteria:
            out.append("criterio " + ", ".join(self.criteria))
        return out

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "Filters":
        d = d or {}
        return Filters(**{k: d.get(k) or ([] if k in ("call_ids", "agents", "types", "estados", "criteria") else None) for k in
                          ("call_ids", "agents", "date_from", "date_to", "types", "estados", "criteria")})


@dataclass
class Parsed:
    text: str
    filters: Filters
    intent: str                 # aggregate | list | card | semantic
    metric: str = ""            # count | rate | avg | rank | list
    polarity: str = "fail"      # fail | pass (para criterios)
    group_by: str = ""          # agent | type | day
    follow_up: bool = False
    inherited: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ fechas
def _d(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _recent_year(month: int, today: date) -> int:
    return today.year if month <= today.month else today.year - 1


def parse_dates(raw: str, qn: str, today: date) -> tuple[str | None, str | None]:
    low = raw.lower()
    iso = lambda d: d.isoformat()  # noqa: E731
    if m := re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", low):
        y = int(m[3]) if m[3] else today.year
        y = y + 2000 if y < 100 else y
        if d := _d(y, int(m[2]), int(m[1])):
            return iso(d), iso(d)
    mon = "|".join(MONTHS)
    if m := re.search(rf"del (\d{{1,2}}) al (\d{{1,2}}) de ({mon})(?: de (\d{{4}}))?", qn):
        mo = MONTHS[m[3]]
        y = int(m[4]) if m[4] else _recent_year(mo, today)
        a, b = _d(y, mo, int(m[1])), _d(y, mo, int(m[2]))
        if a and b:
            return iso(a), iso(b)
    if m := re.search(rf"(?:el |dia )?(\d{{1,2}}) de ({mon})(?: de (\d{{4}}))?", qn):
        mo = MONTHS[m[2]]
        y = int(m[3]) if m[3] else _recent_year(mo, today)
        if d := _d(y, mo, int(m[1])):
            return iso(d), iso(d)
    if m := re.search(rf"\b({mon})(?: de (\d{{4}}))?\b", qn):
        mo = MONTHS[m[1]]
        y = int(m[2]) if m[2] else _recent_year(mo, today)
        first = date(y, mo, 1)
        last = (date(y + (mo == 12), mo % 12 + 1, 1)) - timedelta(days=1)
        return iso(first), iso(last)
    if re.search(r"\bhoy\b", qn):
        return iso(today), iso(today)
    if re.search(r"\bayer\b", qn):
        y = today - timedelta(days=1)
        return iso(y), iso(y)
    if re.search(r"\bsemana pasada\b", qn):
        mon0 = today - timedelta(days=today.weekday() + 7)
        return iso(mon0), iso(mon0 + timedelta(days=6))
    if re.search(r"\besta semana\b", qn):
        return iso(today - timedelta(days=today.weekday())), iso(today)
    if re.search(r"\bmes pasado\b", qn):
        last = date(today.year, today.month, 1) - timedelta(days=1)
        return iso(date(last.year, last.month, 1)), iso(last)
    if re.search(r"\b(este mes|en el mes)\b", qn):
        return iso(date(today.year, today.month, 1)), iso(today)
    if m := re.search(r"\bultim[oa]s? (\d{1,3}) dias\b", qn):
        return iso(today - timedelta(days=int(m[1]))), iso(today)
    if re.search(r"\bultima semana\b", qn):
        return iso(today - timedelta(days=7)), iso(today)
    return None, None


# ------------------------------------------------------------------ filtros
def _has(qn: str, phrase: str) -> bool:
    return f" {phrase} " in f" {qn} " if " " in phrase or len(phrase) <= 3 else bool(re.search(rf"\b{re.escape(phrase)}", qn))


def match_agents(qn: str, agents: list[str]) -> list[str]:
    """Asesor mencionado por nombre completo o por un nombre/apellido que identifique a uno solo."""
    toks = {a: [t for t in normalize(a).split() if len(t) >= 3] for a in agents}
    found = []
    for a, ts in toks.items():
        if not ts:
            continue
        if all(t in qn.split() for t in ts):
            found.append(a)
            continue
        hits = [t for t in ts if t in qn.split()]
        if hits and all(sum(t in o for o in toks.values()) == 1 for t in hits):    # token exclusivo de este asesor
            found.append(a)
    return found


def extract_filters(raw: str, qn: str, today: date, known_ids: list[str], agents: list[str]) -> Filters:
    f = Filters()
    words = set(qn.split())
    f.call_ids = [i for i in known_ids if i.lower() in words]
    f.agents = match_agents(qn, agents)
    f.date_from, f.date_to = parse_dates(raw, qn, today)
    for code, ws in CRITERIA_WORDS.items():
        if any(_has(qn, w) for w in ws):
            f.criteria.append(code)
    for t, ws in TYPE_WORDS.items():
        if any(_has(qn, w) for w in ws):
            f.types.append(t)
    for e, ws in ESTADO_WORDS.items():
        if any(w in f" {qn} " for w in ws):
            f.estados.append(e)
    if "no_aprobada" in f.estados and "aprobada" in f.estados:      # "no aprobadas" contiene "aprobad"
        f.estados.remove("aprobada")
    return f


def _unexplained(qn: str, f: Filters, agents: list[str]) -> int:
    """Palabras de contenido que ni los filtros ni el vocabulario estructurado explican: son un 'tema' libre."""
    known = set(AGG_WORDS) | set(MONTHS) | set(WEEKDAYS)
    for ws in list(CRITERIA_WORDS.values()) + list(TYPE_WORDS.values()):
        for w in ws:
            known.update(w.split())
    for ws in ESTADO_WORDS.values():
        for w in ws:
            known.update(x[:5] for x in w.split())
    for a in agents:
        known.update(normalize(a).split())
    known.update(i.lower() for i in f.call_ids)
    n = 0
    for t in qn.split():
        if t in STOP or t in known or t.isdigit() or len(t) <= 2 or any(t.startswith(k) for k in known if len(k) >= 5):
            continue
        n += 1
    return n


def parse(question: str, *, today: date | None = None, known_ids: list[str] | None = None, agents: list[str] | None = None,
          prev: dict | None = None) -> Parsed:
    today = today or date.today()
    raw = question.strip()
    qn = normalize(raw)
    agents = agents or []
    f = extract_filters(raw, qn, today, known_ids or [], agents)
    follow = bool(re.search(FOLLOW_PAT, qn))
    inherited: list[str] = []
    if follow and prev:
        p = Filters.from_dict(prev)
        for name in ("call_ids", "agents", "types", "estados", "criteria", "date_from", "date_to"):
            if not getattr(f, name) and getattr(p, name):
                setattr(f, name, getattr(p, name))
                inherited.append(name)
    metrics = [m for m, pat in AGG_PATTERNS.items() if re.search(pat, qn) or (m == "rate" and "%" in raw)]
    open_q = bool(re.search(OPEN_PAT, qn))
    polarity = "pass" if re.search(PASS_PAT, qn) and not re.search(FAIL_PAT, qn) else "fail"
    group = "agent" if re.search(r"\bpor (cada )?(asesor|asesora|agente)\b|\bquien\b|\bque asesor|\bcual asesor|\bcuales asesor", qn) else \
        "type" if re.search(r"\bpor tipo\b|\bpor motivo\b", qn) else "day" if re.search(r"\bpor dia\b|\bdiari", qn) else ""
    intent, metric = "semantic", ""
    if f.call_ids and not metrics and not open_q and re.search(CARD_PAT, qn):
        intent = "card"
    elif metrics and not open_q and _unexplained(qn, f, agents) < 2:
        intent = "list" if metrics == ["list"] else "aggregate"
        order = ["rank", "avg", "rate", "count", "list"]
        metric = next(m for m in order if m in metrics)
        if metric == "rank" and not group:
            group = "agent"
    return Parsed(text=raw, filters=f, intent=intent, metric=metric, polarity=polarity, group_by=group, follow_up=follow, inherited=inherited)
