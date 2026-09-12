"""Sections 1-4: bucket every pre-entry feature into broad quantiles
(cuts from the TRAIN half only), report train / test / untouched OOS,
then freeze ONE preregistered rule per feature and test it blind.

Preregistered "bad side" per feature (stated before looking at test/OOS):
  break quality : overshoot_ratio LOW, body_range LOW, close_loc LOW, overshoot LOW
  ordinal       : report only (no rule preregistered)
  efficiency    : se_flip LOW (continuations), se_60 LOW, disturb_2h HIGH, prog_per_disturb LOW
  risk geometry : stop_atr / stop_range60 / stop_med60 - report both tails; rule = block the tail
                  that is negative in TRAIN (if both, block both) - that is ONE extra choice each.
Rule form is always "block the 25% bucket on the bad side" (train quantile).
Blocked-trade accounting is list-based (trade removed from the fixed
baseline sequence). A survivor is then re-simulated with the filter
inside the engine to include the one-position interaction.
"""
import csv
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sp = dict(l.strip().split("=") for l in open(os.path.join(HERE, "split.txt")))
MID = int(sp["mid"])


def load(fn):
    rows = list(csv.DictReader(open(os.path.join(HERE, fn))))
    for r in rows:
        for k, v in r.items():
            if k in ("time", "kind", "why"):
                continue
            try:
                r[k] = float(v)
            except ValueError:
                r[k] = np.nan
    return rows


INS = load("trades_insample.csv")
OOS = load("trades_oos.csv")
TRAIN = [r for r in INS if r["t"] < MID]
TEST = [r for r in INS if r["t"] >= MID]
out = open(os.path.join(HERE, "results_buckets.txt"), "w", encoding="utf-8")


def say(s=""):
    print(s)
    out.write(s + "\n")


def st(rows):
    if not rows:
        return "n    0"
    p = np.array([r["pnl"] for r in rows])
    W = p[p > 0]
    Lo = p[p <= 0]
    cum = np.cumsum(p)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    pf = W.sum() / -Lo.sum() if len(Lo) and Lo.sum() < 0 else float("inf")
    return (f"n {len(p):4d} wr {len(W)/len(p):5.1%} net {p.sum():+8.2f} PF {pf:4.2f} "
            f"exp {p.mean():+.3f} maxDD {np.max(peak-cum):6.2f}")


def buckets(feat, subset=None, label=None):
    label = label or feat
    tr = [r for r in TRAIN if not np.isnan(r[feat]) and (subset is None or subset(r))]
    q25, q75 = np.percentile([r[feat] for r in tr], [25, 75])
    say(f"\n--- {label}: train cuts q25={q25:.3f} q75={q75:.3f}")
    for name, rows in (("TRAIN", TRAIN), ("TEST ", TEST), ("OOS  ", OOS)):
        rows = [r for r in rows if not np.isnan(r[feat]) and (subset is None or subset(r))]
        lo = [r for r in rows if r[feat] <= q25]
        mid_ = [r for r in rows if q25 < r[feat] < q75]
        hi = [r for r in rows if r[feat] >= q75]
        say(f"  {name} lowest25%  {st(lo)}")
        say(f"  {name} middle50%  {st(mid_)}")
        say(f"  {name} highest25% {st(hi)}")
    return q25, q75


def rule(feat, side, cut, subset=None, label=None):
    """side 'low': block feat <= cut ; 'high': block feat >= cut."""
    label = label or f"block {feat} {side} {cut:.3f}"
    say(f"\n  RULE {label}")
    for name, rows in (("TRAIN", TRAIN), ("TEST ", TEST), ("OOS  ", OOS)):
        blk, kept = [], []
        for r in rows:
            v = r[feat]
            applies = subset is None or subset(r)
            bad = applies and not np.isnan(v) and ((v <= cut) if side == "low" else (v >= cut))
            (blk if bad else kept).append(r)
        say(f"    {name} baseline {st(rows)}")
        say(f"    {name} kept     {st(kept)}")
        say(f"    {name} blocked  {st(blk)}")


say(f"baseline: train {st(TRAIN)} | test {st(TEST)} | OOS {st(OOS)}")
say(f"(train = in-sample trades before {MID}; test = after; OOS = untouched 2026-09-08 07:12+)")

say("\n=========== 1. BOS BREAK QUALITY ===========")
choices = 0
for feat in ("overshoot_ratio", "overshoot", "body_range", "close_loc"):
    q25, q75 = buckets(feat)
    rule(feat, "low", q25, label=f"block weakest 25% by {feat} (<= {q25:.3f})")
    choices += 1
say("\n  'tiny close beyond structure with a huge stop' = overshoot_ratio lowest bucket above.")
say("  overshoot_ratio x stop_dist cross-check (train cuts):")
q_os = np.percentile([r["overshoot_ratio"] for r in TRAIN], 25)
q_sd = np.percentile([r["stop_dist"] for r in TRAIN], 75)
for name, rows in (("TRAIN", TRAIN), ("TEST ", TEST), ("OOS  ", OOS)):
    sel = [r for r in rows if r["overshoot_ratio"] <= q_os and r["stop_dist"] >= q_sd]
    say(f"    {name} tiny-break & wide-stop: {st(sel)}")

say("\n=========== 2. TRADE ORDINAL AFTER THE LAST FLIP ===========")
for name, rows in (("TRAIN", TRAIN), ("TEST ", TEST), ("OOS  ", OOS)):
    say(f"  {name}")
    for lbl, fn in (("1st (flip)", lambda r: r["ordinal"] == 1), ("2nd", lambda r: r["ordinal"] == 2),
                    ("3rd", lambda r: r["ordinal"] == 3), ("4th+", lambda r: r["ordinal"] >= 4)):
        say(f"    {lbl:11s} {st([r for r in rows if fn(r)])}")
    say(f"    cont-only  {st([r for r in rows if r['kind']=='cont'])}")
    say(f"    flip-only  {st([r for r in rows if r['kind']=='flip'])}")
say("  (no rule preregistered for ordinal - report only)")

say("\n=========== 3. STRUCTURE EFFICIENCY ===========")
cont = lambda r: r["kind"] == "cont"
q25, _ = buckets("se_flip", subset=cont, label="se_flip (continuations only)")
rule("se_flip", "low", q25, subset=cont, label=f"block continuations with se_flip <= {q25:.3f} (flips untouched)")
choices += 1
q25, _ = buckets("se_60")
rule("se_60", "low", q25, label=f"block se_60 <= {q25:.3f}")
choices += 1
_, q75 = buckets("disturb_2h")
rule("disturb_2h", "high", q75, label=f"block disturb_2h >= {q75:.0f} (chochs+repairs last 2h)")
choices += 1
q25, _ = buckets("prog_per_disturb", subset=cont, label="prog_per_disturb (continuations only)")
rule("prog_per_disturb", "low", q25, subset=cont, label=f"block continuations with prog_per_disturb <= {q25:.1f}")
choices += 1

say("\n=========== 4. RISK GEOMETRY ===========")
for feat in ("stop_atr", "stop_range60", "stop_med60", "stop_dist"):
    q25, q75 = buckets(feat)
    # choose the tail(s) that are negative in TRAIN (one extra choice)
    trn = [r for r in TRAIN if not np.isnan(r[feat])]
    lo_net = sum(r["pnl"] for r in trn if r[feat] <= q25)
    hi_net = sum(r["pnl"] for r in trn if r[feat] >= q75)
    say(f"  train tails: low {lo_net:+.2f} high {hi_net:+.2f}")
    if lo_net < 0:
        rule(feat, "low", q25, label=f"block narrowest 25% by {feat}")
    if hi_net < 0:
        rule(feat, "high", q75, label=f"block widest 25% by {feat}")
    if lo_net >= 0 and hi_net >= 0:
        say("    no negative tail in train -> no rule")
    choices += 2

say(f"\nchoices/parameters tried in this file: {choices} rules (each = one feature, one preregistered side, one train quantile)")
out.close()
