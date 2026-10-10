import sys, json, wave, pathlib, time
import numpy as np, sherpa_onnx
root=pathlib.Path(".")
def run(cid, emb, k, thr=None):
    cl = sherpa_onnx.FastClusteringConfig(num_clusters=k) if k else sherpa_onnx.FastClusteringConfig(threshold=thr)
    cfg=sherpa_onnx.OfflineSpeakerDiarizationConfig(
      segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model="models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx"),num_threads=4),
      embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model="models/"+emb,num_threads=4),
      clustering=cl, min_duration_on=0.3, min_duration_off=0.5)
    sd=sherpa_onnx.OfflineSpeakerDiarization(cfg)
    with wave.open(f"data/audio_tmp/{cid}.wav") as w: a=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    r=sd.process(a).sort_by_start_time()
    return [{"start":x.start,"end":x.end,"spk":x.speaker} for x in r]
if __name__=="__main__":
    for cid in ["2091394","1870590","2091790"]:
        for emb in ["titanet_small.onnx","wespeaker_en_voxceleb_resnet34_LM.onnx","3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"]:
            if not (root/"models"/emb).exists(): continue
            for k in (2,3):
                d=run(cid,emb,k); tt={s:round(sum(x["end"]-x["start"] for x in d if x["spk"]==s)) for s in sorted({x["spk"] for x in d})}
                print(cid,emb[:12],"k=",k,tt,flush=True)
