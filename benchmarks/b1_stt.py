"""B1: mide tiempo, RTF y RAM pico de faster-whisper sobre las muestras. Solo medicion (no es el sistema)."""
import sys, time, json, threading, csv, pathlib, wave
import numpy as np
import psutil
from faster_whisper import WhisperModel

model_name, beam = sys.argv[1], int(sys.argv[2])
root = pathlib.Path(__file__).resolve().parent.parent
files = sorted((root / "data" / "audio_tmp").glob("*.wav"))
out = root / "benchmarks" / "results" / f"{model_name}_beam{beam}"
out.mkdir(parents=True, exist_ok=True)

proc = psutil.Process()
peak = [0]
stop = threading.Event()
def sample():
    while not stop.is_set():
        peak[0] = max(peak[0], proc.memory_info().rss)
        time.sleep(0.2)
threading.Thread(target=sample, daemon=True).start()

t0 = time.time()
model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
load_s = time.time() - t0
print(f"modelo {model_name} cargado en {load_s:.1f}s", flush=True)

rows = []
for f in files:
    t = time.time()
    with wave.open(str(f)) as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, info = model.transcribe(
        audio, language="es", beam_size=beam, vad_filter=True,
        condition_on_previous_text=False, word_timestamps=True,
        initial_prompt="Llamada de atencion al cliente de Angiografia de Occidente y Nueva EPS. Cedula, cita, examen, agenda.",
    )
    seglist = [{"start": s.start, "end": s.end, "text": s.text.strip(),
                "words": [{"w": w.word, "s": w.start, "e": w.end, "p": round(w.probability, 3)} for w in (s.words or [])]}
               for s in segs]
    el = time.time() - t
    (out / f"{f.stem}.json").write_text(json.dumps(seglist, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{f.stem}.txt").write_text("\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in seglist), encoding="utf-8")
    rows.append([f.stem, round(info.duration, 1), round(el, 1), round(el / info.duration, 2), round(peak[0] / 1e9, 2)])
    print(rows[-1], flush=True)

stop.set()
with open(out / "summary.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "audio_s", "proc_s", "RTF", "peak_ram_gb_acumulado"]); w.writerows(rows)
tot_a = sum(r[1] for r in rows); tot_p = sum(r[2] for r in rows)
print(f"TOTAL audio={tot_a:.0f}s proc={tot_p:.0f}s RTF={tot_p/tot_a:.2f} pico_RAM={peak[0]/1e9:.2f}GB carga={load_s:.1f}s")
