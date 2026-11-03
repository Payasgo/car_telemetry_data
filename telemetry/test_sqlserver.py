import sys
from .db import connect, init_db, insert_reading, fetch_rows

def main():
    print("1) Connecting to SQL Server using Windows Authentication...")
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                @@SERVERNAME AS server_name,
                DB_NAME() AS database_name,
                SUSER_SNAME() AS login_name,
                ORIGINAL_LOGIN() AS original_login
        """)
        row = cur.fetchone()
        print(f"   Server:   {row.server_name}")
        print(f"   Database: {row.database_name}")
        print(f"   Login:    {row.login_name}")
        print(f"   Original: {row.original_login}")
    finally:
        conn.close()

    print("2) Checking telemetry table...")
    init_db()
    print("   dbo.TelemetryReadings exists.")

    print("3) Inserting a harmless test row...")
    test_id = insert_reading(
        "test",
        {"test": True, "message": "Taigun telemetry SQL Server connection test"}
    )
    print(f"   Inserted row ID: {test_id}")

    print("4) Reading it back...")
    rows = fetch_rows(limit=5, source="test")
    match = [r for r in rows if r[0] == test_id]
    if not match:
        raise RuntimeError("Test row was inserted but not returned by SELECT.")
    print("   Read-back successful.")
    print("\nSUCCESS: Windows Authentication, SELECT and INSERT are working.")
    print("Remove test rows later with the cleanup SQL in README.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        raise
