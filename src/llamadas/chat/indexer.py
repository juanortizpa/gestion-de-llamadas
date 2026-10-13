"""Mantiene el indice al dia: incremental (solo lo que cambio), con cache de vectores por contenido.

Una llamada se reindexa cuando cambia su auditoria, su transcripcion, su revision humana, el modelo de embeddings o la
version del fragmentador. Las llamadas que desaparecieron de disco se borran del indice (privacidad).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np

from ..config import Settings, load_settings
from ..review import final_view, load_review
from .chunks import CHUNKER_VERSION, build_call
from .retrieve import fts_text
from .store import Store


class Indexer:
    def __init__(self, settings: Settings | None = None, store: Store | None = None, embedder=None, include_synthetic: bool = False):
        self.s = settings or load_settings()
        self.store = store or Store(self.s)
        self.embedder = embedder
        self.include_synthetic = include_synthetic
        self.lock = threading.Lock()
        self.progress = {"running": False, "done": 0, "total": 0}
        self._skip: dict[str, str] = {}      # llamadas sinteticas ya vistas (no se indexan): evita revisarlas cada vez

    # ------------------------------------------------------------ deteccion de cambios
    def _files(self) -> dict[str, Path]:
        res = self.s.data_dir / "results"
        return {p.name[: -len(".audit.json")]: p for p in res.glob("*.audit.json")} if res.exists() else {}

    def _base(self, cid: str, audit_path: Path) -> str:
        res = self.s.data_dir / "results"
        parts = [CHUNKER_VERSION, str(self.s["chat"]["window_words"])]
        for p in (audit_path, res / f"{cid}.transcript.json", self.s.data_dir / "reviews" / f"{cid}.json"):
            parts.append(str(p.stat().st_mtime_ns) if p.exists() else "-")
        return "|".join(parts)

    @staticmethod
    def _needs_update(stored: str | None, base: str, desired: str) -> bool:
        """La firma guardada es `base#bandera`; bandera = modelo de embeddings usado o 'none' (solo palabras).
        Se reindexa si cambiaron los archivos, o si ahora hay vectores disponibles y la llamada no los tiene."""
        if not stored:
            return True
        sb, _, flag = stored.rpartition("#")
        return sb != base or (desired != "none" and flag != desired)

    def _desired(self, allow_embed: bool = True) -> str:
        ok = allow_embed and self.embedder is not None and self.embedder.available()
        return self.embedder.ident if ok else "none"

    def is_stale(self) -> bool:
        """Chequeo barato (solo stat) para decidir si vale la pena sincronizar."""
        known, files, desired = self.store.signatures(), self._files(), self._desired()
        if set(known) - set(files):
            return True
        return any(self._skip.get(c) != self._base(c, p) and self._needs_update(known.get(c), self._base(c, p), desired)
                   for c, p in files.items())

    # ------------------------------------------------------------ sincronizacion
    def sync(self, rebuild: bool = False, allow_embed: bool = True) -> dict:
        """Devuelve conteos. `allow_embed=False` (p. ej. durante un lote de auditoria) indexa solo palabras; los vectores
        se completan en la siguiente sincronizacion porque la firma incluye el identificador del modelo."""
        with self.lock:
            stats = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0, "embedded": 0, "from_cache": 0, "skipped_synthetic": 0,
                     "embed_error": None}
            self.progress = {"running": True, "done": 0, "total": 0}
            try:
                ident = self._desired(allow_embed)
                can_embed = ident != "none"
                prev_model = self.store.get_meta("embed_ident", "")
                if rebuild or (can_embed and prev_model and prev_model != ident):
                    self.store.clear()
                known = self.store.signatures()
                files = self._files()
                for cid in set(known) - set(files):
                    self.store.delete_call(cid)
                    stats["removed"] += 1
                todo = []
                for cid, p in files.items():
                    base = self._base(cid, p)
                    if self._skip.get(cid) == base:
                        stats["unchanged"] += 1
                    elif self._needs_update(known.get(cid), base, ident):
                        todo.append((cid, p, base))
                    else:
                        stats["unchanged"] += 1
                self.progress["total"] = len(todo)
                for i, (cid, p, base) in enumerate(todo, 1):
                    audit = json.loads(p.read_text(encoding="utf-8"))
                    if audit.get("synthetic") and not self.include_synthetic:
                        stats["skipped_synthetic"] += 1
                        self._skip[cid] = base
                        self.progress["done"] = i
                        continue
                    tp = p.with_name(f"{cid}.transcript.json")
                    transcript = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else {}
                    review = load_review(cid, self.s)
                    final = final_view(audit, review, self.s)
                    row, chunks = build_call(audit, transcript, review, final, "", self.s["chat"]["window_words"])
                    vectors, flag = None, "none"
                    if can_embed:
                        try:
                            vectors, n_new, n_cache = self._vectors(chunks)
                            flag = ident
                            stats["embedded"] += n_new
                            stats["from_cache"] += n_cache
                        except Exception as e:      # servidor de embeddings caido: indexa solo palabras y reintenta luego
                            stats["embed_error"] = str(e)
                            can_embed = False
                    row["sig"] = f"{base}#{flag}"
                    self.store.replace_call(row, chunks, vectors, fts_text)
                    stats["added" if cid not in known else "updated"] += 1
                    self.progress["done"] = i
                if stats["added"] or stats["updated"] or stats["removed"]:
                    self.store.bump()
                if stats["removed"]:
                    self.store.purge_cache()
                if can_embed:
                    self.store.set_meta("embed_ident", ident)
                return stats
            finally:
                self.progress["running"] = False

    def _vectors(self, chunks: list[dict]) -> tuple[dict[str, np.ndarray], int, int]:
        hashes = [c["hash"] for c in chunks]
        cached = self.store.cached_vectors(list(set(hashes)))
        missing = [c for c in chunks if c["hash"] not in cached]
        texts = {c["hash"]: c["ctx"] + "\n" + c["body"] for c in missing}
        if texts:
            keys = list(texts)
            vecs = self.embedder.embed_docs([texts[k] for k in keys])
            for k, v in zip(keys, vecs):
                cached[k] = np.asarray(v, dtype=np.float16)
        return {h: cached[h] for h in hashes}, len(texts), len(set(hashes)) - len(texts)
