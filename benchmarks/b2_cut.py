"""B2b: diarizacion solo del tramo previo al hold (llamada 2091394) para ver si asesor/cliente se separan sin el mensaje grabado."""
import json, wave, sys, pathlib
sys.path.insert(0, "benchmarks")
import b2_variants as v

cid, T = "2091394", 95
w = json.load(open(f"benchmarks/results/small_beam1/{cid}.json", encoding="utf-8"))
with wave.open(f"data/audio_tmp/{cid}.wav") as f:
    a = f.readframes(int(16000 * T))
with wave.open("data/audio_tmp/_cut.wav", "wb") as o:
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(16000); o.writeframes(a)
for emb in ["titanet_small.onnx", "wespeaker_en_voxceleb_resnet34_LM.onnx"]:
    d = v.run("_cut", emb, 2)
    print("==", emb)
    for s in w:
        if s["start"] > T:
            break
        ov = {}
        for x in d:
            o = min(s["end"], x["end"]) - max(s["start"], x["start"])
            if o > 0:
                ov[x["spk"]] = ov.get(x["spk"], 0) + o
        print(f"[{s['start']:5.1f}] S{max(ov, key=ov.get) if ov else '?'}: {s['text']}")
pathlib.Path("data/audio_tmp/_cut.wav").unlink()
