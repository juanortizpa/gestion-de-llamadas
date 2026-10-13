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

    def __init__(self, settings: Settings | None = None, mode: str | None = None, *, model: Path | None = None,
                 port: int | None = None, ctx: int | None = None, extra_args: tuple[str, ...] = ()):
        """Por defecto, el LLM de auditoria. `model`/`port`/`extra_args` permiten un segundo servidor (embeddings)."""
        self.s = settings or load_settings()
        cfg = self.s["llm"]
        self.mode = mode or cfg["mode"]
        self.port = port or cfg["port"]
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None
        self.model = model or self.s.models_dir / cfg["models"][self.mode]
        self.exe = self.s.models_dir / cfg["server_exe"]
        self.ctx = ctx or cfg["ctx"]
        self.extra_args = list(extra_args)

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
        log = open(self.s.data_dir / f"llama_server_{self.port}.log", "ab") if (self.s.data_dir).exists() else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            [str(self.exe), "-m", str(self.model), "-t", str(cfg["threads"]), "-c", str(self.ctx), "--port", str(self.port),
             "--host", "127.0.0.1", "--cache-prompt", *self.extra_args],
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

    def chat_stream(self, system: str, user: str, max_tokens: int = 350, temperature: float = 0.1):
        """Respuesta de texto libre, token a token (generador de str). Salida corta: la CPU genera ~10 tok/s."""
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temperature, "seed": 1, "max_tokens": max_tokens, "cache_prompt": True, "stream": True}
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                except (ValueError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Vectores de un servidor arrancado con --embeddings (endpoint compatible OpenAI)."""
        req = urllib.request.Request(self.url + "/v1/embeddings", data=json.dumps({"input": texts, "model": "embed"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.load(r)["data"]
        return [d["embedding"] for d in sorted(data, key=lambda d: d.get("index", 0))]
