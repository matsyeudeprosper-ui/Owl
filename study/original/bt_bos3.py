"""Walk-forward: pick the best (entry-set x RR) cell on days 1-35,
judge it blind on days 36-69. Full grid shown on both halves for
transparency."""
import numpy as np
import bt_bos2
from bt_bos import Struct, S

D = np.load(r"C:\Users\ADMINI~1\AppData\Local\Temp\2\claude"
            r"\C--Users-Administrator--local-bin"
            r"\13a6abff-f560-41e2-b2a1-bbdf64ec7284\scratchpad"
            r"\pro_m1.npz")
O, H, L, C = (D[k].astype(float) for k in "ohlc")
T = D["t"].astype(int)
mid = np.searchsorted(T, T[0] + (T[-1] - T[0]) // 2)
LOT = 0.02


def run(a, b, rr, flip_only):
    st = Struct()
    pos = None
    res = []
    for j in range(a, b):
        t, o, h, l, c = T[j], O[j], H[j], L[j], C[j]
        if pos is not None:
            d, e, sl, tp = pos
            sl_hit = (l <= sl) if d == 1 else (h >= sl - S)
            tp_hit = (h >= tp) if d == 1 else (l <= tp - S)
            if sl_hit:
                res.append((sl - e) * d * LOT)
                pos = None
            elif tp_hit:
                res.append((tp - e) * d * LOT)
                pos = None
        pt = st.trend
        sig = st.step(t, o, h, l, c)
        if sig is None:
            continue
        if flip_only and st.trend == pt:
            continue
        if pos is not None:
            continue
        d, slp = sig
        if d == 1:
            e = c + S
            if e - slp <= S:
                continue
            tp = e + rr * (e - slp)
        else:
            e = c
            if slp - e <= S:
                continue
            tp = e - rr * (slp - e)
        pos = (d, e, slp, tp)
    net = sum(res)
    W = sum(1 for x in res if x > 0)
    return net, len(res), W


print("cell            | days 1-35 | days 36-69")
best = (None, -1e9)
for flip in (False, True):
    for rr in (0.5, 0.8, 1.2, 2.0):
        na, ca, wa = run(0, mid, rr, flip)
        nb, cb, wb = run(mid, len(T), rr, flip)
        tag = f"{'FLIP' if flip else 'ALL '} rr {rr:.1f}"
        print(f"{tag}    | {na:+8.2f} ({ca:3d}) | {nb:+8.2f} ({cb:3d})")
        if na > best[1]:
            best = ((rr, flip), na)
rr, flip = best[0]
nb, cb, wb = run(mid, len(T), rr, flip)
print(f"\nWALK-FORWARD: in-sample winner = "
      f"{'FLIP' if flip else 'ALL'} rr {rr}")
print(f"out-of-sample verdict: net {nb:+.2f} over {cb} trades "
      f"(wr {wb/max(1,cb):.0%})")
