"""Contexto compartido por las reglas + helpers de busqueda con evidencia."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from ..config import Settings
from ..textutil import best_sentence


class Hit(NamedTuple):
    turn: dict
    sentence: str
    wrong_side: bool = False   # la frase existe pero la dijo la otra persona


@dataclass
class Ctx:
    tr: dict
    settings: Settings
    metrics: dict
    turns: list
    roles_ok: bool
    call_type: str = "desconocido"
    extra: dict = field(default_factory=dict)

    @property
    def lex(self) -> dict:
        return self.settings.lex["rules"]

    @property
    def rules(self) -> dict:
        return self.settings["rules"]

    @property
    def duration(self) -> float:
        return self.tr["call"]["duration_s"]


def roles_reliable(tr: dict, settings: Settings) -> bool:
    q = tr.get("quality", {})
    bad = {w for w in q.get("warnings", []) if w.startswith(("diarizacion_sospechosa", "no_se_identifico", "un_solo_hablante",
                                                            "roles_poco", "audio_humano_insuficiente"))}
    return not bad and q.get("role_confidence", 0.0) >= settings["rules"]["min_role_confidence"]


def find(ctx: Ctx, phrases: list[str], who: str = "ASESOR", turns: list | None = None) -> Hit | None:
    """Busca una frase en los turnos de `who`. Si los roles no son fiables busca en todos (sin marcar lado)."""
    turns = ctx.turns if turns is None else turns

    def scan(sel):
        for t in sel:
            s = best_sentence(t["text"], phrases)
            if s:
                return Hit(t, s)
        return None

    if ctx.roles_ok:
        h = scan([t for t in turns if t["speaker"] == who])
        if h:
            return h
        h = scan([t for t in turns if t["speaker"] != who])
        return Hit(h.turn, h.sentence, True) if h else None
    return scan(turns)


def find_all(ctx: Ctx, phrases: list[str], who: str = "ASESOR", turns: list | None = None) -> list[Hit]:
    turns = ctx.turns if turns is None else turns
    sel = [t for t in turns if (t["speaker"] == who or not ctx.roles_ok)]
    out = []
    for t in sel:
        s = best_sentence(t["text"], phrases)
        if s:
            out.append(Hit(t, s))
    return out


def ev(h: Hit | None) -> dict | None:
    if not h:
        return None
    return {"turn_id": h.turn["turn_id"], "quote": h.sentence[:220], "start": h.turn["start"], "end": h.turn["end"]}


def sc(id_: str, passed, hit: Hit | None = None, note: str | None = None, optional: bool = False, evidence=None) -> dict:
    d = {"id": id_, "passed": passed, "source": "rule", "evidence": evidence if evidence is not None else ev(hit)}
    if note:
        d["note"] = note
    if optional:
        d["optional"] = True
    return d


def criterion(code: str, name: str, subs: list[dict], ctx: Ctx, explain: str, conf: float | None = None,
              method: str = "rule", extra: dict | None = None) -> dict:
    req = [s for s in subs if not s.get("optional")]
    if any(s["passed"] is False for s in req):
        score = 0
    elif any(s["passed"] is None for s in req):
        score = None
    else:
        score = 1
    if conf is None:
        conf = 0.85 if ctx.roles_ok else 0.55
        if score == 0:
            conf -= 0.15   # una ausencia puede deberse a un error del STT
    d = {"code": code, "name": name, "score": score, "applicable": True, "method": method,
         "confidence": round(max(conf, 0.1), 2), "sub_checks": subs, "explanation": explain}
    if score is None:
        d["pending"] = "requiere LLM/revision humana (Fase 3)"
    if extra:
        d.update(extra)
    return d
