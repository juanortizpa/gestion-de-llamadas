"""Trazas de la IA: se registra cada llamada, los errores salen como mensaje legible y nada se guarda sin configurar."""
import json
from pathlib import Path

import pytest

from llamadas import trace


class FakeLLM:
    mode = "rapido"
    model = Path("fake.gguf")
    provider = None

    def __init__(self, fail=None):
        self.fail = fail

    def chat_json(self, system, user, schema):
        if self.fail:
            raise self.fail
        return {"checks": []}, {"secs": 0.5, "prompt_tokens": 100, "completion_tokens": 20}

    def chat_stream(self, system, user, max_tokens=350):
        yield from ["Hola ", "mundo"]


@pytest.fixture(autouse=True)
def limpio():
    trace._EVENTS.clear()
    trace._DIR, trace._LOADED = None, True
    yield
    trace._EVENTS.clear()
    trace._DIR = None


SCHEMA = {"type": "object", "properties": {"checks": {"minItems": 2, "maxItems": 2}}}


def test_chat_json_registra_modelo_segundos_y_tokens():
    srv = trace.wrap(FakeLLM())
    trace.CALL_ID.set("1001")
    srv.chat_json("s", "u", SCHEMA)
    ev = trace.events()[-1]
    assert ev["kind"] == "llm" and ev["status"] == "ok" and ev["modelo"] == "fake.gguf" and ev["call_id"] == "1001"
    assert (ev["secs"], ev["prompt_tokens"], ev["completion_tokens"]) == (0.5, 100, 20) and "2 criterio" in ev["label"]


def test_un_error_se_registra_sin_stack_trace_y_se_propaga():
    srv = trace.wrap(FakeLLM(fail=RuntimeError("La API externa limito las peticiones (429).\nTraceback (most recent call last)...")))
    with pytest.raises(RuntimeError):
        srv.chat_json("s", "u", SCHEMA)
    ev = trace.events()[-1]
    assert ev["status"] == "error" and ev["error"] == "La API externa limito las peticiones (429)."


def test_stream_devuelve_los_tokens_y_registra_una_traza():
    srv = trace.wrap(FakeLLM())
    assert "".join(srv.chat_stream("s", "u", 50)) == "Hola mundo"
    ev = trace.events()[-1]
    assert ev["label"].startswith("Redactar") and ev["tokens_estimados"] and ev["completion_tokens"] >= 1


def test_el_envoltorio_delega_el_resto_de_atributos():
    srv = trace.wrap(FakeLLM())
    assert srv.mode == "rapido" and srv.model.name == "fake.gguf" and trace.wrap(srv) is srv


def test_resumen_de_citas_aceptadas_y_descartadas():
    audit = {"llm": {"log": [{"id": "C1.a", "result": "si_verificado"}, {"id": "V2.b", "result": "cita_inventada_descartada"},
                             {"id": "P1.c", "result": "no_sin_evidencia"}], "invalid_batches": 0}, "score": {"pending": ["V2"]}}
    trace.audit_summary("1001", audit)
    ev = trace.events()[-1]
    assert (ev["aceptadas"], ev["descartadas"], ev["sin_evidencia"]) == (1, 1, 1) and ev["pendientes"] == ["V2"]
    assert trace.summary(trace.events())["citas_descartadas"] == 1


def test_solo_se_guarda_en_disco_si_se_configura(tmp_path):
    trace.record("llm", "sin configurar")
    assert not list(tmp_path.glob("*"))
    cfg = type("S", (), {"data_dir": tmp_path})()
    trace.configure(cfg)
    trace.record("llm", "guardada", secs=1.0)
    lineas = (tmp_path / "trazas.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 1 and json.loads(lineas[0])["label"] == "guardada"
    trace.clear()
    assert not (tmp_path / "trazas.jsonl").exists() and trace.events() == []
