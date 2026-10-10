"""Pruebas de Fase 1 con transcripciones SINTETICAS (sin PII)."""
from llamadas.config import load_settings
from llamadas.diarize import keep_intervals
from llamadas.recorded import detect_recorded
from llamadas.roles import assign_roles
from llamadas.textutil import normalize
from llamadas.transcript import assign_speakers, build_turns

S = load_settings()


def seg(t0, t1, text):
    return {"start": t0, "end": t1, "text": text}


def test_normalize():
    assert normalize("¿Cuál es el número, señor Muñoz?") == "cual es el numero senor munoz"


def test_ivr_inicial_tolera_digitos_y_texto_mal_transcrito():
    segs = [
        seg(2, 8, "Señor usuario, para su mayor comodidad, comuníquese por favor a nuestro nuevo número de WhatsApp"),
        seg(9, 12, "300 926 6000."),
        seg(13, 20, "recolecta sus contrapartidas cosas raras del politica de privacidad"),
        seg(21, 30, "Angiografia de Occidente recolecta sus datos personales de acuerdo a la política de privacidad y tratamiento de información de la entidad"),
        seg(50, 54, "Si continúa con la llamada, se entenderá que acepta el tratamiento de datos personales."),
        seg(73, 77, "Nueva EPS, buenas tardes, ¿en qué le puedo servir?"),
        seg(78, 82, "Buenas tardes, quiero una cita para una radiografía."),
    ]
    rec = detect_recorded(segs, S)
    assert rec and rec[0]["kind"] == "ivr_inicial"
    assert 54 <= rec[0]["end"] <= 55
    assert not any(r["kind"] == "grabado_en_llamada" for r in rec)


def test_hold_loop_detectado_y_saludo_del_asesor_no():
    loop = "Gracias por comunicarse con Angiografia de Occidente. Nuestro personal está a su servicio."
    segs = [seg(0, 3, "Angiografia de Occidente, buen día, ¿en qué le puedo servir?"),
            seg(4, 8, "Quiero una cita."), seg(9, 12, "Permítame un momento, no me cuelgue.")]
    segs += [seg(20 + 25 * i, 25 + 25 * i, loop) for i in range(4)]
    segs += [seg(130, 133, "Gracias por esperar, ya le confirmo.")]
    rec = detect_recorded(segs, S)
    kinds = [r["kind"] for r in rec]
    assert kinds == ["grabado_en_llamada"]
    assert rec[0]["start"] == 20 and rec[0]["end"] == 100


def test_keep_intervals():
    rec = [{"start": 0, "end": 40}, {"start": 90, "end": 300}]
    assert keep_intervals(320, rec) == [(40, 90), (300, 320)]


def test_alineacion_y_turnos():
    words = [{"w": " Buenos", "s": 0.0, "e": 0.4, "p": 1}, {"w": " días", "s": 0.4, "e": 0.8, "p": 1},
             {"w": " hola", "s": 2.0, "e": 2.4, "p": 1}]
    diar = [{"start": 0.0, "end": 1.0, "spk": 0}, {"start": 1.8, "end": 2.6, "spk": 1}]
    assign_speakers(words, diar)
    turns = build_turns(words, 1.5)
    assert [t["spk"] for t in turns] == [0, 1]
    assert turns[0]["text"] == "Buenos días"


def test_roles_por_contenido_no_por_orden():
    turns = [
        {"spk": 1, "text": "Buenas tardes, quiero una cita para una radiografía"},
        {"spk": 0, "text": "Angiografia de Occidente, buen día, ¿en qué le puedo servir? Permítame el número de documento"},
        {"spk": 1, "text": "Es para mi mamá"},
        {"spk": 0, "text": "Le queda agendada. ¿Algo más en que le pueda colaborar?"},
    ]
    r = assign_roles(turns, S)
    assert r["roles"] == {0: "ASESOR", 1: "CLIENTE"} and r["confidence"] > 0.5


def test_roles_con_cluster_extra_de_cliente_y_otro_del_asesor():
    turns = [
        {"spk": 0, "text": "Angiografia de Occidente, buen día, ¿en qué le puedo servir?"},
        {"spk": 1, "text": "Quiero una cita para una ecografía"},
        {"spk": 2, "text": "Permítame el número de documento, le confirmo la cita, debe presentarse con la orden médica"},
        {"spk": 1, "text": "Es para mi mamá"},
    ]
    r = assign_roles(turns, S)
    assert r["roles"][0] == "ASESOR" and r["roles"][2] == "ASESOR" and r["roles"][1] == "CLIENTE"
