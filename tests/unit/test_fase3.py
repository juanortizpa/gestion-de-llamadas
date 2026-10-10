"""Fase 3: LLM auditor (con servidor simulado), validador de citas, revision humana y catalogo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synthetic"))
from builder import A, C, GOOD, build, variant  # noqa: E402

from llamadas.audit import audit_transcript  # noqa: E402
from llamadas.auditor import pending_items, resolve_with_llm, verify_quote  # noqa: E402
from llamadas.catalog import Catalog  # noqa: E402
from llamadas.review import final_view  # noqa: E402


class FakeServer:
    mode = "rapido"
    model = Path("fake.gguf")

    def __init__(self, answers=None, raise_=False):
        self.answers, self.raise_ = answers or [], raise_

    def chat_json(self, system, user, schema):
        if self.raise_:
            raise ValueError("json truncado")
        return {"checks": self.answers}, {"secs": 1.0, "prompt_tokens": 10, "completion_tokens": 5}


def prepared():
    """Llamada con criterios pendientes (C1 siempre; V2 sin palabras clave) para que el LLM intervenga."""
    tr = build(variant(GOOD, replace={4: "Gracias, señora Marta Pérez. Continuemos.", 8: "Debe presentarse 20 minutos antes con su cédula y los soportes."}))
    return tr, audit_transcript(tr)


def test_hay_pendientes_para_el_llm():
    tr, au = prepared()
    assert ("C1", "comprende_la_necesidad") in pending_items(au) and ("V2", "pregunta_examen_orden_requisitos") in pending_items(au)


def test_cita_verificada_se_acepta():
    tr, au = prepared()
    items = pending_items(au)
    ans = [{"id": f"{c}.{s}", "passed": True, "turn_id": 3, "quote": "Con gusto señora"} for c, s in items]
    out = resolve_with_llm(au, tr, FakeServer(ans))
    sub = next(s for s in out["criteria"][items[0][0]]["sub_checks"] if s["id"] == items[0][1])
    assert sub["passed"] is True and sub["source"] == "llm" and sub["evidence"]["turn_id"] == 3
    assert out["llm"]["log"][0]["result"] == "si_verificado"


def test_cita_inventada_se_descarta_y_queda_pendiente():
    tr, au = prepared()
    items = pending_items(au)
    ans = [{"id": f"{c}.{s}", "passed": True, "turn_id": 1, "quote": "usted me debe una explicacion urgente"} for c, s in items]
    out = resolve_with_llm(au, tr, FakeServer(ans))
    assert out["criteria"]["C1"]["score"] is None
    assert all(x["result"] == "cita_inventada_descartada" for x in out["llm"]["log"])


def test_no_del_llm_es_solo_una_pista_no_fija_cero():
    tr, au = prepared()
    items = pending_items(au)
    ans = [{"id": f"{c}.{s}", "passed": False, "turn_id": 0, "quote": ""} for c, s in items]
    out = resolve_with_llm(au, tr, FakeServer(ans))
    assert out["human_review"]["required"]
    assert out["criteria"]["C1"]["score"] is None          # un "no" del LLM NO convierte el criterio en 0
    assert any("IA" in r for r in out["human_review"]["reasons"])


def test_json_invalido_deja_todo_pendiente_sin_romper():
    tr, au = prepared()
    out = resolve_with_llm(au, tr, FakeServer(raise_=True))
    assert out["llm"]["invalid_batches"] >= 1
    assert out["criteria"]["C1"]["score"] is None


def test_llm_nunca_toca_e1():
    tr, au = prepared()
    before = au["critical_error"]["status"]
    out = resolve_with_llm(au, tr, FakeServer([]))
    assert out["critical_error"]["status"] == before


def test_verify_quote_exige_tres_palabras_y_aproximacion():
    turns = [{"turn_id": 3, "text": "Le queda agendada la cita para el lunes 12 de octubre"}]
    assert verify_quote("queda agendada la cita", turns, 3, 88)
    assert verify_quote("agendada", turns, 3, 88) is None            # una palabra no basta\n    assert verify_quote("Sí señora", turns, 3, 88) is None           # dos tampoco
    assert verify_quote("la cita es el martes", turns, 3, 88) is None


def test_decision_humana_gana_y_e1_confirmado_da_cero():
    _, au = prepared()
    fin = final_view(au, {"criteria": {"P1": 1, "C1": 1, "C2": 1, "V2": 1}, "reviewed": True})
    assert fin["criteria"]["P1"]["origin"] == "humano"
    fin0 = final_view(au, {"e1": "confirmed", "reviewed": True})
    assert fin0["percent"] == 0 and "error crítico" in fin0["estado"]


def test_nota_final_solo_si_no_hay_pendientes_y_umbral_80():
    tr = build(GOOD)
    au = audit_transcript(tr)
    pend = au["score"]["pending"]
    fin = final_view(au, {"criteria": {c: 1 for c in pend}, "reviewed": True})
    assert fin["percent"] is not None and fin["estado"] in ("Aprobado", "No aprobado")
    assert (fin["percent"] >= 80) == (fin["estado"] == "Aprobado")
    assert final_view(au, {})["percent"] is None or not pend


def test_catalogo_preparacion_requerida():
    assert Catalog.prep_required([{"preparacion": "No requiere ayuno. No suspenda sus medicamentos."}]) is False
    assert Catalog.prep_required([{"preparacion": "Asista en ayuno mínimo de 8 horas."}]) is True
    assert Catalog.prep_required([{"preparacion": ""}]) is False


def test_llamada_descartada_no_se_audita_ni_cuenta():
    tr = build(GOOD)
    au = audit_transcript(tr)
    fin = final_view(au, {"discard": "cortada", "reviewed": True})
    assert fin["discarded"] == "cortada" and fin["percent"] is None and fin["pending"] == []
    assert "no se audita" in fin["estado"].lower() and fin["e1"] == "none"
    # aunque tuviera decisiones o E1 confirmado, el descarte manda
    fin2 = final_view(au, {"discard": "incompleta", "e1": "confirmed", "criteria": {"P1": 0}})
    assert fin2["discarded"] == "incompleta" and fin2["percent"] is None


def test_guardar_revision_valida_el_motivo_de_descarte(tmp_path):
    from llamadas.review import load_review, save_review
    from llamadas.config import load_settings
    import dataclasses
    base = load_settings()
    s = dataclasses.replace(base, raw={**base.raw, 'paths': {**base.raw['paths'], 'data_dir': str(tmp_path)}})
    assert save_review("x1", {"discard": "cortada"}, s)["discard"] == "cortada"
    assert save_review("x1", {"discard": "otra cosa"}, s)["discard"] is None
    assert load_review("x1", s)["discard"] is None

# ---------- descarte automático: regla de 20 s y clasificación de cierre por IA ----------
class CompletionServer:
    mode = "rapido"
    model = Path("fake.gguf")

    def __init__(self, ans=None, raise_=False):
        self.ans, self.raise_, self.calls = ans, raise_, 0

    def chat_json(self, system, user, schema):
        self.calls += 1
        if self.raise_:
            raise ValueError("json truncado")
        return self.ans, {"secs": 1.0}


def _sin_despedida():
    """Llamada que termina abruptamente: se quitan la despedida y el agradecimiento finales."""
    tr = build(variant(GOOD, drop=[len(GOOD) - 1, len(GOOD) - 2]))
    return tr, audit_transcript(tr)


def test_llamada_menor_a_20s_se_descarta_sola_como_cortada():
    from llamadas.review import effective_discard
    tr = build(GOOD, duration=12.0)
    au = audit_transcript(tr)
    assert au["auto_discard"]["value"] == "cortada" and au["auto_discard"]["source"] == "regla"
    assert effective_discard(au, {}) == ("cortada", "automática")
    fin = final_view(au, {})
    assert fin["discarded"] == "cortada" and fin["percent"] is None and fin["discard_origin"] == "automática"
    # 20 s exactos ya no es "menor a 20"
    assert "auto_discard" not in audit_transcript(build(GOOD, duration=20.0))


def test_el_auditor_puede_anular_la_marca_automatica():
    tr = build(GOOD, duration=12.0)
    au = audit_transcript(tr)
    fin = final_view(au, {"discard": "ninguna", "reviewed": True})
    assert fin.get("discarded") is None
    fin2 = final_view(au, {"discard": "incompleta"})
    assert fin2["discarded"] == "incompleta" and fin2["discard_origin"] == "auditor"


def test_con_despedida_y_dos_partes_no_se_gasta_ia():
    from llamadas.auditor import classify_completion
    tr = build(GOOD)
    au = audit_transcript(tr)
    srv = CompletionServer({"estado": "cortada", "turn_id": 0, "quote": "x", "motivo": "x"})
    out = classify_completion(au, tr, srv)
    assert srv.calls == 0 and out["completion"]["estado"] == "finalizada" and "auto_discard" not in out


def test_ia_marca_cortada_si_la_cita_existe_en_la_llamada():
    from llamadas.auditor import classify_completion
    tr, au = _sin_despedida()
    last = tr["turns"][-1]
    srv = CompletionServer({"estado": "cortada", "turn_id": last["turn_id"], "quote": " ".join(last["text"].split()[:6]),
                            "motivo": "La conversación termina sin cierre"})
    out = classify_completion(au, tr, srv)
    assert srv.calls == 1 and out["completion"]["applied"] is True
    assert out["auto_discard"]["value"] == "cortada" and out["auto_discard"]["source"] == "ia"
    from llamadas.review import effective_discard
    assert effective_discard(out, {}) == ("cortada", "automática")


def test_ia_con_cita_inventada_no_marca_nada():
    from llamadas.auditor import classify_completion
    tr, au = _sin_despedida()
    srv = CompletionServer({"estado": "incompleta", "turn_id": 1, "quote": "el cliente colgó de golpe enojado", "motivo": "x"})
    out = classify_completion(au, tr, srv)
    assert "auto_discard" not in out and out["completion"]["applied"] is False and "no se marcó" in out["completion"]["nota"]


def test_ia_dice_finalizada_o_json_invalido_no_marca_nada():
    from llamadas.auditor import classify_completion
    tr, au = _sin_despedida()
    out = classify_completion(au, tr, CompletionServer({"estado": "finalizada", "turn_id": 0, "quote": "", "motivo": "ok"}))
    assert "auto_discard" not in out and out["completion"]["estado"] == "finalizada"
    tr2, au2 = _sin_despedida()
    out2 = classify_completion(au2, tr2, CompletionServer(raise_=True))
    assert "auto_discard" not in out2 and out2["completion"]["estado"] is None


def test_no_se_reclasifica_una_llamada_ya_descartada_por_regla():
    from llamadas.auditor import classify_completion
    tr = build(GOOD, duration=9.0)
    au = audit_transcript(tr)
    srv = CompletionServer({"estado": "incompleta", "turn_id": 0, "quote": "", "motivo": ""})
    classify_completion(au, tr, srv)
    assert srv.calls == 0 and au["auto_discard"]["source"] == "regla"