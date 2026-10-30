"""Correo (con SMTP simulado), comentarios sobre la app y panel de quejas (pistas y estadisticas)."""
import dataclasses
import time

import pytest

from llamadas import complaints, feedback, notify
from llamadas.config import load_settings


@pytest.fixture
def S(tmp_path):
    s = load_settings()
    return dataclasses.replace(s, raw={**s.raw, "paths": {**s.raw["paths"], "data_dir": str(tmp_path)}})


@pytest.fixture
def smtp(monkeypatch):
    sent = []
    for k, v in {"SMTP_HOST": "smtp.test", "SMTP_FROM": "app@test.co", "SMTP_USER": "", "SMTP_PASSWORD": ""}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(notify, "send_mail", lambda subject, body, to: sent.append((subject, body, to)))
    return sent


def test_correo_sin_smtp_no_envia_ni_falla(S, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    notify.save_config(S, "a@b.co", {})
    assert notify.notify(S, "analisis", "x", "y") is False


def test_correo_destinatarios_validos_eventos_y_no_repite(S, smtp):
    d = notify.save_config(S, "uno@b.co, malo, dos@b.co;uno@b.co", {"queja_vencida": False})
    assert d["to"][:2] == ["uno@b.co", "dos@b.co"] and d["events"]["queja_vencida"] is False
    assert notify.notify(S, "analisis", "Resumen", "cuerpo", key="k1") is True
    assert notify.notify(S, "analisis", "Resumen", "cuerpo", key="k1") is False         # misma clave: una sola vez
    assert notify.notify(S, "queja_vencida", "x", "y") is False                          # evento desactivado
    assert len(smtp) == 1 and smtp[0][2][:2] == ["uno@b.co", "dos@b.co"]
    assert notify.status(S)["history"][0]["asunto"] == "Resumen"


def test_aviso_de_queja_vencida_una_vez(S, smtp):
    notify.save_config(S, "a@b.co", {})
    complaints.save_complaint({"usuario": "X", "descripcion": "demora", "plazo": "2020-01-01"}, S)
    notify.periodic_check(S)
    notify.periodic_check(S)
    assert [m for m in smtp if "vencida" in m[0]].__len__() == 1
    assert "documento" not in smtp[0][1].lower()                                         # sin datos personales


def test_comentarios(S, smtp):
    with pytest.raises(ValueError):
        feedback.add({"mensaje": "x"}, S)
    c = feedback.add({"tipo": "error", "mensaje": "El boton no responde", "nombre": "Ana"}, S)
    assert c["id"] == "C-0001" and c["estado"] == "nuevo" and feedback.add({"mensaje": "otro comentario"}, S)["id"] == "C-0002"
    assert feedback.set_estado("C-0001", "resuelto", S) and feedback.list_all(S)["items"][1]["estado"] == "resuelto"
    assert feedback.delete("C-0002", S) and len(feedback.list_all(S)["items"]) == 1
    time.sleep(0.2)


def test_pistas_de_queja_y_estadisticas(S):
    assert complaints.guess("llevo dos horas en espera y es una demora") == ("espera", "media")
    assert complaints.guess("voy a poner una queja en la supersalud por el cobro") == ("cobros", "alta")
    assert complaints.guess("hola buenas") == ("otro", "media")
    complaints.save_complaint({"usuario": "A", "categoria": "espera", "asesor": "Ana", "estado": "cerrada", "fecha": "2026-10-01", "plazo": "2026-10-10"}, S)
    complaints.save_complaint({"usuario": "B", "categoria": "espera", "asesor": "Ana"}, S)
    st = complaints.stats(S)
    assert st["total"] == 2 and st["por_categoria"][0]["n"] == 2 and st["por_asesor"][0]["clave"] == "Ana" and st["cerradas"] == 1
