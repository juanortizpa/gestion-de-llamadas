"""B2: diarizacion con sherpa-onnx (pyannote-seg-3.0 + titanet_small), 2 hablantes. Solo medicion."""
import sys, time, json, wave, pathlib, threading, csv
import numpy as np, psutil, sherpa_onnx
root = pathlib.Path(__file__).resolve().parent.parent
nclust = int(sys.argv[1]) if len(sys.argv) > 1 else 2
cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
    segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
        pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(root/"models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx")),
        num_threads=4),
    embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(root/"models/titanet_small.onnx"), num_threads=4),
    clustering=sherpa_onnx.FastClusteringConfig(num_clusters=nclust),
    min_duration_on=0.3, min_duration_off=0.5)
sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
proc = psutil.Process(); peak=[0]; stop=threading.Event()
def s():
    while not stop.is_set(): peak[0]=max(peak[0],proc.memory_info().rss); time.sleep(0.2)
threading.Thread(target=s,daemon=True).start()
out = root/"benchmarks/results/diar"; out.mkdir(parents=True, exist_ok=True)
tot_a=tot_p=0
for f in sorted((root/"data/audio_tmp").glob("*.wav")):
    with wave.open(str(f)) as w: a=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    t=time.time(); r=sd.process(a).sort_by_start_time(); el=time.time()-t
    segs=[{"start":round(x.start,2),"end":round(x.end,2),"spk":x.speaker} for x in r]
    (out/f"{f.stem}.json").write_text(json.dumps(segs))
    d=len(a)/16000; tot_a+=d; tot_p+=el
    tt={k:round(sum(x["end"]-x["start"] for x in segs if x["spk"]==k),1) for k in sorted({x["spk"] for x in segs})}
    print(f.stem, round(d), "s", round(el,1), "s RTF", round(el/d,2), "segs", len(segs), "habla", tt, flush=True)
stop.set(); print(f"TOTAL RTF={tot_p/tot_a:.2f} pico_RAM={peak[0]/1e9:.2f}GB")
