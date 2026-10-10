"""Llamadas SIMULADAS (sinteticas, sin PII) con fallos conocidos para probar las reglas (D-19).
Nunca cuentan como validacion contra el golden set real: llevan synthetic=True."""
from __future__ import annotations

A, C = "ASESOR", "CLIENTE"

GOOD = [
    (A, "Angiografia de Occidente, buenos días, habla Laura Gómez, ¿en qué le puedo servir?", 0),
    (C, "Buenos días, necesito una cita para una ecografía abdominal.", 1),
    (A, "Con gusto señora. ¿Me confirma su número de documento?", 1),
    (C, "Es el 1 0 6 2 3 3 1 5 6 5.", 1),
    (A, "Gracias, señora Marta Pérez. ¿Tiene la orden médica?", 1),
    (C, "Sí, la tengo aquí.", 1),
    (A, "Permítame un momento por favor.", 1),
    (A, "Gracias por esperar. Le queda agendada la cita para el lunes 12 de octubre a las 8 de la mañana en la sede de la calle 5 con carrera 38, con el doctor Ramírez.", 20),
    (A, "Debe presentarse 20 minutos antes con su cédula, la orden médica y la autorización. Recuerde ir en ayuno de 8 horas.", 1),
    (C, "Perfecto, muchas gracias.", 1),
    (A, "¿Necesita algo más en que le pueda colaborar? Que tenga una buena tarde, hasta luego.", 1),
]


def build(turns, recorded=None, duration=None, roles_ok=True, ivr=True):
    """turns: [(rol, texto, pausa_previa_s)]. Duracion de cada turno = 0.35 s por palabra."""
    t = 40.0 if ivr else 0.0
    out = []
    for i, (spk, text, gap) in enumerate(turns, 1):
        t += gap
        d = max(1.5, 0.35 * len(text.split()))
        out.append({"turn_id": i, "speaker": spk, "start": round(t, 2), "end": round(t + d, 2), "text": text, "avg_prob": 0.9})
        t += d
    dur = duration or round(t + 3, 1)
    rec = [{"kind": "ivr_inicial", "start": 0.0, "end": 40.0}] if ivr else []
    rec += recorded or []
    return {
        "schema_version": "synthetic", "synthetic": True, "status": "completed",
        "call": {"call_id": "SYN", "source_file": "sintetica", "duration_s": dur},
        "quality": {"warnings": [] if roles_ok else ["diarizacion_sospechosa_un_rol_casi_sin_habla"],
                    "role_confidence": 0.9 if roles_ok else 0.0},
        "recorded_intervals": rec, "turns": out,
    }


def variant(base, replace=None, drop=None, gap=None):
    """Copia de `base` modificando textos (por indice), quitando turnos o cambiando pausas."""
    turns = [list(x) for x in base]
    for i, txt in (replace or {}).items():
        turns[i][1] = txt
    for i, g in (gap or {}).items():
        turns[i][2] = g
    keep = [tuple(x) for i, x in enumerate(turns) if i not in (drop or [])]
    return keep
