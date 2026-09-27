from __future__ import annotations
import json, math
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'runtime'/'history'/'پالایش'
OUT=ROOT/'runtime'/'experiments'/'پالایش'/'custom_model_v1_results.json'

def load_rows():
    rows=[]
    for p in sorted(HISTORY.glob('*.json')):
        try: rows += json.loads(p.read_text(encoding='utf-8')).get('daily_history',[])
        except Exception: pass
    d={}
    for r in rows:
        try:
            k=int(r['dEven']); c=float(r.get('pClosing') or r.get('pDrCotVal') or 0)
            if c>0:d[k]=r
        except Exception:pass
    return [d[k] for k in sorted(d)]

def c(r): return float(r.get('pClosing') or r.get('pDrCotVal') or 0)
def h(r): return float(r.get('priceMax') or c(r))
def l(r): return float(r.get('priceMin') or c(r))
def v(r): return float(r.get('qTotTran5J') or 0)
def sma(x,n): return sum(x[-n:])/n if len(x)>=n else None
def ema(x,n):
    if len(x)<n:return None
    z=sum(x[:n])/n;a=2/(n+1)
    for q in x[n:]:z=a*q+(1-a)*z
    return z
def rsi(x,n):
    if len(x)<=n:return None
    g=[max(x[i]-x[i-1],0) for i in range(1,len(x))];d=[max(x[i-1]-x[i],0) for i in range(1,len(x))]
    ag=sum(g[:n])/n;ad=sum(d[:n])/n
    for gg,dd in zip(g[n:],d[n:]):ag=(ag*(n-1)+gg)/n;ad=(ad*(n-1)+dd)/n
    return 100 if ad==0 else 100-100/(1+ag/ad)
def std(x,n):
    if len(x)<n:return None
    m=sum(x[-n:])/n;return math.sqrt(sum((z-m)**2 for z in x[-n:])/n)
def clip(z):return max(-1,min(1,z)) if z is not None and math.isfinite(z) else 0

def scores(rows):
    x=[c(r) for r in rows];hi=[h(r) for r in rows];lo=[l(r) for r in rows];vol=[v(r) for r in rows];last=x[-1]
    ma_parts=[]
    for n in (10,20,50,100,200):
        m=sma(x,n)
        if m:ma_parts.append(clip((last/m-1)*12))
    for n in (9,21,50,100,200):
        m=ema(x,n)
        if m:ma_parts.append(clip((last/m-1)*12))
    ma=mean(ma_parts) if ma_parts else 0
    e12,e26=ema(x,12),ema(x,26); macd=0
    if e12 and e26:
        mline=e12-e26; hist=mline-(ema(x,9)-e26 if len(x)>=26 else mline); macd=clip((mline/last)*25 + (hist/last)*40)
    rvals=[rsi(x,n) for n in (7,14,21)];rvals=[z for z in rvals if z is not None]; rs=mean([clip((z-50)/25) for z in rvals]) if rvals else 0
    n=20;mid=sma(x,n);sd=std(x,n);bb=clip((last-mid)/(2*sd)) if mid and sd else 0
    # Ichimoku uses only data available through decision date.
    ten_n=9;kij_n=26;span_n=52
    if len(x)>=span_n:
        ten=(max(hi[-ten_n:])+min(lo[-ten_n:]))/2;kij=(max(hi[-kij_n:])+min(lo[-kij_n:]))/2;sb=(max(hi[-span_n:])+min(lo[-span_n:]))/2;sa=(ten+kij)/2;cloud=(sa+sb)/2
        ichi=clip((last-cloud)/last*18)+(.2 if ten>kij else -.2)
    else: ichi=0
    return {'ma':ma,'macd':clip(macd),'rsi':rs,'ichimoku':clip(ichi),'bb':bb}

def predict(rows,weights):
    s=scores(rows);z=sum(s[k]*weights[k] for k in weights);cur=c(rows[-1]);sd=std([c(r) for r in rows],20);scale=min(.08,max(.005,(sd/cur) if sd and cur else .02));ret=max(-.12,min(.12,z*scale));return cur*(1+ret),ret,s

def evaluate(rows,start,end,weights):
    abs_err=[];direction=[];move_err=[];pred_rets=[];actual_rets=[]
    for i in range(max(start,200),min(end,len(rows)-1)):
        pred,pret,_=predict(rows[:i+1],weights);cur=c(rows[i]);actual=c(rows[i+1]);aret=actual/cur-1
        abs_err.append(abs(pred/actual-1)*100);move_err.append(abs(pret-aret)*100);direction.append((pret>=0)==(aret>=0));pred_rets.append(pret);actual_rets.append(aret)
    return {'mae_pct':mean(abs_err) if abs_err else None,'direction_accuracy_pct':mean(direction)*100 if direction else None,'mean_absolute_move_error_pct':mean(move_err) if move_err else None,'n':len(abs_err)}

def main():
    rows=load_rows();n=len(rows);train=int(n*.65);val=int(n*.82)
    candidates={
      'equal':{'ma':.20,'macd':.20,'rsi':.20,'ichimoku':.25,'bb':.15},
      'trend':{'ma':.30,'macd':.20,'rsi':.15,'ichimoku':.25,'bb':.10},
      'momentum':{'ma':.15,'macd':.30,'rsi':.25,'ichimoku':.20,'bb':.10},
      'ichi':{'ma':.15,'macd':.15,'rsi':.15,'ichimoku':.40,'bb':.15},
      'bb':{'ma':.15,'macd':.15,'rsi':.20,'ichimoku':.20,'bb':.30},
    }
    valres={k:evaluate(rows,train,val,w) for k,w in candidates.items()}
    # Select by a balanced objective: direction first, then movement error.
    winner=min(valres,key=lambda k:(-valres[k]['direction_accuracy_pct'],valres[k]['mean_absolute_move_error_pct']))
    oos=evaluate(rows,val,n-1,candidates[winner])
    naive=evaluate(rows,val,n-1,{'ma':1,'macd':0,'rsi':0,'ichimoku':0,'bb':0})
    result={'engine_version':'custom-v1.1-direction-plus-magnitude','symbol':'پالایش','rows':n,'weights':candidates[winner],'validation_leader':winner,'validation':valres,'oos':oos,'oos_naive_proxy':naive,'outputs':['direction','predicted_return','predicted_price','confidence_proxy'],'no_lookahead':True,'selection':'validation only; OOS frozen after selection'}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
