"""Asistente de consulta: indice, enrutador, busqueda, ruta directa/IA/degradada. Solo datos sinteticos y servidores simulados."""
import dataclasses
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synthetic"))
from builder import A, C, GOOD, build, variant  # noqa: E402

from llamadas.audit import audit_transcript, save_audit  # noqa: E402
from llamadas.chat import analytics, router  # noqa: E402
from llamadas.chat.chunks import build_call, mask_pii  # noqa: E402
from llamadas.chat.engine import ChatEngine  # noqa: E402
from llamadas.chat.store import Store  # noqa: E402
from llamadas.config import load_settings  # noqa: E402
from llamadas.pipeline import save_result  # noqa: E402
from llamadas.review import final_view, save_review  # noqa: E402

TODAY = date(2026, 10, 13)


class FakeEmbedder:
    """Embedding por hashing de palabras (determinista, sin modelo). Imita la interfaz de LlamaEmbedder."""
    ident = "fake-embed|q|d"

    def __init__(self, ok=True):
        self.ok, self.calls, self.fail = ok, 0, False

    def available(self):
        return self.ok

    def _v(self, text):
        v = np.zeros(64, np.float32)
        for w in re.findall(r"\w+", text.lower()):
            v[hash(w) % 64] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed_docs(self, texts):
        if self.fail:
            raise RuntimeError("servidor caido")
        self.calls += len(texts)
        return np.stack([self._v(t) for t in texts])

    def embed_query(self, text):
        return self._v(text)

    def reap(self, idle_s):
        pass


class FakeServer:
    def __init__(self, answer="Respuesta [1].", ok=True):
        self.answer, self.ok, self.prompts, self.proc, self.starts = answer, ok, [], None, 0

    def available(self):
        return self.ok

    def start(self):
        self.starts += 1

    def stop(self):
        pass

    def chat_stream(self, system, user, max_tokens):
        self.prompts.append(user)
        for w in re.findall(r"\S+\s*", self.answer):
            yield w


@pytest.fixture
def S(tmp_path):
    base = load_settings()
    return dataclasses.replace(base, raw={**base.raw, "paths": {**base.raw["paths"], "data_dir": str(tmp_path)}}, agents=[])


def make_call(S, cid, turns=None, day="20261005", agent="", **review):
    tr = build(turns or GOOD)
    tr["call"].update(call_id=cid, received_date=day, received_time="140300", queue="800197")
    save_result(tr, S)
    au = audit_transcript(tr, S)
    save_audit(au, S)
    decided = {c: 1 for c in final_view(au, {}, S)["pending"]}      # el auditor resuelve lo pendiente: asi hay nota definitiva
    save_review(cid, {"agent": agent, "reviewed": True, "criteria": decided, **review}, S)
    return tr


@pytest.fixture
def world(S):
    """5 llamadas sinteticas: 2 asesoras, fechas distintas, una con fallo conocido (sin despedida)."""
    make_call(S, "1001", agent="Laura Gómez", day="20261005", auditor="Marta", obs="Excelente manejo del tono con el paciente.")
    make_call(S, "1002", agent="Laura Gómez", day="20261006")
    make_call(S, "1003", variant(GOOD, drop=[len(GOOD) - 1]), agent="Pedro Ruiz", day="20261006")
    make_call(S, "1004", agent="Pedro Ruiz", day="20260915")
    make_call(S, "1005", variant(GOOD, replace={0: "Hola."}), agent="Pedro Ruiz", day="20261007")
    return S


def engine(S, answer="Respuesta [1].", embedder=None, busy=False, gen_ok=True):
    srv = FakeServer(answer, gen_ok)
    from llamadas.chat.engine import Generator
    eng = ChatEngine(S, embedder=embedder, generator=Generator(S, srv), busy=lambda: busy, today=lambda: TODAY, include_synthetic=True)
    eng.sync_now()
    return eng, srv


# ---------------------------------------------------------------- privacidad y fragmentos
def test_mask_pii_enmascara_documentos_dictados_y_telefonos():
    assert mask_pii("Es el 1 0 6 2 3 3 1 5 6 5.") == "Es el ****1565."
    assert mask_pii("mi cédula 1062331565 gracias") == "mi cédula ****1565 gracias"
    assert mask_pii("llame al 315 123 4567") == "llame al ****4567"
    assert mask_pii("el lunes 12 de octubre a las 8 con 20 minutos") == "el lunes 12 de octubre a las 8 con 20 minutos"


def test_el_indice_no_contiene_numeros_largos(world):
    eng, _ = engine(world)
    with eng.store.conn() as c:
        bodies = " ".join(r[0] for r in c.execute("SELECT body FROM chunks"))
    assert "1062331565" not in bodies and "6 2 3 3 1" not in bodies and "****1565" in bodies


def test_fragmentos_de_una_llamada(world):
    tr = build(GOOD)
    tr["call"]["call_id"] = "X"
    au = audit_transcript(tr, world)
    row, chunks = build_call(au, tr, {"agent": "Laura Gómez", "obs": "Buen trabajo"}, final_view(au, {}, world), "sig", window_words=40)
    kinds = {c["kind"] for c in chunks}
    assert {"resumen", "criterio", "ventana", "observacion"} <= kinds
    wins = [c for c in chunks if c["kind"] == "ventana"]
    assert len(wins) >= 2 and wins[0]["turn1"] >= wins[1]["turn0"]          # solape de un turno
    assert row["agent"] == "Laura Gómez" and row["date"] == ""


def test_llamada_descartada_solo_aporta_resumen(S):
    tr = build(GOOD, duration=9.0)
    tr["call"]["call_id"] = "D1"
    au = audit_transcript(tr, S)
    _, chunks = build_call(au, tr, {}, final_view(au, {}, S), "s")
    assert [c["kind"] for c in chunks] == ["resumen"] and "No se audita" in chunks[0]["body"]


# ---------------------------------------------------------------- enrutador
def parse(q, **kw):
    kw.setdefault("known_ids", ["1001", "1002"])
    kw.setdefault("agents", ["Laura Gómez", "Pedro Ruiz"])
    return router.parse(q, today=TODAY, **kw)


def test_fechas_en_espanol():
    assert parse("llamadas de septiembre").filters.date_from == "2026-09-01"
    assert parse("llamadas de septiembre").filters.date_to == "2026-09-30"
    assert (parse("el 5 de octubre").filters.date_from, parse("el 5 de octubre").filters.date_to) == ("2026-10-05",) * 2
    assert parse("del 5 al 7 de octubre").filters.date_to == "2026-10-07"
    assert parse("ayer").filters.date_from == "2026-10-12"
    assert parse("esta semana").filters.date_from == "2026-10-12"          # lunes
    assert parse("semana pasada").filters.date_from == "2026-10-05"
    assert parse("el mes pasado").filters.date_from == "2026-09-01"
    assert parse("el 05/10/2026").filters.date_from == "2026-10-05"
    assert parse("diciembre").filters.date_from == "2025-12-01"            # el diciembre mas reciente ya pasado


def test_asesor_criterio_estado():
    p = parse("¿cuántas llamadas no aprobadas tiene Laura en G1?")
    assert p.filters.agents == ["Laura Gómez"] and p.filters.criteria == ["G1"] and p.filters.estados == ["no_aprobada"]
    assert parse("llamadas aprobadas").filters.estados == ["aprobada"]
    assert parse("nota de Pedro").filters.agents == ["Pedro Ruiz"]
    assert parse("cómo es la despedida").filters.criteria == ["Z2"]


def test_intenciones():
    assert parse("¿cuántas llamadas hubo en septiembre?").intent == "aggregate"
    assert parse("¿qué asesor falla más la despedida?").metric == "rank"
    assert parse("nota promedio de Laura").metric == "avg"
    assert parse("dame las llamadas de Pedro").intent == "list"
    assert parse("resumen de la llamada 1001").intent == "card"
    assert parse("¿por qué falló Z1 en la llamada 1001?").intent == "semantic"
    assert parse("¿qué dicen los clientes cuando reclaman por la cita?").intent == "semantic"
    # conteo con tema libre que los datos estructurados no explican -> busqueda, no un conteo engañoso
    assert parse("¿cuántas llamadas mencionan problemas con la autorización de resonancia?").intent == "semantic"


def test_seguimiento_hereda_filtros():
    p1 = parse("llamadas de Laura en octubre")
    p2 = parse("¿y su nota promedio?", prev=p1.filters.to_dict())
    assert p2.follow_up and p2.filters.agents == ["Laura Gómez"] and p2.metric == "avg"
    assert parse("nota promedio de septiembre", prev=p1.filters.to_dict()).filters.agents == []     # sin marca de seguimiento: no hereda
    p3 = parse("¿y esa asesora cuántas tiene?", prev=p1.filters.to_dict())
    assert p3.follow_up and p3.filters.agents == ["Laura Gómez"] and "agents" in p3.inherited
    p4 = parse("¿y de Pedro?", prev=p1.filters.to_dict())
    assert p4.filters.agents == ["Pedro Ruiz"] and p4.filters.date_from == p1.filters.date_from


# ---------------------------------------------------------------- indice
def test_sync_incremental_y_borrado(world):
    eng, _ = engine(world, embedder=FakeEmbedder())
    st = eng.store.stats()
    assert st["calls"] == 5 and st["chunks"] > 20 and st["vectors"] == st["chunks"]
    v = eng.store.version()
    again = eng.sync_now()
    assert again["added"] == again["updated"] == 0 and again["unchanged"] == 5 and eng.store.version() == v
    save_review("1002", {"agent": "Laura Gómez", "obs": "Revisada de nuevo", "reviewed": True}, world)
    ch = eng.sync_now()
    assert ch["updated"] == 1 and ch["embedded"] > 0 and ch["from_cache"] > 0       # solo lo nuevo se embebe
    for f in (world.data_dir / "results").glob("1005.*"):
        f.unlink()
    assert eng.sync_now()["removed"] == 1 and eng.store.stats()["calls"] == 4


def test_sin_embedder_indexa_palabras_y_luego_completa_vectores(world):
    emb = FakeEmbedder(ok=False)
    eng, _ = engine(world, embedder=emb)
    assert eng.store.stats()["vectors"] == 0 and eng.store.stats()["chunks"] > 0
    emb.ok = True
    r = eng.sync_now()
    assert r["updated"] == 5 and eng.store.stats()["vectors"] == eng.store.stats()["chunks"]


def test_embedder_caido_a_mitad_no_rompe_el_indexado(world):
    emb = FakeEmbedder()
    emb.fail = True
    eng, _ = engine(world, embedder=emb)
    assert eng.store.stats()["calls"] == 5 and eng.store.stats()["vectors"] == 0
    emb.fail = False
    eng.sync_now()
    assert eng.store.stats()["vectors"] > 0


def test_durante_un_lote_no_se_calculan_vectores(world):
    emb = FakeEmbedder()
    eng, _ = engine(world, embedder=emb, busy=True)
    assert emb.calls == 0 and eng.store.stats()["vectors"] == 0


def test_eliminar_llamada_borra_fragmentos_vectores_y_cache(world):
    eng, _ = engine(world, embedder=FakeEmbedder())
    eng.forget("1003")
    st = eng.store.stats()
    with eng.store.conn() as c:
        assert c.execute("SELECT COUNT(*) FROM chunks WHERE call_id='1003'").fetchone()[0] == 0
        if eng.store.native:  # sin la extension (python.org en macOS) los vectores viven solo en embcache
            assert c.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == st["vectors"]
        assert st["vectors"] == st["chunks"]
        assert c.execute("SELECT COUNT(*) FROM fts").fetchone()[0] == st["chunks"]


# ---------------------------------------------------------------- analitica (sin IA)
def rows_of(eng):
    return eng.store.calls()


def test_conteos_y_filtros(world):
    eng, srv = engine(world)
    rows = rows_of(eng)
    assert len(analytics.filter_rows(rows, router.Filters(agents=["Pedro Ruiz"]))) == 3
    assert len(analytics.filter_rows(rows, router.Filters(date_from="2026-10-06", date_to="2026-10-06"))) == 2
    r = eng.ask("¿cuántas llamadas hubo en septiembre?")
    assert "**1**" in r["answer"] and r["route"] == "directo" and not srv.prompts


def test_ranking_por_asesor_marca_pocas_llamadas(world):
    eng, srv = engine(world)
    r = eng.ask("¿qué asesor tiene la nota promedio más baja?")
    assert "pocas llamadas" in r["answer"] and "|" in r["answer"] and not srv.prompts


def test_tasa_de_fallo_de_un_criterio(world):
    eng, srv = engine(world)
    r = eng.ask("¿cuántas llamadas fallan Z2?")
    assert "Z2" in r["answer"] and "no cumple" in r["answer"] and not srv.prompts
    assert "1003" in " ".join(s["call_id"] for s in r["sources"])


def test_lista_de_llamadas_con_enlaces(world):
    eng, _ = engine(world)
    r = eng.ask("dame las llamadas de Pedro Ruiz")
    assert "(call:1003)" in r["answer"] and "(call:1001)" not in r["answer"]


def test_ficha_de_llamada_sin_ia(world):
    eng, srv = engine(world)
    r = eng.ask("resumen de la llamada 1003")
    assert "Llamada" in r["answer"] and "Pedro Ruiz" in r["answer"] and not srv.prompts


def test_sin_resultados_con_filtros_imposibles(world):
    eng, _ = engine(world)
    assert "No hay llamadas" in eng.ask("cuántas llamadas hubo en diciembre")["answer"]


# ---------------------------------------------------------------- busqueda + IA
def test_pregunta_abierta_usa_ia_con_fragmentos_y_citas(world):
    eng, srv = engine(world, answer="El asesor confirma la cita para el lunes [1] y pide la orden [2].", embedder=FakeEmbedder())
    r = eng.ask("¿qué dicen los asesores sobre la orden médica?")
    assert r["route"] == "busqueda" and len(srv.prompts) == 1
    prompt = srv.prompts[0]
    assert prompt.startswith("FRAGMENTOS:") and "PREGUNTA:" in prompt and "[1]" in prompt
    assert any(s["cited"] for s in r["sources"]) and not r["warnings"]
    assert 1 <= len(r["sources"]) <= world["chat"]["top_k"]


def test_respeta_presupuesto_de_tokens_y_diversidad(world):
    eng, srv = engine(world, embedder=FakeEmbedder())
    cfg = dict(eng.cfg, context_tokens=300, top_k=6, max_per_call=1)
    from llamadas.chat import retrieve
    p = router.parse("orden médica cita lunes", today=TODAY, known_ids=[], agents=[])
    hits = retrieve.search(eng.store, p, None, eng.embedder, cfg)
    assert hits and sum(retrieve.est_tokens(h.ctx + h.body) + 12 for h in hits) <= 300 + 12
    assert len({h.call_id for h in hits}) == len(hits)                       # a lo sumo uno por llamada
    wins = [h for h in hits if h.kind == "ventana"]
    for a in wins:
        for b in wins:
            assert a is b or not retrieve._overlaps(a, b)


def test_busqueda_respeta_filtro_de_asesor(world):
    eng, srv = engine(world, embedder=FakeEmbedder())
    r = eng.ask("¿qué dice la orden médica? asesor Pedro Ruiz")
    assert r["sources"] and all(s["call_id"] in ("1003", "1004", "1005") for s in r["sources"])


def test_cita_invalida_se_quita_y_frase_inventada_se_avisa(world):
    eng, _ = engine(world, answer='Dijo «usted debe pagar una multa inmediata por cancelar» [9] y confirma [1].')
    r = eng.ask("¿qué dicen sobre cancelar la cita?")
    assert "[9]" not in r["answer"] and "[1]" in r["answer"]
    assert any("no existe" in w for w in r["warnings"]) and any("Frase no encontrada" in w for w in r["warnings"])


def test_respuesta_sin_citas_genera_aviso(world):
    eng, _ = engine(world, answer="Los asesores suelen confirmar la cita con fecha, hora y sede al final de la llamada.")
    assert any("no cita" in w for w in eng.ask("¿cómo confirman la cita los asesores?")["warnings"])


def test_degradacion_a_fragmentos_si_hay_lote_en_curso(world):
    eng, srv = engine(world, busy=True)
    r = eng.ask("¿qué dicen sobre la orden médica?")
    assert not srv.prompts and "no está disponible" in r["answer"] and "análisis de llamadas en curso" in r["answer"]
    assert r["sources"] and r["stats"]["degraded"]


def test_degradacion_si_el_modelo_no_esta_instalado(world):
    eng, srv = engine(world, gen_ok=False)
    assert "no está instalado" in eng.ask("¿qué dicen sobre la orden médica?")["answer"]


def test_pregunta_sin_coincidencias_no_gasta_ia(world):
    eng, srv = engine(world)
    r = eng.ask("hipopótamo submarino cuántico")
    assert "No encontré" in r["answer"] and not srv.prompts


def test_cache_evita_repetir_computo_y_se_invalida_al_reindexar(world):
    eng, srv = engine(world, answer="Confirman la cita [1].")
    q = "¿qué dicen sobre la orden médica?"
    eng.ask(q)
    r2 = eng.ask(q)
    assert len(srv.prompts) == 1 and r2["route"] == "cache"
    save_review("1002", {"agent": "Laura Gómez", "obs": "cambio", "reviewed": True}, world)
    eng.sync_now()
    eng.ask(q)
    assert len(srv.prompts) == 2


def test_historial_solo_viaja_en_preguntas_de_seguimiento(world):
    eng, srv = engine(world)
    hist = [{"q": "¿qué dicen de la orden?", "a": "Piden la orden médica."}]
    eng.ask("¿qué dicen sobre la cita?", history=hist)
    eng.ask("¿y qué dice esa asesora sobre la orden?", ctx={"filters": {"agents": ["Laura Gómez"]}}, history=hist)
    assert "CONVERSACIÓN PREVIA" not in srv.prompts[0] and "CONVERSACIÓN PREVIA" in srv.prompts[1]


def test_vacio_y_preguntas_vacias(S):
    eng = ChatEngine(S, embedder=None, generator=None, today=lambda: TODAY)
    assert "Todavía no hay llamadas" in eng.ask("hola")["answer"]
    assert eng.ask("   ").get("error")


def test_fts_tolera_consultas_raras(world):
    eng, _ = engine(world)
    from llamadas.chat import retrieve
    for q in ['"', "OR AND NOT", "((", "a*", "'; DROP TABLE chunks; --"]:
        p = router.parse(q, today=TODAY, known_ids=[], agents=[])
        retrieve.search(eng.store, p, None, None, eng.cfg)
    assert eng.store.stats()["chunks"] > 0


# ---------------------------------------------------------------- servidor HTTP (flujo NDJSON)
def _serve(eng, monkeypatch):
    import json as _json
    import threading
    from http.server import ThreadingHTTPServer

    from llamadas.gui import server
    monkeypatch.setattr(server, "chat_engine", lambda: eng)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, _json


def test_endpoint_chat_emite_eventos_ndjson(world, monkeypatch):
    import urllib.request
    eng, srv = engine(world, answer="Piden la orden [1].")
    httpd, _json = _serve(eng, monkeypatch)
    try:
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat", data=_json.dumps({"question": "¿qué dicen sobre la orden médica?"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            assert r.headers["Content-Type"].startswith("application/x-ndjson")
            events = [_json.loads(line) for line in r.read().decode("utf-8").splitlines() if line.strip()]
        types = [e["type"] for e in events]
        assert types[0] == "route" and types[-1] == "done" and "token" in types and "sources" in types
        assert "".join(e["text"] for e in events if e["type"] == "token").strip() == "Piden la orden [1]."
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/chat/status", timeout=10) as r:
            assert _json.load(r)["calls"] == 5
    finally:
        httpd.shutdown()


def test_endpoint_rechaza_cuerpos_enormes_y_json_invalido(world, monkeypatch):
    import urllib.error
    import urllib.request
    eng, _ = engine(world)
    httpd, _json = _serve(eng, monkeypatch)
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/chat"
        with pytest.raises(urllib.error.HTTPError) as e1:
            urllib.request.urlopen(urllib.request.Request(url, data=b"x" * 30_000, headers={"Content-Type": "application/json"}), timeout=10)
        assert e1.value.code == 413
        with pytest.raises(urllib.error.HTTPError) as e2:
            urllib.request.urlopen(urllib.request.Request(url, data=b"{no es json", headers={"Content-Type": "application/json"}), timeout=10)
        assert e2.value.code == 400
    finally:
        httpd.shutdown()


def test_cortar_el_flujo_libera_el_candado_de_la_ia(world):
    eng, srv = engine(world, answer="uno dos tres cuatro cinco seis siete [1]")
    gen = eng.ask_stream("¿qué dicen sobre la orden médica?")
    for ev in gen:
        if ev["type"] == "token":
            break
    gen.close()                                   # el usuario pulso «Detener»
    assert eng.gen_lock.acquire(blocking=False)   # no quedo bloqueado para la siguiente pregunta
    eng.gen_lock.release()


# ---------------------------------------------------------------- base vectorial (sqlite-vec o numpy)
@pytest.mark.parametrize("native", [True, False], ids=["sqlite-vec", "numpy"])
def test_base_vectorial_knn_y_filtro_por_llamada(tmp_path, native):
    from llamadas.chat.store import Store, vec_extension_available
    if native and not vec_extension_available():
        pytest.skip("este Python no permite cargar extensiones de SQLite (p. ej. el de python.org en macOS)")
    st = Store(path=tmp_path / "index.db", native=native)
    e = lambda *v: np.asarray(v, dtype=np.float32) / np.linalg.norm(v)
    ch = lambda h: {"kind": "ventana", "ctx": "", "body": h, "hash": h}
    st.replace_call({"call_id": "A"}, [ch("a1"), ch("a2")], {"a1": e(1, 0, 0), "a2": e(0, 1, 0)}, lambda c: c["body"])
    st.replace_call({"call_id": "B"}, [ch("b1")], {"b1": e(0.9, 0.1, 0)}, lambda c: c["body"])
    assert st.stats()["vectors"] == 3
    ids = {r["body"]: r["id"] for r in st.chunks_by_ids([1, 2, 3]).values()}
    top = st.dense(e(1, 0, 0), None, 2)
    assert top[0][0] == ids["a1"] and top[0][1] > 0.99          # coseno ~1 con el mismo vector
    assert [i for i, _ in top][1] == ids["b1"]                  # el siguiente mas parecido
    solo_b = st.dense(e(1, 0, 0), {"B"}, 2)
    assert [i for i, _ in solo_b] == [ids["b1"]]                # el filtro excluye la llamada A
    assert st.dense(np.ones(7, np.float32), None, 2) == []      # dimension distinta: no se mezcla
    st.delete_call("A")
    assert st.stats()["vectors"] == 1
