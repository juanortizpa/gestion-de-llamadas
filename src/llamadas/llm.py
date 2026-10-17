"""LLM de la auditoria. Por defecto LOCAL: llama.cpp (llama-server), sin Ollama y sin internet al usar (D-01, D-02).

Opcionalmente, el instalador (o LLM_PROVIDER en .env) puede usar una API externa (Groq o Gemini) con el MISMO contrato
(chat_json / chat_stream), para equipos sin recursos para un modelo local. Con API externa los textos de las llamadas
salen del equipo: el instalador lo advierte antes de guardar la eleccion.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import Settings, load_settings

PROVIDERS = {
    "groq": {"key": "GROQ_API_KEY", "model": "groq_model", "name": "Groq (GPT-OSS 120B)"},
    "gemini": {"key": "GEMINI_API_KEY", "model": "gemini_model", "name": "Google Gemini 1.5 Flash"},
}


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


def active_provider(settings: Settings | None = None) -> str:
    """'local' (por defecto), 'groq' o 'gemini'. LLM_PROVIDER en .env manda sobre [llm].provider de settings.toml."""
    s = settings or load_settings()
    p = (os.environ.get("LLM_PROVIDER") or s["llm"].get("provider", "local")).strip().lower()
    return p if p in PROVIDERS else "local"


def external_provider(settings: Settings | None = None) -> str | None:
    """Proveedor externo listo para usar (con clave): el de LLM_PROVIDER si es externo, si no el primero con clave. None si no hay."""
    s = settings or load_settings()
    pref = active_provider(s)
    order = ([pref] if pref in PROVIDERS else []) + [p for p in PROVIDERS if p != pref]
    return next((p for p in order if os.environ.get(PROVIDERS[p]["key"], "").strip()), None)


class RemoteLLM:
    """API externa (Groq o Gemini) con el mismo contrato que LlamaServer: chat_json, chat_stream, available, start/stop."""

    def __init__(self, settings: Settings | None = None, provider: str = "groq", mode: str | None = None):
        self.s = settings or load_settings()
        cfg = self.s["llm"]
        self.provider = provider
        self.mode = mode or cfg["mode"]
        self.key_var = PROVIDERS[provider]["key"]
        self.model_id = cfg["remote"][PROVIDERS[provider]["model"]]      # identificador completo (puede llevar "org/")
        self.model = Path(self.model_id)                                 # solo para exponer .name como LlamaServer
        self.proc = None
        self.max_tokens = cfg["max_tokens"]
        self.timeout = cfg["remote"].get("timeout_s", 60)

    @property
    def key(self) -> str:
        return os.environ.get(self.key_var, "").strip()

    def available(self) -> bool:
        return bool(self.key)

    def healthy(self) -> bool:
        return self.available()

    def start(self, timeout_s: int = 0) -> None:
        if not self.available():
            raise RuntimeError(f"Falta {self.key_var} en el archivo .env (ejecute Instalar.bat o copie .env.example)")

    def stop(self) -> None:
        pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.stop()

    # ---------------------------------------------------------------- HTTP
    def _request(self, body: dict, stream: bool = False) -> urllib.request.Request:
        if self.provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.key}"}
        else:
            verb = "streamGenerateContent?alt=sse" if stream else "generateContent"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:{verb}"
            headers = {"x-goog-api-key": self.key}      # en cabecera: la clave no queda en la URL ni en logs
        # User-Agent propio: el de urllib ("Python-urllib/3.x") lo bloquea el firewall de algunos proveedores (403)
        return urllib.request.Request(url, data=json.dumps(body).encode(),
                                      headers={"Content-Type": "application/json", "User-Agent": "auditoria-llamadas/0.1", **headers})

    @staticmethod
    def _fail(e: Exception) -> RuntimeError:
        """Mensaje legible, sin cuerpo de la respuesta ni cabeceras (nunca la clave)."""
        if isinstance(e, urllib.error.HTTPError):
            if e.code == 429:
                return RuntimeError("La API externa limito las peticiones (429). Espere un momento e intente de nuevo.")
            if e.code == 401:
                return RuntimeError("La API externa rechazo la clave (revise la clave en .env).")
            if e.code == 403:
                return RuntimeError("La API externa nego el acceso (403): la clave no tiene permiso, o la red/proveedor bloquea la peticion.")
            return RuntimeError(f"La API externa respondio con error {e.code}.")
        if isinstance(e, TimeoutError) or "timed out" in str(e):
            return RuntimeError("La API externa tardo demasiado en responder.")
        return RuntimeError("No se pudo conectar con la API externa (revise la conexion a internet).")

    def _body(self, system: str, user: str, *, temperature: float, max_tokens: int, json_mode: bool, stream: bool = False) -> dict:
        if self.provider == "groq":
            body = {"model": self.model_id, "temperature": temperature, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if "gpt-oss" in self.model_id:
                body["reasoning_effort"] = "low"     # modelo de razonamiento: sin esto gasta los tokens pensando y la respuesta sale vacia
                body["max_tokens"] = max_tokens + 512   # los tokens de razonamiento cuentan dentro del limite: se da margen
            if json_mode:
                body["response_format"] = {"type": "json_object"}
                body["seed"] = 1
            if stream:
                body["stream"] = True
            return body
        gen = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        return {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gen}

    # ---------------------------------------------------------------- contrato LlamaServer
    def chat_json(self, system: str, user: str, schema: dict) -> tuple[dict, dict]:
        """JSON que cumple `schema`. La API no impone el esquema como llama.cpp: se pide en el prompt y se valida al parsear."""
        system = f"{system}\n\nResponde SOLO con un objeto JSON que cumpla este esquema:\n{json.dumps(schema, ensure_ascii=False)}"
        body = self._body(system, user, temperature=0, max_tokens=self.max_tokens, json_mode=True)
        t = time.time()
        try:
            with urllib.request.urlopen(self._request(body), timeout=self.timeout) as r:
                resp = json.load(r)
        except Exception as e:
            raise self._fail(e) from None
        if self.provider == "groq":
            content, usage = resp["choices"][0]["message"]["content"], resp.get("usage", {})
            pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
        else:
            content = resp["candidates"][0]["content"]["parts"][0]["text"]
            um = resp.get("usageMetadata", {})
            pt, ct = um.get("promptTokenCount"), um.get("candidatesTokenCount")
        try:
            data = json.loads(content)
        except ValueError:
            raise RuntimeError("La API externa devolvio un JSON invalido.") from None
        return data, {"secs": round(time.time() - t, 1), "prompt_tokens": pt, "completion_tokens": ct}

    def chat_stream(self, system: str, user: str, max_tokens: int = 350, temperature: float = 0.1):
        """Texto libre token a token (SSE), igual que LlamaServer.chat_stream."""
        body = self._body(system, user, temperature=temperature, max_tokens=max_tokens, json_mode=False, stream=True)
        try:
            with urllib.request.urlopen(self._request(body, stream=True), timeout=self.timeout) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                        if self.provider == "groq":
                            delta = obj["choices"][0].get("delta", {}).get("content")
                        else:
                            delta = obj["candidates"][0]["content"]["parts"][0].get("text")
                    except (ValueError, KeyError, IndexError):
                        continue
                    if delta:
                        yield delta
        except Exception as e:
            raise self._fail(e) from None


def make_llm(settings: Settings | None = None, mode: str | None = None, engine: str | None = None):
    """Fabrica unica del LLM de auditoria y chat. `engine`: "local" | "externa" | None (None = lo que diga active_provider(),
    o sea LLM_PROVIDER en .env). "externa" usa el proveedor con clave; si no hay ninguno, devuelve uno no disponible
    (available() == False) para que la interfaz explique que falta la clave."""
    s = settings or load_settings()
    if engine == "local":
        return LlamaServer(s, mode)
    if engine == "externa":
        return RemoteLLM(s, external_provider(s) or next(iter(PROVIDERS)), mode)
    p = active_provider(s)
    return LlamaServer(s, mode) if p == "local" else RemoteLLM(s, p, mode)
