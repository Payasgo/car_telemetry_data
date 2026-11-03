# Taigun Telemetry V1.0

Read-only educational telemetry logger for a 2025 Volkswagen Taigun 1.0 TSI manual.

## Architecture
- ESP32 + GPS + MPU6050 send independent sensor data over Wi-Fi UDP to the laptop.
- A separate OBD-II adapter connects to the vehicle diagnostic port. `python-OBD` reads supported standard PIDs.
- Laptop stores both streams in SQL Server.
- Streamlit serves the dashboard to laptop and mobile devices on the same Wi-Fi network.
- Optional background worker syncs local records to Supabase. Microsoft SQL Server remains the local source of truth.

This is a prototype, not an automotive-certified device or factory instrumentation.

## Safety
1. Keep OBD use read-only. Do not send ECU commands, coding, adaptations, actuator tests, or write operations.
2. Do not splice factory wiring or connect ESP32 directly to vehicle CAN-H/CAN-L.
3. Never probe airbags, ABS/ESC, brake, steering, engine-control, or high-voltage circuits.
4. Initially power ESP32 from a USB power bank. Do not hardwire to vehicle 12 V.
5. Secure devices/cables away from pedals, steering, airbags, visibility areas, hot/moving parts.
6. Configure/test while parked. A passenger should operate/observe during road tests; driver must not use laptop/phone.
7. Performance testing only on a closed course.
8. OBD-II compliance does not guarantee every PID is exposed.
9. GPS/IMU values are estimates. IMU requires calibration and axis alignment; it is not brake pressure or tyre grip.
10. Ask a Volkswagen service partner before permanent installation. Remove OBD adapter when parked until sleep/battery-drain behaviour is verified.

## Hardware
- ESP32 DevKit board (3.3 V logic)
- MPU6050 breakout with 3.3 V-compatible I2C
- GPS module with UART output (e.g. NEO-M8N breakout)
- USB power bank and cable
- Jumper wires, secure enclosure, mounting bracket
- Reputable OBD-II adapter supporting ISO 15765-4 CAN and your laptop/OS

Do not assume a GPS breakout accepts 5 V. Check its exact input voltage and UART logic. ESP32 GPIO is 3.3 V logic.

## Wiring: independent sensor module
Power from ESP32 3V3 only if the breakout specifications permit it. Grounds must be common.

| ESP32 | MPU6050 | GPS |
|---|---|---|
| 3V3 | VCC (if 3.3 V supported) | VCC (only if board supports 3.3 V input) |
| GND | GND | GND |
| GPIO 21 | SDA | — |
| GPIO 22 | SCL | — |
| GPIO 16 (UART2 RX) | — | GPS TX |
| GPIO 17 (UART2 TX) | — | GPS RX (optional, voltage compatible only) |

GPS TX -> ESP32 RX is the essential data path. GPS RX is optional.
Never feed a 5 V UART signal into ESP32 GPIO.
MPU6050 I2C address is commonly 0x68 (sometimes 0x69); firmware uses default 0x68.
Mount IMU rigidly and align axes: X forward, Y left, Z up. Firmware reports raw-axis acceleration (m/s²) and gyro (rad/s), not calibrated vehicle-frame values.

## OBD-II
Use a reputable adapter with documented ISO 15765-4 CAN support. Plug into the factory diagnostic socket; do not open adapter or tap vehicle wiring.
Read-only standard PIDs: RPM, vehicle speed, coolant temperature, throttle position, calculated engine load, intake air temperature. Unsupported PIDs are omitted or null. Generic adapters may be incompatible or slow.

## Install
Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`. Set Wi-Fi settings in firmware and `LAPTOP_IP` in firmware to the laptop's LAN IPv4 address.

## Flash ESP32
1. Install Arduino IDE and ESP32 board support.
2. Install Arduino libraries: Adafruit MPU6050, Adafruit Unified Sensor, TinyGPSPlus, ArduinoJson.
3. Open `firmware/taigun_telemetry_v1.ino`.
4. Set Wi-Fi SSID/password and laptop IP.
5. Flash while board is USB-connected to your computer.
6. Power from USB power bank for vehicle testing.

ESP32 sends JSON UDP packets to laptop port 5005. Both devices must share a Wi-Fi network. A phone hotspot may work if client-to-client traffic is allowed; some guest networks isolate clients.

## Run laptop system
Use separate terminals in the project directory.

Terminal 1:
```bash
python -m telemetry.udp_receiver
```
Terminal 2:
```bash
python -m telemetry.obd_collector
```
Terminal 3:
```bash
streamlit run telemetry/dashboard.py --server.address 0.0.0.0 --server.port 8501
```

Laptop: `http://localhost:8501`
Phone on same Wi-Fi: `http://LAPTOP_IP:8501` (replace with actual laptop LAN IP).
Allow Python/Streamlit through laptop firewall on a private network only. Do not port-forward to public internet.

## Secure cloud dashboard (optional)

The Windows laptop remains the **local diagnostics host and source of truth**:
- `dashboard.py` uses Windows Authentication to read SQL Server locally.
- OBD-II polling and the ESP32 UDP receiver continue to run only on the laptop/LAN.
- `cloud_sync.py` sends a one-way copy of local telemetry to Supabase over HTTPS.
- `cloud_dashboard.py` is a separate Streamlit Community Cloud app. It does not connect to your laptop, SQL Server, OBD adapter, or ESP32.

### 1. Create the Supabase project and private user
1. Create a project at https://supabase.com/.
2. In **Authentication → Users**, create your own user with email/password. Confirm the account if email confirmation is enabled.
3. Copy the user's UUID (not the email) from the user details. This is the value for `SUPABASE_OWNER_ID`.
4. In **Project Settings → API**, copy the Project URL, anon/publishable key, and service_role/secret key.

### 2. Create the private table and row-level security
1. Open **SQL Editor** in Supabase.
2. Run the complete script in `sql/supabase_secure_cloud.sql`.
3. The script enables RLS and permits authenticated users to read only rows whose `owner_id` equals their Supabase Auth user ID. It does not create public/anonymous data access or browser insert permissions.
4. The local worker uses the service_role key to insert/upsert records. That key bypasses RLS and is highly privileged.

### 3. Configure local Windows cloud sync
Add these values to the laptop's private `.env` file (never commit it):
```dotenv
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_SECRET
SUPABASE_OWNER_ID=YOUR_SUPABASE_AUTH_USER_UUID
CLOUD_BATCH_SIZE=100
CLOUD_POLL_SECONDS=5
```
Keep the existing SQL Server connection string. Install dependencies and start the worker in a separate Command Prompt from the project folder:
```bat
py -m pip install -r requirements.txt
py -m telemetry.cloud_sync
```
The worker retries failed batches and marks local SQL Server rows synced only after Supabase confirms success. Each row has a stable `origin_id`, so retries are idempotent. SQL Server remains authoritative.

### 4. Deploy the cloud dashboard
1. Push/merge this code to GitHub `master`.
2. In https://share.streamlit.io/, create an app from `Payasgo/car_telemetry_data`.
3. Set the branch to `master` and main file to `telemetry/cloud_dashboard.py`.
4. In **App settings → Secrets**, add only:
```toml
SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
SUPABASE_ANON_KEY = "YOUR_ANON_OR_PUBLISHABLE_KEY"
```
5. Deploy. Sign in with the Supabase Auth email/password created above.

**Never add `SUPABASE_SERVICE_ROLE_KEY` to Streamlit Cloud, GitHub Actions, Git, browser code, or ESP32 firmware.** The cloud dashboard uses the anon key plus a signed-in Supabase Auth session; RLS limits reads to that user's rows. Do not create an unrestricted SELECT policy for anon/public.

### 5. What runs where

| Component | Where it runs | Data access |
|---|---|---|
| Local dashboard | Windows laptop | SQL Server via Windows Authentication |
| OBD collector | Windows laptop | Read-only standard OBD-II PIDs |
| ESP32 receiver | Windows laptop | UDP packets from ESP32 on private LAN |
| Cloud sync worker | Windows laptop | SQL Server read + Supabase HTTPS insert/upsert |
| Cloud dashboard | Streamlit Community Cloud | Supabase Auth + owner-scoped read-only query |

Cloud telemetry is a delayed copy, not live remote vehicle control. The cloud app cannot wake the laptop, reach a local UDP port, or read the OBD adapter directly. Do not port-forward SQL Server or the telemetry receiver to the public internet.


## Data model
SQL Server database: `TaigunTelemetry`; table: `dbo.TelemetryReadings`.
- `id`
- `received_at_utc`
- `source` (`esp32` or `obd`)
- `payload_json`
- `cloud_synced`

ESP32 payload includes device uptime, GPS fix/time, GPS speed, position, accelerometer and gyroscope. Laptop receive time is stored separately. OBD payload contains supported PID values and units.

## Troubleshooting
- No ESP32 packets: check Wi-Fi credentials, laptop IP, UDP port 5005, firewall, client isolation.
- No GPS fix indoors: test outdoors with clear sky view; allow time to acquire.
- IMU missing: check 3.3 V, SDA/SCL, ground and I2C address.
- OBD connection failure: check adapter compatibility, Bluetooth pairing/serial port, ignition state and OS permissions.
- Missing OBD values: normal if ECU/adapter does not expose PID.
- Phone cannot open dashboard: same LAN, laptop IP, private-network firewall.
- Cloud failure: check URL/key, table, RLS policy and worker output.

## V1 limitations
No ECU control/writes. No direct brake pressure, steering angle, wheel speed, tyre temperature or fuel-flow measurement. Generic OBD polling is slow and not synchronized to ECU sample time. GPS/IMU are not safety-critical measurements. Cloud sync requires your own Supabase project and secure policy configuration.


## SQL Server setup (V1.0 database backend)

1. Install Microsoft SQL Server (Developer or Express edition is suitable for a personal development project), or use an existing SQL Server instance.
2. Install **Microsoft ODBC Driver 18 for SQL Server** on the computer running the Python collectors.
3. Create the database in SSMS:

```sql
CREATE DATABASE TaigunTelemetry;
GO
```

4. Copy `.env.example` to `.env` and edit `SQLSERVER_CONNECTION_STRING`.
   - Windows integrated authentication example is provided.
   - For SQL authentication, use a dedicated least-privilege login; do not use `sa`.
   - For a remote server, use its hostname/IP and configure firewall/network access only on a trusted private network.
5. Install Python requirements (`pyodbc` is included).
6. Run `sql/setup_sqlserver.sql` in SSMS as an administrator to create the database, telemetry table, indexes and application permissions. The Python app verifies the schema but does not create or alter it at runtime.

The table stores UTC receive time, source, JSON payload and cloud-sync status. Raw JSON preserves sensor fields as the firmware evolves. Do not expose SQL Server directly to the public internet.


## Windows 10 + SQL Server Standard/Enterprise + Windows Authentication

### A. Find the SQL Server instance
In SSMS, connect to the same SQL Server you intend to use. Run:

```sql
SELECT @@SERVERNAME AS ServerName, SERVERPROPERTY('InstanceName') AS InstanceName,
       SERVERPROPERTY('ProductVersion') AS ProductVersion;
```

Use `localhost` only if SQL Server is installed on this same laptop and is the default instance.
For a named instance, use `COMPUTERNAME\INSTANCE` (for example `OFFICEPC\SQLSERVER`).
For a remote instance, use its actual server hostname/instance or a configured TCP port.

### B. Install the SQL Server ODBC driver
Install Microsoft ODBC Driver 18 for SQL Server matching your Windows architecture.
Then in Command Prompt:

```bat
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

If `pyodbc` reports no driver named `ODBC Driver 18 for SQL Server`, the ODBC driver is not installed or its name differs. Check installed driver names in ODBC Data Sources (64-bit) > Drivers.

### C. Provision database and least-privilege permissions
1. Edit `sql/setup_sqlserver.sql`: replace both occurrences of `YOURDOMAIN\YourWindowsUser` with the Windows login or AD group that runs Python. A local account is usually `COMPUTERNAME\WindowsUser`; an AD account is `DOMAIN\username`.
2. Run the script in SSMS as a SQL Server administrator.
3. It creates `TaigunTelemetry`, the telemetry table and indexes, a Windows login/database user, and grants only SELECT, INSERT and UPDATE on the telemetry table.
4. Do not grant `sysadmin`, `db_owner`, or `db_ddladmin` to the telemetry application identity.

If the Python process runs under a different Windows account (for example a scheduled task/service identity), grant permissions to that identity instead. Windows Authentication uses the identity of the process running Python, not the SSMS user.

### D. Configure `.env`
Copy `.env.example` to `.env`. Example for a local default SQL Server instance:

```ini
SQLSERVER_CONNECTION_STRING=DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=TaigunTelemetry;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes
```

For a named instance replace `localhost` with `COMPUTERNAME\\INSTANCE`.
For a remote SQL Server, use the server DNS name and a valid TLS certificate. Prefer `TrustServerCertificate=no` when the SQL Server certificate is trusted and correctly matches its DNS name. `TrustServerCertificate=yes` encrypts but skips certificate identity validation; use it only on a trusted network when needed.
Do not add `UID` or `PWD` when using Windows Authentication.

### E. Test before collecting car data
From the project root, activate your virtual environment and run:

```bat
py -m telemetry.test_sqlserver
```

It prints the connected server, database and Windows login, verifies the table, inserts one test row and reads it back. Success requires SELECT and INSERT permissions. The optional cloud worker also requires UPDATE permission on `CloudSynced`.

To remove test rows after testing, run in SSMS:

```sql
USE TaigunTelemetry;
DELETE FROM dbo.TelemetryReadings
WHERE Source = N'test'
  AND PayloadJson LIKE N'%Taigun telemetry SQL Server connection test%';
```

### F. Start the application
Open separate Command Prompt windows from the project root:

```bat
py -m telemetry.udp_receiver
```

```bat
py -m telemetry.obd_collector
```

```bat
py -m streamlit run telemetry/dashboard.py --server.address 0.0.0.0 --server.port 8501
```

Open `http://localhost:8501` on the laptop. For phone access on the same private Wi-Fi, open `http://LAPTOP_LAN_IP:8501`. Allow the Streamlit/Python process through Windows Defender Firewall on Private networks only. Do not expose SQL Server port 1433 or Streamlit to the public internet.

### G. Troubleshooting
- `Login failed for user`: the Windows identity running Python is not mapped/granted in the target database; compare `whoami` in the same Command Prompt with the login configured in the SQL script.
- `Cannot open database`: check database name and user mapping.
- `Named Pipes Provider` / server not found: verify server\instance, SQL Server service, SQL Browser if using a named instance, and TCP/IP configuration.
- `ODBC Driver 18 not found`: install the Microsoft ODBC Driver 18 matching Python's architecture.
- `certificate verify failed`: use the SQL Server's trusted certificate; only temporarily use `TrustServerCertificate=yes` on a trusted private network.
- `permission denied`: re-run the DBA setup script with the correct Windows identity; do not solve by granting db_owner.

### Security and operations note
The application verifies the table but does not create or alter schema at runtime. Schema changes are DBA-managed. The app identity has only table-level SELECT/INSERT/UPDATE. SQL Server should be reachable only on a trusted private network. Back up the database and define retention before long-term continuous logging.

---

# KM Autos Telemetry Upgrade

This version keeps the existing SQL Server database, Windows Authentication connection string, ESP32 UDP input, horse/tachometer logo and red/black theme. It adds live refresh, acquisition-health indicators, live ECU gauges, expanded ESP32 health telemetry, reconnecting OBD collection, trip sessions, GPS trip summaries, CSV export and a PDF telemetry summary.

## Upgrade an existing installation

1. Back up the `TaigunTelemetry` database and copy your existing project folder.
2. Extract this project over the existing project, but **keep your current `.env` file**. The ZIP intentionally does not contain `.env` or credentials.
3. From the project folder run:

   ```bat
   py -m pip install -r requirements.txt
   ```

4. In SSMS, connect to the same SQL Server and run `sql/migrations/001_trip_sessions.sql` once. This creates only `dbo.TelemetryTrips`; it does not alter or delete `dbo.TelemetryReadings`. The migration grants SELECT/INSERT/UPDATE to `ECM\ECM_Repair` if that database user exists. If your Python process uses a different Windows identity, change the grant target in the migration before running it. If the app identity is already mapped as `dbo`, it already has the required access.
5. Re-flash the ESP32 only if you want the additional Wi-Fi RSSI and GPS HDOP/age fields. Existing firmware packets remain compatible with this dashboard.
6. Run the three processes in separate Command Prompt windows:

   ```bat
   py -m telemetry.udp_receiver
   ```

   ```bat
   py -m telemetry.obd_collector
   ```

   ```bat
   py -m streamlit run telemetry/dashboard.py --server.address 0.0.0.0 --server.port 8501
   ```

7. Open `http://localhost:8501`. The dashboard refreshes automatically every 3 seconds by default; this can be changed or disabled in the sidebar.

## New telemetry features

- **Live overview:** SQL, OBD-II, ESP32 UDP and GPS-fix freshness indicators. OBD stale threshold is 12 seconds; ESP32 stale threshold is 4 seconds. These are software communication-health thresholds, not vehicle fault thresholds.
- **Live gauges:** RPM, vehicle speed, coolant temperature and throttle. Gauge arcs are visual display scales only, not Volkswagen OEM warning limits.
- **Sensor quality:** ESP32 IMU-ready state, Wi-Fi RSSI (with upgraded firmware), GPS satellites, valid GPS coordinates and packet receive time.
- **Trip sessions:** Start/stop a named trip, persist the session in SQL Server, review completed sessions, estimate GPS distance and speed statistics, inspect the route, and export trip records.
- **Analytics and reports:** Export selected telemetry to CSV and generate a PDF summary from the actual stored readings.
- **Collector resilience:** OBD collector retries connection with backoff and logs supported and unsupported standard PIDs. It does not issue ECU write/control commands.

## Data and measurement limitations

Trip association is timestamp-window based; raw telemetry rows are not modified with a trip ID. GPS distance is a point-to-point estimate and may drift or undercount/overcount with poor reception, sparse samples or multipath. The MPU6050 readings are raw sensor axes; mount alignment, bias calibration and vibration filtering are not yet applied. Wi-Fi/SQL freshness indicates data transport, not vehicle health. Generic OBD values depend on what the Taigun ECU and adapter expose. No unsupported parameter is fabricated; unavailable values display as `—`.

The dashboard is a telemetry and analysis tool, not a certified scan tool, vehicle speedometer, odometer, safety monitor or substitute for workshop diagnostics. Continue to use the read-only OBD setup and independent ESP32 sensors only. Keep the laptop/phone out of the driver's hands while moving.
