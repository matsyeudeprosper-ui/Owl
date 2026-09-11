"""Spread-correct replay of the LIVE page config (calm-only entries,
one position, clean chart after close) + fix grid.

Execution model (bars are BID; ask = bid + S, S=$7 flat per data):
 BUY  enter ask=C+S; SL price L<=sl fills sl;  TP when H>=tp
 SELL enter bid=C;   SL when H>=sl-S (ask);    TP when L<=tp-S
Ties (both in one bar): PESSIMISTIC = loss (also tally half/half).
Lock40 mirrors live: secure min(S+10pts, half of favorable).

Grid: SL cap x TP fraction. cap=None -> wall (risk<=`$2.50).
Usage: python bt_fix.py [calib]  (calib = live-test window only)
"""
import sys
import numpy as np
from datetime import datetime, timezone

D = np.load(r"C:\Users\ADMINI~1\AppData\Local\Temp\2\claude"
            r"\C--Users-Administrator--local-bin"
            r"\13a6abff-f560-41e2-b2a1-bbdf64ec7284\scratchpad"
            r"\pro_m1.npz")
O, H, L, C = (D[k].astype(float) for k in "ohlc")
T = D["t"].astype(int)
S = 7.0
N = len(T)

CALIB = len(sys.argv) > 1 and sys.argv[1] == "calib"
if CALIB:
    t0 = datetime(2026, 9, 7, 15, 39, tzinfo=timezone.utc).timestamp()
    t1 = datetime(2026, 9, 8, 7, 9, tzinfo=timezone.utc).timestamp()
else:
    t0, t1 = T[0], T[-1] + 1

_tr = np.maximum(H[1:] - L[1:], np.maximum(
    np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))
_cs = np.concatenate([[0.0], np.cumsum(_tr)])
def atr14(i):
    a, b = max(0, i - 15), i - 1
    return (_cs[b] - _cs[a]) / max(1, b - a)


class Det:
    def __init__(self):
        self.up, self.dn = {}, {}

    def step(self, i):
        po, pc = O[i - 1], C[i - 1]
        ph, pl = H[i - 1], L[i - 1]
        co, cc, ch, cl = O[i], C[i], H[i], L[i]
        up, dn = self.up, self.dn
        sig = None
        if pc > po and cc > co and cc > ph:
            up.update(leg=True, peak=ch, glow=cl)
        elif up.get("leg"):
            up["peak"] = max(up["peak"], ch)
            if cc > co:
                up["glow"] = cl
            elif cc < up["glow"]:
                up.update(pending=up["peak"], plow=cl, leg=False,
                          pt=T[i], retest=None)
        if up.get("pending"):
            up["plow"] = min(up.get("plow", cl), cl)
            if T[i] - up["pt"] > 21600:
                up["pending"] = None
            elif cc > up["pending"]:
                wd = abs(up["pending"] - up["plow"])
                if cc - up["pending"] > max(20.0, 0.35 * wd):
                    up.update(retest=up["pending"], rt_plow=up["plow"],
                              rt_t=T[i], pending=None)
                else:
                    sig = (1, up["plow"]); up["pending"] = None
        elif up.get("retest"):
            if T[i] - up.get("rt_t", T[i]) > 21600:
                up["retest"] = None
            elif cl <= up["retest"] + 15.0 and cc >= up["retest"] - 15.0:
                sig = (1, up.get("rt_plow", cl)); up["retest"] = None
        if pc < po and cc < co and cc < pl:
            dn.update(leg=True, dip=cl, rhigh=ch)
        elif dn.get("leg"):
            dn["dip"] = min(dn["dip"], cl)
            if cc < co:
                dn["rhigh"] = ch
            elif cc > dn["rhigh"]:
                dn.update(pending=dn["dip"], phigh=ch, leg=False,
                          pt=T[i], retest=None)
        if dn.get("pending") and sig is None:
            dn["phigh"] = max(dn.get("phigh", ch), ch)
            if T[i] - dn["pt"] > 21600:
                dn["pending"] = None
            elif cc < dn["pending"]:
                wd = abs(dn["phigh"] - dn["pending"])
                if dn["pending"] - cc > max(20.0, 0.35 * wd):
                    dn.update(retest=dn["pending"],
                              rt_phigh=dn["phigh"], rt_t=T[i],
                              pending=None)
                else:
                    sig = (-1, dn["phigh"]); dn["pending"] = None
        elif dn.get("retest") and sig is None:
            if T[i] - dn.get("rt_t", T[i]) > 21600:
                dn["retest"] = None
            elif ch >= dn["retest"] - 15.0 and cc <= dn["retest"] + 15.0:
                sig = (-1, dn.get("rt_phigh", ch)); dn["retest"] = None
        return sig


def run(cap, tpf, lot=0.01, tie_mode="loss", rand_seed=None):
    det = Det()
    pos = None
    res = []          # (i, pnl, kind)
    rs = [rand_seed if rand_seed else 0]

    def rnd():
        rs[0] = (rs[0] * 1103515245 + 12345) % (2 ** 31)
        return rs[0] / (2 ** 31)

    for i in range(40, N):
        if pos is not None:
            d, e = pos["d"], pos["e"]
            # trigger prices in BID terms
            if d == 1:
                sl_hit = L[i] <= pos["slv"]
                tp_hit = H[i] >= pos["tp"]
                fav = H[i] - e
            else:
                sl_hit = H[i] >= pos["slv"] - S
                tp_hit = L[i] <= pos["tp"] - S
                fav = e - (L[i] + S)
            prize = abs(pos["tp"] - e)
            if not pos["locked"] and fav >= 0.40 * prize:
                pos["locked"] = True
                secure = min(S + 10.0, 0.5 * fav)
                pos["slv"] = e + d * secure
                # re-eval hits with the new stop this same bar
                if d == 1:
                    sl_hit = L[i] <= pos["slv"]
                else:
                    sl_hit = H[i] >= pos["slv"] - S
            if tp_hit and sl_hit:
                if tie_mode == "loss":
                    px = pos["slv"]
                    kind = "tie_sl"
                else:
                    px = pos["tp"] if rnd() < 0.5 else pos["slv"]
                    kind = "tie"
            elif sl_hit:
                px, kind = pos["slv"], ("scratch" if pos["locked"]
                                        else "sl")
            elif tp_hit:
                px, kind = pos["tp"], "tp"
            else:
                continue
            pnl = (px - e) * d * lot
            res.append((i, pnl, kind))
            pos = None
            det = Det()               # clean chart after close
            continue
        sig = det.step(i)
        if rand_seed is not None:
            sig = None
            if rnd() < 1.0 / 470.0:
                d0 = 1 if rnd() < 0.5 else -1
                sig = (d0, C[i] - d0 * 100.0)
        if sig is None or not (t0 <= T[i] < t1):
            continue
        d, wall = sig
        e_bid = C[i]
        dist = abs(e_bid - wall)
        if dist < 60.0 or dist * lot > 2.50:
            continue
        if abs(C[i] - O[i]) >= atr14(i):
            continue                   # calm-only
        disc = min(1.0, 0.25 * dist * lot)
        tpd = dist - disc / lot
        tpd = min(tpd, 1.50 / lot) * tpf
        e = e_bid + (S if d == 1 else 0.0)   # fill price
        slp = dist if cap is None else min(dist, cap)
        pos = dict(d=d, e=e, slv=e_bid - d * slp,
                   tp=e_bid + d * tpd, locked=False)
    return res


def report(tag, res):
    W = [r for r in res if r[1] > 0.005]
    Lo = [r for r in res if r[1] < -0.005]
    net = sum(r[1] for r in res)
    days = {}
    for i, p, k in res:
        dk = datetime.fromtimestamp(int(T[i]),
                                    tz=timezone.utc).strftime("%m-%d")
        days[dk] = days.get(dk, 0.0) + p
    wr = len(W) / max(1, len(W) + len(Lo))
    print(f"{tag}: n {len(res)} wr {wr:.0%} net {net:+.2f} "
          f"avgW {sum(r[1] for r in W)/max(1,len(W)):+.3f} "
          f"avgL {sum(r[1] for r in Lo)/max(1,len(Lo)):+.3f} "
          f"worstday {min(days.values(), default=0):+.2f} "
          f"greendays {sum(1 for v in days.values() if v>0)}"
          f"/{len(days)}")
    return net


if CALIB:
    print("== CALIBRATION vs live 33 trades (16W/16L net -2.22) ==")
    report("sim cap25 tp0.25 tie=loss", run(25.0, 0.25))
    report("sim cap25 tp0.25 tie=coin", run(25.0, 0.25,
                                            tie_mode="coin",
                                            rand_seed=None))
    sys.exit()

print(f"== GRID over {(T[-1]-T[0])/86400:.0f} days, ties=LOSS ==")
for cap in (25.0, 35.0, 50.0, 75.0, 100.0, None):
    for tpf in (0.25, 0.5, 1.0):
        report(f"cap {str(cap):>5} tpf {tpf:.2f}",
               run(cap, tpf))
