"""Exporta a Excel con el formato de la plantilla 'Matriz de Auditorias' (una fila por llamada)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .config import Settings, load_settings
from .review import CODES, DISCARD, final_view, load_review

HEAD = ["ID Auditoría", "Fecha", "Auditor", "Agente", "ID Audio / Registro", "Duración (Min)", "Motivo Llamada",
        "P1: Saludo Guión", "P2: Nombre Cliente", "V1: Conf. Documento", "V2: Valida Datos/Hist", "G1: Control Hold (<60s)",
        "G2: Agilidad Sistema", "C1: Escucha Activa", "C2: Tono y Lenguaje", "Z1: Conf. Solución/Cita", "Z2: Despedida Guión",
        "E1: Error Crítico", "Puntaje Obtenido", "Puntaje Máximo", "Nota Calidad (%)", "Estado Final", "Observaciones y Plan de Acción"]

TYPE_ES = {"nueva_cita": "Solicitud de cita", "cancelacion": "Cancelar cita", "confirmacion": "Confirmación de cita",
           "informacion": "Información", "desconocido": ""}


def collect(settings: Settings | None = None) -> list[dict]:
    settings = settings or load_settings()
    rows = []
    for f in sorted((settings.data_dir / "results").glob("*.audit.json")):
        au = json.loads(f.read_text(encoding="utf-8"))
        if au.get("synthetic"):
            continue
        cid = au["call"]["call_id"]
        rv = load_review(cid, settings)
        rows.append({"id": cid, "audit": au, "review": rv, "final": final_view(au, rv, settings)})
    return rows


def export_xlsx(path: Path, settings: Settings | None = None, only_reviewed: bool = False) -> Path:
    settings = settings or load_settings()
    wb = Workbook()
    ws = wb.active
    ws.title = "Matriz de Auditorias"
    ws["A1"] = "MATRIZ CONSOLIDADA DE AUDITORÍA DE LLAMADAS"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Generado automáticamente el {datetime.now():%Y-%m-%d %H:%M}. Las filas 'Pendiente' requieren revisión humana."
    for i, h in enumerate(HEAD, 1):
        c = ws.cell(row=4, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    r = 5
    n = 0
    discarded = []
    for row in collect(settings):
        au, rv, fin = row["audit"], row["review"], row["final"]
        if fin.get("discarded"):
            discarded.append(row)
            continue
        if only_reviewed and not fin.get("reviewed"):
            continue
        if not au.get("criteria"):
            continue
        n += 1
        date = au["call"].get("received_date") or ""
        date = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else date
        vals = [f"AUD-{n:03d}", date, rv.get("auditor", ""), rv.get("agent", ""), au["call"]["source_file"].rsplit(".", 1)[0],
                round(au["call"]["duration_s"] / 60, 1), rv.get("motivo") or TYPE_ES.get(au["call_type"]["type"], "")]
        vals += ["Pend." if fin["criteria"][c]["value"] is None else fin["criteria"][c]["value"] for c in CODES]
        vals += [1 if fin["e1"] in ("confirmed", "candidato") else 0, fin["points"], 10,
                 "Pend." if fin["percent"] is None else fin["percent"] / 100, fin["estado"], rv.get("obs", "")]
        for i, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=i, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top", horizontal="center" if 8 <= i <= 21 else "left")
        ws.cell(row=r, column=21).number_format = "0%"
        r += 1
    for i, w in enumerate([11, 11, 14, 18, 36, 9, 22] + [9] * 11 + [9, 9, 10, 24, 50], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A5"
    if discarded:
        wd = wb.create_sheet("Descartadas")
        wd["A1"] = "LLAMADAS NO AUDITADAS (cortadas o incompletas)"
        wd["A1"].font = Font(bold=True, size=14)
        for i, h in enumerate(["ID Audio / Registro", "Fecha", "Duración (Min)", "Motivo del descarte", "Marcada por", "Detalle", "Auditor", "Observaciones"], 1):
            c = wd.cell(row=3, column=i, value=h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="7F7F7F")
        for k, row in enumerate(discarded, 4):
            au, rv = row["audit"], row["review"]
            d = au["call"].get("received_date") or ""
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d
            auto = au.get("auto_discard") or {}
            by = row["final"]["discard_origin"]
            by = {"automática": f"Sistema ({'regla' if auto.get('source') == 'regla' else 'IA'})"}.get(by, "Auditor")
            detail = auto.get("reason", "") if row["final"]["discard_origin"] == "automática" else ""
            for i, v in enumerate([au["call"]["source_file"].rsplit(".", 1)[0], d, round(au["call"]["duration_s"] / 60, 1),
                                   DISCARD[row["final"]["discarded"]].capitalize(), by, detail, rv.get("auditor", ""), rv.get("obs", "")], 1):
                wd.cell(row=k, column=i, value=v).alignment = Alignment(wrap_text=True, vertical="top")
        for i, w in enumerate([40, 12, 14, 22, 16, 44, 16, 40], 1):
            wd.column_dimensions[get_column_letter(i)].width = w
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
