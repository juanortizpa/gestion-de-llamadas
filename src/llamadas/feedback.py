"""Comentarios sobre la propia app (sugerencias, errores, dudas). Se guardan en data/comentarios.json y, si el correo
esta configurado, se avisa al equipo. No se pide ningun dato personal: nombre y contacto son opcionales."""
from __future__ import annotations

import json
import threading
import time

from .config import Settings, load_settings

TIPOS = {"sugerencia": "Sugerencia", "error": "Algo no funciona", "duda": "Duda", "elogio": "Algo que funciona bien"}
ESTADOS = {"nuevo": "Nuevo", "leido": "Leído", "resuelto": "Resuelto"}
_LOCK = threading.Lock()


def _path(s: Settings):
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s.data_dir / "comentarios.json"


def _load(s: Settings) -> list[dict]:
    p = _path(s)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def _save(s: Settings, items: list[dict]) -> None:
    p = _path(s)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def list_all(s: Settings | None = None) -> dict:
    s = s or load_settings()
    with _LOCK:
        return {"items": _load(s)[::-1], "tipos": TIPOS, "estados": ESTADOS}


def add(data: dict, s: Settings | None = None) -> dict:
    s = s or load_settings()
    msg = str(data.get("mensaje") or "").strip()[:3000]
    if len(msg) < 5:
        raise ValueError("Escriba el comentario (mínimo 5 caracteres).")
    with _LOCK:
        items = _load(s)
        n = max((int(c["id"][2:]) for c in items if str(c.get("id", "")).startswith("C-") and c["id"][2:].isdigit()), default=0) + 1
        c = {"id": f"C-{n:04d}", "fecha": time.strftime("%Y-%m-%d %H:%M"), "tipo": data.get("tipo") if data.get("tipo") in TIPOS else "sugerencia",
             "mensaje": msg, "nombre": str(data.get("nombre") or "").strip()[:80], "contacto": str(data.get("contacto") or "").strip()[:120],
             "vista": str(data.get("vista") or "")[:30], "estado": "nuevo"}
        items.append(c)
        _save(s, items)
    from .notify import notify

    threading.Thread(target=notify, args=(s, "comentario", f"Comentario {c['id']}: {TIPOS[c['tipo']]}",
                                          f"{TIPOS[c['tipo']]} ({c['fecha']}, pestaña {c['vista'] or '—'})\nDe: {c['nombre'] or 'anónimo'} {c['contacto']}\n\n{msg}"), daemon=True).start()
    return c


def set_estado(cid: str, estado: str, s: Settings | None = None) -> bool:
    s = s or load_settings()
    with _LOCK:
        items = _load(s)
        c = next((x for x in items if x["id"] == cid), None)
        if not c or estado not in ESTADOS:
            return False
        c["estado"] = estado
        _save(s, items)
        return True


def delete(cid: str, s: Settings | None = None) -> bool:
    s = s or load_settings()
    with _LOCK:
        items = _load(s)
        keep = [x for x in items if x["id"] != cid]
        if len(keep) == len(items):
            return False
        _save(s, keep)
        return True
