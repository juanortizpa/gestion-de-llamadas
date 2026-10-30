"""Busqueda hibrida: palabras (FTS5/BM25) + semantica (vectores), fusion RRF, diversidad y presupuesto de tokens.

El presupuesto de tokens es la optimizacion central: la CPU lee ~40 tok/s, asi que cada fragmento de mas cuesta segundos.
Se entregan pocos fragmentos, de llamadas distintas, que no se solapan y que caben en `context_tokens`.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..textutil import normalize
from .router import STOP, Parsed
from .store import Store

RRF_K = 60


def est_tokens(text: str) -> int:
    """Estimacion barata (~3,6 caracteres por token en espanol). No es el tokenizador real."""
    return math.ceil(len(text) / 3.6)


def stem_prefix(tok: str) -> str:
    """Raiz ligera para el espanol: llamadas/llamada/llamo -> prefijo comun. Los numeros y palabras cortas van exactos."""
    n = len(tok)
    if tok.isdigit() or n <= 4:
        return tok
    k = max(4, n - 2)
    return tok[:k] + "*" if k < n else tok


def fts_text(chunk: dict) -> str:
    return normalize(chunk["ctx"] + " " + chunk["body"])


def match_query(question: str, max_terms: int = 12) -> str:
    seen, terms = set(), []
    for t in normalize(question).split():
        if t in STOP or len(t) < 3 and not t.isdigit():
            continue
        s = stem_prefix(t)
        if s not in seen:
            seen.add(s)
            terms.append(f'"{s[:-1]}"*' if s.endswith("*") else f'"{s}"')
    return " OR ".join(terms[:max_terms])


@dataclass
class Hit:
    id: int
    call_id: str
    kind: str
    criterion: str | None
    ctx: str
    body: str
    t0: float | None
    t1: float | None
    turn0: int | None
    turn1: int | None
    score: float
    via: str                    # lex | vec | lex+vec


def _overlaps(a: Hit, b: Hit) -> bool:
    if a.call_id != b.call_id or a.kind != "ventana" or b.kind != "ventana":
        return False
    return a.turn0 is not None and b.turn0 is not None and not (a.turn1 < b.turn0 or b.turn1 < a.turn0)


def search(store: Store, p: Parsed, allowed: set[str] | None, embedder, cfg: dict, debug: dict | None = None) -> list[Hit]:
    lim = 40
    lex = store.lexical(match_query(p.text), allowed, lim)
    dense: list[tuple[int, float]] = []
    if embedder is not None:
        try:
            qv = embedder.embed_query(p.text)
            dense = [(i, s) for i, s in store.dense(qv, allowed, lim) if s >= cfg["min_cosine"]]
        except Exception as e:           # servidor de embeddings caido: se sigue solo con palabras
            if debug is not None:
                debug["embed_error"] = str(e)
    if debug is not None:
        debug.update(lex=len(lex), dense=len(dense), dense_top=dense[:3])
    if not lex and not dense:
        return []
    score: dict[int, float] = {}
    via: dict[int, set[str]] = {}
    for rank, (cid, _) in enumerate(lex):
        score[cid] = score.get(cid, 0) + 1 / (RRF_K + rank)
        via.setdefault(cid, set()).add("lex")
    for rank, (cid, _) in enumerate(dense):
        score[cid] = score.get(cid, 0) + 1 / (RRF_K + rank)
        via.setdefault(cid, set()).add("vec")
    chunks = store.chunks_by_ids(list(score))
    crit = set(p.filters.criteria)
    wants_obs = bool(re.search(r"observaci|plan de accion|anoto|comentari", normalize(p.text)))
    for cid, ch in chunks.items():
        if ch["criterion"] in crit:
            score[cid] *= 1.4
        if ch["kind"] == "observacion" and wants_obs:
            score[cid] *= 1.4
        if ch["kind"] == "resumen" and not p.filters.call_ids:
            score[cid] *= 0.85           # el resumen es util pero no debe desplazar a la evidencia textual
    ordered = sorted(score, key=lambda c: -score[c])
    picked: list[Hit] = []
    per_call: dict[str, int] = {}
    budget = cfg["context_tokens"]
    for cid in ordered:
        ch = chunks[cid]
        if len(picked) >= cfg["top_k"]:
            break
        if per_call.get(ch["call_id"], 0) >= (cfg["max_per_call"] if not p.filters.call_ids else cfg["top_k"]):
            continue
        h = Hit(id=cid, call_id=ch["call_id"], kind=ch["kind"], criterion=ch["criterion"], ctx=ch["ctx"], body=ch["body"], t0=ch["t0"],
                t1=ch["t1"], turn0=ch["turn0"], turn1=ch["turn1"], score=score[cid], via="+".join(sorted(via[cid])))
        if any(_overlaps(h, o) for o in picked):
            continue
        cost = est_tokens(h.ctx + h.body) + 12
        if cost > budget:
            if picked:
                continue                  # no cabe: se prueba un fragmento mas corto
            h.body = h.body[: int((budget - 12) * 3.6)]       # el primero siempre entra, recortado si es enorme
            cost = budget
        budget -= cost
        per_call[h.call_id] = per_call.get(h.call_id, 0) + 1
        picked.append(h)
    return picked
