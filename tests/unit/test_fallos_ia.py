"""Fallos de la IA externa que pide la entrega (timeout, respuesta invalida, API caida): mensaje legible, sin traza ni clave."""
import io
import json
import socket
import urllib.error

import pytest

from llamadas import llm
from llamadas.config import load_settings

CLAVE = "gsk_clave_de_prueba_123"


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *a):
        return False


def _mensaje(monkeypatch, error=None, contenido=None):
    """Mensaje que ve el usuario cuando urlopen lanza `error` o la IA responde `contenido`."""
    monkeypatch.setenv("GROQ_API_KEY", CLAVE)

    def urlopen(req, timeout=None):
        if error is not None:
            raise error
        return _Resp({"choices": [{"message": {"content": contenido}}], "usage": {}})
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError) as e:
        llm.RemoteLLM(load_settings(), "groq").chat_json("s", "u", {})
    msg = str(e.value)
    assert CLAVE not in msg and "Traceback" not in msg
    assert e.value.__suppress_context__  # "from None": no se encadena la excepcion original (ni su URL ni cabeceras)
    return msg


def test_timeout_de_lectura(monkeypatch):
    assert "tardo demasiado" in _mensaje(monkeypatch, error=TimeoutError("The read operation timed out"))


def test_timeout_de_conexion(monkeypatch):
    assert "tardo demasiado" in _mensaje(monkeypatch, error=urllib.error.URLError(socket.timeout("timed out")))


def test_respuesta_que_no_es_json(monkeypatch):
    assert "JSON invalido" in _mensaje(monkeypatch, contenido="Claro, aqui tiene la respuesta: {checks: ")


def test_api_caida_sin_conexion(monkeypatch):
    msg = _mensaje(monkeypatch, error=urllib.error.URLError(ConnectionRefusedError(10061, "conexion rechazada")))
    assert "No se pudo conectar" in msg


def test_api_caida_error_del_servidor(monkeypatch):
    err = urllib.error.HTTPError("https://api.groq.com", 503, "Service Unavailable", {}, io.BytesIO(b'{"error": "down"}'))
    msg = _mensaje(monkeypatch, error=err)
    assert "error 503" in msg and "down" not in msg


def test_clave_rechazada(monkeypatch):
    err = urllib.error.HTTPError("https://api.groq.com", 401, "Unauthorized", {}, io.BytesIO(b""))
    assert "rechazo la clave" in _mensaje(monkeypatch, error=err)


def test_sin_clave_avisa_antes_de_llamar(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Falta GROQ_API_KEY"):
        llm.RemoteLLM(load_settings(), "groq").start()
