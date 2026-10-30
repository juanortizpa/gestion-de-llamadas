"""Descarga los modelos que NO viven en git (carpeta models/). Ejecutar una sola vez con internet.

Uso:  .venv\\Scripts\\python.exe scripts\\descargar_modelos.py [--preciso]

  (siempre)   Whisper large-v3 (el de config/settings.toml), diarizacion (segmentacion + titanet), llama.cpp y Qwen2.5-3B  (~5 GB)
  --preciso   ademas Qwen2.5-7B (~4.5 GB), para el modo "Preciso"
  --chat      ademas el modelo de embeddings del Asistente (~150 MB; sin el, el Asistente busca solo por palabras)

Es idempotente: lo que ya existe no se vuelve a bajar.
"""
from __future__ import annotations

import argparse
import json
import platform
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
LLM = MODELS / "llm"

SEG_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
# "recongition" es el nombre real (con la errata) del release de sherpa-onnx
TITANET_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_small.onnx"


def bajar(url: str, dest: Path) -> None:
    print(f"  descargando {dest.name} ...", flush=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


def whisper() -> None:
    """Baja el MISMO modelo que usa la app ([stt] model en config/settings.toml); si no, el primer analisis lo bajaria sin avisar."""
    import tomllib
    modelo = tomllib.loads((ROOT / "config" / "settings.toml").read_text(encoding="utf-8"))["stt"]["model"]
    print(f"[1/4] Whisper {modelo} (voz a texto)")
    from faster_whisper.utils import download_model
    print("  listo:", download_model(modelo))


def diarizacion() -> None:
    print("[2/4] Diarizacion (separar asesor/cliente)")
    seg = MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    if not seg.exists():
        tgz = MODELS / "seg.tar.bz2"
        bajar(SEG_URL, tgz)
        with tarfile.open(tgz) as t:
            t.extractall(MODELS)
        tgz.unlink()
    emb = MODELS / "titanet_small.onnx"
    if not emb.exists():
        bajar(TITANET_URL, emb)
    print("  listo")


def llama_asset_key() -> str:
    """Fragmento del nombre del release de llama.cpp que corresponde a este sistema (version CPU: funciona en cualquier equipo)."""
    sistema, maquina = platform.system(), platform.machine().lower()
    arm = maquina in ("arm64", "aarch64")
    if sistema == "Windows":
        return "win-cpu-arm64" if arm else "win-cpu-x64"
    if sistema == "Darwin":
        return "macos-arm64" if arm else "macos-x64"
    if sistema == "Linux":
        return "ubuntu-arm64" if arm else "ubuntu-x64"
    raise SystemExit(f"Sistema no soportado para llama.cpp: {sistema} {maquina}")


def _find_server(base: Path) -> Path | None:
    return next((p for n in ("llama-server.exe", "llama-server") for p in base.rglob(n) if p.is_file()), None)


def llama_cpp() -> None:
    print("[3/4] llama.cpp (motor de la IA local)")
    base = LLM / "llama.cpp"
    if base.exists() and _find_server(base):
        print("  ya existe")
        return
    key = llama_asset_key()
    rels = json.load(urllib.request.urlopen("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"))
    rel = next(r for r in rels if r["tag_name"].startswith("b"))
    asset = next((a for a in rel["assets"] if f"bin-{key}." in a["name"] and a["name"].endswith((".zip", ".tar.gz"))), None)
    if asset is None:
        raise SystemExit(f"El release {rel['tag_name']} de llama.cpp no trae el paquete '{key}'. Descargue llama.cpp a mano en {base}")
    pkg = LLM / asset["name"]
    bajar(asset["browser_download_url"], pkg)
    base.mkdir(parents=True, exist_ok=True)
    if pkg.name.endswith(".zip"):
        with zipfile.ZipFile(pkg) as z:
            z.extractall(base)
    else:
        with tarfile.open(pkg) as t:
            t.extractall(base, filter="data")      # filtro seguro: rechaza rutas absolutas y enlaces que salgan de la carpeta
    pkg.unlink()
    exe = _find_server(base)
    if exe is None:
        raise SystemExit(f"No encontre llama-server dentro de {base}")
    if platform.system() != "Windows":
        exe.chmod(exe.stat().st_mode | 0o111)      # el .tar.gz puede perder el permiso de ejecucion
    print("  listo", rel["tag_name"], "->", exe.relative_to(MODELS))


def gguf(repo: str, fichero: str, etiqueta: str) -> None:
    print(etiqueta)
    if (LLM / fichero).exists():
        print("  ya existe")
        return
    from huggingface_hub import hf_hub_download
    hf_hub_download(repo, fichero, local_dir=str(LLM))
    print("  listo")


def embeddings() -> None:
    """multilingual-e5-small en GGUF (conversion de la comunidad: verificar licencia y calidad antes de uso en produccion)."""
    print("[+] Modelo de embeddings del Asistente (multilingual-e5-small, ~150 MB)")
    dest = LLM / "multilingual-e5-small-q8_0.gguf"
    if dest.exists():
        print("  ya existe")
        return
    from huggingface_hub import hf_hub_download, list_repo_files
    repo = "TwinSunsLLC/multilingual-e5-small-gguf"
    files = [f for f in list_repo_files(repo) if f.lower().endswith(".gguf")]
    pick = next((f for f in files if "q8_0" in f.lower()), None) or next(iter(files), None)
    if not pick:
        raise SystemExit(f"No encontre archivos .gguf en {repo}. Descargue un GGUF de multilingual-e5-small y guardelo como {dest}")
    path = hf_hub_download(repo, pick, local_dir=str(LLM / "_e5"))
    Path(path).replace(dest)
    print("  listo:", pick)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preciso", action="store_true", help="descarga tambien Qwen2.5-7B (modo Preciso)")
    ap.add_argument("--chat", action="store_true", help="descarga tambien el modelo de embeddings del Asistente")
    ap.add_argument("--solo-voz", action="store_true", help="solo voz a texto y separacion de hablantes (~3,2 GB): para usar IA externa")
    a = ap.parse_args()
    MODELS.mkdir(exist_ok=True)
    LLM.mkdir(exist_ok=True)
    whisper()
    diarizacion()
    if a.solo_voz:
        print("\nModelos de voz listos. Ya puede ejecutar iniciar.py")
        raise SystemExit(0)
    llama_cpp()
    gguf("Qwen/Qwen2.5-3B-Instruct-GGUF", "qwen2.5-3b-instruct-q4_k_m.gguf", "[4/4] IA local rapida (Qwen2.5-3B, ~2 GB)")
    if a.preciso:
        gguf("bartowski/Qwen2.5-7B-Instruct-GGUF", "Qwen2.5-7B-Instruct-Q4_K_M.gguf", "[+] IA local precisa (Qwen2.5-7B, ~4.5 GB)")
    if a.chat:
        embeddings()
    print("\nModelos listos. Ya puede ejecutar iniciar.py")
