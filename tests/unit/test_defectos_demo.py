"""Defectos hallados por eval/ (docs/decisiones.md §4): citas 【n】, reintento ante 429 y llamada cortada a media frase."""
import io
import json
import urllib.error
from types import SimpleNamespace

from llamadas import auditor, llm
from llamadas.chat.engine import ChatEngine
from llamadas.config import load_settings

HITS = [SimpleNamespace(body="x"), SimpleNamespace(body="y")]


def test_citas_de_ancho_completo_se_reconocen():
    clean, warns, cited = ChatEngine.verify("Atiende de lunes a viernes 【1】 y cierra los domingos【2】.", HITS)
    assert clean == "Atiende de lunes a viernes [1] y cierra los domingos [2]." and cited == {1, 2} and not warns


def test_cita_de_ancho_completo_inexistente_se_quita():
    clean, warns, cited = ChatEngine.verify("Dato 【5】.", HITS)
    assert "5" not in clean and not cited and "no existe" in warns[0]


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *a):
        return False


def _srv(monkeypatch, fallos):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    esperas, intentos = [], []
    ok = {"choices": [{"message": {"content": '{"checks": []}'}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}

    def urlopen(req, timeout=None):
        intentos.append(1)
        if len(intentos) <= fallos:
            raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(b""))
        return _Resp(ok)
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(llm.time, "sleep", esperas.append)
    return llm.RemoteLLM(load_settings(), "groq"), esperas, intentos


def test_429_se_reintenta_con_espera_creciente(monkeypatch):
    srv, esperas, intentos = _srv(monkeypatch, fallos=2)
    data, meta = srv.chat_json("s", "u", {})
    assert data == {"checks": []} and len(intentos) == 3 and meta["retries"] == 2 and esperas == [4, 8]


def test_429_persistente_se_rinde_con_mensaje_legible(monkeypatch):
    srv, esperas, intentos = _srv(monkeypatch, fallos=99)
    try:
        srv.chat_json("s", "u", {})
        assert False, "debio fallar"
    except RuntimeError as e:
        assert "429" in str(e) and len(intentos) == 3


def test_ultima_frase_sin_punto_es_senal_de_corte():
    assert auditor._ends_open([{"text": "Le queda agendada la cita para el lunes con"}])
    assert not auditor._ends_open([{"text": "Que tenga un buen día."}])
    assert not auditor._ends_open([{"text": "¿Necesita algo más?"}])
    assert not auditor._ends_open([])


def test_429_con_espera_larga_no_se_reintenta_y_avisa_de_la_cuota(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    intentos, esperas = [], []

    def urlopen(req, timeout=None):
        intentos.append(1)
        raise urllib.error.HTTPError(req.full_url, 429, "x", {"Retry-After": "182"}, io.BytesIO(b""))
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(llm.time, "sleep", esperas.append)
    try:
        llm.RemoteLLM(load_settings(), "groq").chat_json("s", "u", {})
        assert False, "debio fallar"
    except RuntimeError as e:
        assert "cuota" in str(e) and "3 min" in str(e) and len(intentos) == 1 and not esperas
