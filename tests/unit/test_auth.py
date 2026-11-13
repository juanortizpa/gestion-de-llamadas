"""Usuarios y sesiones: contrasenas derivadas (nunca en claro), bloqueo por intentos, caducidad, roles y bitacora."""
import json

import pytest

from llamadas.auth import Auth, AuthError

CLAVE = "clave-segura-2026"


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def auth(tmp_path):
    a = Auth(tmp_path, clock=Reloj())
    a.create_user("laura", CLAVE, "admin", "Laura Gómez")
    return a


def test_la_clave_no_se_guarda_en_claro(auth, tmp_path):
    texto = (tmp_path / "usuarios.json").read_text(encoding="utf-8")
    assert CLAVE not in texto and json.loads(texto)["laura"]["rol"] == "admin"
    assert all("clave" not in u and "sal" not in u for u in auth.users())


def test_login_correcto_e_incorrecto_dan_el_mismo_mensaje(auth):
    token, ses = auth.login("Laura ", CLAVE)
    assert auth.session(token)["user"] == "laura" and ses["role"] == "admin" and ses["csrf"]
    for usuario, clave in (("laura", "otra-clave-2026"), ("no-existe", CLAVE)):
        with pytest.raises(AuthError) as e:
            auth.login(usuario, clave)
        assert e.value.code == 401 and str(e.value) == "Usuario o contraseña incorrectos."


def test_bloqueo_tras_cinco_intentos_y_se_levanta_solo(auth):
    for _ in range(5):
        with pytest.raises(AuthError):
            auth.login("laura", "mala-clave-0000")
    with pytest.raises(AuthError) as e:
        auth.login("laura", CLAVE)  # ni con la clave correcta mientras dure el bloqueo
    assert e.value.code == 429 and "Espere 5 min" in str(e.value)
    auth.clock.t += 5 * 60 + 1
    assert auth.login("laura", CLAVE)[0]


def test_la_sesion_caduca_por_inactividad_y_por_tiempo_maximo(auth):
    token, _ = auth.login("laura", CLAVE)
    auth.clock.t += 29 * 60
    assert auth.session(token)  # el uso renueva la inactividad
    auth.clock.t += 31 * 60
    assert auth.session(token) is None
    token, _ = auth.login("laura", CLAVE)
    for _ in range(17):  # activa todo el tiempo, pero pasan mas de 8 horas
        auth.clock.t += 29 * 60
        auth.session(token)
    assert auth.session(token) is None


def test_logout_y_token_desconocido(auth):
    token, _ = auth.login("laura", CLAVE)
    auth.logout(token)
    assert auth.session(token) is None and auth.session("inventado") is None and auth.session(None) is None


@pytest.mark.parametrize("usuario, clave", [("ab", CLAVE), ("Con Espacio", CLAVE), ("pedro", "corta1"), ("pedro", "solamenteletras"),
                                             ("pedro", "1234567890123"), ("pedro", "pedro-2026-clave")])
def test_usuarios_y_claves_debiles_se_rechazan(auth, usuario, clave):
    with pytest.raises(AuthError):
        auth.create_user(usuario, clave)


def test_no_se_puede_duplicar_ni_dejar_el_sistema_sin_administrador(auth):
    with pytest.raises(AuthError):
        auth.create_user("laura", CLAVE)
    auth.create_user("pedro", CLAVE, "auditor")
    with pytest.raises(AuthError, match="propio"):
        auth.delete_user("laura", por="laura")
    with pytest.raises(AuthError, match="administrador"):
        auth.delete_user("laura", por="pedro")


def test_eliminar_un_usuario_cierra_sus_sesiones(auth):
    auth.create_user("pedro", CLAVE, "auditor")
    token, _ = auth.login("pedro", CLAVE)
    auth.delete_user("pedro", por="laura")
    assert auth.session(token) is None
    with pytest.raises(AuthError):
        auth.login("pedro", CLAVE)


def test_cambiar_la_clave_exige_la_actual_y_cierra_las_otras_sesiones(auth):
    t1, _ = auth.login("laura", CLAVE)
    t2, _ = auth.login("laura", CLAVE)
    with pytest.raises(AuthError):
        auth.set_password("laura", "no-es-la-actual-1", "nueva-clave-2027")
    auth.set_password("laura", CLAVE, "nueva-clave-2027", keep=t1)
    assert auth.session(t1) and auth.session(t2) is None
    assert auth.login("laura", "nueva-clave-2027")[0]


def test_la_bitacora_registra_eventos_sin_claves_ni_tokens(auth, tmp_path):
    token, _ = auth.login("laura", CLAVE)
    with pytest.raises(AuthError):
        auth.login("laura", "mala-clave-0000")
    texto = (tmp_path / "accesos.jsonl").read_text(encoding="utf-8")
    assert CLAVE not in texto and "mala-clave-0000" not in texto and token not in texto
    assert [e["evento"] for e in auth.events()][:2] == ["login_fallido", "login"]
