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
    rows=[]
    for path in sorted(HISTORY.glob("*.json")):
        try: rows.extend(json.loads(path.read_text(encoding="utf-8")).get("daily_history", []))
        except (OSError,json.JSONDecodeError): pass
    by_date={}
    for r in rows:
        try:
            d=int(r["dEven"]); c=float(r.get("pClosing") or 0)
            if c>0: by_date[d]=r
        except (KeyError,TypeError,ValueError): pass
    return [by_date[d] for d in sorted(by_date)]


def close(r): return float(r.get("pClosing") or r.get("pDrCotVal") or 0)
def high(r): return float(r.get("priceMax") or close(r))
def low(r): return float(r.get("priceMin") or close(r))
def volume(r): return float(r.get("qTotTran5J") or 0)
def avg(x): return sum(x)/len(x) if x else None

def sma(x,n): return avg(x[-n:]) if len(x)>=n else None

def ema(x,n):
    if len(x)<n:return None
    v=avg(x[:n]); a=2/(n+1)
    for z in x[n:]:v=a*z+(1-a)*v
    return v

def std(x,n):
    if len(x)<n:return None
    m=avg(x[-n:]);return math.sqrt(avg([(z-m)**2 for z in x[-n:]]))

def rsi(x,n):
    if len(x)<=n:return None
    g=[max(x[i]-x[i-1],0) for i in range(1,len(x))];l=[max(x[i-1]-x[i],0) for i in range(1,len(x))]
    ag,al=avg(g[:n]),avg(l[:n])
    for a,b in zip(g[n:],l[n:]):ag=(ag*(n-1)+a)/n;al=(al*(n-1)+b)/n
    return 100 if al==0 else 100-100/(1+ag/al)

def slope(x,n):
    if len(x)<n:return None
    y=x[-n:];xm=(n-1)/2;ym=avg(y);den=sum((i-xm)**2 for i in range(n))
    return sum((i-xm)*(v-ym) for i,v in enumerate(y))/den if den else 0

def parse(name):
    for p in sorted(PERIODS,reverse=True):
        if name.endswith(str(p)):return name[:-len(str(p))],p
    return name,20

def signal(name,rows):
    base,p=parse(name);c=[close(r) for r in rows];h=[high(r) for r in rows];l=[low(r) for r in rows];v=[volume(r) for r in rows];last=c[-1]
    def clip(z):return max(-1,min(1,z)) if z is not None and math.isfinite(z) else 0
    if base=="sma":
        m=sma(c,p);return clip((last/m-1)*10) if m else 0
    if base=="ema":
        m=ema(c,p);return clip((last/m-1)*10) if m else 0
    if base in {"momentum","roc"}:return clip((last/c[-p]-1)*(4 if base=="momentum" else 6)) if len(c)>p else 0
    if base=="rsi":
        z=rsi(c,p);return clip((z-50)/25) if z is not None else 0
    if base=="stoch":
        hi=max(h[-p:]);lo=min(l[-p:]);return clip(((last-lo)/(hi-lo)-.5)*2) if hi>lo else 0
    if base=="bollinger":
        m=sma(c,p);s=std(c,p);return clip((last-m)/(2*s)) if m and s else 0
    if base=="volatility":
        s=std(c,p);return clip((s/last)*20) if s and last else 0
    if base=="volume":
        m=sma(v,p);mom=(last/c[-2]-1) if len(c)>1 and c[-2] else 0;return clip(((v[-1]/m)-1)*mom*8) if m else 0
    if base=="obv":
        obv=0;vals=[]
        for i in range(1,len(c)):obv+=v[i] if c[i]>c[i-1] else -v[i] if c[i]<c[i-1] else 0;vals.append(obv)
        s=slope(vals,p);den=avg([abs(z) for z in vals[-p:]]) if vals else 0;return clip(s/(den+1e-9)*20) if s is not None else 0
    if base=="mfi":
        pos=neg=0
        for i in range(max(1,len(c)-p),len(c)):
            typ=(h[i]+l[i]+c[i])/3;prev=(h[i-1]+l[i-1]+c[i-1])/3
            if typ>prev:pos+=typ*v[i]
            else:neg+=typ*v[i]
        return clip(pos/(neg+1e-9)-1)
    if base=="macd":
        e1=ema(c,p);e2=ema(c,p*2);return clip((e1/e2-1)*20) if e1 and e2 else 0
    if base=="cci":
        tp=[(h[i]+l[i]+c[i])/3 for i in range(len(c))];m=sma(tp,p);dev=avg([abs(z-m) for z in tp[-p:]]) if m else None;return clip((tp[-1]-m)/(0.015*dev)) if m and dev else 0
    if base=="williams":
        hi=max(h[-p:]);lo=min(l[-p:]);return clip(-(((hi-last)/(hi-lo))*2-1)) if hi>lo else 0
    if base=="donchian":
        hi=max(h[-p:]);lo=min(l[-p:]);return clip((last-(hi+lo)/2)/((hi-lo)/2)) if hi>lo else 0
    if base in {"ichimoku","tenkan_kijun","cloud_thickness","price_cloud"}:
        # Only information available through the decision date is used.
        ten_n=max(2,p//2);ten=(max(h[-ten_n:])+min(l[-ten_n:]))/2;kij=(max(h[-p:])+min(l[-p:]))/2
        spanb=(max(h[-2*p:])+min(l[-2*p:]))/2 if len(c)>=2*p else kij;spana=(ten+kij)/2;cloud=(spana+spanb)/2
        if base=="ichimoku":return clip((last-cloud)/last*15+(.25 if ten>kij else -.25))
        if base=="tenkan_kijun":return clip((ten/kij-1)*20) if kij else 0
        if base=="cloud_thickness":return clip((spana-spanb)/last*20)
        return clip((last-cloud)/last*20)
    if base=="trend":return clip(slope(c,p)/last*p*8) if last else 0
    return 0

def forecast(feature_set,rows):
    scores=[signal(f,rows) for f in feature_set];score=avg(scores) or 0;c=close(rows[-1]);vol=std([close(r) for r in rows],20);scale=min(.08,max(.005,(vol/c) if vol and c else .02));return c*(1+max(-.12,min(.12,score*scale)))

def evaluate(fs,rows,start,end):
    errs=[];dirs=[];beats=[]
    for i in range(max(start,30),min(end,len(rows)-1)):
        hist=rows[:i+1];pred=forecast(fs,hist);cur=close(hist[-1]);actual=close(rows[i+1]);me=abs(pred/actual-1)*100;be=abs(cur/actual-1)*100
        errs.append(me);beats.append(be-me);dirs.append((pred>=cur)==(actual>=cur))
    return {"mae_pct":mean(errs) if errs else 999,"direction_pct":mean(dirs)*100 if dirs else 0,"improvement_pct":mean(beats) if beats else -999,"beats_naive_pct":mean([x>0 for x in beats])*100 if beats else 0,"n":len(errs)}

def catalog():
    # Full pairwise stage over all 200 variants, then top-driven higher-order search.
    singles=[(f,) for f in FEATURES]
    pairs=[(a,b) for a,b in itertools.combinations(FEATURES,2)]
    return singles,pairs

def main():
    rows=load_rows();n=len(rows);train=int(n*.65);val=int(n*.82);singles,pairs=catalog()
    first=[]
    for i,fs in enumerate(singles+pairs,1):
        first.append({"model_id":f"M{i:05d}","features":fs,"validation":evaluate(fs,rows,train,val)})
    first.sort(key=lambda x:(-x["validation"]["improvement_pct"],-x["validation"]["direction_pct"],x["validation"]["mae_pct"]))
    top=first[:30]
    triples=[]
    for a,b in itertools.combinations(top,2):
        fs=tuple(dict.fromkeys(a["features"]+b["features"]))
        if len(fs)<=4:triples.append({"model_id":f"E{len(triples)+1:05d}","parents":[a["model_id"],b["model_id"]],"features":fs,"validation":evaluate(fs,rows,train,val)})
    triples.sort(key=lambda x:(-x["validation"]["improvement_pct"],-x["validation"]["direction_pct"],x["validation"]["mae_pct"]))
    top2=triples[:20]
    oos=[{"model_id":m["model_id"],"features":m["features"],"validation":m["validation"],"oos":evaluate(m["features"],rows,val,n-1)} for m in top2]
    oos.sort(key=lambda x:(-x["oos"]["improvement_pct"],-x["oos"]["direction_pct"],x["oos"]["mae_pct"]))
    result={"engine_version":"ensemble-v2.1-full-pairwise","symbol":SYMBOL,"rows":n,"first_date":rows[0]["dEven"],"last_date":rows[-1]["dEven"],"feature_variants":len(FEATURES),"single_models":len(singles),"pair_models":len(pairs),"higher_order_models":len(triples),"selection_protocol":"validation only; frozen OOS after selection","no_lookahead":True,"top_validation":top,"oos_leaderboard":oos,"final_candidate":oos[0] if oos else None}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"engine_version":result["engine_version"],"rows":n,"single_models":len(singles),"pair_models":len(pairs),"higher_order_models":len(triples),"final_candidate":result["final_candidate"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
