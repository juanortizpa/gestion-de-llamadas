"""B3: prueba el LLM local (llama-server) con sub-checks sí/no + cita literal sobre transcripciones reales.
Mide latencia, validez del JSON y si las citas existen literalmente en la transcripción."""
import json
import sys
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "src"))
from llamadas.textutil import normalize  # noqa: E402

QUESTIONS = [
    ("P1_saludo", "¿El ASESOR saluda cordialmente (buenos días/tardes/noches o similar)?"),
    ("P1_entidad", "¿El ASESOR menciona el nombre de la entidad (Angiografía de Occidente o Nueva EPS)?"),
    ("P1_nombre", "¿El ASESOR dice su propio nombre al presentarse?"),
    ("V1_documento", "¿El ASESOR solicita el número de documento/cédula del paciente?"),
    ("V2_examen", "¿El ASESOR pregunta o verifica el tipo de examen, la orden médica o requisitos previos?"),
    ("Z1_fecha_hora", "¿El ASESOR confirma al cliente la fecha y la hora de la cita?"),
    ("Z1_direccion", "¿El ASESOR indica la dirección o sede donde será la cita?"),
    ("Z1_soportes", "¿El ASESOR indica qué documentos o soportes debe llevar el paciente?"),
    ("Z2_algo_mas", "¿El ASESOR pregunta si el cliente necesita algo más?"),
    ("Z2_despedida", "¿El ASESOR se despide cordialmente?"),
]
SCHEMA = {
    "type": "object",
    "properties": {"checks": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "passed": {"type": "boolean"},
                       "turn_id": {"type": "integer"}, "quote": {"type": "string"}},
        "required": ["id", "passed", "turn_id", "quote"]}}},
    "required": ["checks"],
}


def ask(call_id: str) -> dict:
    tr = json.loads((root / "data" / "results" / f"{call_id}.transcript.json").read_text(encoding="utf-8"))
    convo = "\n".join(f"[{t['turn_id']}] {t['speaker']}: {t['text']}" for t in tr["turns"])
    qs = "\n".join(f"- {i}: {q}" for i, q in QUESTIONS)
    system = ("Eres un auditor de calidad de llamadas de un centro de atencion en español. Respondes SOLO con JSON. "
              "Para cada pregunta devuelve passed=true solo si hay evidencia clara en la transcripcion, con el turn_id y "
              "una CITA LITERAL copiada de ese turno (maximo 15 palabras). Si no hay evidencia: passed=false, turn_id=0, quote=\"\". "
              "La transcripcion puede tener errores de reconocimiento de voz; los roles ASESOR/CLIENTE pueden estar mal asignados en algunos turnos.")
    user = f"TRANSCRIPCION:\n{convo}\n\nPREGUNTAS:\n{qs}\n\nDevuelve {{\"checks\":[...]}} con una entrada por pregunta."
    body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0, "seed": 1, "max_tokens": 900, "cache_prompt": True,
            "response_format": {"type": "json_object", "schema": SCHEMA}}
    req = urllib.request.Request("http://127.0.0.1:8089/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    resp = json.load(urllib.request.urlopen(req, timeout=900))
    el = time.time() - t
    txt = resp["choices"][0]["message"]["content"]
    u = resp.get("usage", {})
    out = {"call": call_id, "secs": round(el, 1), "prompt_tok": u.get("prompt_tokens"), "gen_tok": u.get("completion_tokens")}
    try:
        checks = json.loads(txt)["checks"]
        out["json_ok"] = True
    except Exception:
        out["json_ok"] = False
        out["raw"] = txt[:300]
        return out
    by_turn = {t["turn_id"]: normalize(t["text"]) for t in tr["turns"]}
    rows = []
    for c in checks:
        q = normalize(c.get("quote", ""))
        quote_ok = (c["turn_id"] in by_turn and q != "" and q in by_turn[c["turn_id"]]) if c["passed"] else None
        rows.append((c["id"], c["passed"], c["turn_id"], quote_ok, c.get("quote", "")[:70]))
    out["checks"] = rows
    return out


if __name__ == "__main__":
    for cid in sys.argv[1:]:
        r = ask(cid)
        print(f"== {cid}: {r['secs']}s prompt={r['prompt_tok']} gen={r['gen_tok']} json_ok={r['json_ok']}")
        for row in r.get("checks", []):
            print("  ", row)
        if not r["json_ok"]:
            print(r.get("raw"))
