"""Read-only standard OBD-II PID collector with reconnect and health metadata."""
import logging
import time
import obd
from telemetry.config import OBD_PORT
from telemetry.db import insert_reading, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
COMMANDS = {
    "rpm": obd.commands.RPM,
    "speed_kmh": obd.commands.SPEED,
    "coolant_temp": obd.commands.COOLANT_TEMP,
    "throttle_pct": obd.commands.THROTTLE_POS,
    "engine_load_pct": obd.commands.ENGINE_LOAD,
    "intake_temp": obd.commands.INTAKE_TEMP,
}


def serialise_response(response):
    if response is None or response.is_null():
        return None
    value = response.value
    if hasattr(value, "magnitude"):
        return {"value": float(value.magnitude), "unit": str(value.units)}
    try:
        return {"value": float(value), "unit": ""}
    except (TypeError, ValueError):
        return {"value": str(value), "unit": ""}


def main():
    init_db()
    delay = 2
    while True:
        connection = None
        try:
            logging.info("Connecting to OBD adapter (read-only standard PIDs)...")
            connection = obd.OBD(portstr=OBD_PORT, fast=False, timeout=2.0)
            if not connection.is_connected():
                raise RuntimeError("OBD adapter is not connected")
            supported = {name: cmd for name, cmd in COMMANDS.items() if connection.supports(cmd)}
            unsupported = sorted(set(COMMANDS) - set(supported))
            logging.info("Supported PIDs: %s", ", ".join(supported) or "none")
            if unsupported:
                logging.info("Unavailable PIDs: %s", ", ".join(unsupported))
            delay = 2
            while connection.is_connected():
                started = time.perf_counter()
                pids = {}
                for name, command in supported.items():
                    try:
                        pids[name] = serialise_response(connection.query(command))
                    except Exception as exc:
                        logging.warning("PID %s query failed: %s", name, exc)
                        pids[name] = None
                elapsed = round((time.perf_counter() - started) * 1000, 1)
                payload = {"adapter": "python-obd", "connection": "connected", "pids": pids,
                           "supported_pids": list(supported), "unsupported_pids": unsupported,
                           "poll_duration_ms": elapsed}
                insert_reading("obd", payload)
                time.sleep(max(0.1, 1.0 - elapsed / 1000.0))
            logging.warning("OBD adapter disconnected; reconnecting.")
        except KeyboardInterrupt:
            logging.info("Stopping OBD collector.")
            break
        except Exception as exc:
            logging.error("OBD collector: %s", exc)
            time.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
