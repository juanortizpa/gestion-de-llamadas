import json, sys, pathlib
r=pathlib.Path("benchmarks/results")
for cid in sys.argv[1:]:
    d=json.load(open(r/"diar"/f"{cid}.json")); w=json.load(open(r/"small_beam1"/f"{cid}.json"))
    print("=====",cid)
    prev=None
    for s in w:
        ov={}
        for x in d:
            o=min(s["end"],x["end"])-max(s["start"],x["start"])
            if o>0: ov[x["spk"]]=ov.get(x["spk"],0)+o
        spk=max(ov,key=ov.get) if ov else "?"
        print(f"[{s['start']:6.1f}] S{spk}: {s['text']}")
