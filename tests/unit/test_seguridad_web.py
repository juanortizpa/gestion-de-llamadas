"""Puerta de entrada del servidor (gui/seguridad.py): sin sesion no hay datos; CSRF, roles, tamanos y cabeceras."""
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from llamadas.auth import Auth
from llamadas.gui import seguridad

CLAVE = "clave-segura-2026"


class App(seguridad.Protegido, BaseHTTPRequestHandler):
    """Aplicacion minima detras de la puerta: lo que se prueba es la puerta, no las rutas."""

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _file(self, path, ctype=None, download_name=None):
        self._json({"archivo": path.name})

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def _get(self):
        if self.path == "/api/explota":
            raise RuntimeError("detalle interno que no debe verse")
        self._json({"ruta": self.path, "usuario": (self.session or {}).get("user")})

    _post = _delete = _get


class Cliente:
    def __init__(self, port):
        self.port, self.cookies = port, {}

    def req(self, method, path, body=None, headers=None, csrf=True):
        h = {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()), **(headers or {})}
        if csrf and method != "GET":
            h["X-CSRF-Token"] = self.cookies.get("gdl_csrf", "")
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=None if body is None else json.dumps(body).encode(), headers=h)
        r = c.getresponse()
        raw = r.read()
        for k, v in r.getheaders():
            if k.lower() == "set-cookie":
                name, _, val = v.split(";")[0].partition("=")
                self.cookies[name] = val
        c.close()
        try:
            return r.status, json.loads(raw or b"{}"), r
        except ValueError:
            return r.status, {}, r


@pytest.fixture
def web(tmp_path, monkeypatch):
    auth = Auth(tmp_path)
    monkeypatch.setattr(seguridad, "AUTH", auth)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), App)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield Cliente(httpd.server_address[1]), auth
    httpd.shutdown()
    httpd.server_close()


def _admin(c):
    assert c.req("POST", "/api/auth/crear-admin", {"usuario": "laura", "nombre": "Laura", "clave": CLAVE})[0] == 200


def test_sin_sesion_no_hay_datos(web):
    c, _ = web
    assert c.req("GET", "/api/calls")[0] == 401
    assert c.req("POST", "/api/process", {})[0] == 401
    assert c.req("DELETE", "/api/call/123")[0] == 401
    st, _, r = c.req("GET", "/")
    assert st == 302 and r.getheader("Location") == "/login"
    assert c.req("GET", "/login")[1] == {"archivo": "login.html"}
    assert c.req("GET", "/static/app.js")[0] == 200  # la interfaz es publica; los datos no


def test_primer_arranque_crea_el_administrador_una_sola_vez(web):
    c, _ = web
    assert c.req("GET", "/api/auth/estado")[1] == {"configurado": False, "sesion": None}
    _admin(c)
    assert c.req("GET", "/api/auth/estado")[1]["sesion"] == {"usuario": "laura", "nombre": "Laura", "rol": "admin"}
    assert c.req("GET", "/api/calls")[1]["usuario"] == "laura"
    otro = Cliente(c.port)
    assert otro.req("POST", "/api/auth/crear-admin", {"usuario": "intruso", "clave": CLAVE})[0] == 403


def test_cookie_de_sesion_no_es_legible_por_javascript(web):
    c, _ = web
    c.req("POST", "/api/auth/crear-admin", {"usuario": "laura", "clave": CLAVE})
    _, _, r = Cliente(c.port).req("POST", "/api/auth/login", {"usuario": "laura", "clave": CLAVE})
    cookies = [v for k, v in r.getheaders() if k.lower() == "set-cookie"]
    ses = next(v for v in cookies if v.startswith("gdl_sesion="))
    assert "HttpOnly" in ses and "SameSite=Strict" in ses


def test_login_fallido_no_da_sesion_ni_pistas(web):
    c, _ = web
    _admin(c)
    otro = Cliente(c.port)
    st, d, _ = otro.req("POST", "/api/auth/login", {"usuario": "laura", "clave": "mala-clave-0000"})
    assert st == 401 and d["error"] == "Usuario o contraseña incorrectos." and "gdl_sesion" not in otro.cookies
    assert otro.req("POST", "/api/auth/login", {"usuario": "nadie", "clave": CLAVE})[1] == d


def test_csrf_sin_token_o_desde_otro_sitio_se_rechaza(web):
    c, _ = web
    _admin(c)
    assert c.req("POST", "/api/process", {})[0] == 200
    assert c.req("POST", "/api/process", {}, csrf=False)[0] == 403
    assert c.req("POST", "/api/process", {}, headers={"Origin": "https://sitio-malo.example"})[0] == 403
    assert c.req("GET", "/api/calls", headers={"Host": "sitio-malo.example"})[0] == 403  # DNS rebinding


def test_el_auditor_no_puede_borrar_ni_administrar(web):
    c, auth = web
    _admin(c)
    assert c.req("POST", "/api/usuarios", {"usuario": "pedro", "clave": CLAVE, "rol": "auditor"})[0] == 200
    p = Cliente(c.port)
    assert p.req("POST", "/api/auth/login", {"usuario": "pedro", "clave": CLAVE})[0] == 200
    assert p.req("POST", "/api/review/123", {})[0] == 200  # su trabajo si
    for method, path in (("DELETE", "/api/call/123"), ("DELETE", "/api/quejas/q1"), ("POST", "/api/trazas/limpiar"), ("POST", "/api/notify"),
                         ("GET", "/api/usuarios"), ("POST", "/api/usuarios"), ("DELETE", "/api/usuarios/laura"), ("GET", "/api/accesos")):
        assert p.req(method, path, {})[0] == 403, (method, path)
    assert c.req("DELETE", "/api/call/123")[0] == 200  # el administrador si
    eventos = [(e["evento"], e["usuario"]) for e in auth.events()]
    assert ("permiso_denegado", "pedro") in eventos and ("accion", "laura") in eventos


def test_salir_cierra_la_sesion(web):
    c, _ = web
    _admin(c)
    assert c.req("POST", "/api/auth/salir", {})[0] == 200
    assert c.req("GET", "/api/calls")[0] == 401


def test_cuerpos_enormes_y_errores_internos_no_muestran_detalles(web):
    c, _ = web
    _admin(c)
    conn = http.client.HTTPConnection("127.0.0.1", c.port, timeout=10)
    conn.putrequest("POST", "/api/process")
    conn.putheader("Content-Length", str(seguridad.MAX_JSON + 1))
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()
    st, d, _ = c.req("GET", "/api/explota")
    assert st == 500 and "detalle interno" not in json.dumps(d) and "Traceback" not in json.dumps(d)
    assert c.req("POST", "/api/auth/login", [1, 2])[0] == 400  # JSON que no es un objeto


def test_cabeceras_de_seguridad_en_todas_las_respuestas(web):
    c, _ = web
    for path in ("/api/calls", "/login", "/static/app.js"):
        _, _, r = c.req("GET", path)
        csp = r.getheader("Content-Security-Policy")
        assert "connect-src 'self'" in csp and "img-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert r.getheader("X-Content-Type-Options") == "nosniff" and r.getheader("X-Frame-Options") == "DENY"
        assert r.getheader("Cache-Control") == "no-store"


def test_el_servidor_real_esta_detras_de_la_puerta(tmp_path, monkeypatch):
    from llamadas.gui import server
    monkeypatch.setattr(seguridad, "AUTH", Auth(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = Cliente(httpd.server_address[1])
        for path in ("/api/calls", "/api/state", "/api/quejas", "/api/trazas", "/api/export", "/api/audio/123", "/api/call/123"):
            assert c.req("GET", path)[0] == 401, path
        assert c.req("DELETE", "/api/call/123")[0] == 401 and c.req("POST", "/api/chat", {"question": "hola"})[0] == 401
        assert c.req("GET", "/")[0] == 302 and c.req("GET", "/login")[0] == 200 and c.req("GET", "/static/auth.js")[0] == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
