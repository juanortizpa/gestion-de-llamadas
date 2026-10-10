"""Descarga Qwen2.5-7B-Instruct Q4_K_M (GGUF) para comparar con el 3B en B3."""
import time
from pathlib import Path

from huggingface_hub import hf_hub_download

dest = Path(__file__).resolve().parent.parent / "models" / "llm"
t = time.time()
p = hf_hub_download("bartowski/Qwen2.5-7B-Instruct-GGUF", "Qwen2.5-7B-Instruct-Q4_K_M.gguf", local_dir=str(dest))
print("modelo", p, round(time.time() - t), "s", flush=True)
