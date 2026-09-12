"""Live probe of the OKX v5 public websocket 'liquidation-orders' channel: measures
exchange-timestamp -> our-receive latency for BTC-USDT-SWAP over ~100 s. No orders."""
import asyncio, json, time, datetime as dt, sys
import websockets
URL = "wss://ws.okx.com:8443/ws/v5/public"
async def main(seconds=100):
    t0 = time.time(); n = 0; lat = []; other = 0; msgs = 0
    async with websockets.connect(URL, ping_interval=20, ping_timeout=20, max_size=2**22) as ws:
        t_conn = time.time() - t0
        await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]}))
        sub = None
        while time.time() - t0 < seconds:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=seconds - (time.time() - t0))
            except asyncio.TimeoutError:
                break
            recv = time.time(); msgs += 1
            m = json.loads(raw)
            if "event" in m:
                sub = m; continue
            for d in m.get("data", []):
                if d.get("instId") != "BTC-USDT-SWAP":
                    other += 1; continue
                for det in d.get("details", []):
                    n += 1
                    ts = int(det["ts"]) / 1000
                    lat.append(recv - ts)
                    if n <= 5:
                        print(f"  fill exch {dt.datetime.utcfromtimestamp(ts).strftime('%H:%M:%S.%f')[:-3]} recv +{recv-ts:.3f}s side {det.get('side')} posSide {det.get('posSide')} sz {det.get('sz')} px {det.get('bkPx')}", flush=True)
    print(f"connected in {t_conn:.2f}s; subscribe ack: {sub}")
    print(f"listened {seconds}s: {msgs} messages, BTC-USDT-SWAP fills {n}, other instruments' fills {other}")
    if lat:
        import statistics as st
        print(f"exchange->receive latency s: median {st.median(lat):.3f} p90 {sorted(lat)[int(0.9*len(lat))-1]:.3f} max {max(lat):.3f} min {min(lat):.3f}")
    fields = None
asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 100))
