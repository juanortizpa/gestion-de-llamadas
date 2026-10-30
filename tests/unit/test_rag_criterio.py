"""Busqueda del Asistente: una palabra de criterio en una pregunta sobre la conversacion no debe desplazar la transcripcion."""
from datetime import date

from llamadas.chat import retrieve, router

CFG = {"min_cosine": 0.8, "context_tokens": 1100, "top_k": 6, "max_per_call": 2}


class _Store:
    """La ventana con la respuesta sale 1.a por palabras; el fragmento de criterio Z1 de otra llamada, 2.o."""
    CHUNKS = {
        1: {"call_id": "A", "kind": "ventana", "criterion": None, "ctx": "", "body": "tiene que traer la creatinina",
            "t0": 0.0, "t1": 9.0, "turn0": 0, "turn1": 2},
        2: {"call_id": "B", "kind": "criterio", "criterion": "Z1", "ctx": "", "body": "Z1 confirma la cita y la preparacion",
            "t0": None, "t1": None, "turn0": None, "turn1": None},
    }

    def lexical(self, query, allowed, lim):
        return [(1, 1.0), (2, 0.9)]

    def chunks_by_ids(self, ids):
        return {i: self.CHUNKS[i] for i in ids}


def _primero(pregunta):
    p = router.parse(pregunta, today=date(2026, 10, 30), known_ids=[], agents=[])
    assert p.filters.criteria == ["Z1"]
    return retrieve.search(_Store(), p, None, None, CFG)[0].kind


def test_pregunta_sobre_la_conversacion_no_sube_el_criterio():
    assert _primero("¿Qué preparación se le da al paciente para tomografía con contraste?") == "ventana"


def test_pregunta_sobre_la_evaluacion_si_sube_el_criterio():
    assert _primero("¿En qué llamadas falló la preparación?") == "criterio"
