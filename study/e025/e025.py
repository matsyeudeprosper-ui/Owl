"""E025 - pullback entry AT the trend's pending dot, stop at the previous dot
(PREREG_E025.md).  Usage:
  python e025.py r0                       # R0 ticks (TRAIN/TEST)
  python e025.py era <label> <m1.npz> <S> # consumed era, M1 pess mode
"""
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit"))
sys.path.insert(0, os.path.join(HERE, "..", "regime"))
import exec_audit as A  # noqa: E402
from bt_bos import Struct  # noqa: E402
from regime_features import Pre2  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
MID = 1785880410
END = 1788851460
RR = 0.8
LOT = 0.02
S_MIN = 10.0
POLL_MS = 1000


def say(s=""):
    print(s, flush=True)
    OUT.write(s + "\n")


def dot_series(P):
    """Per bar: the trend, the pending dot on the trend side (entry level)
    and the previous dot on the same side (stop level). Values are the
    state AFTER bar j closes, i.e. usable from bar j+1 on."""
    N = P.N
    O, H, L, C, T = P.O, P.H, P.L, P.C, P.T
    trend = np.zeros(N, np.int8)
    d_cur = np.full(N, np.nan)
    d_prev = np.full(N, np.nan)
    d_id = np.full(N, -1, np.int64)          # identity of the armed dot
    st = Struct()
    lows, highs = [], []                     # confirmed dots, in order
    nid = 0
    for j in range(N):
        pt_lo, pt_hi = len(lows), len(highs)
        sig = st.step(int(T[j]), O[j], H[j], L[j], C[j])
        if sig is not None:
            if sig[0] == 1:
                lows.append((float(sig[1]), nid))
            else:
                highs.append((float(sig[1]), nid))
            nid += 1
        trend[j] = st.trend
        if st.trend == 1 and len(lows) >= 2:
            d_cur[j], d_id[j] = lows[-1][0], lows[-1][1]
            d_prev[j] = lows[-2][0]
        elif st.trend == -1 and len(highs) >= 2:
            d_cur[j], d_id[j] = highs[-1][0], highs[-1][1]
            d_prev[j] = highs[-2][0]
    return trend, d_cur, d_prev, d_id


def simulate(P, trend, d_cur, d_prev, d_id, mode, tk=None, S=7.0,
             gate=None, rng=None):
    """One position at a time. A limit sits at d_cur (the pending dot);
    when price reaches it we enter, stop at d_prev, target at 0.8R."""
    H, L, T = P.H, P.L, P.T
    N = P.N
    out = []
    used = set()
    armed = set()
    fills = 0
    busy_ms = -1                      # the open trade's exit time (ms)
    busy_bar = -1                     # M1 mode: index of the exit bar
    for j in range(1, N):
        d = int(trend[j - 1])
        lvl, slp, did = d_cur[j - 1], d_prev[j - 1], int(d_id[j - 1])
        if d == 0 or np.isnan(lvl) or np.isnan(slp):
            continue
        if did in used:
            continue
        armed.add(did)
        if abs(lvl - slp) <= S_MIN:
            continue
        if gate is not None and not gate[j]:
            continue
        if d == 1:
            if L[j] > lvl:
                continue
        else:
            if H[j] < lvl:
                continue
        if mode == "tick":
            t0, t1 = int(T[j]) * 1000, (int(T[j]) + 60) * 1000
            if t1 <= busy_ms:
                continue
            i_start = tk.idx_at(max(t0, busy_ms + 1))
            i1 = tk.first_true(i_start, (lambda s: tk.bid[s] <= lvl) if d == 1
                               else (lambda s: tk.bid[s] >= lvl))
            if i1 is None or tk.t[i1] >= t1:
                continue
            i2 = tk.idx_at(tk.t[i1] + POLL_MS)
            if i2 >= tk.n:
                continue
            used.add(did)
            fills += 1
            dd = d if rng is None else (1 if rng.random() < 0.5 else -1)
            e = tk.ask[i2] if dd == 1 else tk.bid[i2]
            dist = abs(e - slp)
            if dist <= S_MIN:
                continue
            sl, tp = slp, e + dd * RR * dist
            cond = ((lambda s: (tk.bid[s] <= sl) | (tk.bid[s] >= tp)) if dd == 1
                    else (lambda s: (tk.ask[s] >= sl) | (tk.ask[s] <= tp)))
            xi = tk.first_true(i2 + 1, cond)
            if xi is None:
                continue
            if dd == 1:
                hit_tp = tk.bid[xi] >= tp and not tk.bid[xi] <= sl
                px = tp if hit_tp else tk.bid[xi]
            else:
                hit_tp = tk.ask[xi] <= tp and not tk.ask[xi] >= sl
                px = tp if hit_tp else tk.ask[xi]
            busy_ms = int(tk.t[xi])
            out.append(dict(t=int(T[j]), d=dd, e=e, x=px,
                            pnl=(px - e) * dd * LOT,
                            why=("tp" if hit_tp else "sl"), dist=dist))
        else:
            if j <= busy_bar:
                continue
            used.add(did)
            fills += 1
            dd = d if rng is None else (1 if rng.random() < 0.5 else -1)
            e = (lvl + S) if dd == 1 else lvl
            dist = abs(e - slp)
            if dist <= S_MIN:
                continue
            sl, tp = slp, e + dd * RR * dist
            k = j
            while k < N:
                if dd == 1:
                    hit_sl, hit_tp = L[k] <= sl, H[k] >= tp
                else:
                    hit_sl, hit_tp = H[k] + S >= sl, L[k] + S <= tp
                if hit_sl or hit_tp:
                    got_tp = hit_tp and not hit_sl     # stop wins a tie
                    px = tp if got_tp else sl
                    out.append(dict(t=int(T[j]), d=dd, e=e, x=px,
                                    pnl=(px - e) * dd * LOT,
                                    why=("tp" if got_tp else "sl"), dist=dist))
                    busy_bar = k
                    break
                k += 1
    return out, fills, len(armed)


def line(tr, label, lo=None, hi=None):
    x = [t for t in tr if (lo is None or t["t"] >= lo) and (hi is None or t["t"] < hi)]
    if not x:
        say(f"  {label:<38s} n 0")
        return
    p = np.array([t["pnl"] for t in x])
    g = p[p > 0].sum()
    l_ = -p[p <= 0].sum()
    cum = np.cumsum(p)
    dd = np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)
    say(f"  {label:<38s} n {len(x):5d} net {p.sum():+8.2f} PF {g/l_ if l_ else float('inf'):5.2f} "
        f"wr {(p>0).mean():4.0%} exp {p.mean():+6.3f} maxDD {dd:6.2f} "
        f"dist med {np.median([t['dist'] for t in x]):5.0f}")


def baseline(P, tk, mode, S):
    return A.simulate(P, mode, ("flip", "cont"), True, S=S, ticks=tk, min_dist=10)


if sys.argv[1] == "r0":
    OUT = open(os.path.join(HERE, "results_r0.txt"), "w", encoding="utf-8")
    O, H, L, C, T = A.load_m1(os.path.join(DATA, "pro_m1.npz"))
    P = Pre2(O, H, L, C, T)
    tk = A.Ticks(*A.load_ticks(os.path.join(DATA, "ticks_btcusd.npz")))
    trend, dc, dp, di = dot_series(P)
    tr_dot, fills, armed = simulate(P, trend, dc, dp, di, "tick", tk)
    tr_gate, _, _ = simulate(P, trend, dc, dp, di, "tick", tk, gate=P.awake_sig)
    tr_rand, _, _ = simulate(P, trend, dc, dp, di, "tick", tk, rng=np.random.default_rng(25))
    base = baseline(P, tk, "tick", 7.0)
    say(f"R0: niveaux de point armes {armed}, touches {fills} ({fills/max(armed,1):.0%})")
    for nm, lo, hi in (("TOUT R0", None, END), ("TRAIN (< 08-04)", None, MID), ("TEST (08-04 -> 09-07)", MID, END)):
        say(f"\n=== {nm}, execution tick, net $ a 0.02 ===")
        line(base, "BASELINE live (BOS, SL au point)", lo, hi)
        line(tr_dot, "DOT entree au point, SL point-1", lo, hi)
        line(tr_gate, "DOT + porte 2h", lo, hi)
        line(tr_rand, "DOT direction aleatoire", lo, hi)
    say("done")
    OUT.close()
else:
    label, path, S = sys.argv[2], sys.argv[3], float(sys.argv[4])
    OUT = open(os.path.join(HERE, f"results_{label}.txt"), "w", encoding="utf-8")
    D = np.load(path)
    T = D["t"].astype(np.int64)
    if T[0] > 1e11:
        T = T // 1000
    P = Pre2(D["o"].astype(float), D["h"].astype(float), D["l"].astype(float), D["c"].astype(float), T)
    trend, dc, dp, di = dot_series(P)
    tr_dot, fills, armed = simulate(P, trend, dc, dp, di, "pess", None, S)
    tr_gate, _, _ = simulate(P, trend, dc, dp, di, "pess", None, S, gate=P.awake_sig)
    tr_rand, _, _ = simulate(P, trend, dc, dp, di, "pess", None, S, rng=np.random.default_rng(25))
    say(f"{label}: niveaux armes {armed}, touches {fills} ({fills/max(armed,1):.0%})")
    say(f"\n=== {label}, mode M1 pess, net $ a 0.02 ===")
    line(baseline(P, None, "pess", S), "BASELINE live")
    line(tr_dot, "DOT entree au point, SL point-1")
    line(tr_gate, "DOT + porte 2h")
    line(tr_rand, "DOT direction aleatoire")
    say("done")
    OUT.close()
