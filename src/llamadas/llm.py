"""LLM local via llama.cpp (llama-server). Sin Ollama, sin APIs externas (D-01, D-02)."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

from .config import Settings, load_settings


class LlamaServer:
    """Arranca/detiene llama-server bajo demanda y habla con el por HTTP local (127.0.0.1)."""

    def __init__(self, settings: Settings | None = None, mode: str | None = None):
        self.s = settings or load_settings()
        cfg = self.s["llm"]
        self.mode = mode or cfg["mode"]
        self.port = cfg["port"]
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None
        self.model = self.s.models_dir / cfg["models"][self.mode]
        self.exe = self.s.models_dir / cfg["server_exe"]

    def available(self) -> bool:
        return self.exe.exists() and self.model.exists()

    def healthy(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=2) as r:
                return b"ok" in r.read()
        except Exception:
            return False

    def start(self, timeout_s: int = 180) -> None:
        if self.healthy():
            return
        if not self.available():
            raise RuntimeError(f"Modelo LLM no disponible: {self.model.name}")
        cfg = self.s["llm"]
        log = open(self.s.data_dir / "llama_server.log", "ab") if (self.s.data_dir).exists() else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            [str(self.exe), "-m", str(self.model), "-t", str(cfg["threads"]), "-c", str(cfg["ctx"]), "--port", str(self.port),
             "--host", "127.0.0.1", "--cache-prompt"],
            stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self.healthy():
                return
            if self.proc.poll() is not None:
                raise RuntimeError("llama-server termino inesperadamente (ver data/llama_server.log)")
            time.sleep(1.5)
        raise RuntimeError("llama-server no respondio a tiempo")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.stop()

    def chat_json(self, system: str, user: str, schema: dict) -> tuple[dict, dict]:
        """Respuesta JSON forzada por esquema (temperatura 0, semilla fija: reproducible)."""
        cfg = self.s["llm"]
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0, "seed": 1, "max_tokens": cfg["max_tokens"], "cache_prompt": True,
                "response_format": {"type": "json_object", "schema": schema}}
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t = time.time()
        with urllib.request.urlopen(req, timeout=1800) as r:
            resp = json.load(r)
        content = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage", {})
        return json.loads(content), {"secs": round(time.time() - t, 1), "prompt_tokens": usage.get("prompt_tokens"),
                                     "completion_tokens": usage.get("completion_tokens")}
