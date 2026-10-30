"""Proveedor externo opcional (Groq / Gemini): mismo contrato que el LLM local, sin red real."""
import io
import json
import urllib.error

import pytest

from llamadas import llm
from llamadas.config import load_settings


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(payload, seen):
    def _open(req, timeout=None):
        seen.append(req)
        return Resp(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
    return _open


def test_proveedor_por_defecto_es_local(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm.active_provider() == "local"
    assert isinstance(llm.make_llm(load_settings(), "rapido"), llm.LlamaServer)


def test_env_elige_proveedor_externo(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    srv = llm.make_llm(load_settings(), "rapido")
    assert isinstance(srv, llm.RemoteLLM) and srv.available() and srv.model_id == "openai/gpt-oss-120b"
    monkeypatch.setenv("LLM_PROVIDER", "desconocido")
    assert llm.active_provider() == "local"


def test_sin_clave_no_esta_disponible_y_start_explica(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    srv = llm.RemoteLLM(load_settings(), "gemini")
    assert not srv.available()
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        srv.start()


def test_groq_chat_json(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "secreta")
    seen = []
    resp = {"choices": [{"message": {"content": '{"P1.a": 1}'}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen(resp, seen))
    data, meta = llm.RemoteLLM(load_settings(), "groq").chat_json("sistema", "usuario", {"type": "object"})
    assert data == {"P1.a": 1} and meta["prompt_tokens"] == 7 and meta["completion_tokens"] == 3
    req = seen[0]
    assert req.get_header("Authorization") == "Bearer secreta" and "secreta" not in req.full_url
    body = json.loads(req.data)
    assert body["response_format"] == {"type": "json_object"} and '"type": "object"' in body["messages"][0]["content"]


def test_gemini_chat_json_clave_en_cabecera(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secreta")
    seen = []
    resp = {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2}}
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen(resp, seen))
    data, meta = llm.RemoteLLM(load_settings(), "gemini").chat_json("s", "u", {"type": "object"})
    assert data == {"ok": True} and meta["prompt_tokens"] == 5
    assert seen[0].get_header("X-goog-api-key") == "secreta" and "secreta" not in seen[0].full_url


def test_stream_groq_y_gemini(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    g = b'data: {"choices":[{"delta":{"content":"Ho"}}]}\n\ndata: {"choices":[{"delta":{"content":"la"}}]}\n\ndata: [DONE]\n\n'
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen(g, []))
    assert "".join(llm.RemoteLLM(load_settings(), "groq").chat_stream("s", "u")) == "Hola"
    m = b'data: {"candidates":[{"content":{"parts":[{"text":"Ho"}]}}]}\n\ndata: {"candidates":[{"content":{"parts":[{"text":"la"}]}}]}\n\n'
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen(m, []))
    assert "".join(llm.RemoteLLM(load_settings(), "gemini").chat_stream("s", "u")) == "Hola"


@pytest.mark.parametrize("code,texto", [(429, "limito"), (401, "clave"), (403, "403"), (500, "500")])
def test_errores_http_sin_traza_ni_clave(monkeypatch, code, texto):
    monkeypatch.setenv("GROQ_API_KEY", "secreta")

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b"cuerpo con secreta"))
    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError) as e:
        llm.RemoteLLM(load_settings(), "groq").chat_json("s", "u", {})
    assert texto in str(e.value) and "secreta" not in str(e.value)


def test_json_invalido_y_caida_de_red(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    resp = {"choices": [{"message": {"content": "no es json"}}]}
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen(resp, []))
    with pytest.raises(RuntimeError, match="JSON invalido"):
        llm.RemoteLLM(load_settings(), "groq").chat_json("s", "u", {})

    def down(req, timeout=None):
        raise urllib.error.URLError("sin red")
    monkeypatch.setattr(llm.urllib.request, "urlopen", down)
    with pytest.raises(RuntimeError, match="conectar"):
        llm.RemoteLLM(load_settings(), "groq").chat_json("s", "u", {})
