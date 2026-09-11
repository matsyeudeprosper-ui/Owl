"""Probe grid on the BOS rule: entry set (every BOS vs flip-BOS
only) x RR (0.5/0.8/1.2/2.0). Then 3 random controls on the best
cell. Same engine, execution and pessimistic ties as bt_bos."""
import numpy as np
from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02


def run(rr, flip_only, mode="signal", seed=1, quiet=False):
    st = Struct()
    pos = None
    res = []
    rs = [seed]

    def rnd():
        rs[0] = (rs[0] * 1103515245 + 12345) % (2 ** 31)
        return rs[0] / (2 ** 31)

    for j in range(len(T)):
        t, o, h, l, c = T[j], O[j], H[j], L[j], C[j]
        if pos is not None:
            d, e, sl, tp = pos
            if d == 1:
                sl_hit = l <= sl
                tp_hit = h >= tp
            else:
                sl_hit = h >= sl - S
                tp_hit = l <= tp - S
            if sl_hit:
                res.append((j, (sl - e) * d * LOT))
                pos = None
            elif tp_hit:
                res.append((j, (tp - e) * d * LOT))
                pos = None
        pt = st.trend
        sig = st.step(t, o, h, l, c)
        if sig is None:
            continue
        flip = st.trend != pt          # trend changed on this candle
        if flip_only and not flip:
            continue
        if pos is not None:
            continue
        d, slp = sig
        if mode == "random":
            dist = abs(c - slp)
            d = 1 if rnd() < 0.5 else -1
            slp = c - d * dist
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
    W = [r for r in res if r[1] > 0]
    Lo = [r for r in res if r[1] < 0]
    net = sum(r[1] for r in res)
    cum = peak = mdd = 0.0
    for r in res:
        cum += r[1]
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    if not quiet:
        print(f"{'FLIP' if flip_only else 'ALL '} rr {rr:.1f} "
              f"{mode:6s}: n {len(res):4d} "
              f"wr {len(W)/max(1,len(W)+len(Lo)):.0%} "
              f"net {net:+8.2f} maxDD {mdd:7.2f}")
    return net


print("== probe grid (69 days, $7 spread, 0.02, one-at-a-time) ==")
best = (None, -1e9)
for flip in (False, True):
    for rr in (0.5, 0.8, 1.2, 2.0):
        n = run(rr, flip)
        if n > best[1]:
            best = ((rr, flip), n)
print(f"\nbest cell: rr {best[0][0]} flip_only {best[0][1]} "
      f"-> random controls:")
for s in (11, 22, 33):
    run(best[0][0], best[0][1], mode="random", seed=s)
