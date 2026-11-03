"""SQL Server persistence for KM Autos telemetry and trip sessions."""
import json
from datetime import datetime, timezone
import pyodbc
from telemetry.config import SQLSERVER_CONNECTION_STRING


def utc_now():
    return datetime.now(timezone.utc)


def connect():
    if not SQLSERVER_CONNECTION_STRING:
        raise RuntimeError("Set SQLSERVER_CONNECTION_STRING in .env. See README.md.")
    return pyodbc.connect(SQLSERVER_CONNECTION_STRING, timeout=5)


def init_db():
    """Verify base schema. Optional trip table is installed by the supplied migration."""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT CASE WHEN OBJECT_ID(N'dbo.TelemetryReadings', N'U') IS NULL THEN 0 ELSE 1 END")
        if cur.fetchone()[0] != 1:
            raise RuntimeError("dbo.TelemetryReadings is missing. Run sql/setup_sqlserver.sql as an administrator.")
    finally:
        conn.close()


def insert_reading(source, payload, received_at=None):
    received_at = received_at or utc_now()
    payload_json = json.dumps(payload, separators=(",", ":"), default=str, allow_nan=False)
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO dbo.TelemetryReadings (ReceivedAtUtc, Source, PayloadJson)
            OUTPUT INSERTED.Id VALUES (?, ?, ?)
        """, received_at, source, payload_json)
        row = cur.fetchone()
        conn.commit()
        return int(row[0])
    finally:
        conn.close()


def fetch_rows(limit=5000, source=None, start_utc=None, end_utc=None):
    conn = connect()
    try:
        cur = conn.cursor()
        clauses, params = [], []
        if source and source != "all":
            clauses.append("Source=?")
            params.append(source)
        if start_utc is not None:
            clauses.append("ReceivedAtUtc>=?")
            params.append(start_utc)
        if end_utc is not None:
            clauses.append("ReceivedAtUtc<=?")
            params.append(end_utc)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        cur.execute(f"""
            SELECT TOP (?) Id, CONVERT(varchar(40), ReceivedAtUtc, 127) AS ReceivedAtUtc,
                   Source, PayloadJson, CloudSynced
            FROM dbo.TelemetryReadings{where} ORDER BY Id DESC
        """, int(limit), *params)
        rows = cur.fetchall()
        return [(int(r[0]), str(r[1]), r[2], r[3], bool(r[4])) for r in reversed(rows)]
    finally:
        conn.close()


def trip_table_available():
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT CASE WHEN OBJECT_ID(N'dbo.TelemetryTrips', N'U') IS NULL THEN 0 ELSE 1 END")
        return cur.fetchone()[0] == 1
    finally:
        conn.close()


def get_active_trip():
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT TOP 1 TripId, TripName,
                   CONVERT(varchar(40), StartedAtUtc, 127), Notes
            FROM dbo.TelemetryTrips WHERE Status='active' ORDER BY TripId DESC
        """)
        row = cur.fetchone()
        return None if row is None else {"id": int(row[0]), "name": row[1], "started_at": str(row[2]), "notes": row[3] or ""}
    finally:
        conn.close()


def start_trip(name, notes=""):
    name = ((name or "").strip() or "Vehicle trip")[:100]
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.TelemetryTrips WHERE Status='active'")
        if cur.fetchone()[0]:
            raise RuntimeError("A trip is already active. Stop it before starting another.")
        cur.execute("""
            INSERT INTO dbo.TelemetryTrips (TripName, Notes, StartedAtUtc, Status)
            OUTPUT INSERTED.TripId VALUES (?, ?, ?, 'active')
        """, name, (notes or "")[:500], utc_now())
        trip_id = int(cur.fetchone()[0])
        conn.commit()
        return trip_id
    finally:
        conn.close()


def stop_trip(trip_id):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE dbo.TelemetryTrips SET EndedAtUtc=?, Status='completed'
            WHERE TripId=? AND Status='active'
        """, utc_now(), int(trip_id))
        changed = cur.rowcount
        conn.commit()
        if not changed:
            raise RuntimeError("That trip is no longer active.")
    finally:
        conn.close()


def fetch_trips(limit=50):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT TOP (?) TripId, TripName,
              CONVERT(varchar(40), StartedAtUtc, 127),
              CONVERT(varchar(40), EndedAtUtc, 127), Status, Notes
            FROM dbo.TelemetryTrips ORDER BY TripId DESC
        """, int(limit))
        return [{"id": int(r[0]), "name": r[1], "started_at": str(r[2]),
                 "ended_at": str(r[3]) if r[3] else None, "status": r[4], "notes": r[5] or ""}
                for r in cur.fetchall()]
    finally:
        conn.close()


def pending_cloud_rows(limit=100):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT TOP (?) Id, CONVERT(varchar(40), ReceivedAtUtc, 127), Source, PayloadJson
            FROM dbo.TelemetryReadings WHERE CloudSynced=0 ORDER BY Id
        """, int(limit))
        return [(int(r[0]), str(r[1]), r[2], r[3]) for r in cur.fetchall()]
    finally:
        conn.close()


def mark_cloud_synced(ids):
    if not ids:
        return
    conn = connect()
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany("UPDATE dbo.TelemetryReadings SET CloudSynced=1 WHERE Id=?", [(int(i),) for i in ids])
        conn.commit()
    finally:
        conn.close()
