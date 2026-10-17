#!/usr/bin/env python3
"""Lanzador UNICO y multiplataforma (Windows, macOS y Linux): un solo archivo prepara todo y abre el programa.

    python iniciar.py                 primera vez: crea el entorno, instala dependencias, muestra el menu de instalacion
                                      (IA local o APIs externas) y abre el programa; despues, solo lo abre
    python iniciar.py --instalar      vuelve a mostrar el menu (cambiar de IA local a externa o viceversa)
    python iniciar.py --solo-preparar prepara el entorno y sale (sin abrir el programa)

Solo necesita Python 3.12 o superior (https://www.python.org/downloads/). Usa unicamente la biblioteca estandar:
todo lo demas (dependencias, ffmpeg, modelos) lo instala el propio lanzador dentro de la carpeta del proyecto (.venv/, models/).
Dobles clics: Iniciar.bat (Windows) / run.sh (macOS y Linux).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

MIN_PY = (3, 12)
ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
MARCA = VENV / ".dependencias"       # hash de pyproject.toml con el que se instalo: si cambia, se reinstala


def python_del_entorno() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def revisar_python() -> None:
    if sys.version_info >= MIN_PY:
        return
    ver = ".".join(map(str, sys.version_info[:3]))
    print(f"Se necesita Python {MIN_PY[0]}.{MIN_PY[1]} o superior (este es {ver}).")
    print({"nt": "Instale Python desde https://www.python.org/downloads/ (marque 'Add python.exe to PATH')."
                  " Con winget: winget install --id Python.Python.3.12 -e",
           }.get(os.name, "Instale Python 3.12+: https://www.python.org/downloads/  (macOS: brew install python@3.12 · "
                          "Ubuntu/Debian: sudo apt install python3.12 python3.12-venv)"))
    raise SystemExit(1)


def entorno_utf8() -> dict[str, str]:
    """Consola en UTF-8: evita caracteres rotos con tildes en la consola de Windows."""
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def ejecutar(cmd: list[str], **kw) -> int:
    return subprocess.call([str(c) for c in cmd], cwd=ROOT, env=entorno_utf8(), **kw)


def preparar_entorno() -> None:
    py = python_del_entorno()
    if not py.exists():
        print("Creando el entorno de Python (una sola vez)...")
        try:
            venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
        except Exception as e:
            print(f"No se pudo crear el entorno: {e}")
            if sys.platform.startswith("linux"):
                print("En Ubuntu/Debian falta el modulo venv:  sudo apt install python3-venv")
            raise SystemExit(1) from None
    firma = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    if MARCA.exists() and MARCA.read_text(encoding="utf-8").strip() == firma:
        return
    print("Instalando dependencias (puede tardar unos minutos la primera vez)...")
    if ejecutar([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"]) != 0 or ejecutar([py, "-m", "pip", "install", "-e", "."]) != 0:
        print("\nNo se pudieron instalar las dependencias. Revise la conexion a internet y vuelva a ejecutar iniciar.py.")
        raise SystemExit(1)
    MARCA.write_text(firma, encoding="utf-8")


def menu_instalacion() -> int:
    return ejecutar([python_del_entorno(), "scripts/instalar.py"])


def abrir_programa(puerto: int) -> int:
    print("\nAbriendo el programa en el navegador. No cierre esta ventana mientras lo use (Ctrl+C para salir).")
    return ejecutar([python_del_entorno(), "-m", "llamadas", "gui", "--port", str(puerto)])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instalar", action="store_true", help="mostrar de nuevo el menu de instalacion (IA local o externa)")
    ap.add_argument("--solo-preparar", action="store_true", help="preparar el entorno y salir, sin abrir el programa")
    ap.add_argument("--puerto", type=int, default=8765)
    a = ap.parse_args()

    revisar_python()
    preparar_entorno()
    if a.instalar or not (ROOT / ".env").exists():       # sin .env = primera ejecucion: se elige IA local o externa
        rc = menu_instalacion()
        if rc != 0 and not (ROOT / ".env").exists():
            print("\nLa instalacion no termino. Vuelva a ejecutar iniciar.py para repetirla.")
            return rc
    return 0 if a.solo_preparar else abrir_programa(a.puerto)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCerrado.")
        sys.exit(0)
