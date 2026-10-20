"""Procesamiento por lotes (secuencial, reanudable). Lo usan la CLI y la interfaz grafica."""
from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from .audio import parse_filename, sha256_file
from .audit import audit_transcript, save_audit
from .auditor import classify_completion, resolve_with_llm
from .config import Settings, load_settings
from .llm import LlamaServer, make_llm
from .pipeline import process_file, save_result

STAGES = [("audio", "Preparando el audio"), ("stt", "Transcribiendo la conversación"), ("grabado", "Detectando mensajes grabados"),
          ("diar", "Separando asesor y cliente"), ("reglas", "Aplicando reglas de calidad"), ("llm", "Análisis con IA")]
AUDIO_EXT = {".gsm", ".mp3", ".wav"}


def store_dir(s: Settings) -> Path:
    d = s.data_dir / "audio_store"
    d.mkdir(parents=True, exist_ok=True)
    return d


def incoming_dir(s: Settings) -> Path:
    d = s.data_dir / "incoming"
    d.mkdir(parents=True, exist_ok=True)
    return d


def already_done(s: Settings, sha: str) -> str | None:
    """call_id si este audio (por hash) ya fue procesado."""
    idx = s.data_dir / "index.json"
    if idx.exists():
        return json.loads(idx.read_text(encoding="utf-8")).get(sha)
    return None


def _register(s: Settings, sha: str, call_id: str) -> None:
    idx = s.data_dir / "index.json"
    data = json.loads(idx.read_text(encoding="utf-8")) if idx.exists() else {}
    data[sha] = call_id
    idx.write_text(json.dumps(data), encoding="utf-8")


def forget(s: Settings, call_id: str) -> None:
    idx = s.data_dir / "index.json"
    if idx.exists():
        data = {k: v for k, v in json.loads(idx.read_text(encoding="utf-8")).items() if v != call_id}
        idx.write_text(json.dumps(data), encoding="utf-8")


class JobManager:
    """Un solo lote a la vez. Estado consultable por la GUI."""

    def __init__(self, settings: Settings | None = None):
        self.s = settings or load_settings()
        self.lock = threading.Lock()
        self.cancel_ev = threading.Event()
        self.thread: threading.Thread | None = None
        self.state = self._idle()

    @staticmethod
    def _idle() -> dict:
        return {"running": False, "total": 0, "done": 0, "skipped": 0, "current": None, "stage": None, "stage_idx": 0,
                "stages": [n for _, n in STAGES], "errors": [], "started": None, "finished": None, "eta_s": None,
                "message": "", "use_llm": False, "mode": None, "call_ids": [], "auto_discarded": []}

    def status(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def start(self, use_llm: bool, mode: str, engine: str | None = None) -> bool:
        """`engine`: "local" | "externa" | None (None = el proveedor de .env)."""
        if self.thread and self.thread.is_alive():
            return False
        files = sorted(f for f in incoming_dir(self.s).iterdir() if f.suffix.lower() in AUDIO_EXT)
        self.cancel_ev.clear()
        self.state = {**self._idle(), "running": True, "total": len(files), "started": time.time(), "use_llm": use_llm,
                      "mode": mode, "engine": engine, "message": "Iniciando…"}
        self.thread = threading.Thread(target=self._run, args=(files, use_llm, mode, engine), daemon=True)
        self.thread.start()
        return True

    def cancel(self):
        self.cancel_ev.set()
        self._set(message="Cancelando al terminar la llamada actual…")

    # ------------------------------------------------------------------
    def _run(self, files: list[Path], use_llm: bool, mode: str, engine: str | None = None):
        s = self.s
        server = None
        try:
            if use_llm:
                server = make_llm(s, mode, engine)
                ext = getattr(server, "provider", None) is not None       # True si es una API externa
                kind = "externa" if ext else "local"
                if server.available():
                    self._set(message="Conectando con la IA externa…" if ext else "Encendiendo la IA local (puede tardar 1–2 minutos)…")
                    try:
                        server.start()
                    except Exception as e:  # sin LLM el sistema sigue (modo degradado D-09)
                        self.state["errors"].append(f"IA {kind} no disponible, se continúa solo con reglas: {e}")
                        server = None
                else:
                    self.state["errors"].append("No hay clave de IA externa (ejecute Instalar.bat): se continúa solo con reglas." if ext
                                                else "El modelo de IA local no está instalado: se continúa solo con reglas.")
                    server = None
            t_start = time.time()
            for i, f in enumerate(files):
                if self.cancel_ev.is_set():
                    break
                meta = parse_filename(f.name)
                self._set(current=meta.get("masked_name", f.name), stage="Preparando", stage_idx=0, message="")
                try:
                    cid = self._one(f, server)
                    if cid:
                        with self.lock:
                            self.state["call_ids"].append(cid)
                except Exception as e:
                    self.state["errors"].append(f"{meta.get('masked_name', f.name)}: {e}")
                    (s.data_dir / "errores.log").open("a", encoding="utf-8").write(f"{f.name}\n{traceback.format_exc()}\n")
                done = i + 1
                per = (time.time() - t_start) / done
                self._set(done=done, eta_s=int(per * (len(files) - done)))
        finally:
            if server:
                server.stop()
            self._set(running=False, finished=time.time(), current=None, stage=None,
                      message="Cancelado" if self.cancel_ev.is_set() else "Listo")
            try:                                   # aviso por correo (si esta configurado); nunca debe romper el lote
                from .notify import job_finished
                job_finished(s, list(self.state["call_ids"]), list(self.state["errors"]))
            except Exception:
                pass

    def _stage(self, key: str):
        names = [k for k, _ in STAGES]
        self._set(stage=dict(STAGES)[key], stage_idx=names.index(key))

    def _one(self, f: Path, server: LlamaServer | None) -> str:
        """Procesa un audio y devuelve su call_id (el existente si ya se había analizado)."""
        s = self.s
        sha = sha256_file(f)
        known = already_done(s, sha)
        if known and (s.data_dir / "results" / f"{known}.audit.json").exists():
            self.state["skipped"] += 1
            f.unlink()
            return known

        def log(msg: str):
            if msg.startswith("decodificando"):
                self._stage("audio")
            elif msg.startswith("transcribiendo"):
                self._stage("stt")
            elif msg.startswith("audio grabado"):
                self._stage("grabado")
            elif msg.startswith("diarizando"):
                self._stage("diar")

        tr = process_file(f, s, log)
        cid = tr["call"]["call_id"]
        save_result(tr, s)
        dest = store_dir(s) / f"{cid}{f.suffix.lower()}"
        shutil.move(str(f), dest)
        _register(s, sha, cid)
        self._stage("reglas")
        au = audit_transcript(tr, s)
        au["analyzed_at"] = datetime.now().isoformat(timespec="seconds")
        save_audit(au, s)
        if server is not None and au.get("criteria") and not au.get("auto_discard"):
            self._stage("llm")
            try:
                au = classify_completion(au, tr, server, s)   # ¿finalizó, se cortó o está incompleta?
                save_audit(au, s)
                if not au.get("auto_discard"):                # si quedó descartada no se gasta IA en calificarla
                    au = resolve_with_llm(au, tr, server, s)
                    save_audit(au, s)
            except Exception as e:
                self.state["errors"].append(f"{cid}: la IA falló, quedan pendientes ({e})")
        if au.get("auto_discard"):
            with self.lock:
                self.state["auto_discarded"].append(cid)
        return cid
