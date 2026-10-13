"""CLI: python -m llamadas transcribe <archivo|carpeta>... [--show]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

AUDIO_EXT = {".gsm", ".mp3", ".wav"}


def _collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in AUDIO_EXT) if p.is_dir() else [p]
    return files


def _dedupe(files: list[Path]) -> list[Path]:
    from .audio import sha256_file

    seen, out = set(), []
    for f in files:
        h = sha256_file(f)
        if h in seen:
            print(f"  (duplicado exacto omitido: {f.name})")
            continue
        seen.add(h)
        out.append(f)
    return out


_SYM = {1: "1", 0: "0", None: "?"}


def _audit(args) -> int:
    import json

    from .audit import ORDER, audit_transcript, save_audit
    from .config import load_settings

    s = load_settings()
    paths = [Path(p) for p in args.paths] or [s.data_dir / "results"]
    files: list[Path] = []
    for p in paths:
        files += sorted(p.glob("*.transcript.json")) if p.is_dir() else [p]
    print(f"{'llamada':<10}{'tipo':<13}" + " ".join(f"{c:>3}" for c in ORDER) + "   pts  rango%    E1   estado")
    for f in files:
        tr = json.loads(f.read_text(encoding="utf-8"))
        au = audit_transcript(tr, s)
        save_audit(au, s)
        cid = au["call"]["call_id"]
        if not au.get("criteria"):
            print(f"{cid:<10}{'-':<13}" + " ".join("  -" for _ in ORDER) + f"   -     -      -    {au['status']}")
            continue
        cells = []
        for c in ORDER:
            cr = au["criteria"][c]
            cells.append(f"{'n/a' if not cr['applicable'] else _SYM[cr['score']]:>3}")
        sc_ = au["score"]
        e1 = "cand" if au["critical_error"]["status"] != "none" else "-"
        print(f"{cid:<10}{au['call_type']['type']:<13}" + " ".join(cells) +
              f"   {sc_['points_confirmed']:>3}  {sc_['percent_min']}-{sc_['percent_max']:<5} {e1:>5}   {au['status']}")
        if args.detail:
            for c in ORDER:
                cr = au["criteria"][c]
                for sub in cr["sub_checks"]:
                    ev = sub.get("evidence") or {}
                    q = (ev.get("quote") or "")[:70] if isinstance(ev, dict) else ""
                    extra = f" [{sub['note']}]" if sub.get("note") else ""
                    print(f"      {c}.{sub['id']:<30} {_SYM[sub['passed']]}  {q}{extra}")
            if au["critical_error"]["findings"]:
                for fd in au["critical_error"]["findings"]:
                    print(f"      E1 candidato {fd['code']}: {fd['description']}")
    return 0


def _chat_cmd(args) -> int:
    from .chat import ChatEngine

    eng = ChatEngine()
    st = eng.sync_now(rebuild=getattr(args, "rebuild", False))
    emb = "activos" if eng.status()["vectors_enabled"] else "no disponibles (busqueda solo por palabras)"
    print(f"Indice: {eng.store.stats()['calls']} llamadas · +{st['added']} nuevas, {st['updated']} actualizadas, {st['removed']} borradas · "
          f"vectores {emb}" + (f" · aviso embeddings: {st['embed_error']}" if st.get("embed_error") else ""))
    if args.cmd == "index":
        return 0
    ctx, hist = None, []
    questions = [" ".join(args.question)] if args.question else None
    try:
        while True:
            q = questions.pop(0) if questions else (input("\nPregunta (vacio para salir): ").strip() if args.question == [] else None)
            if not q:
                break
            r = eng.ask(q, ctx, hist, debug=args.debug)
            print(f"\n[{r['route']}] " + (" · ".join(r["filters"]) if r["filters"] else "sin filtros"))
            print(r["answer"])
            for s in r["sources"]:
                print(f"   [{s['n']}]{'*' if s.get('cited') else ' '} {s['call_id']} {s.get('ctx', '')}")
            for w in r["warnings"]:
                print("   AVISO:", w)
            if args.debug:
                print("   stats:", r["stats"])
            ctx = r["ctx"]
            hist = (hist + [{"q": q, "a": r["answer"][:400]}])[-3:]
            if args.question and not questions:
                break
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        eng.gen.server.stop()
        if eng.embedder is not None:
            eng.embedder.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="llamadas")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("transcribe", help="Fase 1: audio -> transcripcion con turnos asesor/cliente")
    t.add_argument("paths", nargs="+")
    t.add_argument("--show", action="store_true", help="imprime los turnos en consola")
    g = sub.add_parser("gui", help="Abre la interfaz grafica en el navegador (http://127.0.0.1:8765)")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--no-browser", action="store_true")
    r = sub.add_parser("resolve", help="Fase 3: la IA local resuelve los criterios pendientes de las auditorias existentes")
    r.add_argument("--mode", choices=["rapido", "preciso"], default=None)
    a = sub.add_parser("audit", help="Fase 2: transcripcion -> auditoria parcial por reglas/timestamps")
    a.add_argument("paths", nargs="*", help="*.transcript.json o carpeta (por defecto data/results)")
    a.add_argument("--detail", action="store_true", help="muestra sub-checks y evidencia")
    ix = sub.add_parser("index", help="Asistente: actualiza el indice de busqueda (fragmentos y vectores) con las auditorias existentes")
    ix.add_argument("--rebuild", action="store_true", help="borra el indice y lo reconstruye")
    ch = sub.add_parser("chat", help="Asistente de consulta en la terminal (sin interfaz grafica)")
    ch.add_argument("question", nargs="*", help="pregunta unica; sin ella abre una conversacion")
    ch.add_argument("--debug", action="store_true", help="muestra la ruta, los filtros y los puntajes de busqueda")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.cmd in ("index", "chat"):
        return _chat_cmd(args)
    if args.cmd == "resolve":
        import json

        from .audit import save_audit
        from .auditor import classify_completion, pending_items, resolve_with_llm
        from .config import load_settings
        from .llm import LlamaServer

        s = load_settings()
        todo = []
        for f in sorted((s.data_dir / "results").glob("*.audit.json")):
            au = json.loads(f.read_text(encoding="utf-8"))
            if not au.get("synthetic") and (pending_items(au) or ("completion" not in au and au.get("criteria"))):
                todo.append((f, au))
        print(f"{len(todo)} auditorias por resolver (criterios pendientes o cierre sin clasificar)")
        with LlamaServer(s, args.mode) as srv:
            for f, au in todo:
                cid = au["call"]["call_id"]
                tr = json.loads((s.data_dir / "results" / f"{cid}.transcript.json").read_text(encoding="utf-8"))
                au = classify_completion(au, tr, srv, s)
                save_audit(au, s)
                comp = au.get("completion") or {}
                print(f"  {cid}: cierre={comp.get('estado')} ({comp.get('source')}) aplicado={comp.get('applied')} {comp.get('motivo', '')}")
                if au.get("auto_discard"):
                    continue
                au = resolve_with_llm(au, tr, srv, s)
                save_audit(au, s)
                if au.get("llm"):
                    print(f"      {au['llm']['secs']}s  {[(x['id'], x['result']) for x in au['llm']['log']]}")
        return 0
    if args.cmd == "gui":
        from .gui.server import run
        run(args.port, not args.no_browser)
        return 0
    if args.cmd == "audit":
        return _audit(args)
    from .pipeline import process_file, save_result

    files = _dedupe(_collect(args.paths))
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f.name}")
        res = process_file(f, log=lambda m: print("   ·", m))
        out = save_result(res)
        q = res["quality"]
        print(f"   -> {res['status']}  {res['call']['duration_s']}s  proc={res['pipeline'].get('processing_s')}s  "
              f"roles_conf={q.get('role_confidence')}  avisos={q.get('warnings')}  ({out.name})")
        if args.show:
            for r in res["recorded_intervals"]:
                print(f"   [GRABADO {r['kind']} {r['start']}-{r['end']}s]")
            for t in res["turns"]:
                print(f"   [{t['start']:6.1f}] {t['speaker']:<8} {t['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
