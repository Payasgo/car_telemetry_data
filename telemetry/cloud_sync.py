import time
import json
import logging
import requests
from .config import SUPABASE_URL, SUPABASE_KEY, CLOUD_BATCH_SIZE, CLOUD_POLL_SECONDS
from .db import pending_cloud_rows, mark_cloud_synced, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def main():
    init_db()
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_KEY in .env to enable cloud sync.")
    endpoint = f"{SUPABASE_URL}/rest/v1/telemetry_events"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    logging.info("Cloud sync worker started; local SQLite remains authoritative.")
    while True:
        rows = pending_cloud_rows(CLOUD_BATCH_SIZE)
        if not rows:
            time.sleep(CLOUD_POLL_SECONDS)
            continue
        payload = [
            {"created_at": created_at, "source": source, "payload": json.loads(payload_json)}
            for _id, created_at, source, payload_json in rows
        ]
        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            mark_cloud_synced([row[0] for row in rows])
            logging.info("Synced %d records.", len(rows))
        except requests.RequestException as exc:
            logging.error("Cloud sync failed; records remain local and will retry: %s", exc)
            time.sleep(max(CLOUD_POLL_SECONDS, 10))

if __name__ == "__main__":
    main()
