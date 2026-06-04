"""
Phase 4.5 — event generator (P1: chaos injection)

Same as the base generator, plus two things that make the production-hardening
features VISIBLE in the demo:
  - duplicates   (~DUP_RATE): the same event re-emitted in a LATER file, so
                  dropDuplicatesWithinWatermark has something real to remove.
  - out-of-order (~OOO_RATE): an event whose event_time is a bit in the past, to
                  prove the watermark still lands late events in their correct
                  window (events later than the watermark would be dropped).

Replaces the earlier generate_events.py.

Writes JSON-Lines files into:
  <BASE_DIR>/orders/   ->  silver_realtime_orders
  <BASE_DIR>/ads/      ->  silver_realtime_ads

Local now; point BASE_DIR at a UC Volume to feed Databricks. Stop with Ctrl+C.
"""
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone, timedelta

# ---------------- config ----------------
BASE_DIR       = os.environ.get("STREAM_BASE_DIR", "./streaming_landing")
ORDERS_PER_SEC = 1
ADS_PER_SEC    = 1
FLUSH_SECONDS  = 3
CHANNELS       = ["facebook", "google", "tiktok", "bing"]

ANOMALY_EVERY_S    = 180
ANOMALY_DURATION_S = 45
CRASH_CHANNEL      = CHANNELS[0]

# P1 chaos injection
DUP_RATE      = 0.05     # ~5% of fresh events get re-emitted later as a duplicate
OOO_RATE      = 0.05     # ~5% of events carry a slightly-late (out-of-order) timestamp
OOO_MIN_LAG_S = 20
OOO_MAX_LAG_S = 90       # stay within the 2-min watermark so late events still count
# ----------------------------------------

orders_dir = os.path.join(BASE_DIR, "orders")
ads_dir    = os.path.join(BASE_DIR, "ads")
os.makedirs(orders_dir, exist_ok=True)
os.makedirs(ads_dir, exist_ok=True)

recent_order_ids = []
dup_orders = []   # orders queued to be re-emitted later (genuine cross-file dupes)
dup_ads    = []


def event_time_iso(late=False):
    t = datetime.now(timezone.utc)
    if late:
        t -= timedelta(seconds=random.randint(OOO_MIN_LAG_S, OOO_MAX_LAG_S))
    return t.isoformat()


def make_order():
    late = random.random() < OOO_RATE
    oid = f"ord_{uuid.uuid4().hex[:12]}"
    recent_order_ids.append(oid)
    if len(recent_order_ids) > 500:
        recent_order_ids.pop(0)
    return {
        "order_id":     oid,
        "customer_id":  f"cust_{random.randint(1, 5000)}",
        "order_amount": round(random.uniform(20, 400), 2),
        "event_time":   event_time_iso(late),
    }


def make_ad(crashing=False):
    late = random.random() < OOO_RATE
    if crashing:
        channel, attributed = CRASH_CHANNEL, False
    else:
        channel = random.choice(CHANNELS)
        attributed = random.random() < 0.6
    return {
        "ad_event_id": f"ad_{uuid.uuid4().hex[:12]}",
        "order_id":    random.choice(recent_order_ids) if (attributed and recent_order_ids) else None,
        "channel":     channel,
        "ad_spend":    round(random.uniform(1, 8), 2),
        "event_time":  event_time_iso(late),
    }


def write_jsonl(directory, records):
    if not records:
        return
    fname = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f") + ".json"
    path  = os.path.join(directory, fname)
    tmp   = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, path)


def main():
    print(f"Generating events into {BASE_DIR}/  (Ctrl+C to stop)")
    start = time.time()
    last_anomaly = 0.0
    total_o = total_a = total_dup = 0
    try:
        while True:
            batch_start = time.time()
            elapsed = batch_start - start

            if elapsed - last_anomaly >= ANOMALY_EVERY_S:
                last_anomaly = elapsed
            in_crash = (elapsed - last_anomaly) < ANOMALY_DURATION_S and elapsed >= ANOMALY_EVERY_S

            orders, ads = [], []

            # fresh orders (some scheduled to be re-emitted later as duplicates)
            for _ in range(ORDERS_PER_SEC * FLUSH_SECONDS):
                o = make_order()
                orders.append(o)
                if random.random() < DUP_RATE:
                    dup_orders.append(dict(o))
            # fresh ads
            for _ in range(ADS_PER_SEC * FLUSH_SECONDS):
                a = make_ad(crashing=False)
                ads.append(a)
                if random.random() < DUP_RATE:
                    dup_ads.append(dict(a))
            # crash spike (extra spend on the crashing channel, no attribution)
            if in_crash:
                for _ in range(8 * FLUSH_SECONDS):
                    ads.append(make_ad(crashing=True))

            # re-emit up to 2 queued duplicates per stream (genuine later dupes)
            dups_now = 0
            for _ in range(min(2, len(dup_orders))):
                orders.append(dup_orders.pop(0)); dups_now += 1
            for _ in range(min(2, len(dup_ads))):
                ads.append(dup_ads.pop(0)); dups_now += 1

            write_jsonl(orders_dir, orders)
            write_jsonl(ads_dir, ads)
            total_o += len(orders); total_a += len(ads); total_dup += dups_now

            tag = f"   <<< {CRASH_CHANNEL} ROAS CRASH" if in_crash else ""
            print(f"[{int(elapsed):>5}s] +{len(orders):>2}o/+{len(ads):>2}a  "
                  f"dups_now={dups_now}{tag}")

            time.sleep(max(0, FLUSH_SECONDS - (time.time() - batch_start)))
    except KeyboardInterrupt:
        print(f"\nStopped. {total_o} orders, {total_a} ads, ~{total_dup} duplicates re-emitted")
        print(f"Output: {os.path.abspath(orders_dir)} / {os.path.abspath(ads_dir)}")


if __name__ == "__main__":
    main()