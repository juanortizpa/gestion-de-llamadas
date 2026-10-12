"""Panel de quejas: deteccion en transcripciones (sinteticas, sin PII) y registro local en data/quejas.json."""
import json
from datetime import date, timedelta

from llamadas.complaints import (delete_complaint, detect, dismiss_suggestion, list_complaints, save_complaint,
                                 suggestions)
from llamadas.config import Settings, load_settings

FRASES = ["quiero poner una queja", "pesimo servicio", "queja"]


def turns(*pairs):
    return [{"turn_id": i, "speaker": spk, "start": 10.0 * i, "text": txt} for i, (spk, txt) in enumerate(pairs, 1)]


def tmp_settings(tmp_path):
    base = load_settings()
    return Settings(raw={**base.raw, "paths": {**base.raw["paths"], "data_dir": str(tmp_path)}}, lex=base.lex,
                    rubric=base.rubric, agents=[])


def test_detecta_queja_del_cliente_con_cita_literal():
    tr = turns(("ASESOR", "Buenos días, ¿en qué le puedo servir?"),
               ("CLIENTE", "Buenas. Quiero poner una queja, llevo una hora esperando."))
    hits = detect(tr, FRASES)
    assert len(hits) == 1 and hits[0]["turn_id"] == 2 and hits[0]["start"] == 20.0
    assert hits[0]["cita"] == "Quiero poner una queja, llevo una hora esperando."


def test_frases_del_asesor_no_cuentan():
    tr = turns(("ASESOR", "Si desea poner una queja puede escribirnos."), ("CLIENTE", "No, gracias, todo bien."))
    assert detect(tr, FRASES) == []


def test_ignora_tildes_y_mayusculas_y_exige_palabra_completa():
    assert detect(turns(("CLIENTE", "¡Qué PÉSIMO servicio!")), FRASES)[0]["frases"] == ["pesimo servicio"]
    assert detect(turns(("CLIENTE", "Se quejaba de la vecina, pero eso no importa.")), FRASES) == []


def test_registro_plazo_por_prioridad_y_cierre(tmp_path):
    s = tmp_settings(tmp_path)
    hoy = date.today()
    q = save_complaint({"usuario": "Paciente Prueba", "prioridad": "alta", "fecha": hoy.isoformat(), "categoria": "trato"}, s)
    assert q["id"] == "Q-0001" and q["estado"] == "abierta" and q["plazo"] == (hoy + timedelta(days=3)).isoformat()
    q2 = save_complaint({**q, "estado": "cerrada", "respuesta": "Se llamó al usuario"}, s)
    assert q2["id"] == "Q-0001" and q2["cerrada_el"] == hoy.isoformat() and q2["creada"] == q["creada"]
    assert save_complaint({**q2, "estado": "en_gestion"}, s)["cerrada_el"] == ""
    assert save_complaint({"usuario": "Otro"}, s)["id"] == "Q-0002"
    assert len(list_complaints(s)) == 2
    assert delete_complaint("Q-0001", s) and not delete_complaint("Q-0001", s)
    assert [q["id"] for q in list_complaints(s)] == ["Q-0002"]


def test_valores_invalidos_se_corrigen(tmp_path):
    s = tmp_settings(tmp_path)
    q = save_complaint({"prioridad": "urgentisima", "estado": "x", "categoria": "nada", "fecha": "ayer", "documento": "1" * 50}, s)
    assert (q["prioridad"], q["estado"], q["categoria"]) == ("media", "abierta", "otro")
    assert q["fecha"] == date.today().isoformat() and len(q["documento"]) == 20


def test_vencida_solo_si_no_esta_cerrada(tmp_path):
    s = tmp_settings(tmp_path)
    ayer = (date.today() - timedelta(days=1)).isoformat()
    save_complaint({"usuario": "A", "plazo": ayer}, s)
    save_complaint({"usuario": "B", "plazo": ayer, "estado": "cerrada"}, s)
    assert [q["vencida"] for q in list_complaints(s)] == [True, False]


def test_sugerencias_desde_resultados(tmp_path):
    s = tmp_settings(tmp_path)
    res = tmp_path / "results"
    res.mkdir()
    queja = {"turns": turns(("CLIENTE", "Quiero poner una queja por el mal servicio."))}
    for cid in ("100", "300"):
        (res / f"{cid}.transcript.json").write_text(json.dumps(queja), encoding="utf-8")
    (res / "100.audit.json").write_text(json.dumps({"call": {"call_id": "100", "received_date": "20261010", "duration_s": 95.0}}), encoding="utf-8")
    (res / "200.transcript.json").write_text(json.dumps({"turns": turns(("CLIENTE", "Gracias, muy amable."))}), encoding="utf-8")
    sug = suggestions(s)
    assert [x["llamada"] for x in sug] == ["100", "300"] and sug[0]["fecha"] == "2026-10-10"
    dismiss_suggestion("100", s)  # el auditor dice que no es queja
    save_complaint({"usuario": "C", "llamada": "300"}, s)  # ya registrada
    assert suggestions(s) == []
