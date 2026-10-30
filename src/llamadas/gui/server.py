"""Interfaz grafica local (navegador). Solo escucha en 127.0.0.1: los audios y datos nunca salen del equipo."""
from __future__ import annotations

import io
import json
import mimetypes
import re
import subprocess
import tempfile
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..audio import find_ffmpeg, parse_filename
from ..complaints import (complaints_xlsx, delete_complaint, dismiss_suggestion, list_complaints, options,
                          save_complaint, stats, suggestions)
from ..config import ROOT, load_settings
from ..export import collect, export_xlsx
from ..jobs import AUDIO_EXT, JobManager, forget, incoming_dir, store_dir
from ..llm import make_llm
from .. import feedback, notify, trace, vocab
from ..review import CODES, final_view, load_review, save_review, ui_state

STATIC = Path(__file__).parent / "static"
S = load_settings()
JOBS = JobManager(S)
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
NL = bytes([10])        # separador de lineas del flujo NDJSON
_CHAT = None
_CHAT_LOCK = threading.Lock()


def _engine_arg(v) -> str | None:
    """Solo "local" o "externa"; cualquier otra cosa = el proveedor configurado en .env."""
    return v if v in ("local", "externa") else None


def _external_info() -> dict:
    """Estado de la IA externa para la interfaz (nunca incluye la clave)."""
    from ..llm import PROVIDERS, external_provider
    p = external_provider(S)
    if p is None:
        return {"available": False, "provider": None, "label": "IA externa", "model": None}
    return {"available": True, "provider": p, "label": PROVIDERS[p]["name"], "model": S["llm"]["remote"][PROVIDERS[p]["model"]]}


def _default_engine(local_ok: dict) -> str:
    """Que IA se preselecciona: la externa si el instalador la eligio o si no hay modelo local pero si clave."""
    from ..llm import active_provider
    ext = _external_info()["available"]
    if active_provider(S) != "local" and ext:
        return "externa"
    if not any(local_ok.values()) and ext:
        return "externa"
    return "local"


def chat_engine():
    """Asistente de consulta (se crea al primer uso). Mientras corre un lote de analisis no enciende la IA del chat."""
    global _CHAT
    with _CHAT_LOCK:
        if _CHAT is None:
            from ..chat import ChatEngine
            _CHAT = ChatEngine(S, busy=lambda: bool(JOBS.status().get("running")))
            _CHAT.start_background()
        return _CHAT

GUIDE = {
    "P1": ("Saludo", "Saluda amablemente, indica la entidad y se identifica con nombre."),
    "P2": ("Nombre del cliente", "Personaliza la llamada usando el nombre del cliente durante la atención."),
    "V1": ("Confirma documento", "Solicita y valida el número de cédula/documento (del paciente, también si es menor)."),
    "V2": ("Valida datos / historial", "Verifica antecedentes del paciente, tipo de examen o requisitos previos."),
    "G1": ("Control de espera (hold)", "Mantiene cada espera en retención por debajo de 60 segundos."),
    "G2": ("Agilidad en el sistema", "Muestra destreza y rapidez en la búsqueda de la agenda/plataforma."),
    "C1": ("Escucha activa", "Presta atención, evita interrumpir al usuario y comprende su necesidad."),
    "C2": ("Tono y lenguaje", "Lenguaje claro, profesional, empático y respetuoso."),
    "Z1": ("Confirma cita / solución", "Resume la solución: fecha, hora, sede, especialista, soportes y preparación."),
    "Z2": ("Despedida", "Pregunta si requiere algo más y se despide cordialmente."),
}


def _summary(row: dict) -> dict:
    au, fin = row["audit"], row["final"]
    estado_ui = ui_state(au, fin)
    date = au["call"].get("received_date") or ""
    time_ = au["call"].get("received_time") or ""
    analyzed = au.get("analyzed_at")
    if not analyzed:  # análisis anteriores a este campo: fecha del archivo de resultados
        ap = S.data_dir / "results" / f"{row['id']}.audit.json"
        analyzed = datetime.fromtimestamp(ap.stat().st_mtime).isoformat(timespec="seconds") if ap.exists() else ""
    return {
        "analizada": analyzed,
        "id": row["id"], "archivo": au["call"]["source_file"], "duracion_s": au["call"]["duration_s"],
        "fecha": f"{date[6:8]}/{date[4:6]}/{date[:4]}" if len(date) == 8 else "", "hora": f"{time_[:2]}:{time_[2:4]}" if len(time_) >= 4 else "",
        "tipo": (au.get("call_type") or {}).get("type"), "criterios": {c: v["value"] for c, v in fin.get("criteria", {}).items()},
        "origen": {c: v["origin"] for c, v in fin.get("criteria", {}).items()},
        "nota": fin.get("percent"), "estado": fin.get("estado"), "estado_ui": estado_ui, "e1": fin.get("e1"),
        "agente": row["review"].get("agent", ""), "sintetica": au.get("synthetic", False), "descartada": fin.get("discarded"), "descarte_origen": fin.get("discard_origin"),
    }


def _wav_for_playback(call_id: str) -> Path | None:
    src = next((p for p in store_dir(S).glob(f"{call_id}.*")), None)
    if not src:
        return None
    out = S.data_dir / "cache" / "audio" / f"{call_id}.wav"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [find_ffmpeg(), "-v", "error", "-y"] + (["-f", "gsm", "-ar", "8000"] if src.suffix.lower() == ".gsm" else []) + \
              ["-i", str(src), "-ac", "1", "-ar", "8000", str(out)]
        subprocess.run(cmd, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "AuditoriaLlamadas"

    def log_message(self, *a):  # silencioso
        pass

    # --------------------------- utilidades
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _file(self, path: Path, ctype: str | None = None, download_name: str | None = None):
        if not path.exists():
            return self._json({"error": "no existe"}, 404)
        data = path.read_bytes()
        ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        code, start, end = 200, 0, len(data) - 1
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            start = int(m.group(1) or 0)
            end = int(m.group(2)) if m.group(2) else len(data) - 1
            code = 206
        chunk = data[start:end + 1]
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(chunk)))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(chunk)

    # --------------------------- GET
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if p.startswith("/static/"):
            f = (STATIC / p[len("/static/"):]).resolve()
            if STATIC.resolve() in f.parents:
                return self._file(f)
            return self._json({"error": "no"}, 404)
        if p == "/api/state":
            srv = {m: make_llm(S, m, "local").available() for m in ("rapido", "preciso")}
            return self._json({"job": JOBS.status(), "llm": srv, "mode": S["llm"]["mode"], "external": _external_info(),
                               "default_engine": _default_engine(srv),
                               "pending_files": sorted(f.name for f in incoming_dir(S).iterdir() if f.suffix.lower() in AUDIO_EXT),
                               "pass_percent": S["review"]["pass_percent"], "guide": GUIDE})
        if p == "/api/calls":
            return self._json([_summary(r) for r in collect(S)])
        m = re.match(r"^/api/call/([^/]+)$", p)
        if m and ID_RE.match(m.group(1)):
            cid = m.group(1)
            ap = S.data_dir / "results" / f"{cid}.audit.json"
            tp = S.data_dir / "results" / f"{cid}.transcript.json"
            if not ap.exists():
                return self._json({"error": "no existe"}, 404)
            au = json.loads(ap.read_text(encoding="utf-8"))
            tr = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else {}
            rv = load_review(cid, S)
            return self._json({"audit": au, "turns": tr.get("turns", []), "recorded": tr.get("recorded_intervals", []),
                               "quality": tr.get("quality", {}), "review": rv, "final": final_view(au, rv, S),
                               "has_audio": next(store_dir(S).glob(f"{cid}.*"), None) is not None, "guide": GUIDE})
        m = re.match(r"^/api/audio/([^/]+)$", p)
        if m and ID_RE.match(m.group(1)):
            wav = _wav_for_playback(m.group(1))
            return self._file(wav, "audio/wav") if wav else self._json({"error": "sin audio"}, 404)
        if p == "/api/quejas":
            return self._json({"quejas": list_complaints(S), "sugeridas": suggestions(S), "opciones": options(S), "stats": stats(S)})
        if p == "/api/quejas/export":
            tmp = Path(tempfile.gettempdir()) / "Quejas_Usuarios.xlsx"
            complaints_xlsx(tmp, S)
            return self._file(tmp, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Quejas_Usuarios.xlsx")
        if p == "/api/notify":
            return self._json(notify.status(S))
        if p == "/api/comentarios":
            return self._json(feedback.list_all(S))
        if p == "/api/vocab":
            return self._json(vocab.state(S))
        if p == "/api/trazas":
            q = parse_qs(u.query)
            evs = trace.events(min(int(q.get("limit", ["100"])[0] or 100), trace.MAX_EVENTS))
            return self._json({"eventos": evs, "resumen": trace.summary(evs)})
        if p == "/api/chat/status":
            return self._json(chat_engine().status(_engine_arg(parse_qs(u.query).get("engine", [None])[0])))
        if p == "/api/export":
            q = parse_qs(u.query)
            tmp = Path(tempfile.gettempdir()) / "Matriz_Auditoria_Llamadas.xlsx"
            export_xlsx(tmp, S, only_reviewed=q.get("revisadas", ["0"])[0] == "1")
            return self._file(tmp, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Matriz_Auditoria_Llamadas.xlsx")
        return self._json({"error": "ruta desconocida"}, 404)

    # --------------------------- POST / DELETE
    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/api/upload":
            name = Path(parse_qs(u.query).get("name", ["audio.gsm"])[0]).name
            if Path(name).suffix.lower() not in AUDIO_EXT:
                return self._json({"error": "Formato no soportado (use .gsm, .mp3 o .wav)"}, 400)
            safe = re.sub(r"[^A-Za-z0-9_.()\- ]", "_", name)
            dest = incoming_dir(S) / safe
            dest.write_bytes(self._body())
            return self._json({"ok": True, "name": safe})
        if p == "/api/process":
            d = json.loads(self._body() or b"{}")
            mode = d.get("mode") if d.get("mode") in ("rapido", "preciso") else S["llm"]["mode"]
            vocab.shutdown()           # la entrevista libera la GPU antes de analizar
            ok = JOBS.start(bool(d.get("use_llm", True)), mode, _engine_arg(d.get("engine")))
            return self._json({"ok": ok, "error": None if ok else "Ya hay un análisis en curso"})
        if p in ("/api/notify", "/api/notify/test", "/api/comentarios") or p.startswith("/api/comentarios/"):
            return self._misc(p)
        if p.startswith("/api/vocab/"):
            return self._vocab(p[len("/api/vocab/"):])
        if p == "/api/trazas/limpiar":
            trace.clear()
            return self._json({"ok": True})
        if p == "/api/cancel":
            JOBS.cancel()
            return self._json({"ok": True})
        if p == "/api/clear_incoming":
            for f in incoming_dir(S).iterdir():
                if f.suffix.lower() in AUDIO_EXT:
                    f.unlink()
            return self._json({"ok": True})
        if p == "/api/quejas":
            return self._json({"ok": True, "queja": save_complaint(json.loads(self._body() or b"{}"), S)})
        m = re.match(r"^/api/quejas/descartar/([^/]+)$", p)
        if m and ID_RE.match(m.group(1)):
            dismiss_suggestion(m.group(1), S)
            return self._json({"ok": True})
        if p == "/api/chat":
            return self._chat_stream()
        if p == "/api/chat/reindex":
            d = json.loads(self._body() or b"{}")
            eng = chat_engine()
            if d.get("rebuild"):
                threading.Thread(target=lambda: eng.sync_now(rebuild=True), daemon=True).start()
            else:
                eng.ensure_fresh(force=True)
            return self._json({"ok": True})
        m = re.match(r"^/api/review/([^/]+)$", p)
        if m and ID_RE.match(m.group(1)):
            saved = save_review(m.group(1), json.loads(self._body() or b"{}"), S)
            au = json.loads((S.data_dir / "results" / f"{m.group(1)}.audit.json").read_text(encoding="utf-8"))
            return self._json({"ok": True, "review": saved, "final": final_view(au, saved, S)})
        return self._json({"error": "ruta desconocida"}, 404)

    def _misc(self, p: str):
        """Correo (config y prueba) y comentarios sobre la app."""
        try:
            d = json.loads(self._body() or b"{}")
        except ValueError:
            return self._json({"error": "JSON inválido"}, 400)
        try:
            if p == "/api/notify":
                return self._json(notify.save_config(S, d.get("to", ""), d.get("events") or {}))
            if p == "/api/notify/test":
                return self._json(notify.send_test(S))
            if p == "/api/comentarios":
                return self._json({"ok": True, "comentario": feedback.add(d, S)})
            m = re.match(r"^/api/comentarios/([A-Za-z0-9-]{1,12})$", p)
            if m:
                return self._json({"ok": feedback.set_estado(m.group(1), str(d.get("estado")), S)})
        except (ValueError, RuntimeError) as e:
            return self._json({"error": str(e)}, 400)
        return self._json({"error": "ruta desconocida"}, 404)

    def _vocab(self, action: str):
        """Entrevista de vocabulario del dominio (ver vocab.py)."""
        try:
            d = json.loads(self._body() or b"{}")
        except ValueError:
            return self._json({"error": "JSON inválido"}, 400)
        try:
            if action == "turn":
                if JOBS.status().get("running"):
                    return self._json({"error": "Hay un análisis en curso: la GPU está ocupada. Espere a que termine."}, 409)
                return self._json(vocab.turn(S, str(d.get("answer") or "")[:1000], skip=bool(d.get("skip"))))
            if action == "status":
                return self._json(vocab.set_status(S, str(d.get("status"))))
            if action == "edit":
                return self._json(vocab.edit(S, str(d.get("action")), str(d.get("kind", "terms")), int(d.get("index", -1)), str(d.get("value", ""))[:80]))
        except Exception as e:
            return self._json({"error": str(e)}, 500)
        return self._json({"error": "ruta desconocida"}, 404)

    def _chat_stream(self):
        """Respuesta del asistente en NDJSON: una linea JSON por evento (ruta, tokens, fuentes, fin). La IA local genera
        ~10 tokens/s, asi que se muestra a medida que sale."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20_000:
            return self._json({"error": "Pregunta demasiado larga"}, 413)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "JSON inválido"}, 400)
        hist = [{"q": str(h.get("q", ""))[:600], "a": str(h.get("a", ""))[:600]} for h in (d.get("history") or [])[-3:] if isinstance(h, dict)]
        ctx = d.get("ctx") if isinstance(d.get("ctx"), dict) else None
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        gen = chat_engine().ask_stream(str(d.get("question", "")), ctx, hist, engine=_engine_arg(d.get("engine")))
        seen: dict = {"route": "", "sources": []}
        try:
            for ev in gen:
                if ev["type"] == "route":
                    seen["route"] = ev["route"]
                elif ev["type"] == "sources":
                    seen["sources"] = ev["sources"]
                elif ev["type"] == "done":
                    trace.chat_summary(str(d.get("question", "")), seen["route"], ev["stats"], seen["sources"], ev["warnings"])
                self.wfile.write(json.dumps(ev, ensure_ascii=False).encode("utf-8") + NL)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass                       # el usuario cerro la pestana o paro la respuesta
        except Exception as e:         # nunca dejar la conexion colgada
            try:
                self.wfile.write(json.dumps({"type": "error", "message": f"Error del asistente: {e}"}, ensure_ascii=False).encode("utf-8") + NL)
            except OSError:
                pass
        finally:
            gen.close()                # libera el candado de la IA si se corto a mitad

    def do_DELETE(self):
        p = urlparse(self.path).path
        m = re.match(r"^/api/comentarios/([A-Za-z0-9-]{1,12})$", p)
        if m:
            return self._json({"ok": feedback.delete(m.group(1), S)})
        m = re.match(r"^/api/quejas/([^/]+)$", p)
        if m and ID_RE.match(m.group(1)):
            return self._json({"ok": delete_complaint(m.group(1), S)})
        m = re.match(r"^/api/call/([^/]+)$", p)
        if not (m and ID_RE.match(m.group(1))):
            return self._json({"error": "no"}, 404)
        cid = m.group(1)
        for pat in (S.data_dir / "results", S.data_dir / "reviews", S.data_dir / "audio_store", S.data_dir / "cache" / "audio"):
            for f in pat.glob(f"{cid}.*"):
                f.unlink()
        forget(S, cid)
        chat_engine().forget(cid)      # privacidad: tambien se borran sus fragmentos y vectores del asistente
        return self._json({"ok": True})


def run(port: int = 8765, open_browser: bool = True) -> None:
    S.data_dir.mkdir(parents=True, exist_ok=True)
    trace.configure(S)
    notify.start_background(S)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Auditoría de Llamadas lista en {url}  (Ctrl+C para cerrar)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
