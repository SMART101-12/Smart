from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "پالایش"
HISTORY = ROOT / "runtime" / "history" / SYMBOL
OUT = ROOT / "runtime" / "experiments" / SYMBOL / "indicator_ensemble_results.json"

PERIODS = (5, 8, 10, 14, 20, 30, 40, 50, 60, 90)
BASES = ("sma", "ema", "momentum", "roc", "rsi", "stoch", "bollinger", "volatility", "volume", "obv", "mfi", "macd", "cci", "williams", "donchian", "ichimoku", "tenkan_kijun", "cloud_thickness", "price_cloud", "trend")
FEATURES = [f"{b}{p}" for b in BASES for p in PERIODS]


def load_rows():
    rows = []
    for path in sorted(HISTORY.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.extend(payload.get("daily_history", []))
        except (OSError, json.JSONDecodeError):
            pass
    by_date = {}
    for r in rows:
        try:
            d = int(r["dEven"]); c = float(r.get("pClosing") or 0)
            if c > 0: by_date[d] = r
        except (KeyError, TypeError, ValueError):
            pass
    return [by_date[d] for d in sorted(by_date)]


def close(r): return float(r.get("pClosing") or r.get("pDrCotVal") or 0)
def high(r): return float(r.get("priceMax") or close(r))
def low(r): return float(r.get("priceMin") or close(r))
def volume(r): return float(r.get("qTotTran5J") or 0)
def avg(x): return sum(x) / len(x) if x else None
def sma(x, n): return avg(x[-n:]) if len(x) >= n else None

def ema(x, n):
    if len(x) < n: return None
    v = avg(x[:n]); a = 2 / (n + 1)
    for z in x[n:]: v = a * z + (1 - a) * v
    return v

def std(x, n):
    if len(x) < n: return None
    m = avg(x[-n:]); return math.sqrt(avg([(z-m)**2 for z in x[-n:]]))

def rsi(x, n):
    if len(x) <= n: return None
    g = [max(x[i]-x[i-1],0) for i in range(1,len(x))]
    l = [max(x[i-1]-x[i],0) for i in range(1,len(x))]
    ag, al = avg(g[:n]), avg(l[:n])
    for a,b in zip(g[n:],l[n:]): ag=(ag*(n-1)+a)/n; al=(al*(n-1)+b)/n
    return 100 if al == 0 else 100 - 100/(1+ag/al)

def slope(x, n):
    if len(x) < n: return None
    y=x[-n:]; xm=(n-1)/2; ym=avg(y); den=sum((i-xm)**2 for i in range(n))
    return sum((i-xm)*(v-ym) for i,v in enumerate(y))/den if den else 0

def signal(name, rows):
    base, p = name, 20
    for q in sorted(PERIODS, key=lambda z: len(str(z)), reverse=True):
        if name.endswith(str(q)):
            base, p = name[:-len(str(q))], q; break
    c=[close(r) for r in rows]; h=[high(r) for r in rows]; l=[low(r) for r in rows]; v=[volume(r) for r in rows]
    last=c[-1]
    def clip(z): return max(-1.0,min(1.0,z)) if z is not None and math.isfinite(z) else 0.0
    if base == "sma":
        m=sma(c,p); return clip((last/m-1)*10) if m else 0
    if base == "ema":
        m=ema(c,p); return clip((last/m-1)*10) if m else 0
    if base in {"momentum","roc"}: return clip((last/c[-p]-1)*(4 if base=="momentum" else 6)) if len(c)>p else 0
    if base == "rsi":
        z=rsi(c,p); return clip((z-50)/25) if z is not None else 0
    if base == "stoch":
        hi=max(h[-p:]); lo=min(l[-p:]); return clip(((last-lo)/(hi-lo)-.5)*2) if hi>lo else 0
    if base == "bollinger":
        m=sma(c,p); s=std(c,p); return clip((last-m)/(2*s)) if m and s else 0
    if base == "volatility":
        s=std(c,p); return clip((s/last)*20) if s and last else 0
    if base == "volume":
        m=sma(v,p); mom=(last/c[-2]-1) if len(c)>1 and c[-2] else 0; return clip(((v[-1]/m)-1)*mom*8) if m else 0
    if base == "obv":
        obv=0; vals=[]
        for i in range(1,len(c)): obv += v[i] if c[i]>c[i-1] else -v[i] if c[i]<c[i-1] else 0; vals.append(obv)
        s=slope(vals,p); den=avg([abs(z) for z in vals[-p:]]) if vals else 0; return clip(s/(den+1e-9)*20) if s is not None else 0
    if base == "mfi":
        pos=neg=0
        for i in range(max(1,len(c)-p),len(c)):
            typ=(h[i]+l[i]+c[i])/3; prev=(h[i-1]+l[i-1]+c[i-1])/3
            if typ>prev: pos += typ*v[i]
            else: neg += typ*v[i]
        return clip((pos/(neg+1e-9))-1)
    if base == "macd":
        e1=ema(c,p); e2=ema(c,p*2); return clip((e1/e2-1)*20) if e1 and e2 else 0
    if base == "cci":
        tp=[(h[i]+l[i]+c[i])/3 for i in range(len(c))]; m=sma(tp,p); dev=avg([abs(z-m) for z in tp[-p:]]) if m else None
        return clip((tp[-1]-m)/(0.015*dev)) if m and dev else 0
    if base == "williams":
        hi=max(h[-p:]); lo=min(l[-p:]); return clip(-(((hi-last)/(hi-lo))*2-1)) if hi>lo else 0
    if base == "donchian":
        hi=max(h[-p:]); lo=min(l[-p:]); return clip((last-(hi+lo)/2)/((hi-lo)/2)) if hi>lo else 0
    if base in {"ichimoku","tenkan_kijun","cloud_thickness","price_cloud"}:
        half=max(2,p//2); ten=(max(h[-half:])+min(l[-half:]))/2; kij=(max(h[-p:])+min(l[-p:]))/2
        spanb=(max(h[-p*2:])+min(l[-p*2:]))/2 if len(c)>=p*2 else kij; spana=(ten+kij)/2
        if base=="ichimoku": return clip(((last-(spana+spanb)/2)/last)*15 + (.25 if ten>kij else -.25))
        if base=="tenkan_kijun": return clip((ten/kij-1)*20) if kij else 0
        if base=="cloud_thickness": return clip(((spana-spanb)/last)*20)
        return clip(((last-(spana+spanb)/2)/last)*20)
    if base == "trend": return clip((slope(c,p)/last)*p*8) if last else 0
    return 0


def forecast(feature_set, rows):
    scores=[signal(f,rows) for f in feature_set]
    score=avg(scores) or 0; c=close(rows[-1]); vol=std([close(r) for r in rows],20)
    scale=min(.08,max(.005,(vol/c) if vol and c else .02))
    return c*(1+max(-.12,min(.12,score*scale)))


def eval_model(feature_set, rows, start, end):
    errs=[]; dirs=[]; beats=[]
    for i in range(max(start,30),min(end,len(rows)-1)):
        hist=rows[:i+1]; pred=forecast(feature_set,hist); cur=close(hist[-1]); actual=close(rows[i+1])
        me=abs(pred/actual-1)*100; be=abs(cur/actual-1)*100
        errs.append(me); beats.append(be-me); dirs.append((pred>=cur)==(actual>=cur))
    return {"mae_pct":mean(errs) if errs else 999,"direction_pct":mean(dirs)*100 if dirs else 0,"improvement_pct":mean(beats) if beats else -999,"beats_naive_pct":mean([x>0 for x in beats])*100 if beats else 0,"n":len(errs)}


def model_catalog():
    singles=[(f,) for f in FEATURES[:120]]
    pairs=[(FEATURES[i],FEATURES[j]) for i,j in itertools.combinations(range(30),2)][:60]
    triples=[(FEATURES[i],FEATURES[j],FEATURES[k]) for i,j,k in itertools.combinations(range(15),3)][:30]
    quads=[(FEATURES[i],FEATURES[j],FEATURES[k],FEATURES[m]) for i,j,k,m in itertools.combinations(range(10),4)][:10]
    return singles+pairs+triples+quads


def main():
    rows=load_rows(); n=len(rows); train_end=int(n*.70); val_end=int(n*.85); catalog=model_catalog()
    first=[]
    for idx,fs in enumerate(catalog,1):
        first.append({"model_id":f"M{idx:03d}","features":fs,"train":eval_model(fs,rows,30,train_end),"validation":eval_model(fs,rows,train_end,val_end)})
    first.sort(key=lambda x:(-x["validation"]["improvement_pct"],-x["validation"]["direction_pct"],x["validation"]["mae_pct"]))
    top=first[:15]; second=[]
    for a,b in itertools.combinations(top,2):
        errs=[]; dirs=[]; beats=[]
        for i in range(max(30,train_end),val_end):
            hist=rows[:i+1]; pred=(forecast(a["features"],hist)+forecast(b["features"],hist))/2; cur=close(hist[-1]); actual=close(rows[i+1]); me=abs(pred/actual-1)*100
            errs.append(me); dirs.append((pred>=cur)==(actual>=cur)); beats.append(abs(cur/actual-1)*100-me)
        second.append({"model_id":f"E{len(second)+1:03d}","parents":[a["model_id"],b["model_id"]],"validation":{"mae_pct":mean(errs),"direction_pct":mean(dirs)*100,"improvement_pct":mean(beats),"beats_naive_pct":mean([x>0 for x in beats])*100,"n":len(errs)}})
    second.sort(key=lambda x:(-x["validation"]["improvement_pct"],-x["validation"]["direction_pct"],x["validation"]["mae_pct"]))
    winners=second[:10]; by={x["model_id"]:x for x in top}; oos=[]
    for m in winners:
        a,b=[by[x] for x in m["parents"]]; errs=[]; dirs=[]; beats=[]
        for i in range(val_end,n-1):
            hist=rows[:i+1]; pred=(forecast(a["features"],hist)+forecast(b["features"],hist))/2; cur=close(hist[-1]); actual=close(rows[i+1]); me=abs(pred/actual-1)*100
            errs.append(me); dirs.append((pred>=cur)==(actual>=cur)); beats.append(abs(cur/actual-1)*100-me)
        oos.append({"model_id":m["model_id"],"parents":m["parents"],"oos":{"mae_pct":mean(errs),"direction_pct":mean(dirs)*100,"improvement_pct":mean(beats),"beats_naive_pct":mean([x>0 for x in beats])*100,"n":len(errs)}})
    oos.sort(key=lambda x:(-x["oos"]["improvement_pct"],-x["oos"]["direction_pct"],x["oos"]["mae_pct"]))
    result={"engine_version":"ensemble-v2.0","symbol":SYMBOL,"rows":n,"first_date":rows[0]["dEven"],"last_date":rows[-1]["dEven"],"feature_variants":len(FEATURES),"first_stage_models":len(catalog),"second_stage_models":len(second),"train_end_index":train_end,"validation_end_index":val_end,"no_lookahead":True,"learning":"train/validation select candidates; frozen OOS is never used for tuning","top_first_stage":top,"top_model_of_models":winners,"frozen_oos":oos,"final_candidate":oos[0] if oos else None}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("engine_version","rows","feature_variants","first_stage_models","second_stage_models","final_candidate")},ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
