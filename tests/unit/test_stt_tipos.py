"""faster-whisper entrega los tiempos como numpy.float64. Si llegan asi a las reglas, una comparacion (G2: silencio <= 30 s)
da numpy.bool_ y la auditoria no se puede guardar en JSON: el primer analisis de una llamada con silencios largos fallaba."""
import json
from types import SimpleNamespace

import numpy as np

from llamadas import stt
from llamadas.config import load_settings


class _Modelo:
    def transcribe(self, audio, **kw):
        w = SimpleNamespace(word=" Hola", start=np.float64(1.25), end=np.float64(1.9), probability=np.float32(0.91))
        seg = SimpleNamespace(start=np.float64(1.25), end=np.float64(1.9), text=" Hola", words=[w])
        return [seg], None


def test_la_transcripcion_entrega_floats_de_python(monkeypatch):
    monkeypatch.setattr(stt, "_get_model", lambda cfg: _Modelo())
    seg = stt.transcribe(np.zeros(16000, np.float32), load_settings())[0]
    valores = [seg["start"], seg["end"], seg["words"][0]["s"], seg["words"][0]["e"], seg["words"][0]["p"]]
    assert all(type(v) is float for v in valores)
    json.dumps({"g2_ok": seg["end"] <= 30.0})  # con numpy.float64 esto lanzaba TypeError
