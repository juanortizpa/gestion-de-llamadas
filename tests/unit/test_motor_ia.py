"""Seleccion de IA (local / externa) para el analisis y el asistente."""
import pytest

from llamadas import llm
from llamadas.chat.engine import ChatEngine
from llamadas.chat.store import Store
from llamadas.config import load_settings


@pytest.fixture
def S():
    return load_settings()


def test_engine_explicito_manda_sobre_env(S, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert isinstance(llm.make_llm(S, "rapido", "local"), llm.LlamaServer)         # Rapido/Preciso piden local aunque .env diga groq
    assert isinstance(llm.make_llm(S, "rapido", "externa"), llm.RemoteLLM)
    monkeypatch.setenv("LLM_PROVIDER", "local")
    assert isinstance(llm.make_llm(S, "rapido"), llm.LlamaServer)
    assert isinstance(llm.make_llm(S, "rapido", "externa"), llm.RemoteLLM)         # y externa funciona con .env en local


def test_external_provider_elige_el_que_tiene_clave(S, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "local")
    assert llm.external_provider(S) is None
    assert not llm.make_llm(S, "rapido", "externa").available()                    # sin clave: no disponible, la GUI lo explica
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert llm.external_provider(S) == "gemini"
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert llm.external_provider(S) == "groq"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert llm.external_provider(S) == "gemini"                                    # el elegido en el instalador tiene prioridad


def test_modelo_con_prefijo_se_envia_completo(S, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    r = llm.RemoteLLM(S, "groq")
    assert r.model_id == "openai/gpt-oss-120b" and r.model.name == "gpt-oss-120b"
    body = r._body("s", "u", temperature=0, max_tokens=100, json_mode=False)
    assert body["model"] == "openai/gpt-oss-120b" and body["reasoning_effort"] == "low" and body["max_tokens"] > 100


def make_chat(S, tmp_path, busy):
    return ChatEngine(S, store=Store(S, tmp_path / "i.db"), embedder=None, busy=lambda: busy)


def test_chat_ia_externa_no_espera_al_lote(S, tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    eng = make_chat(S, tmp_path, busy=True)
    assert "análisis" in eng._llm_unavailable(eng.generator("local"))              # la local cede la CPU al lote
    assert eng._llm_unavailable(eng.generator("externa")) is None                  # la externa no usa la CPU: responde igual
    st = eng.status("externa")
    assert st["engine"] == "externa" and st["llm_available"] and not st["busy_batch"] and st["model"] == "openai/gpt-oss-120b"


def test_chat_externa_sin_clave_dice_que_falta(S, tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    eng = make_chat(S, tmp_path, busy=False)
    assert "clave" in eng._llm_unavailable(eng.generator("externa"))
    assert eng.generator("externa") is eng.generator("externa")                    # se crea una vez
    assert eng.generator(None) is eng.gen and eng.generator("otra") is eng.gen     # valor desconocido = el configurado
