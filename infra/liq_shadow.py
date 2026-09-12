"""LIQUIDATION SHADOW OBSERVER (E016 latency logger; E017 forward stream from 2026-09-12 13:07 UTC). NO ORDERS.

Subscribes to the OKX v5 public websocket channel 'liquidation-orders'
(instType SWAP), keeps BTC-USDT-SWAP fills, maintains the rolling burst
measure of PREREG_E016.md (W seconds, trailing-7-day 95th percentile of
the fill-sampled burst, 300 s cooldown; the window W and the seed history
come from liq_shadow_config.json written by the E016 freeze) and, for
every detection, logs the theoretical trade the frozen rule would take on
Exness BTCUSD: receive latency, the quote at detection, the quote after
the frozen delay, and outcomes at 5/10/30/60/120/300 s plus MFE/MAE.

Also logs EVERY fill with exchange time vs receive time (latency
measurement) to liq_shadow_fills.csv. Reads the Exness quote from the
demo Pro terminal (read-only, same feed as live).
"""
import asyncio
import csv
import datetime as dt
import json
import os
import time

import MetaTrader5 as mt5
import websockets

DIR = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(DIR, "liq_shadow_config.json")
FILLS = os.path.join(DIR, "liq_shadow_fills.csv")
EVENTS = os.path.join(DIR, "liq_shadow_events.csv")
LOG = os.path.join(DIR, "liq_shadow.log")
STATE = os.path.join(DIR, "liq_shadow_state.json")
URL = "wss://ws.okx.com:8443/ws/v5/public"
TERMINAL = r"C:\NestTerminals\u476954287\terminal64.exe"
LOGIN = 476954287
SERVER = "Exness-MT5Trial9"
SYMBOL = "BTCUSD"
utc = dt.timezone.utc


def say(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now(utc).isoformat()} {msg}\n")


def load_cfg():
    try:
        return json.load(open(CFG, encoding="utf-8"))
    except Exception:
        return {"W": 60, "pct": 95, "cooldown_s": 300, "delay_s": 20, "horizons_s": [5, 10, 30, 60, 120, 300], "slip": 5.0, "note": "defaults (no freeze file)"}


def quote():
    tk = mt5.symbol_info_tick(SYMBOL)
    if tk is None:
        return None
    now = time.time()
    return dict(t=now, bid=tk.bid, ask=tk.ask, tms=tk.time_msc, spread=round(tk.ask - tk.bid, 2), age=round(now - tk.time_msc / 1000, 3))


class Burst:
    def __init__(self, W, pct, cooldown, seed):
        self.W, self.pct, self.cool = W, pct, cooldown
        self.fills = []                   # (t_s, size_btc, dir) recent (within W)
        self.hist = seed[:]               # fill-sampled burst values with times, trailing 7 d
        self.last_det = -1e18

    def add(self, t, sz, d):
        self.fills.append((t, sz, d))
        while self.fills and self.fills[0][0] <= t - self.W:
            self.fills.pop(0)
        b = sum(x[1] for x in self.fills)
        bs = sum(x[1] for x in self.fills if x[2] == -1)
        bb = b - bs
        self.hist.append((t, b))
        cut = t - 7 * 86400
        while self.hist and self.hist[0][0] < cut:
            self.hist.pop(0)
        if len(self.hist) < 500 or t - self.last_det < self.cool:
            return None
        vals = sorted(v for _, v in self.hist[:-1])
        thr = vals[min(len(vals) - 1, int(self.pct / 100 * len(vals)))]
        if b >= thr:
            self.last_det = t
            return dict(burst=b, thr=thr, forced=-1 if bs >= bb else 1)
        return None


async def outcome_logger(ev, cfg):
    """Track the theoretical trade after the frozen delay."""
    await asyncio.sleep(max(0.0, cfg["delay_s"] - (time.time() - ev["t_recv"])))
    q = quote()
    if q is None:
        return
    d = -ev["forced"]                     # trade direction
    e = q["ask"] if d == 1 else q["bid"]
    ev["entry_t"], ev["entry"] = q["t"], e
    mfe = mae = 0.0
    res = {}
    t0 = q["t"]
    last_h = max(cfg["horizons_s"])
    nxt = sorted(cfg["horizons_s"])
    while time.time() - t0 <= last_h + 1:
        await asyncio.sleep(0.5)
        q2 = quote()
        if q2 is None:
            continue
        x = q2["bid"] if d == 1 else q2["ask"]
        pnl = (x - e) * d
        mfe, mae = max(mfe, pnl), max(mae, -pnl)
        el = time.time() - t0
        while nxt and el >= nxt[0]:
            res[nxt[0]] = round(pnl - cfg["slip"], 2)
            nxt.pop(0)
    row = [dt.datetime.utcfromtimestamp(ev["t_exch"]).isoformat(timespec="milliseconds"), round(ev["t_recv"] - ev["t_exch"], 3), round(ev["t_det"] - ev["t_exch"], 3),
           ev["forced"], d, round(ev["burst"], 3), round(ev["thr"], 3), ev["q_det"]["bid"], ev["q_det"]["ask"], ev["q_det"].get("spread", ""), ev["q_det"].get("age", ""), round(ev["entry_t"] - ev["t_exch"], 3), e, q["spread"], q["age"]] + [res.get(h, "") for h in sorted(cfg["horizons_s"])] + [round(mfe, 2), round(mae, 2)]
    new = not os.path.exists(EVENTS)
    with open(EVENTS, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["exch_utc", "recv_latency_s", "det_latency_s", "forced_side", "trade_dir", "burst_btc", "thr_btc", "bid_at_det", "ask_at_det", "spread_at_det", "quote_age_det_s", "entry_delay_s", "entry_px", "spread_at_entry", "quote_age_entry_s"] + [f"net_{h}s" for h in sorted(cfg["horizons_s"])] + ["mfe", "mae"])
        w.writerow(row)
    say(f"EVENT {row[0]} forced {ev['forced']:+d} burst {ev['burst']:.2f}/{ev['thr']:.2f} latency recv {row[1]}s -> outcomes {res} mfe {mfe:.1f} mae {mae:.1f}")


async def main():
    cfg = load_cfg()
    assert mt5.initialize(path=TERMINAL, login=LOGIN, password=json.load(open(os.path.join(DIR, "owl_secrets.json"), encoding="utf-8"))["mt5_password"], server=SERVER, timeout=60000), "MT5 init failed"
    mt5.symbol_select(SYMBOL, True)
    seed = [(x[0], x[1]) for x in cfg.get("seed_hist", [])]
    bst = Burst(cfg["W"], cfg["pct"], cfg["cooldown_s"], seed)
    say(f"shadow observer starting: W {cfg['W']}s p{cfg['pct']} cooldown {cfg['cooldown_s']}s delay {cfg['delay_s']}s; seed hist {len(seed)}; {cfg.get('note','')}")
    n = 0
    while True:
        try:
            async with websockets.connect(URL, ping_interval=20, ping_timeout=20, max_size=2 ** 22) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]}))
                say("websocket connected + subscribed")
                while True:
                    raw = await ws.recv()
                    t_recv = time.time()
                    m = json.loads(raw)
                    if "event" in m:
                        continue
                    for dd in m.get("data", []):
                        if dd.get("instId") != "BTC-USDT-SWAP":
                            continue
                        for det in dd.get("details", []):
                            t_ex = int(det["ts"]) / 1000
                            sz = float(det["sz"]) * 0.01
                            forced = -1 if det.get("posSide") == "long" else 1
                            n += 1
                            new = not os.path.exists(FILLS)
                            with open(FILLS, "a", newline="", encoding="utf-8") as f:
                                w = csv.writer(f)
                                if new:
                                    w.writerow(["exch_utc", "recv_utc", "latency_s", "posSide", "sz_btc", "bkPx"])
                                w.writerow([dt.datetime.utcfromtimestamp(t_ex).isoformat(timespec="milliseconds"), dt.datetime.utcfromtimestamp(t_recv).isoformat(timespec="milliseconds"), round(t_recv - t_ex, 3), det.get("posSide"), round(sz, 4), det.get("bkPx")])
                            hit = bst.add(t_ex, sz, forced)
                            if hit:
                                q = quote()
                                ev = dict(t_exch=t_ex, t_recv=t_recv, t_det=time.time(), q_det=q or {"bid": "", "ask": ""}, **hit)
                                asyncio.create_task(outcome_logger(ev, cfg))
                            if n % 500 == 0:
                                json.dump({"fills": n, "alive": dt.datetime.now(utc).isoformat(), "hist": len(bst.hist)}, open(STATE, "w"))
        except Exception as e:
            say(f"websocket error {type(e).__name__}: {e}; reconnecting in 5 s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
