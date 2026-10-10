"""Descarga llama.cpp (binario Windows CPU) y un GGUF pequeno para B3. Solo preparacion de benchmark."""
import json, urllib.request, zipfile, pathlib, sys, time
root = pathlib.Path(__file__).resolve().parent.parent
dest = root / "models" / "llm"
dest.mkdir(parents=True, exist_ok=True)

rels = json.load(urllib.request.urlopen("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"))
rel = next(r for r in rels if r["tag_name"].startswith("b"))   # 'latest' puede apuntar a otro tag
asset = next(a for a in rel["assets"] if "win-cpu-x64" in a["name"] and a["name"].endswith(".zip"))
print("llama.cpp", rel["tag_name"], asset["name"], round(asset["size"] / 1e6), "MB", flush=True)
zp = dest / asset["name"]
urllib.request.urlretrieve(asset["browser_download_url"], zp)
with zipfile.ZipFile(zp) as z:
    z.extractall(dest / "llama.cpp")
print("llama.cpp listo", flush=True)

from huggingface_hub import hf_hub_download
t = time.time()
p = hf_hub_download("Qwen/Qwen2.5-3B-Instruct-GGUF", "qwen2.5-3b-instruct-q4_k_m.gguf", local_dir=str(dest))
print("modelo", p, round(time.time() - t), "s", flush=True)
