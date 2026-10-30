"""Trazas de las llamadas a la IA: que se pidio, a que modelo, cuanto tardo, cuantos tokens, que se acepto y que fallo.

Se ven en la pestana «Trazas» de la interfaz (en vivo) y quedan en data/trazas.jsonl (local, fuera de git).
Nada de esto cambia el comportamiento de la IA: TracedLLM solo mira y delega. Los errores se guardan como mensaje
legible, nunca como stack trace.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from statistics import median

from .config import Settings

MAX_EVENTS = 300
CALL_ID: ContextVar[str | None] = ContextVar("trace_call_id", default=None)    # llamada que se esta auditando
_LOCK = threading.Lock()
_EVENTS: deque[dict] = deque(maxlen=MAX_EVENTS)
_LOADED = False
_SEQ = 0
_DIR: Path | None = None        # carpeta donde se guardan las trazas; None = solo memoria (pruebas, CLI)


def est_tokens(text: str) -> int:
    """Estimacion barata (~3,6 caracteres por token en espanol). Solo para respuestas en streaming, que no traen `usage`."""
    return int(len(text) / 3.6) + 1


def configure(settings: Settings) -> None:
    """La interfaz activa el guardado en data/trazas.jsonl. Sin esto las trazas viven solo en memoria."""
    global _DIR, _LOADED
    _DIR, _LOADED = settings.data_dir, False


def _file() -> Path | None:
    return _DIR / "trazas.jsonl" if _DIR else None


def _load() -> None:
    """Al arrancar, recupera lo ultimo guardado para que la demo no empiece vacia tras reiniciar."""
    global _LOADED, _SEQ
    if _LOADED:
        return
    _LOADED = True
    p = _file()
    if p is None or not p.exists():
        return
    try:
        for line in p.read_text(encoding="utf-8").splitlines()[-MAX_EVENTS:]:
            ev = json.loads(line)
            _EVENTS.append(ev)
            _SEQ = max(_SEQ, int(ev.get("id", 0)))
    except (OSError, ValueError):
        pass


def record(kind: str, label: str, *, status: str = "ok", **fields) -> dict:
    """Agrega una traza (memoria + archivo). kind: llm | auditoria | asistente."""
    global _SEQ
    with _LOCK:
        _load()
        _SEQ += 1
        ev = {"id": _SEQ, "ts": datetime.now().isoformat(timespec="seconds"), "kind": kind, "label": label, "status": status, **fields}
        _EVENTS.append(ev)
        p = _file()
        if p is not None:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            except OSError:
                pass                  # la traza nunca debe romper el analisis
    return ev


def events(limit: int = 100, since: int = 0) -> list[dict]:
    with _LOCK:
        _load()
        return [e for e in list(_EVENTS)[-limit:] if e["id"] > since]


def clear() -> None:
    with _LOCK:
        _EVENTS.clear()
        p = _file()
        try:
            if p is not None:
                p.unlink(missing_ok=True)
        except OSError:
            pass


def summary(evs: list[dict]) -> dict:
    """Cifras para el encabezado del panel: solo las llamadas reales a la IA (kind == llm)."""
    llm = [e for e in evs if e["kind"] == "llm"]
    ok = [e for e in llm if e["status"] == "ok"]
    secs = [e["secs"] for e in ok if e.get("secs") is not None]
    toks = [(e.get("prompt_tokens") or 0) + (e.get("completion_tokens") or 0) for e in ok]
    aud = [e for e in evs if e["kind"] == "auditoria"]
    return {"llamadas_ia": len(llm), "fallos": len(llm) - len(ok), "mediana_s": round(median(secs), 2) if secs else None,
            "mediana_tokens": int(median(toks)) if toks else None, "tokens_total": sum(toks),
            "citas_aceptadas": sum(e.get("aceptadas", 0) for e in aud), "citas_descartadas": sum(e.get("descartadas", 0) for e in aud)}


def friendly_error(e: Exception) -> str:
    """Mensaje corto para mostrar en pantalla (sin cuerpo de la respuesta, sin claves, sin stack trace)."""
    msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    return msg[:200]


# --------------------------------------------------------------------------- envoltura del cliente de IA
class TracedLLM:
    """Delega todo en `inner` (LlamaServer o RemoteLLM) y registra cada chat_json / chat_stream."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __enter__(self):
        self._inner.start()
        return self

    def __exit__(self, *a):
        self._inner.stop()

    def _who(self) -> dict:
        i = self._inner
        return {"modelo": getattr(i, "model_id", None) or getattr(getattr(i, "model", None), "name", None) or "?",
                "motor": getattr(i, "provider", None) or "local", "call_id": CALL_ID.get()}

    def chat_json(self, system: str, user: str, schema: dict):
        props = (schema or {}).get("properties", {})
        n = (props.get("checks", {}) or {}).get("maxItems")
        label = "Clasificar cómo terminó la llamada" if "estado" in props else f"Verificar {n} criterio(s) pendiente(s)" if n else "Consulta estructurada"
        t0 = time.time()
        try:
            data, meta = self._inner.chat_json(system, user, schema)
        except Exception as e:
            record("llm", label, status="error", error=friendly_error(e), secs=round(time.time() - t0, 1), **self._who())
            raise
        record("llm", label, secs=meta.get("secs"), prompt_tokens=meta.get("prompt_tokens"), completion_tokens=meta.get("completion_tokens"),
               **self._who())
        return data, meta

    def chat_stream(self, system: str, user: str, *a, **kw):
        t0, first, out = time.time(), None, []
        try:
            for tok in self._inner.chat_stream(system, user, *a, **kw):
                if first is None:
                    first = round(time.time() - t0, 2)
                out.append(tok)
                yield tok
        except Exception as e:
            record("llm", "Redactar respuesta del Asistente", status="error", error=friendly_error(e), secs=round(time.time() - t0, 1), **self._who())
            raise
        record("llm", "Redactar respuesta del Asistente", secs=round(time.time() - t0, 1), primer_token_s=first,
               prompt_tokens=est_tokens(system + user), completion_tokens=est_tokens("".join(out)), tokens_estimados=True, **self._who())


def wrap(server):
    return server if isinstance(server, TracedLLM) else TracedLLM(server)


# --------------------------------------------------------------------------- resumenes de alto nivel
def audit_summary(call_id: str, audit: dict) -> None:
    """Que paso con las citas de la IA en una llamada: aceptadas (verificadas en la transcripcion) vs descartadas (inventadas)."""
    llm = audit.get("llm") or {}
    log = llm.get("log") or []
    acc = sum(1 for x in log if x["result"] == "si_verificado")
    disc = sum(1 for x in log if x["result"] == "cita_inventada_descartada")
    comp = audit.get("completion") or {}
    if not log and not comp:
        return
    record("auditoria", f"Llamada {call_id}", call_id=call_id, aceptadas=acc, descartadas=disc,
           sin_evidencia=sum(1 for x in log if x["result"] == "no_sin_evidencia"), sin_respuesta=sum(1 for x in log if x["result"] == "sin_respuesta"),
           lotes_invalidos=llm.get("invalid_batches", 0), cierre=comp.get("estado"), cierre_aplicado=comp.get("applied"),
           pendientes=(audit.get("score") or {}).get("pending", []), detalle=log[:12])


def chat_summary(question: str, route: str, stats: dict, sources: list[dict], warnings: list[str]) -> None:
    """Resumen de una consulta al Asistente: por donde se respondio, cuanto tardo y que fragmentos se citaron."""
    cited = sum(1 for s in sources if s.get("cited"))
    record("asistente", question.strip()[:90], ruta=route, ms=stats.get("ms"), fragmentos=stats.get("fragments"),
           citados=cited, no_citados=max(0, len(sources) - cited) if stats.get("fragments") else None,
           degradado=stats.get("degraded"), avisos=warnings[:3], tokens_prompt_est=stats.get("prompt_tokens_est"),
           tokens_respuesta_est=stats.get("completion_tokens_est"))
