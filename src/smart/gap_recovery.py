from __future__ import annotations
import json, os, sqlite3, time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from .tsetmc_adapter import TsetmcAdapter
ROOT=Path(__file__).resolve().parents[2]; DB_PATH=ROOT/"data"/"smart.db"; RUNTIME=ROOT/"runtime"; HISTORY_DIR=RUNTIME/"history"; QUALITY_DIR=RUNTIME/"data_quality"; RETRY_SECONDS=int(os.getenv("SMART_GAP_RETRY_SECONDS","3600"))
def _date(v:Any)->date|None:
 r=str(v or "").replace("-","").replace("/","").strip()
 if len(r)!=8 or not r.isdigit(): return None
 try:return date(int(r[:4]),int(r[4:6]),int(r[6:8]))
 except ValueError:return None
def _db_dates(symbol,source="tsetmc"):
 if not DB_PATH.exists(): return []
 with sqlite3.connect(DB_PATH) as c: rows=c.execute("SELECT market_date FROM daily_history WHERE symbol=? AND source=? ORDER BY market_date",(symbol,source)).fetchall()
 return [str(x[0]).replace("-","") for x in rows if x[0]]
def _load_history(symbol):
 p=HISTORY_DIR/f"{symbol}.json"; return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"symbol":symbol,"daily_history":[]}
def _save_history(symbol,payload):
 HISTORY_DIR.mkdir(parents=True,exist_ok=True); rows=payload.get("daily_history",[]); payload["daily_history"]=sorted(rows,key=lambda r:int(r.get("dEven",0)),reverse=True); payload["history_rows"]=len(rows); payload["first_history_date"]=payload["daily_history"][-1].get("dEven") if rows else None; payload["last_history_date"]=payload["daily_history"][0].get("dEven") if rows else None; payload["repaired_at"]=datetime.now(timezone.utc).isoformat(); (HISTORY_DIR/f"{symbol}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
def _quality_path(symbol): QUALITY_DIR.mkdir(parents=True,exist_ok=True); return QUALITY_DIR/f"{symbol}.json"
def _load_quality(symbol):
 p=_quality_path(symbol); return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"symbol":symbol,"dates":{}}
def _save_quality(symbol,q): q["checked_at"]=datetime.now(timezone.utc).isoformat(); _quality_path(symbol).write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding="utf-8")
def _expected_dates(start,end):
 cur=start
 while cur<=end:
  if cur.weekday() in (5,6,0,1,2): yield cur
  cur+=timedelta(days=1)
def _calendar_dates(rows):
 out=set()
 def walk(v):
  if isinstance(v,dict):
   for k,x in v.items():
    if k in ("dEven","market_date","date","dateInt","DEven"):
     d=_date(x)
     if d: out.add(d)
    walk(x)
  elif isinstance(v,list):
   for x in v: walk(x)
 walk(rows); return out
def _monthly_lookup_payloads(symbol,payload):
 groups=defaultdict(list); fields=("dEven","pClosing","pDrCotVal","priceFirst","priceMin","priceMax","priceYesterday","priceChange","zTotTran","qTotTran5J","qTotCap","iClose","yClose","last","hEven")
 for row in payload.get("daily_history",[]):
  raw=str(row.get("dEven",""));
  if len(raw)==8 and raw.isdigit(): groups[raw[:6]].append({k:row.get(k) for k in fields if k in row})
 return {m:{"symbol":symbol,"ins_code":payload.get("ins_code"),"source":payload.get("source","tsetmc"),"month":m,"updated_at":payload.get("repaired_at"),"rows":len(rs),"daily":sorted(rs,key=lambda r:int(r.get("dEven",0)),reverse=True)} for m,rs in groups.items()}
def _sync_to_git(symbol,payload,quality):
 from .command_agent import put_json
 put_json(f"runtime/history/{symbol}.json",payload,f"agent: gap recovery {symbol}"); put_json(f"runtime/data_quality/{symbol}.json",quality,f"agent: data quality {symbol}")
 for m,p in _monthly_lookup_payloads(symbol,payload).items(): put_json(f"runtime/history_lookup/{symbol}/{m}.json",p,f"agent: gap recovery lookup {symbol} {m}")
def repair_symbol(symbol,*,today=None):
 today=today or datetime.now(timezone.utc).date(); db_dates=_db_dates(symbol); payload=_load_history(symbol); existing={d:r for r in payload.get("daily_history",[]) if (d:=_date(r.get("dEven")))}; db_parsed=[d for x in db_dates if (d:=_date(x))]
 if not existing and not db_parsed: return {"symbol":symbol,"status":"no_history","missing":[]}
 start=min([*existing,*db_parsed]); q=_load_quality(symbol); dates=q.setdefault("dates",{}); adapter=TsetmcAdapter(); ins_code=str(payload.get("ins_code","")).strip()
 if not ins_code:
  ins_code=str(adapter.resolve_symbol(symbol)["insCode"]); payload["ins_code"]=ins_code
 calendar_dates=_calendar_dates(adapter.instrument_calendar(ins_code))
 # Only completed dates are checked. Today is checked only if TSETMC calendar already contains it.
 scan_end=today-timedelta(days=1)
 candidates=[d for d in _expected_dates(start,scan_end) if d in calendar_dates and d not in existing and d not in db_parsed]
 repaired=[]; unresolved=[]; closed=[]
 for d in _expected_dates(start,scan_end):
  if d in existing or d in db_parsed: continue
  key=d.strftime("%Y%m%d"); e=dates.setdefault(key,{"attempts":0}); e["last_check"]=datetime.now(timezone.utc).isoformat()
  if d not in calendar_dates:
   e.update({"status":"MARKET_CLOSED_OR_NO_TRADING","market_open":False,"retry":False}); closed.append(key); continue
  e["attempts"]=int(e.get("attempts",0))+1
  try:
   row=adapter.closing_price_daily(ins_code,key)
   if isinstance(row,dict) and _date(row.get("dEven"))==d:
    existing[d]=row; e.update({"status":"DATA_AVAILABLE","market_open":True,"retry":False}); repaired.append(key)
   else:
    e.update({"status":"UNRESOLVED","market_open":True,"retry":True}); unresolved.append(key)
  except Exception as exc:
   e.update({"status":"FETCH_FAILED","market_open":True,"retry":True,"error":str(exc)}); unresolved.append(key)
 payload["daily_history"]=list(existing.values()); _save_history(symbol,payload); q["summary"]={"calendar_trading_dates":len(calendar_dates),"missing_before":len(candidates),"repaired":len(repaired),"unresolved":len(unresolved),"closed_or_no_trading":len(closed),"next_retry_seconds":RETRY_SECONDS}; _save_quality(symbol,q); _sync_to_git(symbol,payload,q)
 return {"symbol":symbol,**q["summary"],"repaired_dates":repaired,"unresolved_dates":unresolved,"closed_or_no_trading_dates":closed}
def run(symbols):
 while True:
  for symbol in symbols:
   try: print(f"gap-recovery {symbol}: {repair_symbol(symbol)}",flush=True)
   except Exception as exc: print(f"gap-recovery {symbol}: {type(exc).__name__}: {exc}",flush=True)
  time.sleep(RETRY_SECONDS)
