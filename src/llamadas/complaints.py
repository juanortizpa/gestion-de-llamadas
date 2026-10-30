"""Panel de quejas: registro de quejas de usuarios (estado, plazo, responsable) y deteccion de posibles quejas
en las transcripciones. Todo vive en data/quejas.json (no versionado: incluye documento y telefono del usuario)."""
from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .catalog import get_catalog
from .config import Settings, load_settings
from .review import load_review
from .textutil import best_sentence, normalize

ESTADOS = {"abierta": "Abierta", "en_gestion": "En gestión", "cerrada": "Cerrada"}
PRIORIDADES = {"alta": "Alta", "media": "Media", "baja": "Baja"}
PLAZO_DIAS = {"alta": 3, "media": 8, "baja": 15}  # plazo de respuesta por defecto (dias calendario desde hoy o la fecha)
CANALES = {"llamada": "Llamada", "presencial": "Presencial", "whatsapp": "WhatsApp", "correo": "Correo", "otro": "Otro"}
CATEGORIAS = {
    "espera": "Demora en la atención o en la espera",
    "trato": "Trato del asesor",
    "cita": "Asignación, cambio o cancelación de cita",
    "informacion": "Información errada o incompleta",
    "comunicacion": "Llamada cortada o sin respuesta",
    "autorizacion": "Autorizaciones / EPS",
    "resultados": "Entrega de resultados",
    "cobros": "Cobros o facturación",
    "otro": "Otro",
}
TEXTOS = {"usuario": 120, "documento": 20, "telefono": 30, "asesor": 80, "sede": 120, "llamada": 60, "responsable": 80,
          "descripcion": 3000, "respuesta": 3000}

_LOCK = threading.Lock()  # el servidor atiende peticiones en varios hilos
_SCAN: dict[str, tuple[float, list]] = {}  # transcripcion -> (mtime, hallazgos)


def _path(settings: Settings) -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "quejas.json"


def _load(settings: Settings) -> dict:
    p = _path(settings)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"quejas": data.get("quejas", []), "descartadas": data.get("descartadas", [])}


def _write(settings: Settings, data: dict) -> None:
    p = _path(settings)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)  # escritura atomica: un corte de luz no deja el archivo a medias


def _iso(value) -> str:
    try:
        return date.fromisoformat(str(value or "")[:10]).isoformat()
    except ValueError:
        return ""


def _next_id(quejas: list[dict]) -> str:
    nums = [int(q["id"][2:]) for q in quejas if str(q.get("id", "")).startswith("Q-") and q["id"][2:].isdigit()]
    return f"Q-{max(nums, default=0) + 1:04d}"


def default_deadline(fecha: str, prioridad: str) -> str:
    """Fecha limite por prioridad, contada desde la fecha de la queja (o desde hoy si esa fecha ya paso)."""
    base = max(date.fromisoformat(fecha), date.today())
    return (base + timedelta(days=PLAZO_DIAS.get(prioridad, PLAZO_DIAS["media"]))).isoformat()


def is_overdue(q: dict, today: date | None = None) -> bool:
    return q.get("estado") != "cerrada" and bool(q.get("plazo")) and q["plazo"] < (today or date.today()).isoformat()


def list_complaints(settings: Settings | None = None) -> list[dict]:
    s = settings or load_settings()
    blank = {k: "" for k in TEXTOS} | {"fecha": "", "plazo": "", "cerrada_el": "", "canal": "otro", "categoria": "otro",
                                        "prioridad": "media", "estado": "abierta"}
    return [{**blank, **q, "vencida": is_overdue(q)} for q in _load(s)["quejas"]]


def save_complaint(data: dict, settings: Settings | None = None) -> dict:
    """Crea (sin id) o actualiza una queja. Valores fuera de catalogo se corrigen, no se rechazan."""
    s = settings or load_settings()
    with _LOCK:
        db = _load(s)
        old = next((q for q in db["quejas"] if q["id"] == data.get("id")), None)
        today = date.today().isoformat()
        q = {k: str(data.get(k) or "").strip()[:n] for k, n in TEXTOS.items()}
        q["fecha"] = _iso(data.get("fecha")) or (old or {}).get("fecha") or today
        q["canal"] = data.get("canal") if data.get("canal") in CANALES else "llamada"
        q["categoria"] = data.get("categoria") if data.get("categoria") in CATEGORIAS else "otro"
        q["prioridad"] = data.get("prioridad") if data.get("prioridad") in PRIORIDADES else "media"
        q["estado"] = data.get("estado") if data.get("estado") in ESTADOS else "abierta"
        q["plazo"] = _iso(data.get("plazo")) or default_deadline(q["fecha"], q["prioridad"])
        q["cerrada_el"] = ""
        if q["estado"] == "cerrada":  # conserva la fecha de cierre original si ya estaba cerrada
            was_closed = (old or {}).get("estado") == "cerrada"
            q["cerrada_el"] = ((old or {}).get("cerrada_el") if was_closed else "") or today
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if old:
            q = {"id": old["id"], "creada": old.get("creada", now), **q, "actualizada": now}
            db["quejas"][db["quejas"].index(old)] = q
        else:
            q = {"id": _next_id(db["quejas"]), "creada": now, **q, "actualizada": now}
            db["quejas"].append(q)
        _write(s, db)
        return q


def delete_complaint(qid: str, settings: Settings | None = None) -> bool:
    s = settings or load_settings()
    with _LOCK:
        db = _load(s)
        keep = [q for q in db["quejas"] if q["id"] != qid]
        if len(keep) == len(db["quejas"]):
            return False
        db["quejas"] = keep
        _write(s, db)
        return True


def dismiss_suggestion(call_id: str, settings: Settings | None = None) -> None:
    """El auditor decidio que en esa llamada no hubo queja: no se vuelve a sugerir."""
    s = settings or load_settings()
    with _LOCK:
        db = _load(s)
        if call_id not in db["descartadas"]:
            db["descartadas"].append(call_id)
            _write(s, db)


def detect(turns: list[dict], phrases: list[str]) -> list[dict]:
    """Turnos del cliente (o sin identificar) con frases de queja. Palabra completa exacta tras normalizar:
    una sugerencia falsa le cuesta tiempo al auditor, asi que se prefiere precision. La cita es literal (§20.6)."""
    hits = []
    for t in turns:
        if t.get("speaker") == "ASESOR":
            continue
        tn = f" {normalize(t.get('text', ''))} "
        found = [p for p in phrases if f" {p} " in tn]
        if found:
            hits.append({"turn_id": t.get("turn_id"), "start": t.get("start", 0.0), "frases": found[:3],
                         "cita": best_sentence(t["text"], found) or t["text"]})
    return hits


# Pistas para proponer categoria y prioridad al registrar una queja detectada (el auditor siempre puede cambiarlas)
PISTAS = {
    "espera": ["espera", "esperando", "demora", "demoran", "tardan", "tardo", "horas"],
    "trato": ["grosero", "grosera", "maltrato", "mal trato", "mala atencion", "no me atienden", "mal atendido"],
    "cita": ["cita", "cancelar", "cancelaron", "cancelada", "reprogramar", "agendar", "agenda"],
    "informacion": ["informacion", "me dijeron", "no me informaron", "me informaron mal"],
    "comunicacion": ["cortaron", "se cae", "nadie contesta", "no contestan", "no me contestan"],
    "autorizacion": ["autorizacion", "autorizar", "eps", "no autorizan"],
    "resultados": ["resultado", "resultados"],
    "cobros": ["cobro", "cobraron", "factura", "facturacion", "cobran"],
}
PISTAS_ALTA = ["supersalud", "tutela", "denuncia", "denunciar", "demanda", "demandar", "abogado", "defensoria", "personeria"]


def guess(texto: str) -> tuple[str, str]:
    """(categoria, prioridad) segun palabras del cliente. Sin pistas: ("otro", "media")."""
    tn = f" {normalize(texto)} "
    score = {c: sum(f" {normalize(w)} " in tn for w in ws) for c, ws in PISTAS.items()}
    cat, n = max(score.items(), key=lambda kv: kv[1])
    alta = any(f" {w} " in tn for w in PISTAS_ALTA)
    return (cat if n else "otro"), ("alta" if alta else "media")


def stats(settings: Settings | None = None) -> dict:
    """Para volver util el panel: donde se concentran las quejas y si se responden a tiempo."""
    s = settings or load_settings()
    qs = list_complaints(s)
    top = lambda key, labels=None: sorted(({"clave": (labels or {}).get(k, k), "n": n} for k, n in
                                           __import__("collections").Counter(q[key] for q in qs if q[key]).items()), key=lambda x: -x["n"])[:6]
    closed = [q for q in qs if q["estado"] == "cerrada" and q["cerrada_el"] and q["fecha"]]
    days = [(date.fromisoformat(q["cerrada_el"]) - date.fromisoformat(q["fecha"])).days for q in closed]
    on_time = [q for q in closed if q["plazo"] and q["cerrada_el"] <= q["plazo"]]
    return {"total": len(qs), "por_categoria": top("categoria", CATEGORIAS), "por_asesor": top("asesor"), "por_sede": top("sede"),
            "dias_cierre": round(sum(days) / len(days), 1) if days else None,
            "a_tiempo_pct": round(100 * len(on_time) / len(closed)) if closed else None, "cerradas": len(closed)}


def suggestions(settings: Settings | None = None) -> list[dict]:
    """Llamadas analizadas donde el cliente parece quejarse y que aun no tienen queja registrada ni fueron descartadas."""
    s = settings or load_settings()
    phrases = [normalize(p) for p in s.lex.get("quejas", {}).get("frases", [])]
    res = s.data_dir / "results"
    if not phrases or not res.exists():
        return []
    db = _load(s)
    skip = {q.get("llamada") for q in db["quejas"]} | set(db["descartadas"])
    out = []
    for tp in sorted(res.glob("*.transcript.json")):
        cid = tp.name[: -len(".transcript.json")]
        if cid in skip:
            continue
        mt = tp.stat().st_mtime
        cached = _SCAN.get(str(tp))
        if not cached or cached[0] != mt:
            tr = json.loads(tp.read_text(encoding="utf-8"))
            cached = (mt, [] if tr.get("synthetic") else detect(tr.get("turns", []), phrases))
            _SCAN[str(tp)] = cached
        if not cached[1]:
            continue
        ap = res / f"{cid}.audit.json"
        call = json.loads(ap.read_text(encoding="utf-8")).get("call", {}) if ap.exists() else {}
        d = call.get("received_date") or ""
        out.append({"llamada": cid, "fecha": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else "",
                    "duracion_s": call.get("duration_s"), "asesor": load_review(cid, s).get("agent", ""),
                    "hallazgos": cached[1], **dict(zip(("categoria", "prioridad"), guess(" ".join(h["cita"] for h in cached[1]))))})
    return out


def options(settings: Settings | None = None) -> dict:
    s = settings or load_settings()
    sedes = sorted({r["sede"] for r in get_catalog().rows if r.get("sede")})
    return {"estados": ESTADOS, "prioridades": PRIORIDADES, "plazo_dias": PLAZO_DIAS, "canales": CANALES,
            "categorias": CATEGORIAS, "asesores": list(s.agents), "sedes": sedes}


def complaints_xlsx(path: Path, settings: Settings | None = None) -> Path:
    s = settings or load_settings()
    wb = Workbook()
    ws = wb.active
    ws.title = "Quejas"
    ws["A1"] = "QUEJAS DE USUARIOS"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Generado el {datetime.now():%Y-%m-%d %H:%M}. Contiene datos personales: no lo comparta fuera de la entidad."
    head = ["ID", "Fecha", "Canal", "Usuario", "Documento", "Teléfono", "Categoría", "Asesor", "Sede", "Llamada",
            "Descripción", "Prioridad", "Fecha límite", "Estado", "Vencida", "Responsable", "Respuesta / solución", "Cerrada el"]
    for i, h in enumerate(head, 1):
        c = ws.cell(row=4, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    for r, q in enumerate(list_complaints(s), 5):
        vals = [q["id"], q["fecha"], CANALES.get(q["canal"], ""), q["usuario"], q["documento"], q["telefono"],
                CATEGORIAS.get(q["categoria"], ""), q["asesor"], q["sede"], q["llamada"], q["descripcion"],
                PRIORIDADES.get(q["prioridad"], ""), q["plazo"], ESTADOS.get(q["estado"], ""), "Sí" if q["vencida"] else "No",
                q["responsable"], q["respuesta"], q["cerrada_el"]]
        for i, v in enumerate(vals, 1):
            ws.cell(row=r, column=i, value=v).alignment = Alignment(wrap_text=True, vertical="top")
    for i, w in enumerate([9, 11, 11, 24, 13, 14, 30, 18, 22, 14, 50, 9, 12, 11, 8, 18, 44, 11], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A5"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
