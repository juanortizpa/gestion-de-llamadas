"""Mide el sistema contra los casos dorados sinteticos de eval/casos.py y deja un CSV con la fecha.

  python eval/run_eval.py                         # auditoria + RAG + Asistente con la IA configurada en .env
  python eval/run_eval.py --suite rag             # solo la busqueda (no gasta IA)
  python eval/run_eval.py --engine local --mode preciso --reps 1
  python eval/run_eval.py --engine ninguna        # solo reglas y busqueda, sin llamar a ninguna IA

Salida (eval/resultados/):
  AAAA-MM-DD_HHMM_<motor>_<modelo>_detalle.csv   una fila por llamada a la IA / criterio / pregunta
  resumen.csv                           una fila por cifra (mediana, n, fecha): se va acumulando entre corridas
  linea_base.json                       la ultima corrida de cada motor:modelo, con las cifras que van en docs/decisiones.md
Todo se calcula en un directorio temporal: no toca data/ ni las llamadas reales.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import re
import sys
import tempfile
import time
import tomllib
from datetime import date, datetime
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

from casos import AUDIT_CASES, CODES, RAG_CORPUS, RAG_QUESTIONS, build  # noqa: E402

from llamadas.audit import audit_transcript, save_audit  # noqa: E402
from llamadas.auditor import classify_completion, pending_items, resolve_with_llm  # noqa: E402
from llamadas.chat import analytics, retrieve, router  # noqa: E402
from llamadas.chat.engine import SYSTEM as CHAT_SYSTEM, ChatEngine, Generator  # noqa: E402
from llamadas.config import load_settings  # noqa: E402
from llamadas.llm import LlamaServer, RemoteLLM, external_provider  # noqa: E402
from llamadas.pipeline import save_result  # noqa: E402
from llamadas.review import save_review  # noqa: E402
from llamadas.textutil import normalize  # noqa: E402

OUT = HERE / "resultados"
FIELDS = ["fecha", "hora", "suite", "motor", "modelo", "caso", "rep", "tipo", "latencia_s", "tokens_in", "tokens_out", "costo_usd",
          "reintentos", "esperado", "obtenido", "correcto", "nota"]
HOY = date(2026, 10, 13)       # fecha fija para que "esta semana" etc. no cambien la medicion


def med(xs, nd=3):
    xs = [x for x in xs if x is not None]
    return round(median(xs), nd) if xs else None


# --------------------------------------------------------------------------- IA medida
class Meter:
    """Envuelve el cliente de IA: mide cada llamada y reintenta con espera si el proveedor responde 429 (limite de peticiones).
    Los 429 y los reintentos quedan contados: son parte del resultado, no se esconden."""

    def __init__(self, inner, price: dict, retries: int = 3):
        self.inner, self.price, self.retries = inner, price, retries
        self.calls: list[dict] = []
        self.rate_limited = 0
        self.waited = 0.0          # segundos esperando por 429: se descuentan de la latencia del Asistente (se reportan aparte)
        self.tag = ""

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def cost(self, pt, ct) -> float:
        return ((pt or 0) * self.price.get("input_per_m", 0) + (ct or 0) * self.price.get("output_per_m", 0)) / 1e6

    def _wait(self, attempt: int, e: Exception) -> bool:
        if "429" in str(e) and "cuota" not in str(e) and attempt < self.retries:
            self.rate_limited += 1
            pausa = 8 * 2 ** attempt
            time.sleep(pausa)
            self.waited += pausa
            return True
        return False

    def chat_json(self, system, user, schema):
        for attempt in range(self.retries + 1):
            try:
                data, meta = self.inner.chat_json(system, user, schema)
            except RuntimeError as e:
                if self._wait(attempt, e):
                    continue
                raise
            self.calls.append({"tag": self.tag, "secs": meta.get("secs"), "pt": meta.get("prompt_tokens"), "ct": meta.get("completion_tokens"),
                               "est": False, "retries": attempt})
            return data, meta

    def chat_stream(self, system, user, max_tokens=350, temperature=0.1):
        for attempt in range(self.retries + 1):
            t0, first, out = time.time(), None, []
            try:
                for tok in self.inner.chat_stream(system, user, max_tokens, temperature):
                    if first is None:
                        first = time.time() - t0
                    out.append(tok)
                    yield tok
            except RuntimeError as e:
                if first is None and self._wait(attempt, e):
                    continue
                raise
            self.calls.append({"tag": self.tag, "secs": round(time.time() - t0, 2), "ttft": first, "pt": retrieve.est_tokens(system + user),
                               "ct": retrieve.est_tokens("".join(out)), "est": True, "retries": attempt})
            return


def make_ia(S, engine: str, mode: str):
    """(cliente, motor, modelo) o None si se pidio medir sin IA / no hay clave / no hay modelo."""
    if engine == "ninguna":
        return None
    if engine == "local":
        srv = LlamaServer(S, mode)
        return (srv, "local", srv.model.name) if srv.available() else None
    prov = external_provider(S)
    if prov is None:
        return None
    srv = RemoteLLM(S, prov, mode)
    return srv, prov, srv.model_id


def prices(motor: str, modelo: str) -> dict:
    t = tomllib.loads((HERE / "precios.toml").read_text(encoding="utf-8"))
    return t.get(motor, {}).get(modelo, {"input_per_m": 0.0, "output_per_m": 0.0})


# --------------------------------------------------------------------------- suite 1: auditoria
def run_audit(S, meter: Meter | None, reps: int, pause: float, rows: list, ctx: dict) -> dict:
    per_rep = []
    for rep in range(1, reps + 1):
        tot = ok = pend = 0
        ia_tot = ia_ok = cierre_tot = cierre_ok = 0
        for caso in AUDIT_CASES:
            tr = caso.transcript()
            au = audit_transcript(tr, S)
            fallo_ia = ""
            if meter and au.get("criteria") and not au.get("auto_discard"):
                meter.tag = caso.id
                try:
                    classify_completion(au, tr, meter, S)
                    if not au.get("auto_discard"):
                        resolve_with_llm(au, tr, meter, S)
                except Exception as e:                      # igual que jobs.py: la IA falla, quedan pendientes
                    fallo_ia = str(e)[:120]
                if pause:
                    time.sleep(pause)
            base = {**ctx, "suite": "auditoria", "caso": caso.id, "rep": rep}
            if fallo_ia:
                rows.append({**base, "tipo": "fallo_ia", "nota": fallo_ia, "correcto": 0})
            # --- cierre de la llamada
            estado = (au.get("completion") or {}).get("estado") or ("finalizada" if not au.get("auto_discard") else (au["auto_discard"]["value"]))
            desc = (au.get("auto_discard") or {}).get("value")
            obtenido = desc or estado
            if meter:                                       # el cierre solo es medible si la IA pudo opinar
                cierre_tot += 1
                good = obtenido == caso.cierre
                cierre_ok += good
                rows.append({**base, "tipo": "cierre", "esperado": caso.cierre, "obtenido": obtenido, "correcto": int(good),
                             "nota": (au.get("completion") or {}).get("nota", "")})
            # --- criterios (solo llamadas que deben auditarse)
            if caso.cierre == "finalizada" and au.get("criteria"):
                for c in CODES:
                    got = au["criteria"][c]["score"]
                    tot += 1
                    pend += got is None
                    good = got == caso.esperado[c]
                    ok += good
                    if got is not None or c in caso.falla or meter:
                        rows.append({**base, "tipo": "criterio", "nota": c, "esperado": caso.esperado[c], "obtenido": "pendiente" if got is None else got,
                                     "correcto": int(good)})
            # --- sub-checks que respondio la IA (solo en llamadas que deben auditarse: en una cortada/incompleta no hay "esperado")
            for x in ((au.get("llm") or {}).get("log", []) if caso.cierre == "finalizada" else []):
                code, sid = x["id"].split(".", 1)
                exp = caso.sub.get(x["id"], caso.esperado.get(code) == 1)
                pred = x["result"] == "si_verificado"
                ia_tot += 1
                ia_ok += pred == exp
                rows.append({**base, "tipo": "subcheck_ia", "nota": x["id"], "esperado": exp, "obtenido": x["result"], "correcto": int(pred == exp)})
        per_rep.append({"acierto_global": ok / tot if tot else None, "pendientes": pend / tot if tot else None,
                        "acierto_ia": ia_ok / ia_tot if ia_tot else None, "acierto_cierre": cierre_ok / cierre_tot if cierre_tot else None})
    return {k: med([r[k] for r in per_rep]) for k in per_rep[0]}


# --------------------------------------------------------------------------- suite 2 y 3: RAG y Asistente
class _SinIA:
    """Generador que nunca esta disponible: el Asistente devuelve los fragmentos tal cual (sirve para medir solo la busqueda)."""
    remote = False
    label = "local"
    server = None

    def available(self):
        return False

    def start(self):
        pass

    def reap(self, idle_s):
        pass


def build_index(S0):
    tmp = Path(tempfile.mkdtemp(prefix="eval_rag_"))
    S = dataclasses.replace(S0, raw={**S0.raw, "paths": {**S0.raw["paths"], "data_dir": str(tmp)}}, agents=[])
    words = 0
    for c in RAG_CORPUS:
        tr = build(c.turns)
        tr["call"].update(call_id=c.id, received_date=c.day, received_time="140300", queue="800197")
        save_result(tr, S)
        save_audit(audit_transcript(tr, S), S)
        save_review(c.id, {"agent": c.agent, "reviewed": True}, S)
        words += sum(len(t["text"].split()) for t in tr["turns"])
    return S, words


def run_rag(S0, rows: list, ctx: dict) -> tuple[dict, ChatEngine, Settings]:
    S, _ = build_index(S0)
    eng = ChatEngine(S, generator=_SinIA(), today=lambda: HOY, include_synthetic=True)
    stats = eng.sync_now()
    vec = eng.embedder is not None and eng.embedder.available() and eng.store.stats()["vectors"] > 0
    calls_rows = eng.store.calls()
    agents = sorted({r["agent"] for r in calls_rows if r["agent"]})
    ids = [r["call_id"] for r in calls_rows]
    res = {"directa": [], "parafraseada": []}
    full_tokens = sum(retrieve.est_tokens(" ".join(t["text"] for t in build(c.turns)["turns"])) for c in RAG_CORPUS)
    ctx_tokens = []
    for q in RAG_QUESTIONS:
        p = router.parse(q.q, today=HOY, known_ids=ids, agents=agents)
        t0 = time.time()
        hits = []
        if p.intent == "semantic":
            allowed = analytics.allowed_ids(calls_rows, p.filters)
            hits = retrieve.search(eng.store, p, allowed, eng.embedder if vec else None, eng.cfg, {})
        ms = (time.time() - t0) * 1000
        rank_call = next((i for i, h in enumerate(hits, 1) if h.call_id == q.call), None)
        rank_frag = next((i for i, h in enumerate(hits, 1) if h.call_id == q.call and q.evidencia in normalize(h.body)), None)
        ctx_tokens.append(retrieve.est_tokens(CHAT_SYSTEM + eng._prompt(p, hits, None)) if hits else 0)
        r = {"call": rank_call, "frag": rank_frag}
        res[q.tipo].append(r)
        rows.append({**ctx, "suite": "rag", "caso": q.call, "tipo": "rag_" + q.tipo, "latencia_s": round(ms / 1000, 4),
                     "esperado": q.evidencia, "obtenido": f"llamada@{rank_call} fragmento@{rank_frag}" + ("" if p.intent == "semantic" else f" (ruta {p.intent})"),
                     "correcto": int(rank_frag is not None), "nota": q.q})

    def hit(rs, key, k):
        return sum(1 for r in rs if r[key] is not None and r[key] <= k) / len(rs) if rs else None

    allr = res["directa"] + res["parafraseada"]
    out = {"vectores": vec, "fragmentos_indexados": eng.store.stats()["chunks"], "llamadas": len(RAG_CORPUS), "preguntas": len(allr),
           "hit1_llamada": hit(allr, "call", 1), "hit3_llamada": hit(allr, "call", 3), "hit6_llamada": hit(allr, "call", 6),
           "hit1_fragmento": hit(allr, "frag", 1), "hit3_fragmento": hit(allr, "frag", 3), "hit6_fragmento": hit(allr, "frag", 6),
           "mrr_fragmento": sum(1 / r["frag"] for r in allr if r["frag"]) / len(allr),
           "hit6_fragmento_directa": hit(res["directa"], "frag", 6), "hit6_fragmento_parafraseada": hit(res["parafraseada"], "frag", 6),
           "tokens_contexto_con_rag_mediana": med(ctx_tokens), "tokens_todo_el_corpus": full_tokens,
           "tokens_por_transcripcion_media": round(full_tokens / len(RAG_CORPUS))}
    out["reduccion_tokens_pct"] = round(100 * (1 - out["tokens_contexto_con_rag_mediana"] / full_tokens), 1)
    return out, eng, S


def run_asistente(eng: ChatEngine, S, meter: Meter, n: int, pause: float, rows: list, ctx: dict) -> dict:
    eng.gen = Generator(S, server=meter)
    eng.cache.clear()
    sem, directo = [], []
    qs = [q for q in RAG_QUESTIONS if q.tipo == "directa"][: n] + [q for q in RAG_QUESTIONS if q.tipo == "parafraseada"][: max(0, n // 2)]
    for q in qs:
        meter.tag = "asistente"
        w0 = meter.waited
        t0, ttft, text, st, srcs, warns = time.time(), None, "", {}, [], []
        for ev in eng.ask_stream(q.q):
            if ev["type"] == "token" and ttft is None:
                ttft = time.time() - t0
            if ev["type"] == "token":
                text += ev["text"]
            elif ev["type"] == "sources":
                srcs = ev["sources"]
            elif ev["type"] == "done":
                st, warns = ev["stats"], ev["warnings"]
        espera = meter.waited - w0
        total = time.time() - t0 - espera
        ttft = ttft - espera if ttft is not None else None
        cited = [s["call_id"] for s in srcs if s.get("cited")]
        fundada = q.call in cited
        # el producto solo reconoce citas "[n]"; algunos modelos escriben "【n】": se cuenta aparte para no mezclar modelo y verificador
        marcadas = {srcs[int(n) - 1]["call_id"] for n in re.findall(r"[\[【](\d{1,2})[\]】]", text) if 1 <= int(n) <= len(srcs)}
        degr = st.get("degraded")
        r = {"total": total, "ttft": ttft, "espera": espera, "marcada": q.call in marcadas, "pt": st.get("prompt_tokens_est"), "ct": st.get("completion_tokens_est"), "fundada": fundada, "degr": degr}
        if not degr:
            sem.append(r)
        rows.append({**ctx, "suite": "asistente", "caso": q.call, "tipo": "asistente_ia", "latencia_s": round(total, 2), "tokens_in": r["pt"],
                     "tokens_out": r["ct"], "costo_usd": round(meter.cost(r["pt"], r["ct"]), 6), "esperado": q.call, "obtenido": ",".join(sorted(set(cited))),
                     "correcto": int(fundada), "reintentos": int(espera > 0), "nota": ("IA no disponible: " + degr) if degr else
                     (f"primer token {ttft:.1f}s" if ttft else "") + (f"; sin contar {espera:.0f}s de espera por límite 429" if espera else "")})
        if pause:
            time.sleep(pause)
    for q in ["¿Cuántas llamadas hubo en octubre?", "¿Qué asesor tiene la nota promedio más baja?", "Dame las llamadas de Laura Gómez"]:
        t0 = time.time()
        ev = list(eng.ask_stream(q))
        route = next((e["route"] for e in ev if e["type"] == "route"), "")
        directo.append(time.time() - t0)
        rows.append({**ctx, "suite": "asistente", "caso": "-", "tipo": "asistente_directo", "latencia_s": round(directo[-1], 4), "nota": f"{q} -> {route}"})
    return {"preguntas_con_ia": len(sem), "preguntas_fallidas": len(qs) - len(sem),
            "latencia_total_mediana_s": med([r["total"] for r in sem]), "primer_token_mediana_s": med([r["ttft"] for r in sem]),
            "preguntas_con_espera_429": sum(1 for r in sem if r["espera"]), "espera_429_total_s": round(sum(r["espera"] for r in sem)),
            "tokens_entrada_est_mediana": med([r["pt"] for r in sem]), "tokens_salida_est_mediana": med([r["ct"] for r in sem]),
            "costo_por_pregunta_usd_mediana": med([meter.cost(r["pt"], r["ct"]) for r in sem], 6),
            "respuestas_fundadas_pct": round(100 * sum(r["fundada"] for r in sem) / len(sem), 1) if sem else None,
            "respuestas_con_cita_correcta_cualquier_formato_pct": round(100 * sum(r["marcada"] for r in sem) / len(sem), 1) if sem else None,
            "latencia_directo_mediana_ms": round(1000 * median(directo), 1)}


# --------------------------------------------------------------------------- salida
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", default="todo", choices=["todo", "auditoria", "rag", "asistente"])
    ap.add_argument("--engine", default="externa", choices=["externa", "local", "ninguna"], help="IA que se mide (externa = la de .env)")
    ap.add_argument("--mode", default="rapido", choices=["rapido", "preciso"], help="modelo local")
    ap.add_argument("--reps", type=int, default=3, help="repeticiones de la suite de auditoria (para la mediana)")
    ap.add_argument("--preguntas", type=int, default=8, help="preguntas abiertas que se hacen al Asistente con IA")
    ap.add_argument("--pause", type=float, default=0.0, help="segundos de espera entre casos (limites de peticiones)")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    S = load_settings()
    ia = make_ia(S, a.engine, a.mode)
    now = datetime.now()
    if ia is None and a.engine != "ninguna":
        print(f"AVISO: no hay IA '{a.engine}' disponible (clave en .env o modelo instalado); se miden solo reglas y busqueda.")
    motor, modelo = (ia[1], ia[2]) if ia else ("sin_ia", "-")
    ctx = {"fecha": now.date().isoformat(), "hora": now.strftime("%H:%M"), "motor": motor, "modelo": modelo}
    meter = Meter(ia[0], prices(motor, modelo)) if ia else None
    if meter:
        meter.inner.start()
    rows: list[dict] = []
    summary: dict = {"fecha": ctx["fecha"], "hora": ctx["hora"], "motor": motor, "modelo": modelo, "casos_auditoria": len(AUDIT_CASES)}
    try:
        if a.suite in ("todo", "auditoria"):
            acc = run_audit(S, meter, a.reps, a.pause, rows, ctx)
            llm = [c for c in (meter.calls if meter else []) if c["tag"].startswith("A") and not c["est"]]
            for c in llm:
                rows.append({**ctx, "suite": "auditoria", "caso": c["tag"], "tipo": "llamada_ia", "latencia_s": c["secs"], "tokens_in": c["pt"],
                             "tokens_out": c["ct"], "costo_usd": round(meter.cost(c["pt"], c["ct"]), 6), "reintentos": c["retries"]})
            tok = [(c["pt"] or 0) + (c["ct"] or 0) for c in llm]
            summary["auditoria"] = {"reps": a.reps, "llamadas_ia": len(llm), "limite_429": meter.rate_limited if meter else 0,
                                    "latencia_ia_mediana_s": med([c["secs"] for c in llm]), "tokens_por_llamada_mediana": med(tok),
                                    "tokens_entrada_mediana": med([c["pt"] for c in llm]), "tokens_salida_mediana": med([c["ct"] for c in llm]),
                                    "costo_por_llamada_ia_usd_mediana": med([meter.cost(c["pt"], c["ct"]) for c in llm], 6) if meter else None,
                                    "costo_suite_usd": round(sum(meter.cost(c["pt"], c["ct"]) for c in llm), 5) if meter else None, **acc}
        if a.suite in ("todo", "rag", "asistente"):
            rag, eng, SR = run_rag(S, rows, ctx)
            if a.suite != "asistente":
                summary["rag"] = rag
            if a.suite in ("todo", "asistente") and meter:
                meter.calls.clear()
                summary["asistente"] = run_asistente(eng, SR, meter, a.preguntas, a.pause, rows, ctx)
    finally:
        if meter:
            meter.inner.stop()

    OUT.mkdir(exist_ok=True)
    stamp = now.strftime("%Y-%m-%d_%H%M")
    slug = "".join(ch if ch.isalnum() else "-" for ch in modelo.lower()).strip("-")[:40]
    detalle = OUT / f"{stamp}_{motor}_{slug}_detalle.csv"
    with detalle.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)
    new = not (OUT / "resumen.csv").exists()
    with (OUT / "resumen.csv").open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["fecha", "hora", "motor", "modelo", "suite", "cifra", "valor"])
        for suite in ("auditoria", "rag", "asistente"):
            for k, v in summary.get(suite, {}).items():
                w.writerow([ctx["fecha"], ctx["hora"], motor, modelo, suite, k, v])
    bp = OUT / "linea_base.json"
    base = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else {}
    key = f"{motor}:{modelo}"
    base[key] = {**base.get(key, {}), **summary}
    bp.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\nDetalle: {detalle.relative_to(HERE.parent)}\nResumen acumulado: {(OUT / 'resumen.csv').relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
