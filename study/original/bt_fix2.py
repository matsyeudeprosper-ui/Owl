"""Round 2: is there a GROSS edge, and does a higher timeframe
(bigger walls, fewer trades) beat the spread drag?

Runs, all ties=LOSS, lot 0.01:
 1. M1 cap25 tpf.25 with S=0 (gross) vs RANDOM entries S=0
 2. M1 current config S=7 RANDOM control (completeness)
 3. M5 and M15 resampled, cap sweep, S=7
"""
import numpy as np
from datetime import datetime, timezone

BASE = (r"C:\Users\ADMINI~1\AppData\Local\Temp\2\claude"
        r"\C--Users-Administrator--local-bin"
        r"\13a6abff-f560-41e2-b2a1-bbdf64ec7284\scratchpad")
D = np.load(BASE + r"\pro_m1.npz")
O1, H1, L1, C1 = (D[k].astype(float) for k in "ohlc")
T1 = D["t"].astype(int)


def resample(k):
    n = (len(T1) // k) * k
    o = O1[:n].reshape(-1, k)[:, 0]
    h = H1[:n].reshape(-1, k).max(1)
    l = L1[:n].reshape(-1, k).min(1)
    c = C1[:n].reshape(-1, k)[:, -1]
    t = T1[:n].reshape(-1, k)[:, 0]
    return o, h, l, c, t


class LiveDet:
    def __init__(self, O, H, L, C, T):
        self.O, self.H, self.L, self.C, self.T = O, H, L, C, T
        self.up, self.dn = {}, {}

    def step(self, i):
        O, H, L, C, T = self.O, self.H, self.L, self.C, self.T
        po, pc, ph, pl = O[i-1], C[i-1], H[i-1], L[i-1]
        co, cc, ch, clo = O[i], C[i], H[i], L[i]
        up, dn = self.up, self.dn
        now_t = T[i]
        sig = None
        if pc > po and cc > co and cc > ph:
            up.update(leg=True, peak=ch, glow=clo)
        elif up.get("leg"):
            up["peak"] = max(up.get("peak", ch), ch)
            if cc > co:
                up["glow"] = clo
            elif cc < up.get("glow", float("-inf")):
                up.update(pending=up["peak"], pt=now_t, plow=clo,
                          leg=False, retest=None)
        if up.get("pending"):
            up["plow"] = min(up.get("plow", clo), clo)
            if now_t - up.get("pt", now_t) > 21600:
                up["pending"] = None
            elif cc > up["pending"]:
                wd = abs(up["pending"] - up.get("plow", clo))
                if cc - up["pending"] > max(20.0, 0.35 * wd):
                    up.update(retest=up["pending"],
                              rt_plow=up.get("plow", clo),
                              rt_t=now_t, pending=None)
                else:
                    sig = (1, up.get("plow", clo))
                    up["pending"] = None
        elif up.get("retest") and sig is None:
            if now_t - up.get("rt_t", now_t) > 21600:
                up["retest"] = None
            elif (clo <= up["retest"] + 15.0
                  and cc >= up["retest"] - 15.0):
                sig = (1, up.get("rt_plow", clo))
                up["retest"] = None
        if pc < po and cc < co and cc < pl:
            dn.update(leg=True, dip=clo, rhigh=ch)
        elif dn.get("leg"):
            dn["dip"] = min(dn.get("dip", clo), clo)
            if cc < co:
                dn["rhigh"] = ch
            elif cc > dn.get("rhigh", float("inf")):
                dn.update(pending=dn["dip"], pt=now_t, phigh=ch,
                          leg=False, retest=None)
        if dn.get("pending") and sig is None:
            dn["phigh"] = max(dn.get("phigh", ch), ch)
            if now_t - dn.get("pt", now_t) > 21600:
                dn["pending"] = None
            elif cc < dn["pending"]:
                wd = abs(dn.get("phigh", ch) - dn["pending"])
                if dn["pending"] - cc > max(20.0, 0.35 * wd):
                    dn.update(retest=dn["pending"],
                              rt_phigh=dn.get("phigh", ch),
                              rt_t=now_t, pending=None)
                else:
                    sig = (-1, dn.get("phigh", ch))
                    dn["pending"] = None
        elif dn.get("retest") and sig is None:
            if now_t - dn.get("rt_t", now_t) > 21600:
                dn["retest"] = None
            elif (ch >= dn["retest"] - 15.0
                  and cc <= dn["retest"] + 15.0):
                sig = (-1, dn.get("rt_phigh", ch))
                dn["retest"] = None
        return sig


def run(O, H, L, C, T, cap, tpf, S, lot=0.01, rand_seed=None,
        rand_rate=470.0):
    N = len(T)
    tr = np.maximum(H[1:] - L[1:], np.maximum(
        np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))
    cs = np.concatenate([[0.0], np.cumsum(tr)])

    def atr14(i):
        a, b = max(0, i - 15), i - 1
        return (cs[b] - cs[a]) / max(1, b - a)

    det = LiveDet(O, H, L, C, T)
    pos = None
    res = []
    rs = [rand_seed or 0]

    def rnd():
        rs[0] = (rs[0] * 1103515245 + 12345) % (2 ** 31)
        return rs[0] / (2 ** 31)

    for i in range(40, N):
        if pos is not None:
            d, e = pos["d"], pos["e"]
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
                pos["slv"] = e + d * min(S + 10.0, 0.5 * fav)
                if d == 1:
                    sl_hit = L[i] <= pos["slv"]
                else:
                    sl_hit = H[i] >= pos["slv"] - S
            if tp_hit and sl_hit:
                px, kind = pos["slv"], "tie_sl"
            elif sl_hit:
                px, kind = pos["slv"], "sl"
            elif tp_hit:
                px, kind = pos["tp"], "tp"
            else:
                continue
            res.append((i, (px - e) * d * lot, kind))
            pos = None
            det = LiveDet(O, H, L, C, T)
            continue
        sig = det.step(i)
        if rand_seed is not None:
            sig = None
            if rnd() < 1.0 / rand_rate:
                d0 = 1 if rnd() < 0.5 else -1
                sig = (d0, C[i] - d0 * 100.0)
        if sig is None:
            continue
        d, wall = sig
        e_bid = C[i]
        dist = abs(e_bid - wall)
        if dist < 60.0 or dist * lot > 2.50:
            continue
        if abs(C[i] - O[i]) >= atr14(i):
            continue
        disc = min(1.0, 0.25 * dist * lot)
        tpd = (min(dist - disc / lot, 1.50 / lot)) * tpf
        e = e_bid + (S if d == 1 else 0.0)
        slp = dist if cap is None else min(dist, cap)
        pos = dict(d=d, e=e, slv=e_bid - d * slp,
                   tp=e_bid + d * tpd, locked=False)
    return res


def report(tag, res, T):
    W = [r for r in res if r[1] > 0.005]
    Lo = [r for r in res if r[1] < -0.005]
    net = sum(r[1] for r in res)
    wr = len(W) / max(1, len(W) + len(Lo))
    print(f"{tag}: n {len(res)} wr {wr:.0%} net {net:+.2f} "
          f"avgW {sum(r[1] for r in W)/max(1,len(W)):+.3f} "
          f"avgL {sum(r[1] for r in Lo)/max(1,len(Lo)):+.3f}")


print("-- 1) gross edge check, M1 S=0 --")
report("signal S=0 cap25 tpf.25",
       run(O1, H1, L1, C1, T1, 25.0, 0.25, 0.0), T1)
for sd in (11, 22, 33):
    report(f"RANDOM S=0 seed{sd}",
           run(O1, H1, L1, C1, T1, 25.0, 0.25, 0.0, rand_seed=sd), T1)
print("-- 2) current config S=7 random control --")
for sd in (11, 22, 33):
    report(f"RANDOM S=7 seed{sd}",
           run(O1, H1, L1, C1, T1, 25.0, 0.25, 7.0, rand_seed=sd), T1)
print("-- 3) higher timeframes, S=7 --")
for k, lbl in ((5, "M5"), (15, "M15")):
    O, H, L, C, T = resample(k)
    for cap in (25.0, 50.0, 100.0, None):
        report(f"{lbl} cap {str(cap):>5} tpf .25",
               run(O, H, L, C, T, cap, 0.25, 7.0), T)
    report(f"{lbl} RANDOM cap25 (seed11)",
           run(O, H, L, C, T, 25.0, 0.25, 7.0, rand_seed=11,
               rand_rate=470.0 / k), T)
