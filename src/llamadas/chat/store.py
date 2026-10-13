"""Indice del asistente: SQLite (un solo archivo en data/chat/index.db).

  calls   una fila por llamada con los datos estructurados (para contar/filtrar sin IA)
  chunks  fragmentos de texto (resumen, criterios, ventanas de transcripcion, observaciones)
  fts     FTS5 sobre los fragmentos (busqueda por palabras, BM25)
  vecs    vectores float16 de los fragmentos (busqueda semantica; opcional)
  embcache  vectores por hash de contenido: reindexar no vuelve a calcular lo que no cambio

Los vectores se buscan por fuerza bruta en numpy sobre una matriz en memoria. Es suficiente para decenas de miles de
fragmentos; con cientos de miles hay que filtrar por fecha o pasar a un indice aproximado (sqlite-vec).
Todo vive en data/ (fuera de git) y se borra junto con la llamada (privacidad).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from ..config import Settings, load_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS calls(
  call_id TEXT PRIMARY KEY, sig TEXT, date TEXT, time TEXT, agent TEXT, auditor TEXT, type TEXT, queue TEXT,
  duration_s REAL, percent REAL, points INTEGER, estado TEXT, estado_ui TEXT, e1 TEXT, discarded TEXT, reviewed INTEGER,
  pending TEXT, criteria TEXT, n_holds INTEGER, longest_hold REAL, analyzed_at TEXT);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY, call_id TEXT NOT NULL, kind TEXT NOT NULL, criterion TEXT, t0 REAL, t1 REAL,
  turn0 INTEGER, turn1 INTEGER, ctx TEXT, body TEXT, hash TEXT);
CREATE INDEX IF NOT EXISTS chunks_call ON chunks(call_id);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS vecs(chunk_id INTEGER PRIMARY KEY, vec BLOB);
CREATE TABLE IF NOT EXISTS embcache(hash TEXT PRIMARY KEY, vec BLOB);
"""
CALL_COLS = ["call_id", "sig", "date", "time", "agent", "auditor", "type", "queue", "duration_s", "percent", "points", "estado",
             "estado_ui", "e1", "discarded", "reviewed", "pending", "criteria", "n_holds", "longest_hold", "analyzed_at"]


class Store:
    def __init__(self, settings: Settings | None = None, path: Path | None = None):
        s = settings or load_settings()
        self.path = path or (s.data_dir / "chat" / "index.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._mat: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None   # (ids, call_idx, matriz) en memoria
        self._call_names: list[str] = []
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---------------------------------------------------------------- meta
    def get_meta(self, key: str, default: str = "") -> str:
        with self.conn() as c:
            r = c.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return r["v"] if r else default

    def set_meta(self, key: str, value: str) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, value))

    def version(self) -> str:
        """Cambia con cada reindexado: invalida la cache de respuestas."""
        return self.get_meta("version", "0")

    def bump(self) -> None:
        self.set_meta("version", str(int(self.version()) + 1))
        self._mat = None

    # ---------------------------------------------------------------- escritura
    def signatures(self) -> dict[str, str]:
        with self.conn() as c:
            return {r["call_id"]: r["sig"] for r in c.execute("SELECT call_id, sig FROM calls")}

    def cached_vectors(self, hashes: list[str]) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        with self.conn() as c:
            for i in range(0, len(hashes), 500):
                part = hashes[i:i + 500]
                q = ",".join("?" * len(part))
                for r in c.execute(f"SELECT hash, vec FROM embcache WHERE hash IN ({q})", part):
                    out[r["hash"]] = np.frombuffer(r["vec"], dtype=np.float16)
        return out

    def replace_call(self, row: dict, chunks: list[dict], vectors: dict[str, np.ndarray] | None, fts_text) -> None:
        """Reemplaza TODO lo de una llamada (fila + fragmentos + vectores) en una sola transaccion."""
        with self.lock, self.conn() as c:
            self._delete(c, row["call_id"])
            c.execute(f"INSERT INTO calls({','.join(CALL_COLS)}) VALUES({','.join('?' * len(CALL_COLS))})",
                      [row.get(k) for k in CALL_COLS])
            for ch in chunks:
                cur = c.execute("INSERT INTO chunks(call_id,kind,criterion,t0,t1,turn0,turn1,ctx,body,hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (row["call_id"], ch["kind"], ch.get("criterion"), ch.get("t0"), ch.get("t1"), ch.get("turn0"),
                                 ch.get("turn1"), ch["ctx"], ch["body"], ch["hash"]))
                cid = cur.lastrowid
                c.execute("INSERT INTO fts(rowid, text) VALUES(?,?)", (cid, fts_text(ch)))
                if vectors is not None and ch["hash"] in vectors:
                    blob = np.asarray(vectors[ch["hash"]], dtype=np.float16).tobytes()
                    c.execute("INSERT INTO vecs(chunk_id, vec) VALUES(?,?)", (cid, blob))
                    c.execute("INSERT OR REPLACE INTO embcache(hash, vec) VALUES(?,?)", (ch["hash"], blob))
        self._mat = None

    @staticmethod
    def _delete(c: sqlite3.Connection, call_id: str) -> None:
        ids = [r[0] for r in c.execute("SELECT id FROM chunks WHERE call_id=?", (call_id,))]
        for i in range(0, len(ids), 500):
            q = ",".join("?" * len(ids[i:i + 500]))
            c.execute(f"DELETE FROM fts WHERE rowid IN ({q})", ids[i:i + 500])
            c.execute(f"DELETE FROM vecs WHERE chunk_id IN ({q})", ids[i:i + 500])
        c.execute("DELETE FROM chunks WHERE call_id=?", (call_id,))
        c.execute("DELETE FROM calls WHERE call_id=?", (call_id,))

    def delete_call(self, call_id: str) -> None:
        """Privacidad: al eliminar una llamada desaparecen tambien sus fragmentos y vectores.
        (embcache se limpia aparte: guarda vectores por contenido, no por llamada; ver purge_cache)."""
        with self.lock, self.conn() as c:
            self._delete(c, call_id)
        self._mat = None
        self.bump()

    def purge_cache(self) -> int:
        """Quita de embcache los vectores que ya ningun fragmento usa (p. ej. de llamadas eliminadas)."""
        with self.lock, self.conn() as c:
            n = c.execute("DELETE FROM embcache WHERE hash NOT IN (SELECT hash FROM chunks)").rowcount
        return n

    def clear(self) -> None:
        with self.lock, self.conn() as c:
            for t in ("calls", "chunks", "fts", "vecs", "embcache"):
                c.execute(f"DELETE FROM {t}")
        self._mat = None
        self.bump()

    # ---------------------------------------------------------------- lectura
    def calls(self) -> list[dict]:
        with self.conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM calls")]
        for r in rows:
            r["pending"] = json.loads(r["pending"] or "[]")
            r["criteria"] = json.loads(r["criteria"] or "{}")
        return rows

    def stats(self) -> dict:
        with self.conn() as c:
            return {"calls": c.execute("SELECT COUNT(*) FROM calls").fetchone()[0],
                    "chunks": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                    "vectors": c.execute("SELECT COUNT(*) FROM vecs").fetchone()[0]}

    def chunks_by_ids(self, ids: list[int]) -> dict[int, dict]:
        out: dict[int, dict] = {}
        with self.conn() as c:
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                q = ",".join("?" * len(part))
                for r in c.execute(f"SELECT * FROM chunks WHERE id IN ({q})", part):
                    out[r["id"]] = dict(r)
        return out

    def call_chunks(self, call_id: str, kinds: tuple[str, ...]) -> list[dict]:
        q = ",".join("?" * len(kinds))
        with self.conn() as c:
            return [dict(r) for r in c.execute(f"SELECT * FROM chunks WHERE call_id=? AND kind IN ({q}) ORDER BY id", (call_id, *kinds))]

    def lexical(self, match: str, allowed: set[str] | None, limit: int) -> list[tuple[int, float]]:
        """(chunk_id, bm25) mejores primero. `allowed` = llamadas permitidas (None = todas)."""
        if not match:
            return []
        # se pide de mas y se filtra en Python: evita limites de variables de SQLite con muchas llamadas
        over = limit * 4 if allowed is not None else limit
        try:
            with self.conn() as c:
                rows = c.execute("SELECT f.rowid AS id, bm25(fts) AS s, c.call_id AS call_id FROM fts f JOIN chunks c ON c.id=f.rowid "
                                 "WHERE fts MATCH ? ORDER BY s LIMIT ?", (match, over)).fetchall()
        except sqlite3.OperationalError:    # consulta mal formada: sin resultados en vez de romper el chat
            return []
        out = [(r["id"], -r["s"]) for r in rows if allowed is None or r["call_id"] in allowed]
        return out[:limit]

    def _matrix(self):
        with self.lock:
            if self._mat is None:
                with self.conn() as c:
                    rows = c.execute("SELECT v.chunk_id AS id, c.call_id AS call_id, v.vec AS vec FROM vecs v JOIN chunks c ON c.id=v.chunk_id").fetchall()
                if not rows:
                    self._mat = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros((0, 1), np.float16))
                    self._call_names = []
                else:
                    names: dict[str, int] = {}
                    ids = np.array([r["id"] for r in rows], dtype=np.int64)
                    cidx = np.array([names.setdefault(r["call_id"], len(names)) for r in rows], dtype=np.int64)
                    mat = np.stack([np.frombuffer(r["vec"], dtype=np.float16) for r in rows])
                    self._mat, self._call_names = (ids, cidx, mat), list(names)
            return self._mat

    def dense(self, qvec: np.ndarray, allowed: set[str] | None, limit: int) -> list[tuple[int, float]]:
        """(chunk_id, coseno) mejores primero. Los vectores se guardan normalizados: producto punto = coseno."""
        ids, cidx, mat = self._matrix()
        if len(ids) == 0:
            return []
        if mat.shape[1] != len(qvec):     # modelo de embeddings distinto al indexado: no se mezcla
            return []
        mask = np.ones(len(ids), bool)
        if allowed is not None:
            ok = np.array([n in allowed for n in self._call_names], dtype=bool)
            mask = ok[cidx]
        if not mask.any():
            return []
        sims = mat[mask].astype(np.float32) @ qvec.astype(np.float32)
        sub = ids[mask]
        top = np.argsort(-sims)[:limit]
        return [(int(sub[i]), float(sims[i])) for i in top]
