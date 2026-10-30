"""Entrevista de vocabulario: almacen, deduplicado, prompt de Whisper y flujo de turnos con una IA simulada."""
import dataclasses

import pytest

from llamadas import vocab
from llamadas.config import load_settings


class FakeLLM:
    def __init__(self):
        self.calls = []

    def chat_json(self, system, user, schema):
        self.calls.append(user)
        n = len(self.calls)
        ex = {"terms": [{"term": "Nueva EPS", "category": "aseguradora", "variants": ["nueva e p s"]}], "context": ["Atienden citas"], "predict": []} if n == 2 else {"terms": [], "context": [], "predict": []}
        return {"extracted": ex, "area": "entidad" if n == 1 else "examenes", "question": f"Pregunta {n}",
                "options": ["a", "b"], "why": "sirve"}, {}


@pytest.fixture
def S(tmp_path):
    s = load_settings()
    return dataclasses.replace(s, raw={**s.raw, "paths": {**s.raw["paths"], "data_dir": str(tmp_path)}})


def test_flujo_de_turnos_guarda_y_deduplica(S):
    llm = FakeLLM()
    d = vocab.turn(S, llm=llm)
    assert d["pending"]["question"] == "Pregunta 1" and d["terms"] == []
    d = vocab.turn(S, "Somos Angiografia y trabajamos con Nueva EPS", llm=llm)
    assert [t["term"] for t in d["terms"]] == ["Nueva EPS"] and d["added"]["terms"] and d["answers"] == 1
    assert d["pending"]["question"] == "Pregunta 2"
    d = vocab.turn(S, "otra vez nueva eps", llm=llm)          # no duplica
    assert len(d["terms"]) == 1
    assert '"ultima_respuesta": "otra vez nueva eps"' in llm.calls[-1]


def test_omitir_no_extrae_y_pausa_y_reanuda(S):
    llm = FakeLLM()
    vocab.turn(S, llm=llm)
    d = vocab.turn(S, skip=True, llm=llm)
    assert d["qa"][-1]["a"] == "(omitida)" and d["terms"] == []
    assert vocab.set_status(S, "paused")["status"] == "paused"
    assert vocab.load(S)["pending"]["question"] == d["pending"]["question"]      # la pregunta pendiente se conserva


def test_prompt_de_whisper_y_etiqueta_de_cache(S):
    base, tag = vocab.stt_hints(S)
    assert tag == "" and base == S["stt"]["initial_prompt"]
    vocab.edit(S, "add", value="Angiografia de Occidente")
    prompt, tag = vocab.stt_hints(S)
    assert "Angiografia de Occidente" in prompt and tag.startswith("_v")
    vocab.edit(S, "remove", "terms", 0)
    assert vocab.stt_hints(S)[1] == ""


def test_prompt_respeta_limite_de_caracteres(S):
    for i in range(200):
        vocab.edit(S, "add", value=f"termino{i:03d}largo")
    prompt, _ = vocab.stt_hints(S)
    assert len(prompt) < len(S["stt"]["initial_prompt"]) + 600
