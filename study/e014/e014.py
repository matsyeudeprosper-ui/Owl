"""E014 - does a BOS event carry directional information? FOLLOW vs FADE.

SCREENING ONLY (M1 first-passage, per-bar spread, ties = stop). Event
level: EVERY BOS signal of the frozen structure engine (no one-position
coupling, no gate), so this is about the signal, not the strategy.

Geometry (identical for both sides): entry at the signal bar close (bid
close + spread for the buying side), R = |bid close - pending-dot level|,
SL = 1.0R against, TP = 0.8R for. FOLLOW = BOS direction, FADE = opposite.
Sells: the position is closed on the ask, so SL is hit when bid >= sl -
spread and TP when bid <= tp - spread (bar spread). Signals with R <= 10
points are skipped (production min-distance). Outcome known at the exit
bar; a signal without a hit before the series ends is dropped.

Eras from consumed data only: V3 2025 (compact M1), V2 Jan-Jun 2026 and
R0 / V1 (archive M1, continuous Jan-Sep 2026). V4 not touched.
"""
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bt_bos import Struct  # noqa: E402

utc = dt.timezone.utc
out = open(os.path.join(HERE, "results_e014.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s, flush=True)
    out.write(s + "\n")


def load_2026():
    A = np.load(os.path.join(HERE, "..", "e011", "data", "archive_v2_m1.npz"))
    B = np.load(os.path.join(HERE, "..", "e011", "data", "archive_2026_07_09_m1.npz"))
    T = np.concatenate([A["t"], B["t"]]).astype(np.int64)
    arrs = [np.concatenate([A[k], B[k]]).astype(float) for k in ("o", "h", "l", "c", "sp")]
    o_ = np.argsort(T, kind="stable")
    T = T[o_]
    arrs = [a[o_] for a in arrs]
    keep = np.concatenate([[True], np.diff(T) > 0])
    return (T[keep],) + tuple(a[keep] for a in arrs)


def load_2025():
    M = np.load(os.path.join(HERE, "..", "e011", "data", "v3", "m1.npz"))
    return (M["t"].astype(np.int64), M["o"].astype(float), M["h"].astype(float), M["l"].astype(float), M["c"].astype(float), M["sp"].astype(float))


def era_of(t):
    d = dt.datetime.utcfromtimestamp(t)
    if d.year == 2025:
        return "V3"
    if d < dt.datetime(2026, 7, 1):
        return "V2"
    if d < dt.datetime(2026, 9, 8, 7, 12):
        return "R0"
    return "V1"


def events(T, O, H, L, C, SP):
    """All BOS signals with ordinal since flip and the next-flip bar."""
    st = Struct()
    ev = []
    order = 0
    flips = []
    for j in range(len(T)):
        pt = st.trend
        s = st.step(int(T[j]), O[j], H[j], L[j], C[j])
        if st.trend != pt and st.trend != 0 and pt != 0:
            flips.append(j)
        if s is not None:
            if st.trend != pt:
                order = 1
            else:
                order += 1
            ev.append(dict(j=j, d=int(s[0]), lvl=float(s[1]), ord=order, flip=(st.trend != pt)))
    flips = np.array(flips)
    for e in ev:
        k = np.searchsorted(flips, e["j"], side="right")
        e["next_flip"] = int(flips[k]) if k < len(flips) else len(T) - 1
    return ev


def first_passage(H, L, SPb, j, d, e, sl, tp, jmax):
    """Bars after j: returns (why, exit_bar, exit_px) with ties = stop. d = trade direction."""
    for k in range(j + 1, min(jmax, len(H))):
        if d == 1:
            hit_sl = L[k] <= sl
            hit_tp = H[k] >= tp
        else:
            hit_sl = H[k] >= sl - SPb[k]
            hit_tp = L[k] <= tp - SPb[k]
        if hit_sl:
            return "sl", k, sl
        if hit_tp:
            return "tp", k, tp
    return None, None, None


def barrier_map(H, L, SPb, C, j, d, R, horizon_bars):
    """Relative to BOS direction d: which of +kR / -kR is touched first within the horizon, for k in 0.5,0.8,1.0.
    Uses bid path (H/L) with the spread charged on the adverse side symmetrically (screening)."""
    res = {}
    px = C[j]
    for k in (0.5, 0.8, 1.0):
        up = px + d * k * R      # favourable barrier
        dn = px - d * k * R      # adverse barrier
        first = "none"
        for b in range(j + 1, min(j + 1 + horizon_bars, len(H))):
            if d == 1:
                fav = H[b] >= up
                adv = L[b] <= dn
            else:
                fav = L[b] <= up
                adv = H[b] >= dn
            if adv:
                first = "adverse"
                break
            if fav:
                first = "favourable"
                break
        res[k] = first
    return res


def evaluate(T, O, H, L, C, SP, label):
    ev = events(T, O, H, L, C, SP)
    rows = []
    for e in ev:
        j, d, lvl = e["j"], e["d"], e["lvl"]
        R = abs(C[j] - lvl)
        if R <= 10:
            continue
        rec = dict(t=int(T[j]), era=era_of(int(T[j])), d=d, R=R, ord=e["ord"], flip=e["flip"], month=dt.datetime.utcfromtimestamp(int(T[j])).strftime("%Y-%m"),
                   week=dt.datetime.utcfromtimestamp(int(T[j])).strftime("%Y-W%W"))
        for side, dd in (("follow", d), ("fade", -d)):
            e_px = C[j] + SP[j] if dd == 1 else C[j]
            sl = e_px - dd * R
            tp = e_px + dd * 0.8 * R
            why, k, px = first_passage(H, L, SP, j, dd, e_px, sl, tp, len(T))
            if why is None:
                rec[side] = None
                continue
            pnl_pts = (px - e_px) * dd
            rec[side] = dict(why=why, k=k, R=pnl_pts / R, usd=pnl_pts * 0.02, hold=k - j)
        if rec["follow"] is None or rec["fade"] is None:
            continue
        rec["exit_bar"] = max(rec["follow"]["k"], rec["fade"]["k"])
        for hz, nm in ((15, "15m"), (30, "30m"), (60, "60m"), (e["next_flip"] - j, "flip")):
            rec[f"bm_{nm}"] = barrier_map(H, L, SP, C, j, d, R, max(1, hz))
        # MFE / MAE within 60 bars in R (bid path)
        seg_h = H[j + 1:j + 61]
        seg_l = L[j + 1:j + 61]
        if len(seg_h):
            rec["mfe60"] = ((seg_h.max() - C[j]) if d == 1 else (C[j] - seg_l.min())) / R
            rec["mae60"] = ((C[j] - seg_l.min()) if d == 1 else (seg_h.max() - C[j])) / R
        rows.append(rec)
    say(f"{label}: {len(ev)} signals, {len(rows)} evaluated (R > 10 and both sides resolved)")
    return rows


def stat(rows, side):
    if not rows:
        return "n    0"
    R = np.array([r[side]["R"] for r in rows])
    u = np.array([r[side]["usd"] for r in rows])
    W = u[u > 0]
    Lo = u[u <= 0]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    return f"n {len(R):5d} TPfirst {np.mean([r[side]['why']=='tp' for r in rows]):5.1%} expR {R.mean():+.3f} PF {min(pf,9.99):4.2f} net$ {u.sum():+9.2f}"


# ---------------------------------------------------------------- run
T5, O5, H5, L5, C5, S5 = load_2025()
rows = evaluate(T5, O5, H5, L5, C5, S5, "2025 (V3)")
del T5, O5, H5, L5, C5, S5
T6, O6, H6, L6, C6, S6 = load_2026()
rows += evaluate(T6, O6, H6, L6, C6, S6, "2026 Jan-Sep (V2, R0, V1)")
ERAS = ("V3", "V2", "R0", "V1")

say("\n=== PHASE 1. FOLLOW vs FADE, identical R geometry (SL 1R, TP 0.8R), per-bar spread, M1 first-passage (SCREENING) ===")
for era in ERAS:
    s = [r for r in rows if r["era"] == era]
    say(f"  {era}: FOLLOW {stat(s, 'follow')} | FADE {stat(s, 'fade')} | follow-fade expR gap {np.mean([r['follow']['R'] for r in s]) - np.mean([r['fade']['R'] for r in s]):+.3f}")
    say(f"      MFE60 mean {np.mean([r.get('mfe60', np.nan) for r in s]):.2f}R, MAE60 mean {np.mean([r.get('mae60', np.nan) for r in s]):.2f}R (relative to BOS direction)")
say("\n=== PHASE 3. BY EVENT TYPE ===")
for era in ERAS:
    for lbl, fn in (("FLIP-BOS", lambda r: r["flip"]), ("1st continuation", lambda r: (not r["flip"]) and r["ord"] == 2),
                    ("2nd-3rd continuation", lambda r: (not r["flip"]) and r["ord"] in (3, 4)), ("late continuation (5+)", lambda r: (not r["flip"]) and r["ord"] >= 5)):
        s = [r for r in rows if r["era"] == era and fn(r)]
        if s:
            say(f"  {era} {lbl:24s} FOLLOW {stat(s, 'follow')} | FADE {stat(s, 'fade')}")

say("\n=== PHASE 2. FIRST-PASSAGE MAP relative to BOS direction: P(favourable first) / P(adverse first) / P(neither) ===")
for era in ERAS:
    s = [r for r in rows if r["era"] == era]
    for hz in ("15m", "30m", "60m", "flip"):
        parts = []
        for k in (0.5, 0.8, 1.0):
            v = [r[f"bm_{hz}"][k] for r in s]
            parts.append(f"±{k}R fav {np.mean([x=='favourable' for x in v]):.0%} adv {np.mean([x=='adverse' for x in v]):.0%} none {np.mean([x=='none' for x in v]):.0%}")
        say(f"  {era} {hz:4s}: " + " | ".join(parts))

say("\n=== PHASE 4. POLARITY THROUGH TIME (monthly): FOLLOW expR, FADE expR, difference ===")
months = sorted(set(r["month"] for r in rows))
for m in months:
    s = [r for r in rows if r["month"] == m]
    f = np.mean([r["follow"]["R"] for r in s])
    g = np.mean([r["fade"]["R"] for r in s])
    say(f"  {m} n {len(s):4d} FOLLOW {f:+.3f} FADE {g:+.3f} diff {f-g:+.3f} {'FOLLOW' if f > g else 'FADE'} | follow net$ {sum(r['follow']['usd'] for r in s):+8.1f} fade net$ {sum(r['fade']['usd'] for r in s):+8.1f}")
say("  weekly polarity sign sequence (F = follow better, f = fade better), 2025 -> 2026:")
weeks = sorted(set(r["week"] for r in rows))
seq = []
for w in weeks:
    s = [r for r in rows if r["week"] == w]
    seq.append("F" if np.mean([r["follow"]["R"] for r in s]) > np.mean([r["fade"]["R"] for r in s]) else "f")
say("    " + "".join(seq))
runs = 1 + sum(1 for a, b in zip(seq, seq[1:]) if a != b)
say(f"    {len(seq)} weeks, {runs} runs (a random sequence of this length has ~{len(seq)/2+1:.0f} runs); F share {seq.count('F')/len(seq):.0%}")

say("\n=== PHASE 5. PAST-ONLY POLARITY SCORE (rolling mean of follow R - fade R over the last 20 / 50 RESOLVED signals; sign decides) ===")
rows.sort(key=lambda r: r["t"])
# resolved = both hypothetical exits known before the current signal (exit time = signal time + hold bars * 60 s)
for r in rows:
    r["exit_t"] = r["t"] + 60 * max(r["follow"]["hold"], r["fade"]["hold"])
diffs_t = np.array([r["exit_t"] for r in rows])
diffs_v = np.array([r["follow"]["R"] - r["fade"]["R"] for r in rows])
order = np.argsort(diffs_t)
diffs_t, diffs_v = diffs_t[order], diffs_v[order]
for n in (20, 50):
    for r in rows:
        k = np.searchsorted(diffs_t, r["t"], side="left")     # resolved strictly before this signal
        r[f"pol{n}"] = float(np.mean(diffs_v[max(0, k - n):k])) if k >= n else np.nan
for era in ERAS:
    s = [r for r in rows if r["era"] == era]
    say(f"  {era}: FOLLOW always {stat(s, 'follow')}")
    say(f"  {era}: FADE   always {stat(s, 'fade')}")
    for n in (20, 50):
        chosen = []
        for r in s:
            p = r.get(f"pol{n}", np.nan)
            side = "follow" if (np.isnan(p) or p >= 0) else "fade"
            chosen.append(dict(follow=r[side], fade=r[side], era=r["era"], _side=side))
        say(f"  {era}: rolling-{n} polarity {stat(chosen, 'follow')} | chose FADE on {np.mean([c['_side']=='fade' for c in chosen]):.0%} of signals")

say("\n=== CONTROL: randomized direction per event, same times and R (200 seeds) ===")
rng = np.random.default_rng(14)
for era in ERAS:
    s = [r for r in rows if r["era"] == era]
    fR = np.array([r["follow"]["R"] for r in s])
    gR = np.array([r["fade"]["R"] for r in s])
    sims = []
    for _ in range(200):
        m = rng.random(len(s)) < 0.5
        sims.append(np.where(m, fR, gR).mean())
    sims = np.array(sims)
    say(f"  {era}: FOLLOW expR {fR.mean():+.3f} | FADE {gR.mean():+.3f} | random mean {sims.mean():+.3f} sd {sims.std():.3f} | FOLLOW z {(fR.mean()-sims.mean())/sims.std():+.2f} | FADE z {(gR.mean()-sims.mean())/sims.std():+.2f}")

say("\n=== WITHDRAWAL SIMULATION ($500, 0.02, harvest $100 above baseline, dead at baseline -60), event-level sequences (screening) ===")


def harvest(seqR, label):
    eq = 500.0
    base = 500.0
    w = 0
    dead = None
    for t, usd in seqR:
        eq += usd
        if eq >= base + 100:
            eq -= 100
            w += 100
            base = eq
        if eq <= base - 60:
            dead = t
            break
    say(f"  {label:26s} withdrawn {w:5.0f} | ending {eq:7.2f} | ruin {dt.datetime.utcfromtimestamp(dead).strftime('%Y-%m-%d') if dead else 'none'}")


for era in ("V3", "V2", "R0"):
    s = [r for r in rows if r["era"] == era]
    harvest([(r["t"], r["follow"]["usd"]) for r in s], f"{era} follow-only")
    harvest([(r["t"], r["fade"]["usd"]) for r in s], f"{era} fade-only")
    for n in (20, 50):
        harvest([(r["t"], (r["follow"] if (np.isnan(r.get(f"pol{n}", np.nan)) or r[f"pol{n}"] >= 0) else r["fade"])["usd"]) for r in s], f"{era} polarity-{n}")
say("\ndone")
out.close()
