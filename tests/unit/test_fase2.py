"""Fase 2: reglas probadas con llamadas SIMULADAS con fallos conocidos (D-19) + metricas."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synthetic"))
from builder import A, C, GOOD, build, variant  # noqa: E402

from llamadas.audit import audit_transcript  # noqa: E402
from llamadas.config import Settings, load_settings  # noqa: E402


def audit(turns, **kw):
    return audit_transcript(build(turns, **kw))


def sc(au, code):
    return au["criteria"][code]["score"]


def test_llamada_buena_cumple_lo_determinista():
    au = audit(GOOD)
    assert au["call_type"]["type"] == "nueva_cita"
    for code in ("P1", "P2", "V1", "G1", "Z1", "Z2"):
        assert sc(au, code) == 1, (code, au["criteria"][code])
    assert au["critical_error"]["status"] == "none"
    assert au["synthetic"] is True


def test_sin_saludo_ni_entidad():
    au = audit(variant(GOOD, replace={0: "Sí, dígame, ¿qué necesita?"}))
    assert sc(au, "P1") == 0
    subs = {s["id"]: s["passed"] for s in au["criteria"]["P1"]["sub_checks"]}
    assert subs["saludo"] is False and subs["entidad"] is False


def test_sin_nombre_del_asesor():
    au = audit(variant(GOOD, replace={0: "Angiografia de Occidente, buenos días."}))
    subs = {s["id"]: s["passed"] for s in au["criteria"]["P1"]["sub_checks"]}
    assert subs["saludo"] and subs["entidad"] and subs["nombre_asesor"] is False
    assert sc(au, "P1") == 0


def test_nunca_usa_el_nombre_del_cliente():
    au = audit(variant(GOOD, replace={4: "Gracias. ¿Tiene la orden médica?"}))
    assert sc(au, "P2") == 0


def test_no_pide_documento_y_agenda_genera_candidato_e1():
    au = audit(variant(GOOD, drop=[2, 3]))
    assert sc(au, "V1") == 0
    assert au["critical_error"]["status"] == "candidate_pending_review"
    assert any(f["code"] == "E1.a" for f in au["critical_error"]["findings"])
    # un candidato NUNCA fija la nota en 0: queda para revision humana
    assert au["score"]["percent_final"] != 0 and au["human_review"]["required"]


def test_documento_sin_digitos_transcritos_queda_pendiente_no_falla():
    au = audit(variant(GOOD, replace={3: "Sí, ese es mi número."}))
    assert sc(au, "V1") is None
    assert "V1" in au["score"]["pending"]


def test_hold_de_90_segundos_falla_g1():
    t = variant(GOOD, gap={7: 90})
    au = audit(t, recorded=[{"kind": "grabado_en_llamada", "start": 0, "end": 0}])
    assert sc(au, "G1") == 0
    assert au["metrics"]["longest_hold_s"] >= 85


def test_hold_de_30_segundos_cumple_g1():
    au = audit(variant(GOOD, gap={7: 30}))
    assert sc(au, "G1") == 1
    assert 25 <= au["metrics"]["longest_hold_s"] <= 35


def test_silencio_largo_sin_anunciar_falla_g2():
    au = audit(variant(GOOD, replace={6: "Un momento y le confirmo la disponibilidad."}, gap={7: 40}))
    # con anuncio es hold (G1), no tiempo muerto
    assert au["metrics"]["dead_air_total_s"] == 0
    au2 = audit(variant(GOOD, replace={6: "Estoy buscando en el sistema."}, gap={7: 40}))
    assert sc(au2, "G2") == 0 and au2["metrics"]["dead_air_longest_s"] >= 39


def test_sin_pregunta_de_algo_mas_ni_despedida():
    au = audit(variant(GOOD, replace={10: "Listo, listo."}))
    assert sc(au, "Z2") == 0


def test_solo_despedida_sin_algo_mas():
    t = variant(GOOD, replace={10: "Que tenga una buena tarde, hasta luego."})
    au = audit(t)
    subs = {s["id"]: s["passed"] for s in au["criteria"]["Z2"]["sub_checks"]}
    assert subs["despedida_cordial"] and subs["pregunta_si_requiere_algo_mas"] is False
    assert sc(au, "Z2") == 0          # DECIDIDO (usuario, 2026-10-06): preguntar "algo mas" es obligatorio


def test_z1_falta_hora_y_soportes():
    au = audit(variant(GOOD, replace={7: "Gracias por esperar. Le queda agendada la cita con el doctor Ramírez en la calle 5.",
                                      8: "Listo, ya quedó."}))
    subs = {s["id"]: s["passed"] for s in au["criteria"]["Z1"]["sub_checks"]}
    assert sc(au, "Z1") == 0
    assert subs["hora"] is False and subs["soportes_a_llevar"] is False and subs["cita_agendada"]


def test_lenguaje_inadecuado_falla_c2():
    au = audit(variant(GOOD, replace={4: "Gracias señora Marta Pérez, qué pereza esta llamada. ¿Tiene la orden médica?"}))
    assert sc(au, "C2") == 0


def test_cancelacion_no_exige_v2_ni_slots_de_cita():
    t = [(A, "Nueva EPS, buenas tardes, habla Laura Gómez, ¿en qué le puedo servir?", 0),
         (C, "Quiero cancelar una cita que tengo para mañana.", 1),
         (A, "Claro. ¿Me confirma su número de documento?", 1),
         (C, "Es el 1 0 6 2 3 3 1 5 6 5.", 1),
         (A, "Gracias señor Pérez. Listo, la cita queda cancelada. ¿Algo más en que le pueda colaborar? Hasta luego.", 2),
         (C, "No, gracias.", 1)]
    au = audit(t)
    assert au["call_type"]["type"] == "cancelacion"
    assert au["criteria"]["V2"]["applicable"] is False
    assert sc(au, "Z1") == 1 and sc(au, "V1") == 1 and sc(au, "Z2") == 1


def test_llamada_de_informacion_marca_na():
    t = [(A, "Angiografia de Occidente, buenas tardes, habla Laura Gómez, ¿en qué le puedo servir?", 0),
         (C, "Quisiera información sobre el horario de atención.", 1),
         (A, "Atendemos de lunes a viernes de 7 de la mañana a 6 de la tarde. ¿Algo más en que le pueda colaborar? Hasta luego.", 1)]
    au = audit(t)
    assert au["call_type"]["type"] == "informacion"
    assert not au["criteria"]["V1"]["applicable"] and not au["criteria"]["Z1"]["applicable"]


def test_roles_no_fiables_se_reportan_y_marcan_revision():
    au = audit(GOOD, roles_ok=False)
    assert au["human_review"]["required"]
    assert any("roles" in r for r in au["human_review"]["reasons"])


def test_no_speech_no_genera_nota():
    tr = {"status": "no_speech", "call": {"call_id": "X", "duration_s": 100}, "turns": [], "quality": {"warnings": []}}
    au = audit_transcript(tr)
    assert au["status"] == "no_speech" and au["score"]["percent_final"] is None
