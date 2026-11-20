"""Si la IA local no responde a tiempo, el proceso se apaga: antes quedaba huerfano ocupando RAM y el puerto."""
import pytest

from llamadas import llm
from llamadas.config import load_settings


class _Proceso:
    def __init__(self, *a, **kw):
        self.terminado = False

    def poll(self):
        return 0 if self.terminado else None

    def terminate(self):
        self.terminado = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminado = True


def test_si_no_arranca_a_tiempo_se_apaga(monkeypatch):
    srv = llm.LlamaServer(load_settings(), "rapido")
    procesos = []
    monkeypatch.setattr(srv, "available", lambda: True)
    monkeypatch.setattr(srv, "healthy", lambda: False)
    monkeypatch.setattr(llm.subprocess, "Popen", lambda *a, **kw: procesos.append(_Proceso()) or procesos[-1])
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="no respondio a tiempo"):
        srv.start(timeout_s=0)
    assert procesos and procesos[0].terminado and srv.proc is None
