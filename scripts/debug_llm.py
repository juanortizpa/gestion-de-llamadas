"""Depuracion: muestra la respuesta cruda del LLM para los criterios pendientes de una llamada."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llamadas.auditor import QUESTIONS, SCHEMA, SYSTEM, pending_items  # noqa: E402
from llamadas.config import load_settings  # noqa: E402
from llamadas.llm import LlamaServer  # noqa: E402

s = load_settings()
cid = sys.argv[1]
au = json.loads((s.data_dir / "results" / f"{cid}.audit.json").read_text(encoding="utf-8"))
tr = json.loads((s.data_dir / "results" / f"{cid}.transcript.json").read_text(encoding="utf-8"))
items = pending_items(au)
print("pendientes:", items)
convo = "\n".join(f"[{t['turn_id']}] {t['speaker']}: {t['text']}" for t in tr["turns"])
qs = "\n".join(f"- {c}.{sid}: {QUESTIONS[(c, sid)]}" for c, sid in items[:4])
user = f"TRANSCRIPCIÓN:\n{convo}\n\nPREGUNTAS:\n{qs}\n\nDevuelve {{\"checks\":[...]}} con una entrada por pregunta; usa como id exactamente \"CODIGO.sub_id\"."
with LlamaServer(s, sys.argv[2] if len(sys.argv) > 2 else "rapido") as srv:
    try:
        from llamadas.auditor import schema_for
        out, meta = srv.chat_json(SYSTEM, user, schema_for([f"{c}.{sid}" for c, sid in items[:4]]))
        print(meta)
        print(json.dumps(out, ensure_ascii=False, indent=1))
    except Exception as e:
        print("ERROR", type(e).__name__, e)
