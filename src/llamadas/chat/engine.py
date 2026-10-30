"""Asistente de consulta sobre las auditorias.

Ruta de cada pregunta (de la mas barata a la mas cara):
  1. cache            misma pregunta + mismos filtros + mismo indice  -> sin computo
  2. directo          conteos, tasas, promedios, rankings, listas y fichas -> codigo sobre datos estructurados, sin IA
  3. sin resultados   la busqueda no trae nada relevante                -> se dice, sin gastar IA
  4. IA con fragmentos  busqueda hibrida + presupuesto de tokens + LLM local, con citas [n] verificadas
  5. fragmentos       la IA no esta disponible (apagada, lote en curso, error) -> se muestran los fragmentos tal cual
"""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from datetime import date
from typing import Callable, Iterator

from rapidfuzz import fuzz

from ..config import Settings, load_settings
from ..llm import make_llm
from ..textutil import normalize
from . import analytics, retrieve, router
from .chunks import mmss
from .embed import LlamaEmbedder
from .indexer import Indexer
from .store import Store

MAX_QUESTION = 600
SYSTEM = ("Eres el asistente de un auditor de calidad de llamadas de un centro de atención. Respondes en español, breve y directo "
          "(máximo 6 oraciones o una lista corta). Usa SOLO los FRAGMENTOS entregados: cada uno lleva un número entre corchetes; "
          "cita el número de cada afirmación, por ejemplo [2]. Si los fragmentos no bastan para responder, dilo claramente y no "
          "inventes. No supongas hechos que no estén escritos. Los números largos están enmascarados a propósito. "
          "Criterios de la matriz: P1 Saludo, P2 Nombre del cliente, V1 Documento, V2 Valida datos, G1 Control de espera (menos de 60 s), "
          "G2 Agilidad, C1 Escucha activa, C2 Tono y lenguaje, Z1 Confirma cita, Z2 Despedida.")
KIND_ES = {"resumen": "resumen", "criterio": "criterio", "ventana": "transcripción", "observacion": "observación del auditor", "e1": "posible error crítico"}


class Generator:
    """LLM del chat. Local: se enciende al primer uso y se apaga solo tras un rato sin uso (libera 2-7 GB de RAM).
    Externo (Groq/Gemini): no consume RAM ni CPU de este equipo, asi que tampoco espera a que termine un lote de analisis."""

    def __init__(self, settings: Settings, server=None, engine: str | None = None):
        self.server = server or make_llm(settings, settings["chat"]["mode"], engine)
        self.remote = getattr(self.server, "provider", None) is not None
        self.label = "externa" if self.remote else "local"
        self._last = 0.0

    def available(self) -> bool:
        return self.server.available()

    def start(self) -> None:
        self.server.start()
        self._last = time.time()

    def stream(self, system: str, user: str, max_tokens: int) -> Iterator[str]:
        for t in self.server.chat_stream(system, user, max_tokens):
            self._last = time.time()
            yield t

    def reap(self, idle_s: float) -> None:
        if getattr(self.server, "proc", None) and time.time() - self._last > idle_s:
            self.server.stop()


class ChatEngine:
    def __init__(self, settings: Settings | None = None, *, store: Store | None = None, embedder="auto", generator=None,
                 busy: Callable[[], bool] = lambda: False, today: Callable[[], date] = date.today, include_synthetic: bool = False):
        self.s = settings or load_settings()
        self.cfg = self.s["chat"]
        self.store = store or Store(self.s)
        self.embedder = LlamaEmbedder(self.s) if embedder == "auto" else embedder
        self.gen = generator or Generator(self.s)
        self._gens: dict[str, Generator] = {}      # "local" / "externa", creados al primer uso
        self.busy = busy
        self.today = today
        self.indexer = Indexer(self.s, self.store, self.embedder, include_synthetic)
        self.cache: OrderedDict[tuple, dict] = OrderedDict()
        self.gen_lock = threading.Lock()
        self._checked = 0.0
        self._bg: threading.Thread | None = None
        self._reaper: threading.Thread | None = None

    # ------------------------------------------------------------------ ciclo de vida
    def start_background(self) -> None:
        """Apaga la IA y los embeddings tras `idle_stop_min` sin uso."""
        if self._reaper:
            return
        idle = self.cfg["idle_stop_min"] * 60

        def loop():
            while True:
                time.sleep(30)
                for g in (self.gen, *self._gens.values()):
                    g.reap(idle)
                if self.embedder is not None:
                    self.embedder.reap(idle)
        self._reaper = threading.Thread(target=loop, daemon=True)
        self._reaper.start()

    def ensure_fresh(self, force: bool = False) -> None:
        """Lanza (en segundo plano) la sincronizacion del indice si hay cambios. Barato: solo mira fechas de archivos."""
        if self._bg and self._bg.is_alive():
            return
        if not force and time.time() - self._checked < 5:
            return
        self._checked = time.time()
        if not force and not self.indexer.is_stale():
            return
        self._bg = threading.Thread(target=lambda: self.indexer.sync(allow_embed=not self.busy()), daemon=True)
        self._bg.start()

    def sync_now(self, rebuild: bool = False) -> dict:
        return self.indexer.sync(rebuild=rebuild, allow_embed=not self.busy())

    def forget(self, call_id: str) -> None:
        self.store.delete_call(call_id)
        self.store.purge_cache()
        self.cache.clear()

    def generator(self, engine: str | None = None) -> Generator:
        """IA que responde: "local" | "externa" a pedido del usuario; sin pedido, la configurada (.env)."""
        if engine not in ("local", "externa"):
            return self.gen
        if engine not in self._gens:
            self._gens[engine] = Generator(self.s, engine=engine)
        return self._gens[engine]

    def status(self, engine: str | None = None) -> dict:
        st = self.store.stats()
        emb = self.embedder is not None and self.embedder.available()
        gen = self.generator(engine)
        return {**st, "indexing": dict(self.indexer.progress), "vectors_enabled": emb, "llm_available": gen.available(),
                "busy_batch": bool(self.busy()) and not gen.remote, "engine": gen.label,
                "model": getattr(gen.server, "model_id", None) or getattr(getattr(gen.server, "model", None), "name", None)}

    # ------------------------------------------------------------------ pregunta
    def ask(self, question: str, ctx: dict | None = None, history: list[dict] | None = None, debug: bool = False,
            engine: str | None = None) -> dict:
        """Version no incremental (CLI y pruebas): junta los eventos del flujo en una sola respuesta."""
        out = {"answer": "", "sources": [], "warnings": [], "route": "", "ctx": {}, "stats": {}, "filters": []}
        for ev in self.ask_stream(question, ctx, history, debug, engine):
            t = ev["type"]
            if t == "token":
                out["answer"] += ev["text"]
            elif t == "final_text":
                out["answer"] = ev["text"]
            elif t == "route":
                out["route"], out["filters"] = ev["route"], ev["filters"]
            elif t == "sources":
                out["sources"] = ev["sources"]
            elif t == "done":
                out.update(ctx=ev["ctx"], stats=ev["stats"], warnings=ev["warnings"])
            elif t == "error":
                out["error"] = ev["message"]
        return out

    def ask_stream(self, question: str, ctx: dict | None = None, history: list[dict] | None = None, debug: bool = False,
                   engine: str | None = None) -> Iterator[dict]:
        t0 = time.time()
        gen = self.generator(engine)
        question = (question or "").strip()[:MAX_QUESTION]
        if not question:
            yield {"type": "error", "message": "Escriba una pregunta."}
            return
        self.ensure_fresh()
        if self.store.stats()["calls"] == 0:
            prog = self.indexer.progress
            msg = (f"Estoy preparando el índice ({prog['done']} de {prog['total']} llamadas). Intente de nuevo en un momento."
                   if prog["running"] else "Todavía no hay llamadas analizadas. Cargue y analice audios primero.")
            yield {"type": "route", "route": "vacio", "filters": []}
            yield {"type": "token", "text": msg}
            yield {"type": "sources", "sources": []}
            yield {"type": "done", "ctx": ctx or {}, "stats": {"ms": 0}, "warnings": []}
            return

        rows = self.store.calls()
        agents = sorted({r["agent"] for r in rows if r["agent"]} | set(self.s.agents))
        p = router.parse(question, today=self.today(), known_ids=[r["call_id"] for r in rows], agents=agents,
                         prev=(ctx or {}).get("filters"))
        base_ctx = {"filters": p.filters.to_dict()}
        key = (self.store.version(), normalize(question), repr(p.filters.to_dict()), p.intent)
        if key in self.cache and not debug:
            self.cache.move_to_end(key)
            c = self.cache[key]
            yield {"type": "route", "route": "cache", "filters": p.filters.describe()}
            yield {"type": "token", "text": c["answer"]}
            yield {"type": "sources", "sources": c["sources"]}
            yield {"type": "done", "ctx": base_ctx, "stats": {"ms": int((time.time() - t0) * 1000), "cached": True}, "warnings": c["warnings"]}
            return

        yield {"type": "route", "route": "directo" if p.intent != "semantic" else "busqueda", "filters": p.filters.describe()}

        direct = None
        if p.intent in ("aggregate", "list"):
            direct = analytics.answer(p, rows)
        elif p.intent == "card":
            cid = p.filters.call_ids[0]
            ch = self.store.call_chunks(cid, ("resumen", "criterio"))
            text = (ch[0]["ctx"] + "\n\n" if ch else "") + "\n".join(
                c["body"] if c["kind"] == "resumen" else "- " + c["body"].split("\n")[0] for c in ch)
            direct = analytics.card(cid, rows, text)
        if direct is not None:
            srcs = [{"n": i + 1, "call_id": c, "kind": "ficha", "ctx": "", "snippet": "", "cited": True} for i, c in enumerate(direct["call_ids"][:10])]
            yield {"type": "token", "text": direct["text"]}
            yield {"type": "sources", "sources": srcs}
            self._remember(key, direct["text"], srcs, [])
            yield {"type": "done", "ctx": base_ctx, "stats": {"ms": int((time.time() - t0) * 1000), "intent": p.intent, "metric": p.metric}, "warnings": []}
            return

        # ---- busqueda semantica / de palabras
        dbg: dict = {}
        allowed = analytics.allowed_ids(rows, p.filters)
        embedder = self.embedder if (self.embedder is not None and self.embedder.available() and self.store.stats()["vectors"]) else None
        hits = retrieve.search(self.store, p, allowed, embedder, self.cfg, dbg)
        if not hits:
            scope = ("; ".join(p.filters.describe()) or "todas las llamadas")
            yield {"type": "token", "text": f"No encontré información relacionada con esa pregunta en {scope}. Pruebe con otras palabras o amplíe los filtros."}
            yield {"type": "sources", "sources": []}
            yield {"type": "done", "ctx": base_ctx, "stats": {"ms": int((time.time() - t0) * 1000), "retrieval": dbg}, "warnings": []}
            return
        sources = [self._source(i + 1, h) for i, h in enumerate(hits)]
        user = self._prompt(p, hits, history if p.follow_up else None)
        stats = {"prompt_tokens_est": retrieve.est_tokens(SYSTEM + user), "fragments": len(hits), "retrieval": dbg,
                 "vectors": embedder is not None}

        reason = self._llm_unavailable(gen)
        if reason is None and not self.gen_lock.acquire(blocking=False):
            reason = "ya hay otra consulta en curso"
        text = ""
        if reason is None:
            try:
                gen.start()
                for tok in gen.stream(SYSTEM, user, self.cfg["max_answer_tokens"]):
                    text += tok
                    yield {"type": "token", "text": tok}
                if not text.strip():
                    raise RuntimeError("la IA no devolvió texto")
            except Exception as e:                     # la IA fallo a mitad: se degrada a fragmentos
                reason = f"la IA {gen.label} falló ({e})"
                if text.strip():                       # ya salio texto parcial: se avisa al final, no se mezcla con los fragmentos
                    yield {"type": "final_text", "text": text + f"\n\n_(La respuesta se cortó: {reason}.)_"}
                    yield {"type": "sources", "sources": sources}
                    yield {"type": "done", "ctx": base_ctx, "stats": {**stats, "ms": int((time.time() - t0) * 1000), "degraded": reason}, "warnings": []}
                    return
            finally:
                self.gen_lock.release()
        if reason is not None:
            note = f"_La IA {gen.label} no está disponible ({reason}). Estos son los fragmentos más relevantes:_\n\n"
            body = "\n\n".join(f"**[{s['n']}]** {s['ctx']}\n> {s['snippet']}" for s in sources)
            yield {"type": "token", "text": note + body}
            yield {"type": "sources", "sources": sources}
            yield {"type": "done", "ctx": base_ctx, "stats": {**stats, "ms": int((time.time() - t0) * 1000), "degraded": reason}, "warnings": []}
            return

        clean, warnings, cited = self.verify(text, hits)
        if clean != text:
            yield {"type": "final_text", "text": clean}
        for s in sources:
            s["cited"] = s["n"] in cited
        yield {"type": "sources", "sources": sources}
        stats.update(ms=int((time.time() - t0) * 1000), completion_tokens_est=retrieve.est_tokens(clean))
        self._remember(key, clean, sources, warnings)
        yield {"type": "done", "ctx": base_ctx, "stats": stats, "warnings": warnings}

    # ------------------------------------------------------------------ piezas
    def _llm_unavailable(self, gen: Generator | None = None) -> str | None:
        gen = gen or self.gen
        if self.busy() and not gen.remote:          # la IA externa no usa la CPU de este equipo: no necesita esperar
            return "hay un análisis de llamadas en curso; la CPU se reserva para él"
        if not gen.available():
            return "falta la clave de la IA externa (Instalar.bat)" if gen.remote else "el modelo no está instalado"
        return None

    def _remember(self, key: tuple, answer: str, sources: list, warnings: list) -> None:
        self.cache[key] = {"answer": answer, "sources": sources, "warnings": warnings}
        while len(self.cache) > self.cfg["cache_size"]:
            self.cache.popitem(last=False)

    @staticmethod
    def _source(n: int, h: retrieve.Hit) -> dict:
        snippet = h.body if len(h.body) <= 320 else h.body[:317] + "…"
        label = KIND_ES.get(h.kind, h.kind) + (f" {h.criterion}" if h.criterion else "")
        return {"n": n, "call_id": h.call_id, "kind": h.kind, "criterion": h.criterion, "ctx": f"{h.ctx} · {label}" + (f" · {mmss(h.t0)}" if h.t0 is not None else ""),
                "snippet": snippet, "t0": h.t0, "turn0": h.turn0, "via": h.via, "cited": False}

    def _prompt(self, p: router.Parsed, hits: list[retrieve.Hit], history: list[dict] | None) -> str:
        frags = []
        for i, h in enumerate(hits, 1):
            label = KIND_ES.get(h.kind, h.kind) + (f" {h.criterion}" if h.criterion else "")
            frags.append(f"[{i}] {h.ctx} · {label}" + (f" · {mmss(h.t0)}" if h.t0 is not None else "") + f"\n{h.body}")
        parts = ["FRAGMENTOS:\n" + "\n\n".join(frags)]
        if history:
            lim = self.cfg["history_chars"]
            parts.append("CONVERSACIÓN PREVIA:\n" + "\n".join(f"P: {h.get('q', '')[:lim]}\nR: {h.get('a', '')[:lim]}" for h in history[-2:]))
        parts.append(f"PREGUNTA: {p.text}")
        return "\n\n".join(parts)

    @staticmethod
    def verify(text: str, hits: list[retrieve.Hit]) -> tuple[str, list[str], set[int]]:
        """Revisa la respuesta: citas [n] validas y frases entre comillas que existan en los fragmentos."""
        n_max, warnings = len(hits), []
        cited: set[int] = set()

        def fix(m: re.Match) -> str:
            n = int(m.group(1))
            if 1 <= n <= n_max:
                cited.add(n)
                return m.group(0)
            warnings.append(f"La respuesta citó el fragmento [{n}], que no existe; se quitó la cita.")
            return ""
        clean = re.sub(r"\[(\d{1,3})\]", fix, text)
        body = normalize(" ".join(h.body for h in hits))
        for q in re.findall(r"[«\"“]([^»\"”]{12,})[»\"”]", clean):
            qn = normalize(q)
            if len(qn.split()) >= 4 and qn not in body and fuzz.partial_ratio(qn, body) < 88:
                warnings.append(f"Frase no encontrada literalmente en los fragmentos: «{q[:80]}»")
        if not cited and "no encontr" not in normalize(clean) and len(clean) > 40:
            warnings.append("La respuesta no cita ningún fragmento: verifíquela con las fuentes.")
        return clean, warnings, cited
