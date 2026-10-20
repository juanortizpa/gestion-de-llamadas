"""Vocabulario del dominio construido por entrevista: una IA local le pregunta al usuario (como un test o chat) y va
guardando terminos, contexto y lo que debe esperarse oir. Con eso se arma el `initial_prompt` de Whisper.

Todo vive en data/vocab/knowledge.json (local). El usuario decide si seguir ampliando o dejarlo "listo por ahora".
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from collections import Counter

from .config import Settings, load_settings

AREAS = {
    "entidad": "nombre de la institucion, areas, sedes y direcciones",
    "aseguradoras": "EPS, aseguradoras y convenios que se mencionan",
    "examenes": "examenes, procedimientos, preparaciones y siglas medicas",
    "personas": "nombres de asesores, medicos y otros nombres propios frecuentes",
    "numeros": "como se dictan cedulas, telefonos, codigos de cita y fechas",
    "frases": "frases fijas del guion: saludo, verificacion, despedida, mensajes grabados",
    "pronunciacion": "palabras que suelen transcribirse mal, acentos o muletillas",
    "flujo": "que pasa en una llamada tipica y que debe poder predecirse",
}
CATEGORIES = ["entidad", "sede", "aseguradora", "examen", "persona", "sigla", "medicamento", "lugar", "frase", "otro"]
SCHEMA = {
    "type": "object",
    "properties": {
        "extracted": {"type": "object", "properties": {
            "terms": {"type": "array", "items": {"type": "object", "properties": {
                "term": {"type": "string"}, "category": {"type": "string", "enum": CATEGORIES},
                "variants": {"type": "array", "items": {"type": "string"}}, "note": {"type": "string"}},
                "required": ["term", "category"]}},
            "context": {"type": "array", "items": {"type": "string"}},
            "predict": {"type": "array", "items": {"type": "string"}}},
            "required": ["terms", "context", "predict"]},
        "area": {"type": "string", "enum": list(AREAS)},
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "why": {"type": "string"},
    },
    "required": ["extracted", "area", "question", "options", "why"],
}
SYSTEM = (
    "Eres un entrevistador experto en reconocimiento de voz (Whisper) para llamadas de atencion al cliente en español. "
    "Entrevistas al usuario, UNA pregunta por turno, para construir el vocabulario y contexto que haran la transcripcion exacta.\n"
    "Reglas:\n"
    "1. De la ULTIMA respuesta extrae SOLO lo que el usuario dijo, sin inventar. terms = palabras, siglas o nombres que Whisper "
    "podria escribir mal (variants = como podrian transcribirse mal; note = aclaracion corta). context = hechos utiles del dominio. "
    "predict = que se espera oir o predecir (formatos de numeros, frases fijas, orden de la llamada). Si no hay respuesta, extrae listas vacias.\n"
    "2. Formula una pregunta nueva, concreta y corta, sobre el area menos cubierta; nunca repitas una pregunta previa ni pidas terminos ya conocidos.\n"
    "3. Ofrece de 3 a 6 opciones de respuesta probables y breves (el usuario tambien puede escribir libremente).\n"
    "4. Si hay palabras dudosas detectadas en transcripciones reales, preguntale que significan o como se escriben bien.\n"
    "5. why = en una frase, para que sirve la respuesta.\n"
    "Responde SOLO con el JSON del esquema."
)
_LOCK = threading.RLock()
_LLM = {"obj": None, "last": 0.0, "reaper": None}


def _empty() -> dict:
    return {"terms": [], "context": [], "predict": [], "qa": [], "areas": [], "pending": None, "status": "active", "updated": None}


def _path(s: Settings):
    return s.data_dir / "vocab" / "knowledge.json"


def load(s: Settings | None = None) -> dict:
    s = s or load_settings()
    p = _path(s)
    if p.exists():
        try:
            return {**_empty(), **json.loads(p.read_text(encoding="utf-8"))}
        except ValueError:
            pass
    return _empty()


def save(k: dict, s: Settings | None = None) -> None:
    s = s or load_settings()
    k["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p = _path(s)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def _clip(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def merge(k: dict, ex: dict) -> dict:
    """Incorpora lo extraido sin duplicados (terminos por texto normalizado). Devuelve lo realmente nuevo."""
    new = {"terms": [], "context": [], "predict": []}
    known = {_norm(t["term"]): t for t in k["terms"]}
    for t in (ex.get("terms") or [])[:20]:
        term = _clip(t.get("term") if isinstance(t, dict) else t, 60)
        if len(term) < 2:
            continue
        variants = [v for v in (_clip(x, 60) for x in (t.get("variants") or [])[:6]) if v] if isinstance(t, dict) else []
        variants = [v for v in variants if _norm(v) != _norm(term)]
        cur = known.get(_norm(term))
        if cur:
            cur["variants"] = sorted({*cur.get("variants", []), *variants} - {cur["term"]})
            continue
        item = {"term": term, "category": t.get("category", "otro") if isinstance(t, dict) else "otro",
                "variants": variants, "note": _clip(t.get("note"), 140) if isinstance(t, dict) else ""}
        k["terms"].append(item)
        known[_norm(term)] = item
        new["terms"].append(item)
    for key in ("context", "predict"):
        have = {_norm(x) for x in k[key]}
        for x in (ex.get(key) or [])[:10]:
            x = _clip(x, 220)
            if len(x) >= 4 and _norm(x) not in have:
                k[key].append(x)
                have.add(_norm(x))
                new[key].append(x)
    return new


def weak_words(s: Settings, n: int = 15) -> list[str]:
    """Palabras que Whisper transcribio con poca confianza en llamadas reales y que aun no estan en el vocabulario."""
    known = {_norm(w) for t in load(s)["terms"] for w in t["term"].split()}
    files = sorted((s.data_dir / "cache").glob("*_stt_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
    cnt: Counter = Counter()
    for f in files:
        try:
            for seg in json.loads(f.read_text(encoding="utf-8")):
                for w in seg.get("words", []):
                    word = re.sub(r"[^\wáéíóúñü]", "", str(w.get("w", "")).lower())
                    if len(word) >= 4 and w.get("p", 1) < 0.6 and _norm(word) not in known:
                        cnt[word] += 1
        except (ValueError, OSError):
            continue
    return [w for w, c in cnt.most_common(n) if c >= 2]


# ---------------------------------------------------------------- uso en Whisper
def stt_hints(s: Settings | None = None) -> tuple[str, str]:
    """(initial_prompt, etiqueta de cache). Sin vocabulario: el prompt base y etiqueta vacia (se conserva la cache existente)."""
    s = s or load_settings()
    base = s["stt"]["initial_prompt"]
    terms = [t["term"] for t in load(s)["terms"]]
    if not terms:
        return base, ""
    out, size = [], 0
    for t in terms:                      # Whisper solo lee ~224 tokens del prompt: ~560 caracteres de vocabulario
        if size + len(t) + 2 > 560:
            break
        out.append(t)
        size += len(t) + 2
    prompt = f"{base} Vocabulario: {', '.join(out)}."
    return prompt, "_v" + hashlib.sha1(prompt.encode()).hexdigest()[:8]


# ---------------------------------------------------------------- IA de la entrevista
def _get_llm(s: Settings):
    with _LOCK:
        if _LLM["obj"] is None:
            from .llm import make_llm
            _LLM["obj"] = make_llm(s, s["chat"]["mode"])
        llm = _LLM["obj"]
        if not llm.available():
            raise RuntimeError("No hay IA disponible para la entrevista (falta el modelo local o la clave de la API).")
        llm.start()
        _LLM["last"] = time.time()
        if _LLM["reaper"] is None:
            def loop():
                while True:
                    time.sleep(30)
                    if _LLM["obj"] is not None and getattr(_LLM["obj"], "proc", None) and time.time() - _LLM["last"] > s["chat"]["idle_stop_min"] * 60:
                        _LLM["obj"].stop()
            _LLM["reaper"] = threading.Thread(target=loop, daemon=True)
            _LLM["reaper"].start()
        return llm


def shutdown() -> None:
    """Libera la GPU/RAM de la entrevista (se llama antes de un analisis de llamadas)."""
    with _LOCK:
        if _LLM["obj"] is not None:
            _LLM["obj"].stop()


def _prompt(k: dict, s: Settings) -> str:
    last = k["qa"][-1] if k["qa"] else None
    info = {
        "terminos_ya_conocidos": [t["term"] for t in k["terms"]][-80:],
        "areas_preguntadas_en_orden": k["areas"][-12:],
        "areas_disponibles": AREAS,
        "preguntas_previas": [x["q"] for x in k["qa"]][-10:],
        "palabras_dudosas_en_transcripciones_reales": weak_words(s),
        "ultima_pregunta": last["q"] if last else None,
        "ultima_respuesta": last["a"] if last else None,
    }
    return json.dumps(info, ensure_ascii=False)


def turn(s: Settings | None = None, answer: str | None = None, *, skip: bool = False, llm=None) -> dict:
    """Un turno de la entrevista: registra la respuesta (si hay), extrae lo aprendido y devuelve la siguiente pregunta."""
    s = s or load_settings()
    with _LOCK:
        k = load(s)
        pend = k.get("pending")
        added = {"terms": [], "context": [], "predict": []}
        if pend and (answer or skip):
            k["qa"].append({"q": pend["question"], "a": "(omitida)" if skip else _clip(answer, 1000), "area": pend.get("area")})
            k["qa"] = k["qa"][-200:]
        elif pend and not (answer or skip):
            return state(s)                 # sin respuesta nueva: se muestra la pregunta pendiente
        llm = llm or _get_llm(s)
        data, _ = llm.chat_json(SYSTEM, _prompt(k, s), SCHEMA)
        if k["qa"] and not skip and pend:
            added = merge(k, data.get("extracted") or {})
        q = _clip(data.get("question"), 300)
        if not q:
            raise RuntimeError("La IA no pudo formular la siguiente pregunta; intente de nuevo.")
        area = data.get("area") if data.get("area") in AREAS else "flujo"
        k["areas"].append(area)
        k["areas"] = k["areas"][-60:]
        opts = [o for o in (_clip(o, 90) for o in (data.get("options") or [])[:6]) if o]
        k["pending"] = {"question": q, "options": opts, "why": _clip(data.get("why"), 200), "area": area}
        k["status"] = "active"
        save(k, s)
        out = state(s)
        out["added"] = added
        return out


def state(s: Settings | None = None) -> dict:
    s = s or load_settings()
    k = load(s)
    covered = Counter(a for a in k["areas"])
    return {**k, "qa": k["qa"][-6:], "answers": len(k["qa"]), "areas_info": AREAS,
            "coverage": {a: covered.get(a, 0) for a in AREAS}, "prompt": stt_hints(s)[0]}


def set_status(s: Settings, status: str) -> dict:
    with _LOCK:
        k = load(s)
        k["status"] = "paused" if status == "paused" else "active"
        save(k, s)
    return state(s)


def edit(s: Settings, action: str, kind: str = "terms", index: int = -1, value: str = "") -> dict:
    """Edicion manual: add (termino), remove (cualquier lista), reset (borra todo)."""
    with _LOCK:
        k = load(s)
        if action == "reset":
            k = _empty()
        elif action == "add" and value.strip():
            merge(k, {"terms": [{"term": value, "category": "otro"}]})
        elif action == "remove" and kind in ("terms", "context", "predict") and 0 <= index < len(k[kind]):
            k[kind].pop(index)
        save(k, s)
    return state(s)
