"""Notificaciones por correo (SMTP propio). Las credenciales viven SOLO en .env (SMTP_*); los destinatarios y los avisos
activos, en data/notify.json. Los correos llevan ids, notas y plazos, nunca transcripciones, documentos ni telefonos."""
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage

from .config import Settings, load_settings

EVENTS = {
    "analisis": "Análisis terminado (resumen del lote)",
    "no_aprobada": "Llamada no aprobada o con error crítico",
    "queja_detectada": "Posible queja detectada en una llamada",
    "queja_vencida": "Queja con el plazo vencido",
    "comentario": "Comentario nuevo sobre la app",
}
_LOCK = threading.Lock()
MAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def _path(s: Settings):
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s.data_dir / "notify.json"


def _load(s: Settings) -> dict:
    p = _path(s)
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"to": d.get("to", []), "events": {k: d.get("events", {}).get(k, True) for k in EVENTS},
            "sent": d.get("sent", {}), "history": d.get("history", [])}


def _save(s: Settings, d: dict) -> None:
    d["history"] = d["history"][-60:]
    d["sent"] = dict(list(d["sent"].items())[-2000:])
    p = _path(s)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def smtp_ready() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip() and os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")).strip())


def status(s: Settings | None = None) -> dict:
    s = s or load_settings()
    with _LOCK:
        d = _load(s)
    return {"smtp": smtp_ready(), "host": os.environ.get("SMTP_HOST", "").strip(), "sender": os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")).strip(),
            "to": d["to"], "events": d["events"], "events_info": EVENTS, "history": d["history"][-12:][::-1]}


def save_config(s: Settings, to, events: dict) -> dict:
    mails = [m for m in (x.strip() for x in re.split(r"[,;\n]", ",".join(to) if isinstance(to, list) else str(to or ""))) if MAIL_RE.match(m)][:20]
    with _LOCK:
        d = _load(s)
        d["to"] = mails
        d["events"] = {k: bool((events or {}).get(k, d["events"][k])) for k in EVENTS}
        _save(s, d)
    return status(s)


def send_mail(subject: str, body: str, to: list[str]) -> None:
    """Envia un correo de texto. Lanza RuntimeError con un mensaje legible (nunca incluye la clave)."""
    if not smtp_ready():
        raise RuntimeError("Falta configurar el correo (SMTP_HOST y SMTP_FROM en el archivo .env).")
    host, port = os.environ["SMTP_HOST"].strip(), int(os.environ.get("SMTP_PORT", "587") or 587)
    user, pw = os.environ.get("SMTP_USER", "").strip(), os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", user).strip()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = f"[Auditoría de Llamadas] {subject}", sender, ", ".join(to)
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        if os.environ.get("SMTP_SECURITY", "starttls").lower() == "ssl":
            srv = smtplib.SMTP_SSL(host, port, timeout=20, context=ctx)
        else:
            srv = smtplib.SMTP(host, port, timeout=20)
            srv.starttls(context=ctx)
        with srv:
            if user:
                srv.login(user, pw)
            srv.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("El servidor de correo rechazó el usuario o la contraseña.") from None
    except (smtplib.SMTPException, OSError) as e:
        raise RuntimeError(f"No se pudo enviar el correo ({type(e).__name__}). Revise SMTP_HOST, el puerto y la conexión.") from None


def notify(s: Settings, event: str, subject: str, body: str, key: str | None = None, to: list[str] | None = None) -> bool:
    """Envia el aviso si el evento esta activo, hay destinatarios y SMTP listo. `key` evita repetir el mismo aviso."""
    with _LOCK:
        d = _load(s)
        rcpt = to or d["to"]
        if not d["events"].get(event) or not rcpt or not smtp_ready() or (key and key in d["sent"]):
            return False
    ok, err = True, ""
    try:
        send_mail(subject, body, rcpt)
    except RuntimeError as e:
        ok, err = False, str(e)
    with _LOCK:
        d = _load(s)
        d["history"].append({"ts": time.strftime("%Y-%m-%d %H:%M"), "evento": event, "asunto": subject, "ok": ok, "error": err})
        if ok and key:
            d["sent"][key] = time.strftime("%Y-%m-%d")
        _save(s, d)
    return ok


def send_test(s: Settings) -> dict:
    d = status(s)
    if not d["to"]:
        raise RuntimeError("Escriba al menos un destinatario y guarde.")
    send_mail("Prueba de notificaciones", "Si recibe este mensaje, las notificaciones por correo funcionan.", d["to"])
    return status(s)


# ---------------------------------------------------------------- avisos concretos
def job_finished(s: Settings, call_ids: list[str], errors: list[str]) -> None:
    """Resumen del lote y un aviso por cada llamada no aprobada o con error critico."""
    from .review import final_view, load_review

    if not call_ids:
        return
    res = s.data_dir / "results"
    bad, ok_n, pend = [], 0, 0
    for cid in call_ids:
        ap = res / f"{cid}.audit.json"
        if not ap.exists():
            continue
        au = json.loads(ap.read_text(encoding="utf-8"))
        fv = final_view(au, load_review(cid, s), s)
        if fv.get("discarded") or not au.get("criteria"):
            continue
        pct = fv.get("percent")
        if fv.get("e1") in ("candidato", "confirmed"):
            bad.append((cid, pct, "error crítico"))
        elif pct is None:
            pend += 1
        elif pct < s["review"]["pass_percent"]:
            bad.append((cid, pct, "no aprobada"))
        else:
            ok_n += 1
    lines = [f"Se analizaron {len(call_ids)} llamada(s).", f"Aprobadas: {ok_n}", f"Con criterios pendientes de revisión: {pend}",
             f"No aprobadas o con error crítico: {len(bad)}"]
    lines += [f"  - {c}: {'sin nota' if p is None else f'{p}%'} ({why})" for c, p, why in bad]
    if errors:
        lines += ["", "Avisos del análisis:"] + [f"  - {e[:160]}" for e in errors[:8]]
    lines += ["", "Abra la aplicación para revisar los detalles."]
    notify(s, "analisis", f"Análisis terminado: {len(call_ids)} llamada(s), {len(bad)} no aprobada(s)", "\n".join(lines))
    for cid, p, why in bad:
        notify(s, "no_aprobada", f"Llamada {cid}: {why}", f"La llamada {cid} quedó {why} ({'sin nota' if p is None else f'{p}%'}).\nAbra la aplicación para revisarla.",
               key=f"noap:{cid}")


def periodic_check(s: Settings) -> None:
    """Quejas vencidas y posibles quejas detectadas (una vez por queja / llamada)."""
    from .complaints import list_complaints, suggestions

    for q in list_complaints(s):
        if q["vencida"]:
            notify(s, "queja_vencida", f"Queja {q['id']} vencida", f"La queja {q['id']} (prioridad {q['prioridad']}, categoría {q['categoria']}) venció el {q['plazo']}.\nResponsable: {q['responsable'] or 'sin asignar'}.",
                   key=f"venc:{q['id']}:{q['plazo']}")
    for g in suggestions(s):
        notify(s, "queja_detectada", f"Posible queja en la llamada {g['llamada']}", f"El cliente parece quejarse en la llamada {g['llamada']} (asesor: {g['asesor'] or 'sin identificar'}).\nAbra «Quejas» para registrarla o descartarla.",
               key=f"det:{g['llamada']}")


def start_background(s: Settings, every_min: int = 30) -> None:
    def loop():
        time.sleep(45)
        while True:
            try:
                if smtp_ready():
                    periodic_check(s)
            except Exception:
                pass
            time.sleep(every_min * 60)
    threading.Thread(target=loop, daemon=True).start()
