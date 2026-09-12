"""EXECUTION AUDIT of the deployed BOS strategy (2026-09-11).

Signal logic = the exact deployed rules (structure engine bt_bos.Struct,
flip-BOS on close, continuation TOUCH at the level, awake gate 2h,
SL at the pending dot, TP = RR x risk, one position at a time).
NOTHING in the signal logic is changed here. What changes is only HOW
the fills and exits are judged:

  mode "legacy" : the replica used for the +255 baseline (bt_invert /
                  bt_multi / bt_pbentry / bt_choch): a TOUCH position
                  opened during bar j is NOT checked against bar j's
                  low/high - SL/TP evaluation starts at bar j+1.
                  Later bars: ties (SL and TP both inside one bar) = SL.
  mode "pess"   : entry bar j IS checked, SL first then TP (a low at/
                  below the SL anywhere in the bar = loss, even if it
                  happened before the touch). Later bars: ties = SL.
                  = the rule of the ORIGINAL bt_touch.py (+263).
  mode "opt"    : entry bar checked TP first, later bars ties = TP.
  mode "tick"   : real tick path (Exness Pro BTCUSD tick history):
                  touch = first tick with bid beyond the level while
                  flat; fill = ask/bid of the first tick >= poll_delay
                  later (the bot polls ~1 s); SL fills at the first tick
                  through it (real gap), TP fills at the TP price;
                  flip-BOS fills at the first tick after the bar close +
                  poll_delay. Same min-distance check as production
                  (measured on the actual ask/bid).

Costs: S = spread (Exness Pro BTCUSD observed $7.00 flat over the whole
window, 8.0M ticks), slip_entry / slip_sl = extra points against us on
market fills (stress), min_dist = the production S_MIN_DIST (10) or the
research value (S).

Random control: same signal stream, direction of every trade decided by
a coin (SL/TP mirrored at the same distances), full re-simulation so the
one-position-at-a-time coupling is preserved. N seeds -> distribution.
"""
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bt_bos import Struct  # noqa: E402

RR = 0.8
LOT = 0.02
WIN = 7200


def load_m1(path):
    D = np.load(path)
    return (D["o"].astype(float), D["h"].astype(float),
            D["l"].astype(float), D["c"].astype(float),
            D["t"].astype(np.int64))


def load_ticks(path):
    D = np.load(path)
    return D["t"].astype(np.int64), D["bid"].astype(float), D["ask"].astype(float)


class Pre:
    """Structure engine run ONCE over the bars (it never depends on
    positions); everything the execution loop needs is stored per bar."""

    def __init__(self, O, H, L, C, T):
        N = len(T)
        self.O, self.H, self.L, self.C, self.T = O, H, L, C, T
        self.sig_d = np.zeros(N, np.int8)
        self.sig_sl = np.full(N, np.nan)
        self.sig_flip = np.zeros(N, bool)
        self.tb_lvl = np.full(N, np.nan)   # touch-buy level (hi_v before the bar)
        self.tb_sl = np.full(N, np.nan)    # its SL (pending span low)
        self.ts_lvl = np.full(N, np.nan)
        self.ts_sl = np.full(N, np.nan)
        flips = []
        st = Struct()
        for j in range(N):
            if st.trend == 1 and st.hi_v is not None:
                span = st.kept[st.hi_i + 1:]
                if span and any(x[5] == -1 for x in span):
                    self.tb_lvl[j] = st.hi_v
                    self.tb_sl[j] = min(span, key=lambda x: x[3])[3]
            elif st.trend == -1 and st.lo_v is not None:
                span = st.kept[st.lo_i + 1:]
                if span and any(x[5] == 1 for x in span):
                    self.ts_lvl[j] = st.lo_v
                    self.ts_sl[j] = max(span, key=lambda x: x[2])[2]
            pt = st.trend
            sig = st.step(int(T[j]), O[j], H[j], L[j], C[j])
            if st.trend != pt and st.trend != 0 and pt != 0:
                flips.append(int(T[j]))
            if sig is not None:
                self.sig_d[j] = sig[0]
                self.sig_sl[j] = sig[1]
                if st.trend != pt:
                    self.sig_flip[j] = True   # includes bootstrap 0 -> +-1
        F = np.array(flips, np.int64)
        self.flips = F
        # awake for the touch check at bar j = replica's ev after bar j-1:
        # flips from bars < j with time >= T[j-1] - WIN
        self.awake_touch = np.zeros(N, bool)
        self.awake_sig = np.zeros(N, bool)
        if len(F):
            for j in range(1, N):
                lo = np.searchsorted(F, T[j - 1] - WIN)
                hi = np.searchsorted(F, T[j], side="left")
                self.awake_touch[j] = hi > lo
                lo2 = np.searchsorted(F, T[j] - WIN)
                hi2 = np.searchsorted(F, T[j], side="right")
                self.awake_sig[j] = hi2 > lo2
        self.N = N


class Ticks:
    def __init__(self, t_ms, bid, ask):
        self.t, self.bid, self.ask = t_ms, bid, ask
        self.n = len(t_ms)

    def idx_at(self, t_ms):
        return int(np.searchsorted(self.t, t_ms, side="left"))

    def first_true(self, start, cond_fn, chunk=100000):
        i = start
        n = self.n
        while i < n:
            j = min(n, i + chunk)
            m = cond_fn(slice(i, j))
            if m.any():
                return i + int(np.argmax(m))
            i = j
        return None


def simulate(P, mode="legacy", entries=("flip", "touch"), gate=True,
             S=7.0, min_dist=None, slip_entry=0.0, slip_sl=0.0,
             seed=None, ticks=None, poll_delay_ms=1000, lot=LOT,
             cont_tp="own", max_dist=float("inf"), max_dist_cont_only=True):
    """Returns the list of closed trades (dicts).
    cont_tp: "own" = TP from the close entry (RR x its own risk);
             "touch" = the TP the touch rule would have set (measured
             from the level: level+S +/- RR x (level+S - SL))."""
    if min_dist is None:
        min_dist = S

    def touch_tp(j, d, slp):
        lvl = P.tb_lvl[j] if d == 1 else P.ts_lvl[j]
        if np.isnan(lvl):
            return None
        e_t = lvl + S if d == 1 else lvl
        return e_t + d * RR * abs(e_t - slp)
    O, H, L, C, T = P.O, P.H, P.L, P.C, P.T
    N = P.N
    rng = np.random.default_rng(seed) if seed is not None else None
    pos = None
    out = []
    used_hi = used_lo = None
    tick = (mode == "tick")

    def mk(d, e, dist, kind, j, tick_i=None):
        return dict(d=d, e=e, sl=e - d * dist, tp=e + d * RR * dist,
                    kind=kind, j=j, ti=tick_i, dist=dist, xi=None)

    def close(p, px, k, why):
        pnl = (px - p["e"]) * p["d"] * lot
        out.append(dict(j=p["j"], k=k, kind=p["kind"], d=p["d"], e=p["e"],
                        sl=p["sl"], tp=p["tp"], x=px, pnl=pnl, why=why,
                        t=int(T[p["j"]]), dist=p["dist"],
                        ti=p["ti"], xi=p["xi"]))

    def m1_exit(p, k, entry_bar):
        d = p["d"]
        if d == 1:
            sl_hit = L[k] <= p["sl"]
            tp_hit = H[k] >= p["tp"]
        else:
            sl_hit = H[k] >= p["sl"] - S
            tp_hit = L[k] <= p["tp"] - S
        if not (sl_hit or tp_hit):
            return False
        tp_first = (mode == "opt")
        if sl_hit and tp_hit:
            hit_tp = tp_first
        else:
            hit_tp = tp_hit
        if hit_tp:
            close(p, p["tp"], k, "tp")
        else:
            close(p, p["sl"] - d * slip_sl, k, "sl")
        return True

    def tick_exit(p):
        d, sl, tp = p["d"], p["sl"], p["tp"]
        if d == 1:
            cond = lambda s: (ticks.bid[s] <= sl) | (ticks.bid[s] >= tp)
        else:
            cond = lambda s: (ticks.ask[s] >= sl) | (ticks.ask[s] <= tp)
        i = ticks.first_true(p["ti"] + 1, cond)
        if i is None:
            return False
        p["xi"] = i
        k = int(np.searchsorted(T, ticks.t[i] // 1000, side="right") - 1)
        if d == 1:
            if ticks.bid[i] >= tp and not ticks.bid[i] <= sl:
                close(p, tp, k, "tp")
            else:
                close(p, ticks.bid[i] - slip_sl, k, "sl")
        else:
            if ticks.ask[i] <= tp and not ticks.ask[i] >= sl:
                close(p, tp, k, "tp")
            else:
                close(p, ticks.ask[i] + slip_sl, k, "sl")
        return True

    def coin(d):
        if rng is None:
            return d
        return 1 if rng.random() < 0.5 else -1

    def open_touch(d0, lvl, slp, j, free_from, bar_end):
        """Returns the new position or None. Sets used level only when
        the touch actually fires (tick) / when the bar high crosses (M1)."""
        nonlocal used_hi, used_lo
        if tick:
            if free_from >= bar_end:
                return None
            if d0 == 1:
                i1 = ticks.first_true(free_from, lambda s: ticks.bid[s] > lvl)
            else:
                i1 = ticks.first_true(free_from, lambda s: ticks.bid[s] < lvl)
            if i1 is None or i1 >= bar_end:
                return None
            if d0 == 1:
                used_hi = lvl
            else:
                used_lo = lvl
            i2 = ticks.idx_at(ticks.t[i1] + poll_delay_ms)
            if i2 >= ticks.n:
                return None
            e_ref = ticks.ask[i2] if d0 == 1 else ticks.bid[i2]
            dist = abs(e_ref - slp)
            d = coin(d0)
            e = (ticks.ask[i2] + slip_entry) if d == 1 else (ticks.bid[i2] - slip_entry)
            if dist <= min_dist:
                return None
            p = mk(d, e, dist, "touch", j, i2)
            if not tick_exit(p):
                return None
            return p
        # M1 modes
        if d0 == 1:
            used_hi = lvl
            e_ref = lvl + S
        else:
            used_lo = lvl
            e_ref = lvl
        dist = abs(e_ref - slp)
        if dist <= min_dist:
            return None
        d = coin(d0)
        e = (lvl + S + slip_entry) if d == 1 else (lvl - slip_entry)
        p = mk(d, e, dist, "touch", j)
        if mode in ("pess", "opt") and m1_exit(p, j, True):
            return None
        return p

    for j in range(N):
        if tick:
            bar_i0 = ticks.idx_at(int(T[j]) * 1000)
            bar_end = ticks.idx_at(int(T[j]) * 1000 + 60000)
            if pos is not None and pos["xi"] < bar_i0:
                pos = None
            free_from = bar_i0 if pos is None else pos["xi"] + 1
            touch_ok = pos is None or pos["xi"] < bar_end
        else:
            bar_i0 = bar_end = free_from = None
            if pos is not None and pos["j"] < j and m1_exit(pos, j, False):
                pos = None
            touch_ok = pos is None
        # ---- TOUCH entry during bar j
        if touch_ok and "touch" in entries and (P.awake_touch[j] or not gate):
            lvl_b, lvl_s = P.tb_lvl[j], P.ts_lvl[j]
            if not np.isnan(lvl_b) and H[j] > lvl_b and used_hi != lvl_b:
                p = open_touch(1, lvl_b, P.tb_sl[j], j, free_from, bar_end)
                if p is not None:
                    pos = p
            elif not np.isnan(lvl_s) and L[j] < lvl_s and used_lo != lvl_s:
                p = open_touch(-1, lvl_s, P.ts_sl[j], j, free_from, bar_end)
                if p is not None:
                    pos = p
        # ---- FLIP-BOS entry on the close of bar j
        take_sig = P.sig_d[j] != 0 and (P.awake_sig[j] or not gate) and (
            ("flip" in entries and P.sig_flip[j])
            or ("cont" in entries and not P.sig_flip[j]))
        if take_sig:
            d0 = int(P.sig_d[j])
            slp = P.sig_sl[j]
            if tick:
                i2 = ticks.idx_at((int(T[j]) + 60) * 1000 + poll_delay_ms)
                flip_ok = (pos is None or pos["xi"] < i2) and i2 < ticks.n
                if flip_ok:
                    e_ref = ticks.ask[i2] if d0 == 1 else ticks.bid[i2]
                    dist = abs(e_ref - slp)
                    d = coin(d0)
                    e = (ticks.ask[i2] + slip_entry) if d == 1 else (ticks.bid[i2] - slip_entry)
                    if dist > min_dist and (dist < max_dist or (max_dist_cont_only and P.sig_flip[j])):
                        p = mk(d, e, dist, "flip" if P.sig_flip[j] else "cont", j, i2)
                        if cont_tp == "touch" and not P.sig_flip[j] and d == d0:
                            t2 = touch_tp(j, d, slp)
                            if t2 is not None:
                                p["tp"] = t2
                        if tick_exit(p):
                            pos = p
            elif pos is None:
                e_ref = C[j] + S if d0 == 1 else C[j]
                dist = abs(e_ref - slp)
                d = coin(d0)
                e = (C[j] + S + slip_entry) if d == 1 else (C[j] - slip_entry)
                if dist > min_dist and (dist < max_dist or (max_dist_cont_only and P.sig_flip[j])):
                    pos = mk(d, e, dist, "flip" if P.sig_flip[j] else "cont", j)
                    if cont_tp == "touch" and not P.sig_flip[j] and d == d0:
                        t2 = touch_tp(j, d, slp)
                        if t2 is not None:
                            pos["tp"] = t2
    out.sort(key=lambda x: (x["j"], x["ti"] if x["ti"] is not None else 0))
    return out


def stats(trades, label="", t_lo=None, t_hi=None):
    tr = [x for x in trades
          if (t_lo is None or x["t"] >= t_lo) and (t_hi is None or x["t"] < t_hi)]
    n = len(tr)
    if n == 0:
        return dict(label=label, n=0)
    p = np.array([x["pnl"] for x in tr])
    W = p[p > 0]
    Lo = p[p <= 0]
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    mdd = float(np.max(peak - cum))
    return dict(label=label, n=n, wr=len(W) / n, net=float(p.sum()),
                avgW=float(W.mean()) if len(W) else 0.0,
                avgL=float(Lo.mean()) if len(Lo) else 0.0,
                pf=float(W.sum() / -Lo.sum()) if len(Lo) and Lo.sum() < 0 else float("inf"),
                mdd=mdd, exp=float(p.mean()),
                n_touch=sum(1 for x in tr if x["kind"] == "touch"),
                net_touch=float(sum(x["pnl"] for x in tr if x["kind"] == "touch")),
                n_flip=sum(1 for x in tr if x["kind"] == "flip"),
                net_flip=float(sum(x["pnl"] for x in tr if x["kind"] == "flip")))


def fmt(s):
    if s.get("n", 0) == 0:
        return f"{s.get('label',''):34s}: no trades"
    return (f"{s['label']:34s}: n {s['n']:4d} wr {s['wr']:.1%} net {s['net']:+8.2f} "
            f"avgW {s['avgW']:+.2f} avgL {s['avgL']:+.2f} PF {s['pf']:.2f} "
            f"maxDD {s['mdd']:6.2f} exp/tr {s['exp']:+.3f} "
            f"| flip n {s['n_flip']} {s['net_flip']:+.1f} | touch n {s['n_touch']} {s['net_touch']:+.1f}")


if __name__ == "__main__":
    O, H, L, C, T = load_m1(os.path.join(HERE, "..", "data", "pro_m1.npz"))
    P = Pre(O, H, L, C, T)
    tr = simulate(P, "legacy")
    print(fmt(stats(tr, "PARITY legacy (expect +255.12/622)")))
    tr = simulate(P, "pess")
    print(fmt(stats(tr, "PARITY pess (expect +263.14/622)")))
