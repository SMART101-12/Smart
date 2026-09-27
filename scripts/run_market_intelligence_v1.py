from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean

from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "پالایش"
HISTORY = ROOT / "runtime" / "history" / SYMBOL
OUT = ROOT / "runtime" / "experiments" / SYMBOL / "market_intelligence_v1_results.json"

# Research-driven layers that are actually observable in the current Git history:
# price/trend, volume, turnover/value, trade-count activity, volatility/liquidity,
# price-limit proximity proxies and regime. Real order-book depth, حقیقی/حقوقی flow,
# and Persian sentiment are NOT fabricated here because they are not stored historically.


def load_rows():
    rows = []
    for p in sorted(HISTORY.glob("*.json")):
        try:
            rows.extend(json.loads(p.read_text(encoding="utf-8")).get("daily_history", []))
        except Exception:
            pass
    unique = {}
    for r in rows:
        try:
            d = int(r["dEven"])
            c = float(r.get("pClosing") or r.get("pDrCotVal") or 0)
            if c > 0:
                unique[d] = r
        except Exception:
            pass
    return [unique[d] for d in sorted(unique)]


def val(r, *keys):
    for k in keys:
        try:
            x = float(r.get(k) or 0)
            if x > 0:
                return x
        except Exception:
            pass
    return 0.0


def closes(rows): return [val(r, "pClosing", "pDrCotVal") for r in rows]
def volumes(rows): return [val(r, "qTotTran5J") for r in rows]
def values(rows): return [val(r, "qTotCap") for r in rows]
def trades(rows): return [val(r, "zTotTran") for r in rows]
def highs(rows): return [val(r, "priceMax", "pClosing") for r in rows]
def lows(rows): return [val(r, "priceMin", "pClosing") for r in rows]


def sma(x, n): return mean(x[-n:]) if len(x) >= n else None

def ema(x, n):
    if len(x) < n: return None
    z = mean(x[:n]); a = 2 / (n + 1)
    for q in x[n:]: z = a*q + (1-a)*z
    return z


def std(x, n):
    if len(x) < n: return None
    m = mean(x[-n:]); return math.sqrt(mean((z-m)**2 for z in x[-n:]))


def ret(x, n=1):
    return x[-1] / x[-1-n] - 1 if len(x) > n and x[-1-n] else 0.0


def slope(x, n):
    if len(x) < n: return 0.0
    y = x[-n:]; xm = (n-1)/2; ym = mean(y)
    den = sum((i-xm)**2 for i in range(n))
    return (sum((i-xm)*(v-ym) for i,v in enumerate(y))/den) / (ym or 1)


def features(rows):
    c, v, q, z, h, l = closes(rows), volumes(rows), values(rows), trades(rows), highs(rows), lows(rows)
    last = c[-1]
    out = []
    for n in (1,3,5,10,20,50): out.append(ret(c,n))
    for n in (5,10,20,50,100,200):
        m=sma(c,n); e=ema(c,n); out += [(last/m-1) if m else 0, (last/e-1) if e else 0, slope(c,n)]
    for n in (5,10,20,50):
        mv=sma(v,n); mq=sma(q,n); mz=sma(z,n)
        out += [(v[-1]/mv-1) if mv else 0, (q[-1]/mq-1) if mq else 0, (z[-1]/mz-1) if mz else 0]
    for n in (5,10,20,50):
        s=std(c,n); out += [(s/last) if s and last else 0]
    # Amihud-like illiquidity using absolute return / trade value.
    for n in (5,10,20):
        vals=[]
        for i in range(max(1,len(c)-n),len(c)):
            if q[i] and c[i-1]: vals.append(abs(c[i]/c[i-1]-1)/(q[i]/1e12))
        out.append(mean(vals) if vals else 0)
    # Range/close-location and empirical price-limit proximity; no fixed 5%/10% assumption.
    for n in (5,10,20):
        ranges=[]; locations=[]
        for i in range(max(1,len(c)-n),len(c)):
            rng=max(h[i]-l[i],1e-9); ranges.append(rng/c[i]); locations.append((c[i]-l[i])/rng)
        out += [mean(ranges) if ranges else 0, locations[-1] if locations else .5]
    absrets=[abs(c[i]/c[i-1]-1) for i in range(1,len(c))]
    p95=sorted(absrets[-60:])[max(0,int(len(absrets[-60:])*.95)-1)] if absrets[-60:] else .05
    out.append(abs(ret(c,1))/(p95 or .05))
    # Regime encodings: trend and volatility state.
    s20,s50,s200=sma(c,20),sma(c,50),sma(c,200)
    out += [1 if s50 and s200 and last>s50>s200 else -1 if s50 and s200 and last<s50<s200 else 0]
    s20v,s50v=std(c,20),std(c,50)
    out += [(s20v/s50v-1) if s20v and s50v else 0]
    return out


def dataset(rows):
    X=[]; y_dir=[]; y_ret=[]
    for i in range(200,len(rows)-1):
        c=closes(rows[:i+1]); nxt=closes(rows[:i+2])[-1]
        cur=c[-1]; r=nxt/cur-1
        X.append(features(rows[:i+1])); y_dir.append(int(r>0)); y_ret.append(r)
    return X,y_dir,y_ret


def evaluate(y_dir, p_dir, y_ret, p_ret):
    mae=mean(abs(a-b) for a,b in zip(y_ret,p_ret))*100
    direction=mean(int(a==b) for a,b in zip(y_dir,p_dir))*100
    move_err=mean(abs(a-b) for a,b in zip(y_ret,p_ret))*100
    return {"mae_pct":mae,"direction_accuracy_pct":direction,"mean_absolute_move_error_pct":move_err,"n":len(y_dir)}


def main():
    rows=load_rows(); X,y_dir,y_ret=dataset(rows)
    n=len(X); train=int(n*.65); val=int(n*.82)
    Xtr,Xv,Xo=X[:train],X[train:val],X[val:]
    ydtr,ydv,ydo=y_dir[:train],y_dir[train:val],y_dir[val:]
    yrtr,yrv,yro=y_ret[:train],y_ret[train:val],y_ret[val:]
    candidates={
      "HGB-balanced": (HistGradientBoostingClassifier(max_depth=3,learning_rate=.05,max_iter=250,l2_regularization=1.0,random_state=42), HistGradientBoostingRegressor(max_depth=3,learning_rate=.05,max_iter=250,l2_regularization=1.0,random_state=42)),
      "HGB-conservative": (HistGradientBoostingClassifier(max_depth=2,learning_rate=.04,max_iter=300,l2_regularization=2.0,random_state=42), HistGradientBoostingRegressor(max_depth=2,learning_rate=.04,max_iter=300,l2_regularization=2.0,random_state=42)),
    }
    val_results={}
    for name,(clf,reg) in candidates.items():
        clf=make_pipeline(SimpleImputer(strategy="median"),clf); reg=make_pipeline(SimpleImputer(strategy="median"),reg)
        clf.fit(Xtr,ydtr); reg.fit(Xtr,yrtr)
        pd=clf.predict(Xv); pr=reg.predict(Xv)
        val_results[name]=evaluate(ydv,pd,yrv,pr)
    winner=max(val_results,key=lambda k:(val_results[k]["direction_accuracy_pct"],-val_results[k]["mean_absolute_move_error_pct"]))
    clf,reg=candidates[winner]
    clf=make_pipeline(SimpleImputer(strategy="median"),clf); reg=make_pipeline(SimpleImputer(strategy="median"),reg)
    clf.fit(X[:val],y_dir[:val]); reg.fit(X[:val],y_ret[:val])
    po_dir=clf.predict(Xo); po_ret=reg.predict(Xo)
    oos=evaluate(ydo,po_dir,yro,po_ret)
    result={
      "engine_version":"market-intelligence-v1.0",
      "symbol":SYMBOL,"rows":len(rows),"samples":n,
      "layers":["price_trend","volume","trade_value","trade_count","liquidity_illiquidity","volatility","empirical_limit_proximity","market_regime"],
      "excluded_until_historical_data_exists":["real_legal_flow","order_book_depth","queue_imbalance","news_sentiment","social_sentiment"],
      "model":"two-head gradient boosting: direction classifier + magnitude regressor",
      "selection":"validation only; frozen OOS after selection",
      "no_lookahead":True,
      "validation":val_results,"winner":winner,"oos":oos,
      "target":{"direction":"next-day return > 0","magnitude":"next-day return"},
      "notes":"Order-book and sentiment are deliberately not proxied as fake historical data. They require point-in-time historical feeds before inclusion."
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
