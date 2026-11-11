"""Puerta de entrada del servidor: sesion obligatoria, CSRF, roles, limites de tamano y cabeceras de seguridad.

`Protegido` va delante de BaseHTTPRequestHandler en server.Handler. Recibe TODAS las peticiones (do_GET/do_POST/do_DELETE),
decide si pasan y solo entonces llama a las rutas de la aplicacion (_get/_post/_delete). Asi ninguna ruta nueva queda
abierta por olvido: lo que no este en la lista publica exige sesion.
"""
from __future__ import annotations

import hmac
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from ..auth import Auth, AuthError

STATIC = Path(__file__).parent / "static"
COOKIE, COOKIE_CSRF = "gdl_sesion", "gdl_csrf"
HOSTS = ("127.0.0.1", "localhost", "[::1]")
MAX_JSON, MAX_UPLOAD = 1_000_000, 300_000_000
AUTH: Auth | None = None

# Sin recursos externos: aunque una respuesta de la IA trajera una imagen o un enlace a otro servidor, el navegador no lo
# carga ni le envia datos (img-src / connect-src 'self'). Es el cierre de la «salida» en la interfaz.
HEADERS = (
    ("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; "
                                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
)
# Solo administrador: lo irreversible (borrar), la configuracion del correo, las trazas y los usuarios
ADMIN = (("DELETE", r"^/api/call/"), ("DELETE", r"^/api/quejas/"), ("POST", r"^/api/trazas/limpiar$"), ("POST", r"^/api/notify"),
         ("*", r"^/api/usuarios"), ("GET", r"^/api/accesos$"))
# Queda en la bitacora quien lo hizo
AUDITED = (("DELETE", r"^/api/"), ("GET", r"^/api/export$"), ("GET", r"^/api/quejas/export$"), ("POST", r"^/api/process$"),
           ("POST", r"^/api/review/"), ("POST", r"^/api/notify"), ("POST", r"^/api/trazas/limpiar$"), ("POST", r"^/api/clear_incoming$"))


def configurar(data_dir: Path) -> Auth:
    global AUTH
    AUTH = Auth(data_dir)
    return AUTH


def _match(rules, method: str, p: str) -> bool:
    return any(m in ("*", method) and re.match(rx, p) for m, rx in rules)


def _pub(ses: dict) -> dict:
    return {"usuario": ses["user"], "nombre": ses["name"], "rol": ses["role"]}


class Protegido:
    session: dict | None = None
    _cookies: tuple = ()

    # ---------------------------------------------------------------- cabeceras
    def end_headers(self):
        for k, v in HEADERS:
            self.send_header(k, v)
        if not any(b"cache-control" in h.lower() for h in getattr(self, "_headers_buffer", ())):
            self.send_header("Cache-Control", "no-store")  # datos personales: nada queda en la cache del navegador
        for c in self._cookies:
            self.send_header("Set-Cookie", c)
        self._cookies = ()
        super().end_headers()

    def _cookie(self, name: str) -> str | None:
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return None

    def _set_session(self, token: str, ses: dict) -> None:
        self._cookies = (f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/", f"{COOKIE_CSRF}={ses['csrf']}; SameSite=Strict; Path=/")

    def _clear_session(self) -> None:
        self._cookies = (f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0", f"{COOKIE_CSRF}=; SameSite=Strict; Path=/; Max-Age=0")

    # ---------------------------------------------------------------- comprobaciones
    @staticmethod
    def _local(netloc: str) -> bool:
        return netloc.rsplit(":", 1)[0] in HOSTS or netloc in HOSTS

    def _host_ok(self) -> bool:
        """Solo se atiende si el navegador cree estar hablando con este equipo (corta el «DNS rebinding»), y si la peticion
        viene de otra pagina (Origin), esa pagina tambien debe ser la app."""
        if not self._local(self.headers.get("Host") or ""):
            return False
        origin = self.headers.get("Origin")
        return not origin or self._local(urlparse(origin).netloc)

    def _json_body(self) -> dict:
        d = json.loads(self._body() or b"{}")
        if not isinstance(d, dict):
            raise ValueError("se esperaba un objeto")
        return d

    def _gate(self, method: str, p: str) -> dict | None:
        """Sesion valida para esta peticion, o None si ya se respondio con el rechazo."""
        ses = AUTH.session(self._cookie(COOKIE))
        if not ses:
            if p.startswith("/api/"):
                self._json({"error": "Inicie sesión para continuar.", "login": True}, 401)
            else:
                self.send_response(302)
                self.send_header("Location", "/login")
                self.send_header("Content-Length", "0")
                self.end_headers()
            return None
        if method != "GET" and not hmac.compare_digest(self.headers.get("X-CSRF-Token") or "", ses["csrf"]):
            AUTH.log("csrf_rechazado", ses["user"], ruta=p)
            self._json({"error": "Petición rechazada: recargue la página e intente de nuevo."}, 403)
            return None
        if _match(ADMIN, method, p) and ses["role"] != "admin":
            AUTH.log("permiso_denegado", ses["user"], ruta=f"{method} {p}")
            self._json({"error": "Solo un administrador puede hacer esto."}, 403)
            return None
        return ses

    # ---------------------------------------------------------------- entrada unica
    def do_GET(self):
        self._guard("GET", self._get)

    def do_POST(self):
        self._guard("POST", self._post)

    def do_DELETE(self):
        self._guard("DELETE", self._delete)

    def _guard(self, method: str, handler) -> None:
        p = urlparse(self.path).path
        try:
            if not self._host_ok():
                return self._json({"error": "Origen no permitido."}, 403)
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json({"error": "Petición inválida."}, 400)
            if n < 0 or n > (MAX_UPLOAD if p == "/api/upload" else MAX_JSON):
                return self._json({"error": "El archivo o el mensaje es demasiado grande."}, 413)
            if method == "GET" and p == "/login":
                return self._file(STATIC / "login.html", "text/html; charset=utf-8")
            if method == "GET" and p.startswith("/static/"):
                return handler()  # la interfaz no es secreta; los datos si
            if p.startswith("/api/auth/"):
                return self._auth_api(method, p)
            ses = self._gate(method, p)
            if ses is None:
                return None
            self.session = ses
            if _match(AUDITED, method, p):
                AUTH.log("accion", ses["user"], ruta=f"{method} {p}")
            if p.startswith("/api/usuarios") or p == "/api/accesos":
                return self._users_api(method, p, ses)
            return handler()
        except AuthError as e:
            return self._json({"error": str(e)}, e.code)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None
        except ValueError:
            return self._safe_error("Datos inválidos en la petición.", 400)
        except Exception as e:  # nunca una traza hacia el navegador
            AUTH.log("error_interno", (self.session or {}).get("user", ""), ruta=f"{method} {p}", tipo=type(e).__name__)
            return self._safe_error("Ocurrió un error interno. Intente de nuevo.", 500)

    def _safe_error(self, msg: str, code: int) -> None:
        try:
            self._json({"error": msg}, code)
        except Exception:
            pass  # la respuesta ya habia empezado

    # ---------------------------------------------------------------- /api/auth/*
    def _auth_api(self, method: str, p: str):
        ses = AUTH.session(self._cookie(COOKIE))
        if method == "GET" and p == "/api/auth/estado":
            return self._json({"configurado": AUTH.has_users(), "sesion": _pub(ses) if ses else None})
        if method != "POST":
            return self._json({"error": "ruta desconocida"}, 404)
        d = self._json_body()
        if p == "/api/auth/login":
            token, ses = AUTH.login(d.get("usuario", ""), d.get("clave", ""))
            self._set_session(token, ses)
            return self._json({"ok": True, "sesion": _pub(ses)})
        if p == "/api/auth/crear-admin":
            if AUTH.has_users():  # solo en el primer arranque; despues los usuarios los crea un administrador
                return self._json({"error": "El administrador ya fue creado. Inicie sesión."}, 403)
            AUTH.create_user(d.get("usuario", ""), d.get("clave", ""), "admin", d.get("nombre", ""))
            token, ses = AUTH.login(d.get("usuario", ""), d.get("clave", ""))
            self._set_session(token, ses)
            return self._json({"ok": True, "sesion": _pub(ses)})
        if not ses:
            return self._json({"error": "Inicie sesión para continuar.", "login": True}, 401)
        if not hmac.compare_digest(self.headers.get("X-CSRF-Token") or "", ses["csrf"]):
            return self._json({"error": "Petición rechazada: recargue la página e intente de nuevo."}, 403)
        if p == "/api/auth/salir":
            AUTH.logout(self._cookie(COOKIE))
            self._clear_session()
            return self._json({"ok": True})
        if p == "/api/auth/clave":
            AUTH.set_password(ses["user"], d.get("actual", ""), d.get("nueva", ""), keep=self._cookie(COOKIE))
            return self._json({"ok": True})
        return self._json({"error": "ruta desconocida"}, 404)

    # ---------------------------------------------------------------- /api/usuarios y /api/accesos (solo administrador)
    def _users_api(self, method: str, p: str, ses: dict):
        if method == "GET" and p == "/api/accesos":
            return self._json({"eventos": AUTH.events()})
        if method == "GET" and p == "/api/usuarios":
            return self._json({"usuarios": AUTH.users()})
        if method == "POST" and p == "/api/usuarios":
            d = self._json_body()
            return self._json({"ok": True, "usuario": AUTH.create_user(d.get("usuario", ""), d.get("clave", ""), d.get("rol", "auditor"),
                                                                       d.get("nombre", ""), por=ses["user"])})
        m = re.match(r"^/api/usuarios/([a-z0-9._-]{3,32})$", p)
        if method == "DELETE" and m:
            AUTH.delete_user(m.group(1), ses["user"])
            return self._json({"ok": True})
        return self._json({"error": "ruta desconocida"}, 404)
