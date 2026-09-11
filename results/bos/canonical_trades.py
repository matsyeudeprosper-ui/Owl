"""Canonical live trade table for the BOS bot on 223995441, built from
MT5 deal history (position_id join), NOT from log lines. Entry type is
attached from the bot log by matching the entry deal time (+-10 s)."""
import csv, re, datetime as dt, collections
utc = dt.timezone.utc
deals = list(csv.DictReader(open("deals_223995441_raw.csv")))
deals = [d for d in deals if d["magic"] == "909101"]
pos = collections.defaultdict(dict)
for d in deals:
    p = pos[d["position_id"]]
    if d["entry"] == "0":   # DEAL_ENTRY_IN
        p["in"] = d
    else:
        p["out"] = d
# entry types from the log
log_e = []
pat = re.compile(r"^(\S+) (FLIP-BOS|TOUCH|BOS) ENTRY: (BUY|SELL) ([\d.]+) @ ~([\d.]+) SL ([\d.]+) TP ([\d.]+) \(risk \$([\d.]+)")
pat_add = re.compile(r"^(\S+) PULLBACK ADD: ([\d.]+) bullet")
for line in open(r"C:\Projects\KinoliveLines\live\bos_bot.log", encoding="utf-8", errors="replace"):
    m = pat.match(line.strip())
    if m:
        log_e.append((dt.datetime.fromisoformat(m[1]), m[2], m[3], float(m[4]), float(m[6]), float(m[7]), float(m[8]), float(m[5])))
rows = []
for pid, p in pos.items():
    i = p.get("in"); o = p.get("out")
    if i is None: continue
    ti = dt.datetime.fromisoformat(i["time"])
    kind = ""; sl = tp = risk = ""
    if i["comment"].endswith("-ADD"):
        kind = "ADD"
    else:
        best = min(log_e, key=lambda e: abs((e[0] - ti).total_seconds()))
        if abs((best[0] - ti).total_seconds()) <= 60:
            kind, sl, tp, risk = best[1], best[4], best[5], best[6]
            eref = best[7]; lag = (best[0] - ti).total_seconds()
        else:
            kind = "UNMATCHED"
    direction = "BUY" if i["type"] == "0" else "SELL"
    r = dict(position_id=pid, entry_type=kind, dir=direction, volume=i["volume"], open_time=i["time"], open_price=i["price"], sl_log=sl, tp_log=tp, risk_log=risk)
    if kind not in ("ADD", "UNMATCHED"):
        r["entry_slip_pts"] = round((float(i["price"]) - eref) * (1 if direction == "BUY" else -1), 2)  # positive = filled worse than decision price
        r["order_lag_s"] = round(lag, 1)
    if o:
        r.update(close_time=o["time"], close_price=o["price"], profit=o["profit"], commission=o["commission"], swap=o["swap"], reason=o["reason"], close_comment=o["comment"])
        m2 = re.search(r"\[(sl|tp) ([\d.]+)\]", o["comment"])
        if m2:
            lvl = float(m2[2]); r["exit_kind"] = m2[1]; r["exit_level"] = lvl
            slip = (float(o["price"]) - lvl) * (1 if direction == "BUY" else -1)
            r["exit_slip_pts"] = round(slip, 2)   # negative = worse than the level
        else:
            r["exit_kind"] = "market/kill"
        r["net"] = round(float(o["profit"]) + float(o["commission"]) + float(o["swap"]), 2)
        r["hold_min"] = round((dt.datetime.fromisoformat(o["time"]) - ti).total_seconds() / 60, 1)
    else:
        r.update(close_time="", net="", exit_kind="OPEN")
    rows.append(r)
rows.sort(key=lambda r: r["open_time"])
cols = ["position_id","entry_type","dir","volume","open_time","open_price","entry_slip_pts","order_lag_s","sl_log","tp_log","risk_log","close_time","close_price","exit_kind","exit_level","exit_slip_pts","profit","commission","swap","net","hold_min","reason","close_comment"]
with open("trades_live_canonical.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
    for r in rows: w.writerow({c: r.get(c, "") for c in cols})
closed = [r for r in rows if r["exit_kind"] != "OPEN"]
base = [r for r in closed if r["entry_type"] != "ADD"]
print(f"positions {len(rows)}, closed {len(closed)}, open {len(rows)-len(closed)}")
print(f"ALL closed net {sum(r['net'] for r in closed):+.2f}  (base {sum(r['net'] for r in base):+.2f}, adds {sum(r['net'] for r in closed if r['entry_type']=='ADD'):+.2f})")
for k in ("BOS", "FLIP-BOS", "TOUCH", "ADD", "UNMATCHED"):
    s = [r for r in closed if r["entry_type"] == k]
    if not s: continue
    w = sum(1 for r in s if r["net"] > 0)
    print(f"  {k:9s} n {len(s):2d} W {w:2d} wr {w/len(s):.0%} net {sum(r['net'] for r in s):+7.2f} avgW {sum(r['net'] for r in s if r['net']>0)/max(1,w):+.2f} avgL {sum(r['net'] for r in s if r['net']<=0)/max(1,len(s)-w):+.2f}")
sl_ = [r for r in closed if r.get("exit_kind") == "sl"]; tp_ = [r for r in closed if r.get("exit_kind") == "tp"]
import statistics as st
print(f"SL exits {len(sl_)}: slippage pts mean {st.mean(r['exit_slip_pts'] for r in sl_):+.1f} median {st.median(r['exit_slip_pts'] for r in sl_):+.1f} worst {min(r['exit_slip_pts'] for r in sl_):+.1f}")
print(f"TP exits {len(tp_)}: slippage pts mean {st.mean(r['exit_slip_pts'] for r in tp_):+.1f}")
es=[r["entry_slip_pts"] for r in closed if "entry_slip_pts" in r]
print(f"ENTRY slippage pts (n {len(es)}): mean {st.mean(es):+.1f} median {st.median(es):+.1f} worst {max(es):+.1f} | by type:", {k: round(st.mean([r["entry_slip_pts"] for r in closed if r.get("entry_type")==k and "entry_slip_pts" in r]),1) for k in ("BOS","FLIP-BOS","TOUCH")})
lg=[r["order_lag_s"] for r in closed if "order_lag_s" in r]
print(f"order lag s: mean {st.mean(lg):.1f} median {st.median(lg):.1f} max {max(lg):.1f}")
print("commission total", round(sum(float(r['commission']) for r in closed), 2), "swap total", round(sum(float(r['swap']) for r in closed), 2))
print("state banked per bot:", end=" "); import json; print(json.load(open(r"C:\Projects\KinoliveLines\live\bos_state.json"))["banked"])
