"""Descarga los modelos que NO viven en git (carpeta models/). Ejecutar una sola vez con internet.

Uso:  .venv\\Scripts\\python.exe scripts\\descargar_modelos.py [--preciso]

  (siempre)   Whisper medium, diarizacion (segmentacion + titanet), llama.cpp y Qwen2.5-3B  (~3 GB)
  --preciso   ademas Qwen2.5-7B (~4.5 GB), para el modo "Preciso"

Es idempotente: lo que ya existe no se vuelve a bajar.
"""
from __future__ import annotations

import argparse
import json
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
    print("[1/4] Whisper medium (voz a texto)")
    from faster_whisper.utils import download_model
    print("  listo:", download_model("medium"))


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


def llama_cpp() -> None:
    print("[3/4] llama.cpp (motor de la IA local)")
    exe = LLM / "llama.cpp" / "llama-server.exe"
    if exe.exists():
        print("  ya existe")
        return
    rels = json.load(urllib.request.urlopen("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"))
    rel = next(r for r in rels if r["tag_name"].startswith("b"))
    asset = next(a for a in rel["assets"] if "win-cpu-x64" in a["name"] and a["name"].endswith(".zip"))
    zp = LLM / asset["name"]
    bajar(asset["browser_download_url"], zp)
    with zipfile.ZipFile(zp) as z:
        z.extractall(LLM / "llama.cpp")
    zp.unlink()
    if not exe.exists():  # algunos zips traen una subcarpeta
        found = next((LLM / "llama.cpp").rglob("llama-server.exe"), None)
        raise SystemExit(f"llama-server.exe no quedo en {exe}; encontrado en: {found}")
    print("  listo", rel["tag_name"])


def gguf(repo: str, fichero: str, etiqueta: str) -> None:
    print(etiqueta)
    if (LLM / fichero).exists():
        print("  ya existe")
        return
    from huggingface_hub import hf_hub_download
    hf_hub_download(repo, fichero, local_dir=str(LLM))
    print("  listo")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preciso", action="store_true", help="descarga tambien Qwen2.5-7B (modo Preciso)")
    a = ap.parse_args()
    MODELS.mkdir(exist_ok=True)
    LLM.mkdir(exist_ok=True)
    whisper()
    diarizacion()
    llama_cpp()
    gguf("Qwen/Qwen2.5-3B-Instruct-GGUF", "qwen2.5-3b-instruct-q4_k_m.gguf", "[4/4] IA local rapida (Qwen2.5-3B, ~2 GB)")
    if a.preciso:
        gguf("bartowski/Qwen2.5-7B-Instruct-GGUF", "Qwen2.5-7B-Instruct-Q4_K_M.gguf", "[+] IA local precisa (Qwen2.5-7B, ~4.5 GB)")
    print("\nModelos listos. Ya puede ejecutar Iniciar_Auditoria.bat")
