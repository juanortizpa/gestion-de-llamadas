"""Menu de instalacion: IA LOCAL (sin internet al usar) o APIs EXTERNAS (Groq / Gemini).

Uso:  .venv\\Scripts\\python.exe scripts\\instalar.py            (menu interactivo)
      .venv\\Scripts\\python.exe scripts\\instalar.py --opcion 2 --proveedor groq --clave XXX --sin-prueba   (sin preguntas)

Escribe la eleccion en .env (LLM_PROVIDER y la clave); .env es local y no se versiona. Es seguro repetirlo para cambiar de modo.
"""
from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

ENV = ROOT / ".env"
DEFAULT_DB = "sqlite:///data/chat/index.db"
KEYS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
NAMES = {"groq": "Groq (GPT-OSS 120B)", "gemini": "Google Gemini 1.5 Flash"}

MENU = """
==========================================================
  Auditoria de llamadas con IA - Instalacion
==========================================================
  1) LOCAL        Modelos en este equipo (~5 GB). Sin internet al usar,
                  sin costo por uso y los audios no salen de la empresa.
  2) APIs EXTERNAS  Groq o Gemini. Solo baja los modelos de voz (~3,2 GB,
                  la transcripcion siempre es local), pero los TEXTOS de
                  las llamadas se envian al proveedor y se paga/limita
                  segun su plan.
  3) Salir
"""


def upsert_env(path: Path, values: dict[str, str]) -> None:
    """Actualiza/crea claves en .env conservando el resto de lineas (y comentarios)."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    out = []
    for line in lines:
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and k in pending:
            out.append(f"{k}={pending.pop(k)}")
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in pending.items()]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def ask(prompt: str, default: str = "") -> str:
    r = input(prompt).strip()
    return r or default


def yes(prompt: str, default: bool = False) -> bool:
    r = ask(f"{prompt} [{'S/n' if default else 's/N'}]: ").lower()
    return default if not r else r.startswith(("s", "y"))


def install_local(preciso: bool | None = None, chat: bool | None = None) -> int:
    preciso = yes("¿Incluir modo Preciso (+4,5 GB, mas lento y mas exacto)?") if preciso is None else preciso
    chat = yes("¿Incluir busqueda semantica del Asistente (+150 MB)?", True) if chat is None else chat
    cmd = [sys.executable, str(ROOT / "scripts" / "descargar_modelos.py")] + (["--preciso"] if preciso else []) + (["--chat"] if chat else [])
    print("\nDescargando modelos (necesita internet una sola vez)...")
    rc = subprocess.call(cmd, cwd=ROOT)
    if rc != 0:
        print("\nLa descarga fallo. Revise la conexion y vuelva a ejecutar la instalacion (lo ya descargado no se repite).")
        return rc
    upsert_env(ENV, {"LLM_PROVIDER": "local", "DATABASE_URL": DEFAULT_DB})
    print("\nListo: modo LOCAL. Ejecute iniciar.py (o Iniciar.bat / run.sh)")
    return 0


def test_connection(provider: str) -> str | None:
    """None si responde; si no, el motivo (sin la clave)."""
    from llamadas.config import load_settings
    from llamadas.llm import RemoteLLM
    try:
        out = "".join(RemoteLLM(load_settings(), provider).chat_stream("Responde solo: ok", "ok", max_tokens=64, temperature=0))
        return None if out.strip() else "La API no devolvio texto."
    except Exception as e:      # mensaje ya sanitizado por RemoteLLM
        return str(e)


def install_external(provider: str | None = None, key: str | None = None, probar: bool = True, confirmado: bool = False,
                     descargar: bool = True) -> int:
    if provider is None:
        print("\n  a) Groq    - GPT-OSS 120B: muy rapido y barato; plan gratuito con limites de peticiones.")
        print("  b) Gemini  - Gemini 1.5 Flash: ventana de contexto grande; plan gratuito con limites.")
        provider = {"a": "groq", "b": "gemini"}.get(ask("Proveedor [a/b]: ").lower())
        if provider is None:
            print("Opcion no valida.")
            return 1
    if provider not in KEYS:
        print(f"Proveedor desconocido: {provider}")
        return 1
    if not confirmado:
        print(f"\nAVISO: con {NAMES[provider]} los textos de las llamadas (transcripciones) salen del equipo hacia el proveedor.")
        if not yes("¿Acepta continuar?"):
            print("Cancelado: no se guardo nada.")
            return 1
    key = key or getpass.getpass(f"Pegue su {KEYS[provider]} (no se muestra al escribir): ").strip()
    if not key:
        print("No se escribio ninguna clave.")
        return 1
    upsert_env(ENV, {"LLM_PROVIDER": provider, KEYS[provider]: key, "DATABASE_URL": DEFAULT_DB})
    print(f"\nGuardado en .env: modo {NAMES[provider]}.")
    if descargar:       # la transcripcion y la separacion de hablantes siguen siendo locales aunque la IA sea externa
        print("\nDescargando los modelos de voz (~3,2 GB, necesita internet una sola vez)...")
        rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "descargar_modelos.py"), "--solo-voz"], cwd=ROOT)
        if rc != 0:
            print("\nLa descarga fallo. Revise la conexion y ejecute: python iniciar.py --instalar (lo ya descargado no se repite).")
            return rc
    if probar:
        import os
        os.environ["LLM_PROVIDER"], os.environ[KEYS[provider]] = provider, key
        print("Probando la conexion...")
        err = test_connection(provider)
        print("Conexion correcta." if err is None else f"No se pudo verificar: {err}\nRevise la clave y repita la instalacion.")
        if err is not None:
            return 2
    print("\nListo. Ejecute iniciar.py (o Iniciar.bat / run.sh)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--opcion", type=int, choices=(1, 2, 3), help="1 local, 2 APIs externas, 3 salir (sin menu)")
    ap.add_argument("--proveedor", choices=sorted(KEYS))
    ap.add_argument("--clave")
    ap.add_argument("--sin-prueba", action="store_true", help="no probar la conexion con la API")
    ap.add_argument("--sin-descarga", action="store_true", help="no descargar los modelos de voz (modo APIs externas)")
    ap.add_argument("--acepto-envio-externo", action="store_true", help="confirma que los textos saldran del equipo (modo sin preguntas)")
    ap.add_argument("--preciso", action="store_true")
    ap.add_argument("--chat", action="store_true")
    a = ap.parse_args()
    opcion = a.opcion
    if opcion is None:
        print(MENU)
        opcion = {"1": 1, "2": 2, "3": 3}.get(ask("Elija una opcion [1-3]: "))
        if opcion is None:
            print("Opcion no valida.")
            return 1
    if opcion == 1:
        return install_local(*((a.preciso, a.chat) if a.opcion else (None, None)))
    if opcion == 2:
        return install_external(a.proveedor, a.clave, not a.sin_prueba, a.acepto_envio_externo, not a.sin_descarga)
    return 0


if __name__ == "__main__":
    sys.exit(main())
