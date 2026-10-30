"""Embeddings locales con un segundo `llama-server --embeddings` (modelo GGUF pequeno, p. ej. multilingual-e5-small).

Es OPCIONAL: sin el modelo, el asistente sigue funcionando con busqueda por palabras (FTS5), igual que el resto del proyecto
funciona sin IA (D-09). El servidor de embeddings pesa ~150 MB y se apaga solo tras unos minutos sin uso.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from ..config import Settings, load_settings
from ..llm import LlamaServer

MAX_CHARS = 1800          # el modelo admite 512 tokens; ~1800 caracteres de espanol caben con margen


def _norm(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(n == 0, 1, n)


class LlamaEmbedder:
    """Interfaz que usan el indexador y el buscador: available(), ident, embed_docs(), embed_query(), reap(), close()."""

    def __init__(self, settings: Settings | None = None):
        self.s = settings or load_settings()
        cfg = self.s["chat"]
        self.q_prefix = cfg.get("embed_query_prefix", "")
        self.d_prefix = cfg.get("embed_doc_prefix", "")
        model = self.s.models_dir / cfg["embed_model"]
        self.server = LlamaServer(self.s, model=model, port=cfg["embed_port"], ctx=1024,
                                  extra_args=("--embeddings", "--pooling", "mean", "-b", "1024", "-ub", "1024"))
        self.ident = f"{model.name}|{self.q_prefix}|{self.d_prefix}"
        self._last = 0.0
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self.server.available()

    def _ensure(self) -> None:
        with self._lock:
            self.server.start(timeout_s=120)
            self._last = time.time()

    def _embed(self, texts: list[str]) -> np.ndarray:
        self._ensure()
        out = []
        for i in range(0, len(texts), 16):
            out += self.server.embed([t[:MAX_CHARS] for t in texts[i:i + 16]])
        self._last = time.time()
        return _norm(np.array(out))

    def embed_docs(self, texts: list[str]) -> np.ndarray:
        return self._embed([self.d_prefix + t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([self.q_prefix + text])[0]

    def reap(self, idle_s: float) -> None:
        """Apaga el servidor si lo arranco este proceso y lleva `idle_s` sin usarse."""
        if self.server.proc and time.time() - self._last > idle_s:
            self.server.stop()

    def close(self) -> None:
        self.server.stop()
