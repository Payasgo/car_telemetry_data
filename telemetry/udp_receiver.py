"""Validated ESP32 UDP telemetry receiver; stores packets in SQL Server."""
import json
import socket
import logging
from datetime import datetime, timezone
from telemetry.config import UDP_HOST, UDP_PORT
from telemetry.db import insert_reading, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    init_db()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_HOST, UDP_PORT))
    logging.info("Listening for ESP32 UDP telemetry on %s:%s", UDP_HOST, UDP_PORT)
    accepted = rejected = 0
    while True:
        data, addr = sock.recvfrom(8192)
        try:
            payload = json.loads(data.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("schema") != "taigun.telemetry.v1":
                rejected += 1
                logging.warning("Unexpected packet schema from %s (rejected=%s)", addr, rejected)
                continue
            payload["receiver"] = {"sender_ip": addr[0], "received_utc": datetime.now(timezone.utc).isoformat()}
            insert_reading("esp32", payload)
            accepted += 1
            if accepted % 100 == 0:
                logging.info("Accepted %s packets; rejected %s", accepted, rejected)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            rejected += 1
            logging.warning("Invalid packet from %s: %s", addr, exc)


if __name__ == "__main__":
    main()
