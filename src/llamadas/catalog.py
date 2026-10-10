"""Base maestra de preparacion de examenes y sedes (Excel del usuario) -> consultas para Z1."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from .config import ROOT, Settings, load_settings
from .textutil import normalize


@dataclass
class Catalog:
    rows: list[dict] = field(default_factory=list)       # una fila por (procedimiento, sede)
    sedes: dict[str, str] = field(default_factory=dict)  # nombre normalizado -> direccion
    loaded: bool = False

    def exam_names(self) -> list[str]:
        return sorted({r["procedimiento"] for r in self.rows})

    def match_exam(self, text_n: str, thr: float = 88.0) -> dict | None:
        """Examen del catalogo mencionado en el texto (coincidencia aproximada); None si no hay."""
        best, best_score = None, 0.0
        for name in self.exam_names():
            nn = normalize(name).replace("preparacion para ", "")
            parts = (normalize(p).replace("preparacion para ", "") for p in re.split(r"[,()/]", name))
            keys = [nn] + [k for k in parts if len(k) >= 12]
            for k in keys:
                if len(text_n) >= 0.6 * len(k):
                    sc = fuzz.partial_ratio(k, text_n)
                    if sc > best_score:
                        best, best_score = name, sc
        if best and best_score >= thr:
            return {"procedimiento": best, "score": best_score, "rows": [r for r in self.rows if r["procedimiento"] == best]}
        return None

    @staticmethod
    def prep_required(rows: list[dict]) -> bool:
        """La preparacion es obligatoria si algun registro no empieza con 'No requiere'."""
        for r in rows:
            p = normalize(r.get("preparacion") or "")
            if p and not p.startswith("no requiere"):
                return True
        return False

    def sede_names(self) -> list[str]:
        out = set()
        for n in self.sedes:
            out.add(n)
            for pre in ("ips ", "clinica ", "christus clinica "):
                if n.startswith(pre) and len(n) - len(pre) >= 5:
                    out.add(n[len(pre):])
        # "de occidente" / "occidente" son genericos (nombre de la entidad "Angiografia de Occidente"), no una sede
        out -= {"de occidente", "occidente"}
        return sorted(out, key=len, reverse=True)


def _clean(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def load_catalog(path: Path) -> Catalog:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    cat = Catalog(loaded=True)
    ws = wb.worksheets[0]
    hdr = [normalize(_clean(c)) for c in next(ws.iter_rows(max_row=1, values_only=True))]
    ix = {h: i for i, h in enumerate(hdr)}

    def col(row, name):
        i = ix.get(normalize(name))
        return _clean(row[i]) if i is not None and i < len(row) else ""

    for r in ws.iter_rows(min_row=2, values_only=True):
        if not any(r):
            continue
        cat.rows.append({"procedimiento": col(r, "Nombre del procedimiento"), "sede": col(r, "Sede"),
                         "direccion": col(r, "Dirección"), "llegada": col(r, "Hora de llegada"),
                         "documentos": col(r, "Documentos a presentar"), "preparacion": col(r, "Preparación completa"),
                         "medicamentos": col(r, "Medicamentos a suspender/modificar"), "acompanante": col(r, "Acompañante"),
                         "recomendaciones": col(r, "Recomendaciones importantes")})
        if cat.rows[-1]["sede"]:
            cat.sedes.setdefault(normalize(cat.rows[-1]["sede"]), cat.rows[-1]["direccion"])
    if len(wb.worksheets) > 1:
        for r in wb.worksheets[1].iter_rows(values_only=True):
            if r and len(r) >= 3 and r[1]:
                cat.sedes[normalize(_clean(r[1]))] = _clean(r[2])
    return cat


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    s = load_settings()
    p = ROOT / s.raw.get("catalog", {}).get("path", "Base_maestra_preparacion_examenes.xlsx")
    try:
        return load_catalog(p) if p.exists() else Catalog()
    except Exception:  # catalogo ilegible: el sistema sigue funcionando sin el
        return Catalog()
