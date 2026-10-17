"""Piezas que hacen que el programa corra igual en Windows, macOS y Linux (sin necesitar esos sistemas para probarlas)."""
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dm = cargar("descargar_modelos", ROOT / "scripts" / "descargar_modelos.py")
ini = cargar("iniciar", ROOT / "iniciar.py")

# nombres reales de los paquetes de un release de llama.cpp (incluye variantes GPU que NO deben elegirse)
ASSETS = ["llama-b1-bin-macos-arm64.tar.gz", "llama-b1-bin-macos-x64.tar.gz", "llama-b1-bin-ubuntu-arm64.tar.gz",
          "llama-b1-bin-ubuntu-cuda-12.8-x64.tar.gz", "llama-b1-bin-ubuntu-vulkan-x64.tar.gz", "llama-b1-bin-ubuntu-x64.tar.gz",
          "llama-b1-bin-win-cpu-arm64.zip", "llama-b1-bin-win-cpu-x64.zip", "llama-b1-bin-win-cuda-12.4-x64.zip", "llama-b1-bin-win-vulkan-x64.zip"]


@pytest.mark.parametrize("sistema,maquina,esperado", [
    ("Windows", "AMD64", "llama-b1-bin-win-cpu-x64.zip"), ("Windows", "ARM64", "llama-b1-bin-win-cpu-arm64.zip"),
    ("Darwin", "arm64", "llama-b1-bin-macos-arm64.tar.gz"), ("Darwin", "x86_64", "llama-b1-bin-macos-x64.tar.gz"),
    ("Linux", "x86_64", "llama-b1-bin-ubuntu-x64.tar.gz"), ("Linux", "aarch64", "llama-b1-bin-ubuntu-arm64.tar.gz")])
def test_paquete_de_llama_cpp_por_sistema(monkeypatch, sistema, maquina, esperado):
    monkeypatch.setattr(dm.platform, "system", lambda: sistema)
    monkeypatch.setattr(dm.platform, "machine", lambda: maquina)
    key = dm.llama_asset_key()
    elegidos = [a for a in ASSETS if f"bin-{key}." in a]
    assert elegidos == [esperado]            # exactamente uno: la variante CPU, nunca CUDA/Vulkan


def test_sistema_no_soportado(monkeypatch):
    monkeypatch.setattr(dm.platform, "system", lambda: "Plan9")
    with pytest.raises(SystemExit):
        dm.llama_asset_key()


def test_find_llama_server_en_cualquier_carpeta_y_nombre(tmp_path):
    from llamadas.llm import find_llama_server
    assert not find_llama_server(tmp_path, "").exists()                       # nada instalado
    d = tmp_path / "llm" / "llama.cpp" / "build" / "bin"
    d.mkdir(parents=True)
    (d / "llama-server").write_bytes(b"")                                     # Linux/macOS
    assert find_llama_server(tmp_path, "") == d / "llama-server"
    (d / "llama-server.exe").write_bytes(b"")                                 # Windows tiene prioridad si existe
    assert find_llama_server(tmp_path, "") == d / "llama-server.exe"
    (tmp_path / "otro").write_bytes(b"")
    assert find_llama_server(tmp_path, "otro") == tmp_path / "otro"           # la ruta de settings.toml manda si existe


def test_ffmpeg_cae_al_de_pip(monkeypatch, tmp_path):
    from llamadas import audio
    monkeypatch.setattr(audio.shutil, "which", lambda n: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    falso = types.SimpleNamespace(get_ffmpeg_exe=lambda: "/ruta/ffmpeg-pip")
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", falso)
    assert audio.find_ffmpeg() == "/ruta/ffmpeg-pip"
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)                  # ni sistema ni pip: error claro, sin traza rara
    with pytest.raises(RuntimeError, match="ffmpeg no encontrado"):
        audio.find_ffmpeg()


def test_python_del_entorno_segun_so():
    p = str(ini.python_del_entorno())
    assert p.endswith("python.exe" if os.name == "nt" else "bin/python") and ".venv" in p


def test_python_viejo_se_rechaza(monkeypatch, capsys):
    monkeypatch.setattr(ini, "MIN_PY", (99, 0))
    with pytest.raises(SystemExit) as e:
        ini.revisar_python()
    assert e.value.code == 1 and "Python 99.0" in capsys.readouterr().out


@pytest.fixture
def flujo(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(ini, "ROOT", tmp_path)
    monkeypatch.setattr(ini, "revisar_python", lambda: llamadas.append("python"))
    monkeypatch.setattr(ini, "preparar_entorno", lambda: llamadas.append("entorno"))
    monkeypatch.setattr(ini, "menu_instalacion", lambda: llamadas.append("menu") or 0)
    monkeypatch.setattr(ini, "abrir_programa", lambda puerto: llamadas.append(f"abrir:{puerto}") or 0)
    return llamadas, tmp_path


def test_primera_vez_muestra_el_menu_y_abre(monkeypatch, flujo):
    llamadas, _ = flujo
    monkeypatch.setattr("sys.argv", ["iniciar.py"])
    assert ini.main() == 0
    assert llamadas == ["python", "entorno", "menu", "abrir:8765"]


def test_con_env_solo_abre(monkeypatch, flujo):
    llamadas, raiz = flujo
    (raiz / ".env").write_text("LLM_PROVIDER=local\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["iniciar.py", "--puerto", "9000"])
    assert ini.main() == 0 and llamadas == ["python", "entorno", "abrir:9000"]


def test_instalar_fuerza_el_menu_y_solo_preparar_no_abre(monkeypatch, flujo):
    llamadas, raiz = flujo
    (raiz / ".env").write_text("x=1\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["iniciar.py", "--instalar", "--solo-preparar"])
    assert ini.main() == 0 and llamadas == ["python", "entorno", "menu"]


def test_si_la_instalacion_falla_y_no_hay_env_no_abre(monkeypatch, flujo):
    llamadas, _ = flujo
    monkeypatch.setattr(ini, "menu_instalacion", lambda: 1)
    monkeypatch.setattr("sys.argv", ["iniciar.py"])
    assert ini.main() == 1 and "abrir" not in " ".join(llamadas)


def test_run_sh_tiene_finales_de_linea_unix():
    assert b"\r\n" not in (ROOT / "run.sh").read_bytes()
    assert (ROOT / "run.sh").read_text(encoding="utf-8").startswith("#!/usr/bin/env sh")
