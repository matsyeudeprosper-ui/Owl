"""Does structure-chop predict bad BOS trades? One ungated run of
the user's exact rule; at each entry record the last-2h counts of
chocs / flips / repaired chocs, then bucket the results. Also a
simulated gate (block entries when the window is hot).
"""
from collections import deque

from bt_bos import Struct, O, H, L, C, T, S

LOT = 0.02
RR = 0.8
WIN = 7200          # 2h window


def run():
    st = Struct()
    pos = None
    ev = deque()
    trades = []
    for j in range(len(T)):
        t, o, h, l, c = int(T[j]), O[j], H[j], L[j], C[j]
        if pos is not None:
            d, e, sl, tp, meta = pos
            sl_hit = (l <= sl) if d == 1 else (h >= sl - S)
            tp_hit = (h >= tp) if d == 1 else (l <= tp - S)
            if sl_hit:
                trades.append((meta, (sl - e) * d * LOT))
                pos = None
            elif tp_hit:
                trades.append((meta, (tp - e) * d * LOT))
                pos = None
        pt, pc = st.trend, st.choch
        sig = st.step(t, o, h, l, c)
        if st.choch != pc and st.choch != 0:
            ev.append((t, "choch"))
        if st.trend != pt and st.trend != 0 and pt != 0:
            ev.append((t, "flip"))
        if pc != 0 and st.choch == 0 and st.trend == pt \
                and st.trend != 0:
            ev.append((t, "repair"))
        while ev and ev[0][0] < t - WIN:
            ev.popleft()
        if sig is None or pos is not None:
            continue
        d, slp = sig
        ch = sum(1 for x in ev if x[1] == "choch")
        fl = sum(1 for x in ev if x[1] == "flip")
        rp = sum(1 for x in ev if x[1] == "repair")
        if d == 1:
            e = c + S
            if e - slp <= S:
                continue
            tp = e + RR * (e - slp)
        else:
            e = c
            if slp - e <= S:
                continue
            tp = e - RR * (slp - e)
        pos = (d, e, slp, tp, (ch, fl, rp))
    return trades


def bucket(trades, key, cuts, name):
    print(f"-- by {name} (last 2h) --")
    for lo, hi, lbl in cuts:
        sel = [p for (m, p) in trades if lo <= m[key] <= hi]
        if not sel:
            print(f"  {lbl:>6}: none")
            continue
        w = sum(1 for p in sel if p > 0)
        print(f"  {lbl:>6}: n {len(sel):4d} wr {w/len(sel):.0%} "
              f"net {sum(sel):+8.2f} avg {sum(sel)/len(sel):+.3f}")


tr = run()
print(f"{len(tr)} trades total, net {sum(p for _, p in tr):+.2f}")
bucket(tr, 0, [(0, 1, "0-1"), (2, 3, "2-3"), (4, 99, "4+")], "chocs")
bucket(tr, 1, [(0, 0, "0"), (1, 1, "1"), (2, 99, "2+")], "flips")
bucket(tr, 2, [(0, 0, "0"), (1, 99, "1+")], "repairs")

print("\n-- gate simulations (block when window is hot) --")
for lbl, fn in (
        ("chocs>=3", lambda m: m[0] >= 3),
        ("chocs>=4", lambda m: m[0] >= 4),
        ("flips>=2", lambda m: m[1] >= 2),
        ("chocs>=3 or flips>=2", lambda m: m[0] >= 3 or m[1] >= 2)):
    kept = [p for (m, p) in tr if not fn(m)]
    blk = [p for (m, p) in tr if fn(m)]
    print(f"  {lbl:22s}: kept n {len(kept):4d} net "
          f"{sum(kept):+8.2f} | blocked n {len(blk):4d} net "
          f"{sum(blk):+8.2f}")
