"""Trade-by-trade alignment: tick backtest of the deployed config over the
live window vs the real account's canonical trades (MT5 deals)."""
import csv, datetime as dt, os
HERE = os.path.dirname(os.path.abspath(__file__))
bt = list(csv.DictReader(open(os.path.join(HERE, "results", "trades_tick_live_window.csv"))))
lv = list(csv.DictReader(open(os.path.join(HERE, "..", "..", "results", "bos", "trades_live_canonical.csv"))))
lv = [r for r in lv if r["entry_type"] in ("TOUCH", "FLIP-BOS", "BOS")]
def ts(s): return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None) if "+" not in s else dt.datetime.fromisoformat(s).replace(tzinfo=None)
for r in bt: r["_t"] = ts(r["entry_time_utc"]); r["_used"] = False
matched = []; unmatched = []
for r in lv:
    t = ts(r["open_time"]); d = r["dir"]
    cands = [b for b in bt if not b["_used"] and b["dir"] == d and abs((b["_t"] - t).total_seconds()) <= 180]
    if cands:
        b = min(cands, key=lambda b: abs((b["_t"] - t).total_seconds())); b["_used"] = True
        matched.append((r, b))
    else:
        unmatched.append(r)
print(f"live base trades {len(lv)}, backtest trades in window {len(bt)}, matched {len(matched)}, live-only {len(unmatched)}, backtest-only {sum(1 for b in bt if not b['_used'])}")
same_kind = sum(1 for r, b in matched if (r["entry_type"] == "TOUCH") == (b["kind"] == "touch"))
same_out = sum(1 for r, b in matched if (float(r["net"]) > 0) == (float(b["pnl"]) > 0))
print(f"matched: same entry kind {same_kind}/{len(matched)}, same win/loss outcome {same_out}/{len(matched)}")
print(f"matched P&L: live {sum(float(r['net']) for r, b in matched):+.2f} vs backtest {sum(float(b['pnl']) for r, b in matched):+.2f}")
print(f"live-only trades P&L {sum(float(r['net']) for r in unmatched):+.2f}; backtest-only P&L {sum(float(b['pnl']) for b in bt if not b['_used']):+.2f}")
print("\nlive-only (no backtest twin within 3 min):")
for r in unmatched: print("  ", r["open_time"][:19], r["entry_type"], r["dir"], r["net"])
print("backtest-only:")
for b in bt:
    if not b["_used"]: print("  ", b["entry_time_utc"], b["kind"], b["dir"], b["pnl"])
print("\nmatched pairs (live | backtest): time kind dir live_net bt_pnl")
for r, b in matched: print(f"  {r['open_time'][11:19]} {r['entry_type']:8s} {r['dir']:4s} {float(r['net']):+6.2f} | {b['entry_time_utc'][11:19]} {b['kind']:5s} {float(b['pnl']):+6.2f} {b['why']}")
