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
from ..config import ROOT, load_settings
from ..export import collect, export_xlsx
from ..jobs import AUDIO_EXT, JobManager, forget, incoming_dir, store_dir
from ..llm import LlamaServer
from ..review import CODES, final_view, load_review, save_review

STATIC = Path(__file__).parent / "static"
S = load_settings()
JOBS = JobManager(S)
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")

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
    st = au.get("status")
    sin = not au.get("criteria")
    if fin.get("discarded"):
        estado_ui = "descartada"
    elif sin:
        estado_ui = "sin_conversacion" if st == "no_speech" else "error"
    elif fin.get("reviewed"):
        estado_ui = "revisada"
    elif fin["pending"] or au["human_review"]["required"] or fin["e1"] == "candidato":
        estado_ui = "revisar"
    else:
        estado_ui = "lista"
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
            srv = {m: LlamaServer(S, m).available() for m in ("rapido", "preciso")}
            return self._json({"job": JOBS.status(), "llm": srv, "mode": S["llm"]["mode"],
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
            ok = JOBS.start(bool(d.get("use_llm", True)), mode)
            return self._json({"ok": ok, "error": None if ok else "Ya hay un análisis en curso"})
        if p == "/api/cancel":
            JOBS.cancel()
            return self._json({"ok": True})
        if p == "/api/clear_incoming":
            for f in incoming_dir(S).iterdir():
                if f.suffix.lower() in AUDIO_EXT:
                    f.unlink()
            return self._json({"ok": True})
        m = re.match(r"^/api/review/([^/]+)$", p)
        if m and ID_RE.match(m.group(1)):
            saved = save_review(m.group(1), json.loads(self._body() or b"{}"), S)
            au = json.loads((S.data_dir / "results" / f"{m.group(1)}.audit.json").read_text(encoding="utf-8"))
            return self._json({"ok": True, "review": saved, "final": final_view(au, saved, S)})
        return self._json({"error": "ruta desconocida"}, 404)

    def do_DELETE(self):
        m = re.match(r"^/api/call/([^/]+)$", urlparse(self.path).path)
        if not (m and ID_RE.match(m.group(1))):
            return self._json({"error": "no"}, 404)
        cid = m.group(1)
        for pat in (S.data_dir / "results", S.data_dir / "reviews", S.data_dir / "audio_store", S.data_dir / "cache" / "audio"):
            for f in pat.glob(f"{cid}.*"):
                f.unlink()
        forget(S, cid)
        return self._json({"ok": True})


def run(port: int = 8765, open_browser: bool = True) -> None:
    S.data_dir.mkdir(parents=True, exist_ok=True)
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
