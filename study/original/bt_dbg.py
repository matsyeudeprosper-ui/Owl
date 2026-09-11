"""Debug: where do the live-window signals go? Count raw Det fires
and each gate over the calibration window, with the LIVE state
machine (no up.clear() on leg birth - exact mirror of the bot)."""
import numpy as np
from datetime import datetime, timezone

D = np.load(r"C:\Users\ADMINI~1\AppData\Local\Temp\2\claude"
            r"\C--Users-Administrator--local-bin"
            r"\13a6abff-f560-41e2-b2a1-bbdf64ec7284\scratchpad"
            r"\pro_m1.npz")
O, H, L, C = (D[k].astype(float) for k in "ohlc")
T = D["t"].astype(int)
N = len(T)
t0 = datetime(2026, 9, 7, 15, 39, tzinfo=timezone.utc).timestamp()
t1 = datetime(2026, 9, 8, 7, 9, tzinfo=timezone.utc).timestamp()

_tr = np.maximum(H[1:] - L[1:], np.maximum(
    np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))
_cs = np.concatenate([[0.0], np.cumsum(_tr)])
def atr14(i):
    a, b = max(0, i - 15), i - 1
    return (_cs[b] - _cs[a]) / max(1, b - a)


class LiveDet:
    """Exact mirror of the bot's kino block (no clear on leg birth)."""

    def __init__(self):
        self.up, self.dn = {}, {}

    def step(self, i):
        po, pc = O[i - 1], C[i - 1]
        ph, pl = H[i - 1], L[i - 1]
        co, cc, ch, clo = O[i], C[i], H[i], L[i]
        up, dn = self.up, self.dn
        now_t = T[i]
        sig = None
        if pc > po and cc > co and cc > ph:
            up["leg"] = True
            up["peak"] = ch
            up["glow"] = clo
        elif up.get("leg"):
            up["peak"] = max(up.get("peak", ch), ch)
            if cc > co:
                up["glow"] = clo
            elif cc < up.get("glow", float("-inf")):
                up["pending"] = up["peak"]
                up["pt"] = now_t
                up["plow"] = clo
                up["leg"] = False
                up["retest"] = None
        if up.get("pending"):
            up["plow"] = min(up.get("plow", clo), clo)
            if now_t - up.get("pt", now_t) > 21600:
                up["pending"] = None
            elif cc > up["pending"]:
                wd = abs(up["pending"] - up.get("plow", clo))
                if cc - up["pending"] > max(20.0, 0.35 * wd):
                    up["retest"] = up["pending"]
                    up["rt_plow"] = up.get("plow", clo)
                    up["rt_t"] = now_t
                    up["pending"] = None
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
            dn["leg"] = True
            dn["dip"] = clo
            dn["rhigh"] = ch
        elif dn.get("leg"):
            dn["dip"] = min(dn.get("dip", clo), clo)
            if cc < co:
                dn["rhigh"] = ch
            elif cc > dn.get("rhigh", float("inf")):
                dn["pending"] = dn["dip"]
                dn["pt"] = now_t
                dn["phigh"] = ch
                dn["leg"] = False
                dn["retest"] = None
        if dn.get("pending") and sig is None:
            dn["phigh"] = max(dn.get("phigh", ch), ch)
            if now_t - dn.get("pt", now_t) > 21600:
                dn["pending"] = None
            elif cc < dn["pending"]:
                wd = abs(dn.get("phigh", ch) - dn["pending"])
                if dn["pending"] - cc > max(20.0, 0.35 * wd):
                    dn["retest"] = dn["pending"]
                    dn["rt_phigh"] = dn.get("phigh", ch)
                    dn["rt_t"] = now_t
                    dn["pending"] = None
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


det = LiveDet()
raw = wall_lo = wall_hi = burst = taken = 0
walls = []
for i in range(40, N):
    sig = det.step(i)
    if sig is None or not (t0 <= T[i] < t1):
        continue
    raw += 1
    d, wall = sig
    dist = abs(C[i] - wall)
    walls.append(dist)
    if dist < 60.0:
        wall_lo += 1
        continue
    if dist * 0.01 > 2.50:
        wall_hi += 1
        continue
    if abs(C[i] - O[i]) >= atr14(i):
        burst += 1
        continue
    taken += 1
print(f"raw signals {raw} | wall<60: {wall_lo} | risk>2.50: {wall_hi} "
      f"| burst-skip: {burst} | TAKEN: {taken} (live took 33)")
if walls:
    walls = sorted(walls)
    print("wall dist pcts:", [round(walls[int(q*(len(walls)-1))])
                              for q in (0, .25, .5, .75, 1)])
