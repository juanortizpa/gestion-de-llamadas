"""Menu de instalacion: escribe .env sin pisar lo demas, avisa antes de enviar datos fuera y no filtra la clave."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("instalar", Path(__file__).resolve().parents[2] / "scripts" / "instalar.py")
inst = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inst)


@pytest.fixture
def env(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    monkeypatch.setattr(inst, "ENV", p)
    return p


def test_upsert_conserva_comentarios_y_otras_claves(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# nota\nGROQ_API_KEY=vieja\nOTRA=1\n", encoding="utf-8")
    inst.upsert_env(p, {"GROQ_API_KEY": "nueva", "LLM_PROVIDER": "groq"})
    assert p.read_text(encoding="utf-8").splitlines() == ["# nota", "GROQ_API_KEY=nueva", "OTRA=1", "LLM_PROVIDER=groq"]


def test_externo_guarda_proveedor_y_clave(env):
    assert inst.install_external("groq", "k123", probar=False, confirmado=True) == 0
    txt = env.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=groq" in txt and "GROQ_API_KEY=k123" in txt and "DATABASE_URL=sqlite" in txt


def test_externo_sin_aceptar_el_aviso_no_guarda_nada(env, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    assert inst.install_external("gemini", "k", probar=False) == 1
    assert not env.exists()


def test_externo_sin_clave_no_guarda(env, monkeypatch):
    monkeypatch.setattr(inst.getpass, "getpass", lambda *_: "")
    assert inst.install_external("groq", None, probar=False, confirmado=True) == 1
    assert not env.exists()


def test_proveedor_desconocido(env):
    assert inst.install_external("openai", "k", probar=False, confirmado=True) == 1


def test_menu_opcion_2_con_teclado(env, monkeypatch, capsys):
    respuestas = iter(["2", "b", "s"])        # opcion 2, Gemini, acepta el aviso
    monkeypatch.setattr("builtins.input", lambda *_: next(respuestas))
    monkeypatch.setattr(inst.getpass, "getpass", lambda *_: "clave-gemini")
    monkeypatch.setattr("sys.argv", ["instalar.py", "--sin-prueba"])
    assert inst.main() == 0
    out = capsys.readouterr().out
    assert "Instalacion" in out and "TEXTOS de las llamadas" in out and "clave-gemini" not in out
    assert "LLM_PROVIDER=gemini" in env.read_text(encoding="utf-8")


def test_menu_opcion_invalida(env, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "9")
    monkeypatch.setattr("sys.argv", ["instalar.py"])
    assert inst.main() == 1


def test_local_escribe_proveedor_local(env, monkeypatch):
    llamadas = []
    monkeypatch.setattr(inst.subprocess, "call", lambda cmd, cwd=None: llamadas.append(cmd) or 0)
    assert inst.install_local(preciso=True, chat=True) == 0
    assert "--preciso" in llamadas[0] and "--chat" in llamadas[0]
    assert "LLM_PROVIDER=local" in env.read_text(encoding="utf-8")


def test_local_si_la_descarga_falla_no_cambia_el_modo(env, monkeypatch):
    monkeypatch.setattr(inst.subprocess, "call", lambda cmd, cwd=None: 1)
    assert inst.install_local(preciso=False, chat=False) == 1
    assert not env.exists()
