"""One-way, idempotent SQL Server -> Supabase sync worker.

Run only on the trusted Windows laptop. The Supabase service-role key is a
server-side secret and must never be used by the ESP32 or cloud dashboard.
"""
import json
import logging
import time
import uuid

import requests

from telemetry.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_OWNER_ID,
    CLOUD_BATCH_SIZE,
    CLOUD_POLL_SECONDS,
)
from telemetry.db import pending_cloud_rows, mark_cloud_synced, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def build_cloud_rows(rows, owner_id):
    """Convert local rows to stable, owner-scoped Supabase records."""
    owner = str(uuid.UUID(owner_id))
    return [
        {
            "origin_id": f"local-{int(local_id)}",
            "owner_id": owner,
            "created_at": created_at,
            "source": source,
            "payload": json.loads(payload_json),
        }
        for local_id, created_at, source, payload_json in rows
    ]


def main():
    init_db()
    if not all((SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_OWNER_ID)):
        raise SystemExit(
            "Cloud sync is disabled. Set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY "
            "and SUPABASE_OWNER_ID in the local .env file."
        )
    try:
        uuid.UUID(SUPABASE_OWNER_ID)
    except ValueError as exc:
        raise SystemExit("SUPABASE_OWNER_ID must be the UUID of your Supabase Auth user.") from exc

    endpoint = f"{SUPABASE_URL}/rest/v1/telemetry_events?on_conflict=origin_id"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    logging.info("Secure cloud sync started. Local SQL Server remains authoritative.")
    while True:
        rows = pending_cloud_rows(CLOUD_BATCH_SIZE)
        if not rows:
            time.sleep(CLOUD_POLL_SECONDS)
            continue
        try:
            payload = build_cloud_rows(rows, SUPABASE_OWNER_ID)
            response = requests.post(endpoint, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            mark_cloud_synced([row[0] for row in rows])
            logging.info("Synced %d telemetry records.", len(rows))
        except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as exc:
            logging.error("Cloud sync failed; local rows remain pending and will retry: %s", exc)
            time.sleep(max(CLOUD_POLL_SECONDS, 10))


if __name__ == "__main__":
    main()
