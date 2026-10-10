"""Asignacion de roles (asesor/cliente) por CONTENIDO, no por quien habla primero (llamadas entrantes y salientes).

La diarizacion sobre-segmenta (num_clusters > 2): cada cluster recibe un rol segun su lexico. Asi, una voz del
asesor con poco audio puede formar su propio cluster en vez de fundirse con el cliente (ver B2 / 2072716).
"""
from __future__ import annotations

from rapidfuzz import fuzz

from .config import Settings
from .textutil import normalize

PHRASE_THR = 85
MIN_AGENT_NET = 2  # puntaje minimo para que un cluster sea ASESOR


def _count(text_n: str, phrase: str) -> int:
    """Veces (0..2) que aparece la frase de forma aproximada en el texto."""
    if phrase in text_n:
        return min(text_n.count(phrase), 2)
    return 1 if len(phrase) >= 8 and len(text_n) >= 0.6 * len(phrase) and fuzz.partial_ratio(phrase, text_n) >= PHRASE_THR else 0


def score_speakers(turns: list[dict], settings: Settings) -> dict[int, dict]:
    lex = settings.lex["roles"]
    texts: dict[int, str] = {}
    for t in turns:
        if t["spk"] is not None:
            texts[t["spk"]] = texts.get(t["spk"], "") + " " + normalize(t["text"])
    scores = {}
    for spk, tx in texts.items():
        a = sum(w * _count(tx, p) for p, w in lex["agent_phrases"])
        c = sum(w * _count(tx, p) for p, w in lex["client_phrases"])
        ent = sum(2 for e in lex["entity_names"] if e in tx)
        scores[spk] = {"agent": a + ent, "client": c, "net": a + ent - c, "words": len(tx.split())}
    return scores


def assign_roles(turns: list[dict], settings: Settings) -> dict:
    """{'roles': {spk: 'ASESOR'|'CLIENTE'}, 'confidence': 0..1, 'scores': {...}, 'warning'?}"""
    scores = score_speakers(turns, settings)
    if len(scores) < 2:
        return {"roles": {s: "DESCONOCIDO" for s in scores}, "confidence": 0.0, "scores": scores,
                "warning": "un_solo_hablante_detectado"}
    ranked = sorted(scores, key=lambda s: scores[s]["net"], reverse=True)
    top_net = scores[ranked[0]]["net"]
    roles = {}
    for s in ranked:
        n = scores[s]["net"]
        roles[s] = "ASESOR" if (s == ranked[0] and n > 0) or (n >= MIN_AGENT_NET and n >= 0.4 * top_net) else "CLIENTE"
    client_nets = [scores[s]["net"] for s in ranked if roles[s] == "CLIENTE"]
    best_client = max(client_nets) if client_nets else 0
    denom = abs(top_net) + abs(best_client) + 1e-9
    conf = round(max(0.0, min(1.0, (top_net - best_client) / denom)), 2)
    res = {"roles": roles, "confidence": conf, "scores": scores}
    if top_net <= 0:
        res["warning"] = "no_se_identifico_al_asesor"
    elif conf < 0.3:
        res["warning"] = "roles_poco_confiables"
    if not client_nets:
        res["warning"] = "no_se_identifico_al_cliente"
    return res
