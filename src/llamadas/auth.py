"""Usuarios y sesiones de la interfaz. Solo biblioteca estandar; todo vive en data/ (fuera de git).

- Contrasenas: nunca se guardan; solo su derivado scrypt con sal propia por usuario (data/usuarios.json).
- Sesiones: en memoria (se cierran al reiniciar el programa), con caducidad por inactividad y maxima.
- Intentos fallidos: tras `max_fails` seguidos el usuario queda bloqueado `lock_s` segundos (exista o no: no revela cuales existen).
- Bitacora: data/accesos.jsonl registra entradas, fallos, bloqueos y acciones delicadas. Nunca contrasenas ni tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from pathlib import Path

USER_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
ROLES = ("admin", "auditor")
MIN_CLAVE = 10
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


class AuthError(Exception):
    """Error con mensaje para el usuario y codigo HTTP."""

    def __init__(self, msg: str, code: int = 400):
        super().__init__(msg)
        self.code = code


def _hash(clave: str, sal: bytes) -> bytes:
    return hashlib.scrypt(clave.encode("utf-8"), salt=sal, dklen=32, **SCRYPT)


def check_clave(clave: str, usuario: str = "") -> None:
    if not isinstance(clave, str) or len(clave) < MIN_CLAVE:
        raise AuthError(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres.")
    if len(clave) > 200:
        raise AuthError("La contraseña es demasiado larga.")
    if not (re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", clave) and re.search(r"\d", clave)):
        raise AuthError("La contraseña debe tener letras y números.")
    if usuario and usuario in clave.lower():
        raise AuthError("La contraseña no puede contener el nombre de usuario.")


class Auth:
    def __init__(self, data_dir: Path, *, idle_s: int = 30 * 60, max_s: int = 8 * 3600, max_fails: int = 5, lock_s: int = 5 * 60,
                 clock=time.time):
        self.dir = Path(data_dir)
        self.path = self.dir / "usuarios.json"
        self.log_path = self.dir / "accesos.jsonl"
        self.idle_s, self.max_s, self.max_fails, self.lock_s, self.clock = idle_s, max_s, max_fails, lock_s, clock
        self._lock = threading.RLock()
        self._sessions: dict[str, dict] = {}
        self._fails: dict[str, dict] = {}
        self._dummy = secrets.token_bytes(16)  # sal para gastar el mismo tiempo cuando el usuario no existe

    # ---------------------------------------------------------------- usuarios
    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, users: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(users, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)  # en Windows no aplica; la carpeta data/ ya es local
        except OSError:
            pass
        tmp.replace(self.path)

    def has_users(self) -> bool:
        return bool(self._load())

    def users(self) -> list[dict]:
        return [{"usuario": u, "nombre": r.get("nombre", ""), "rol": r["rol"], "creado": r.get("creado", "")} for u, r in sorted(self._load().items())]

    def create_user(self, usuario: str, clave: str, rol: str = "auditor", nombre: str = "", por: str = "") -> dict:
        u = str(usuario or "").strip().lower()
        if not USER_RE.match(u):
            raise AuthError("El usuario debe tener de 3 a 32 caracteres: letras minúsculas, números, punto, guion o guion bajo.")
        if rol not in ROLES:
            raise AuthError("Rol no válido.")
        check_clave(clave, u)
        with self._lock:
            users = self._load()
            if u in users:
                raise AuthError("Ese usuario ya existe.", 409)
            sal = secrets.token_bytes(16)
            users[u] = {"nombre": str(nombre or "").strip()[:80], "rol": rol, "sal": sal.hex(), "clave": _hash(clave, sal).hex(),
                        "creado": time.strftime("%Y-%m-%d %H:%M")}
            self._save(users)
        self.log("usuario_creado", por or u, sobre=u, rol=rol)
        return {"usuario": u, "nombre": users[u]["nombre"], "rol": rol}

    def delete_user(self, usuario: str, por: str) -> None:
        with self._lock:
            users = self._load()
            if usuario not in users:
                raise AuthError("Ese usuario no existe.", 404)
            if usuario == por:
                raise AuthError("No puede eliminar su propio usuario.")
            if users[usuario]["rol"] == "admin" and sum(r["rol"] == "admin" for r in users.values()) <= 1:
                raise AuthError("Debe quedar al menos un administrador.")
            del users[usuario]
            self._save(users)
            self._drop_sessions(usuario)
        self.log("usuario_eliminado", por, sobre=usuario)

    def set_password(self, usuario: str, actual: str, nueva: str, keep: str | None = None) -> None:
        with self._lock:
            users = self._load()
            rec = users.get(usuario)
            if not rec or not hmac.compare_digest(_hash(str(actual), bytes.fromhex(rec["sal"])), bytes.fromhex(rec["clave"])):
                self.log("clave_fallida", usuario)
                raise AuthError("La contraseña actual no es correcta.", 403)
            check_clave(nueva, usuario)
            sal = secrets.token_bytes(16)
            rec.update(sal=sal.hex(), clave=_hash(nueva, sal).hex())
            self._save(users)
            self._drop_sessions(usuario, keep)  # las demas sesiones de ese usuario se cierran
        self.log("clave_cambiada", usuario)

    # ---------------------------------------------------------------- sesiones
    def _drop_sessions(self, usuario: str, keep: str | None = None) -> None:
        for t in [t for t, s in self._sessions.items() if s["user"] == usuario and t != keep]:
            del self._sessions[t]

    def login(self, usuario: str, clave: str) -> tuple[str, dict]:
        u = str(usuario or "").strip().lower()[:64]
        now = self.clock()
        with self._lock:
            f = self._fails.get(u)
            if f and f["until"] > now:
                self.log("login_bloqueado", u)
                raise AuthError(f"Demasiados intentos. Espere {math.ceil((f['until'] - now) / 60)} min e intente de nuevo.", 429)
        rec = self._load().get(u)
        if rec:
            ok = hmac.compare_digest(_hash(str(clave), bytes.fromhex(rec["sal"])), bytes.fromhex(rec["clave"]))
        else:
            _hash(str(clave), self._dummy)  # mismo costo: el tiempo de respuesta no delata si el usuario existe
            ok = False
        with self._lock:
            if not ok:
                if len(self._fails) > 1000:
                    self._fails.clear()
                f = self._fails.setdefault(u, {"n": 0, "until": 0.0})
                f["n"] += 1
                if f["n"] >= self.max_fails:
                    f.update(n=0, until=now + self.lock_s)
                self.log("login_fallido", u)
                raise AuthError("Usuario o contraseña incorrectos.", 401)
            self._fails.pop(u, None)
            token = secrets.token_urlsafe(32)
            ses = {"user": u, "name": rec.get("nombre", ""), "role": rec["rol"], "csrf": secrets.token_urlsafe(24), "created": now, "seen": now}
            self._sessions[token] = ses
        self.log("login", u)
        return token, ses

    def session(self, token: str | None) -> dict | None:
        """Sesion vigente (y renueva su inactividad) o None."""
        if not token:
            return None
        now = self.clock()
        with self._lock:
            ses = self._sessions.get(token)
            if not ses:
                return None
            if now - ses["seen"] > self.idle_s or now - ses["created"] > self.max_s:
                del self._sessions[token]
                self.log("sesion_caducada", ses["user"])
                return None
            ses["seen"] = now
            return ses

    def logout(self, token: str | None) -> None:
        with self._lock:
            ses = self._sessions.pop(token or "", None)
        if ses:
            self.log("logout", ses["user"])

    # ---------------------------------------------------------------- bitacora
    def log(self, evento: str, usuario: str, **extra) -> None:
        row = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "evento": evento, "usuario": usuario, **extra}
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            with self._lock, self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass  # la bitacora nunca debe tumbar una peticion

    def events(self, limit: int = 200) -> list[dict]:
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()[-limit:]
        except OSError:
            return []
        out = []
        for ln in reversed(lines):
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
        return out
