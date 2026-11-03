"""KM Autos Diagnostics - live vehicle telemetry, trips and engineering analytics."""
import io
import json
import math
import base64
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from telemetry.db import (fetch_rows, init_db, trip_table_available, get_active_trip,
                          start_trip, stop_trip, fetch_trips)

st.set_page_config(page_title="KM Autos | Vehicle Telemetry", page_icon="🏎️", layout="wide", initial_sidebar_state="expanded")
RED, DARK, TEXT, MUTED = "#ff1717", "#050607", "#f4f4f4", "#aeb4ba"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');
:root {{color-scheme:dark}} .stApp {{background-color:{DARK};color:{TEXT};background-image:radial-gradient(circle at 1px 1px,rgba(255,255,255,.055) 1px,transparent 1.8px),linear-gradient(135deg,rgba(255,0,0,.08),transparent 32%),linear-gradient(180deg,#070809,#090b0d 62%,#050607);background-size:7px 7px,auto,auto}}
[data-testid="stHeader"]{{background:rgba(0,0,0,.72)}} [data-testid="stSidebar"]{{background:linear-gradient(180deg,#0b0c0e,#050607);border-right:1px solid rgba(255,23,23,.8)}} [data-testid="stSidebar"] *{{color:{TEXT}}}
.block-container{{max-width:1850px;padding-top:1rem;padding-bottom:2rem}} h1,h2,h3,h4,p,label{{color:{TEXT}}}
.hero{{display:flex;align-items:center;gap:22px;padding:8px 8px 18px;border-bottom:2px solid {RED};margin-bottom:18px}} .hero-logo{{width:245px;max-width:28%;height:auto;object-fit:contain}} .hero-copy{{flex:1;min-width:0}} .hero-title{{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-style:italic;font-size:clamp(2rem,4vw,3.6rem);line-height:1}} .hero-title span{{color:{RED}}}.hero-sub{{margin-top:12px;color:#e6e6e6;font-family:'Barlow Condensed',sans-serif;font-size:1.08rem;letter-spacing:.16em;text-transform:uppercase}}.hero-sub b{{color:{RED};padding:0 9px}}
.section-head{{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1.45rem;border-bottom:1px solid rgba(255,23,23,.75);padding-bottom:8px;margin:8px 0 12px}}
[data-testid="stMetric"]{{background:linear-gradient(145deg,#17191b,#0b0c0d);border:1px solid {RED};border-radius:10px;padding:12px 14px;box-shadow:0 0 12px rgba(255,0,0,.12);min-height:92px}} [data-testid="stMetricLabel"]{{color:#dedede!important}} [data-testid="stMetricValue"]{{color:white!important;font-weight:800}}
.panel{{background:linear-gradient(145deg,rgba(20,22,24,.97),rgba(7,8,9,.97));border:1px solid rgba(255,23,23,.78);border-radius:11px;padding:12px 14px;box-shadow:0 0 15px rgba(255,0,0,.10)}}
div.stButton>button,div.stDownloadButton>button{{background:linear-gradient(90deg,#f20d0d,#a90000);color:white;border:1px solid #ff4b4b;border-radius:8px;font-weight:800}} div.stButton>button:hover,div.stDownloadButton>button:hover{{background:#ff2525;color:white;border-color:white}}
div[data-baseweb="select"]>div{{background:#111315!important;color:white!important;border:1px solid {RED}!important;border-radius:7px!important}} div[data-baseweb="select"] span{{color:white!important}} ul[role="listbox"],ul[role="listbox"] li,div[role="option"]{{background:#111315!important;color:white!important}} div[role="option"]:hover{{background:#5a0909!important;color:white!important}}
.status-pill{{display:inline-block;padding:5px 10px;border-radius:20px;font-weight:700;font-size:.78rem;margin:2px 5px 2px 0;border:1px solid}} .ok{{color:#43e17b;border-color:#168a42;background:rgba(22,138,66,.12)}} .bad{{color:#ff6868;border-color:#a51d1d;background:rgba(165,29,29,.14)}} .warn{{color:#ffd166;border-color:#a77b18;background:rgba(167,123,24,.12)}}
.small-note{{color:{MUTED};font-size:.82rem}} hr{{border-color:rgba(255,23,23,.45)}} footer,#MainMenu{{visibility:hidden}} @media(max-width:700px){{.hero{{gap:10px}}.hero-logo{{width:105px}}.hero-sub{{font-size:.72rem;letter-spacing:.06em}}}}
</style>""", unsafe_allow_html=True)

# Sidebar and refresh control
with st.sidebar:
    st.markdown("## 🔴 TELEMETRY CONTROL")
    st.caption("KM AUTOS · LIVE VEHICLE DATA")
    source_labels = {"all":"All sources", "obd":"OBD-II / ECU", "esp32":"ESP32 / GPS / IMU"}
    source = st.selectbox("Data source", list(source_labels), format_func=lambda x: source_labels[x], key="telemetry_data_source")
    limit = st.slider("Latest records", 100, 20000, 5000, 100)
    auto_refresh = st.toggle("Live auto-refresh", value=True)
    refresh_seconds = st.select_slider("Refresh interval", options=[2, 3, 5, 10], value=3, format_func=lambda x: f"{x} sec")
    if st.button("↻ Refresh now", use_container_width=True): st.rerun()
    st.divider()
    page = st.radio("Navigation", ["Overview", "Live Data", "Trip Recording", "GPS Route", "Analytics & Reports", "Settings"])
    st.divider()
    st.caption("SQL Server · Windows Authentication")
    st.caption("Read-only OBD-II + independent ESP32 sensors")
    st.caption("No ECU writes or control commands")

if auto_refresh:
    st_autorefresh(interval=refresh_seconds * 1000, key="km_autos_live_refresh")

logo_path = Path(__file__).parent / "assets" / "horse_gauge_logo.jpg"
logo_html = ""
if logo_path.exists():
    logo_html = f'<img class="hero-logo" src="data:image/jpeg;base64,{base64.b64encode(logo_path.read_bytes()).decode("ascii")}" alt="KM Autos horse tachometer logo">'
st.markdown(f'''<div class="hero">{logo_html}<div class="hero-copy"><div class="hero-title">Vehicle Telemetry <span>Dashboard</span></div><div class="hero-sub">Diagnose <b>|</b> Monitor <b>|</b> Analyze <b>|</b> Drive Confidently</div></div></div>''', unsafe_allow_html=True)

# Database connection and base data
try:
    init_db()
    trips_ready = trip_table_available()
    rows = fetch_rows(limit=limit, source=source)
    # Connection indicators are independent of the selected display filter.
    latest_obd_health = fetch_rows(limit=1, source="obd")
    latest_esp_health = fetch_rows(limit=1, source="esp32")
    active_trip = get_active_trip() if trips_ready else None
except Exception as exc:
    st.error("Unable to connect to SQL Server. Confirm the .env connection string, SQL Server service and database permissions.")
    st.exception(exc)
    st.stop()

records = []
for row_id, received_at, src, payload_json, cloud_synced in rows:
    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict): continue
    except (json.JSONDecodeError, TypeError):
        continue
    item = {"id":row_id, "received_at":pd.to_datetime(received_at, utc=True, errors="coerce"), "source":src,
            "cloud_synced":bool(cloud_synced), "payload":payload}
    if src == "obd":
        pids = payload.get("pids", {})
        if isinstance(pids, dict):
            for key, value in pids.items(): item[key] = value.get("value") if isinstance(value, dict) else value
        item["poll_duration_ms"] = payload.get("poll_duration_ms")
        item["supported_pid_count"] = len(payload.get("supported_pids", []))
    elif src == "esp32":
        gps = payload.get("gps", {}) if isinstance(payload.get("gps", {}), dict) else {}
        imu = payload.get("imu", {}) if isinstance(payload.get("imu", {}), dict) else {}
        item.update({"gps_speed_kmh":gps.get("speed_kmh"), "latitude":gps.get("lat"), "longitude":gps.get("lon"),
                     "gps_valid":gps.get("valid", False), "satellites":gps.get("satellites"), "course_deg":gps.get("course_deg"),
                     "ax_mps2":imu.get("ax_mps2"), "ay_mps2":imu.get("ay_mps2"), "az_mps2":imu.get("az_mps2"),
                     "gx_rads":imu.get("gx_rads"), "gy_rads":imu.get("gy_rads"), "gz_rads":imu.get("gz_rads"),
                     "imu_ok":payload.get("imu_ok"), "wifi_rssi_dbm":payload.get("wifi_rssi_dbm"), "packet":payload.get("packet")})
    records.append(item)

df = pd.DataFrame(records)
if not df.empty:
    df = df.dropna(subset=["received_at"]).sort_values("received_at").reset_index(drop=True)
else:
    df = pd.DataFrame(columns=["id","received_at","source","cloud_synced","payload"])

obd_df = df[df.source == "obd"].copy() if not df.empty else pd.DataFrame()
esp_df = df[df.source == "esp32"].copy() if not df.empty else pd.DataFrame()

# The ESP32 firmware uses -1 for invalid GPS speed/course; do not display it as a real measurement.
def numeric(data, key):
    if key not in data.columns: return pd.Series(index=data.index, dtype="float64")
    result = pd.to_numeric(data[key], errors="coerce")
    if key in ("gps_speed_kmh", "course_deg"): result = result.where(result >= 0)
    return result

def latest(data, key):
    vals = numeric(data, key).dropna()
    return vals.iloc[-1] if not vals.empty else None

def fmt(value, unit="", digits=1):
    return f"{value:,.{digits}f}{unit}" if value is not None and pd.notna(value) and math.isfinite(float(value)) else "—"

def chart_style(fig, height=280):
    fig.update_layout(template="plotly_dark", height=height, margin=dict(l=10,r=10,t=38,b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(8,10,11,.7)", font=dict(color=TEXT), legend=dict(orientation="h",y=1.12),
                      xaxis=dict(gridcolor="rgba(255,255,255,.10)"), yaxis=dict(gridcolor="rgba(255,255,255,.10)"))
    return fig

def gauge(title, value, low, high, suffix="", threshold=None):
    shown = value if value is not None and pd.notna(value) else 0
    steps = [{"range":[low, high],"color":"#24282c"}]
    fig = go.Figure(go.Indicator(mode="gauge+number", value=shown, title={"text":title,"font":{"size":14}},
        number={"suffix":suffix,"font":{"color":"white","size":25}},
        gauge={"axis":{"range":[low,high],"tickcolor":"#bfc5ca"},"bar":{"color":RED},"bgcolor":"#101214",
               "bordercolor":"#555","steps":steps,"threshold":{"line":{"color":"#ffd166","width":3},"thickness":.8,"value":threshold} if threshold is not None else {}}))
    fig.update_layout(template="plotly_dark",height=205,margin=dict(l=18,r=18,t=40,b=8),paper_bgcolor="rgba(0,0,0,0)",font={"color":TEXT})
    return fig

def freshness(data, seconds):
    if data.empty: return False, None
    ts = data.received_at.dropna()
    if ts.empty: return False, None
    age = max(0.0, (pd.Timestamp.now(tz="UTC") - ts.iloc[-1]).total_seconds())
    return age <= seconds, age

def status_html(label, good, detail=""):
    cls = "ok" if good else "bad"
    state = "ONLINE" if good else "OFFLINE / STALE"
    return f'<span class="status-pill {cls}">{label}: {state}{(" · " + detail) if detail else ""}</span>'

def row_age(latest_row):
    # None means no trustworthy sample; never treat a missing sample as online.
    if not latest_row:
        return None, None, None
    stamp = pd.to_datetime(latest_row[0][1], utc=True, errors="coerce")
    if pd.isna(stamp):
        return None, None, None
    age = max(0.0, (pd.Timestamp.now(tz="UTC") - stamp).total_seconds())
    try:
        payload = json.loads(latest_row[0][3]) if latest_row[0][3] else {}
    except (ValueError, TypeError):
        payload = {}
    return age, latest_row[0], payload

obd_health_age, _, _ = row_age(latest_obd_health)
esp_health_age, _, esp_health_payload = row_age(latest_esp_health)
obd_online = obd_health_age is not None and obd_health_age <= 12
esp_online = esp_health_age is not None and esp_health_age <= 4
obd_age, esp_age = obd_health_age, esp_health_age
latest_health_gps_valid = bool(esp_online and isinstance((esp_health_payload or {}).get("gps", {}), dict) and (esp_health_payload or {}).get("gps", {}).get("valid", False))
now_utc = pd.Timestamp.now(tz="UTC")

# Navigation pages
if page == "Settings":
    st.markdown('<div class="section-head">System & acquisition settings</div>', unsafe_allow_html=True)
    st.write("**Database:** `TaigunTelemetry` · **Table:** `dbo.TelemetryReadings` · **UDP:** port `5005` · **Dashboard:** port `8501`")
    st.write("**OBD collector:** standard SAE J1979 PID requests through python-OBD. **ESP32:** Wi-Fi UDP, GPS and MPU6050.")
    st.write("**Refresh:** " + (f"Every {refresh_seconds} seconds" if auto_refresh else "Manual"))
    st.write("**Trip sessions:** " + ("SQL table available" if trips_ready else "Migration required"))
    st.warning("Read-only telemetry. No CAN frame injection, ECU coding, adaptations, actuator tests or fault clearing are implemented.")
    st.info("Sensor values depend on actual ECU PID support, adapter quality, GPS reception and sensor calibration. A dash means no valid measurement was received.")
    st.stop()

if page == "Trip Recording":
    st.markdown('<div class="section-head">Trip recording & session history</div>', unsafe_allow_html=True)
    if not trips_ready:
        st.error("Trip-session table is not installed yet. Run sql/migrations/001_trip_sessions.sql in SSMS as an administrator, then restart the dashboard.")
        st.stop()
    active_trip = get_active_trip()
    if active_trip:
        st.success(f"Recording active: {active_trip['name']} · Trip #{active_trip['id']} · Started {active_trip['started_at']}")
        if st.button("■ Stop trip recording", type="primary"):
            stop_trip(active_trip["id"]); st.rerun()
    else:
        with st.form("start_trip_form"):
            trip_name = st.text_input("Trip name", value=f"Taigun drive {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            trip_notes = st.text_input("Notes (optional)", placeholder="Route, test purpose, conditions...")
            submitted = st.form_submit_button("● Start trip recording", use_container_width=True)
        if submitted:
            try: start_trip(trip_name, trip_notes); st.rerun()
            except Exception as exc: st.error(str(exc))
    trips = fetch_trips(100)
    st.markdown("**Recent trips**")
    if trips:
        trip_frame = pd.DataFrame(trips).rename(columns={"id":"Trip ID","name":"Trip","started_at":"Started (UTC)","ended_at":"Ended (UTC)","status":"Status","notes":"Notes"})
        st.dataframe(trip_frame, use_container_width=True, hide_index=True)
        completed = [t for t in trips if t["status"] == "completed" and t["ended_at"]]
        if completed:
            chosen = st.selectbox("Review trip", completed, format_func=lambda t:f"#{t['id']} · {t['name']} · {t['started_at']}")
            trip_rows = fetch_rows(limit=20000, source="all", start_utc=pd.to_datetime(chosen["started_at"], utc=True).to_pydatetime(), end_utc=pd.to_datetime(chosen["ended_at"], utc=True).to_pydatetime())
            st.metric("Records captured in trip", f"{len(trip_rows):,}")
            if trip_rows:
                trip_records = []
                for rid, stamp, src, payload_text, synced in trip_rows:
                    try:
                        payload = json.loads(payload_text)
                        gps = payload.get("gps", {}) if src == "esp32" else {}
                        trip_records.append({"id": rid, "received_at": pd.to_datetime(stamp, utc=True, errors="coerce"),
                                             "source": src, "speed": (gps.get("speed_kmh") if gps else None),
                                             "lat": (gps.get("lat") if gps else None), "lon": (gps.get("lon") if gps else None)})
                    except (ValueError, TypeError):
                        continue
                trip_df = pd.DataFrame(trip_records, columns=["id","received_at","source","speed","lat","lon"])
                gps_df = trip_df[(trip_df.source == "esp32")].dropna(subset=["lat", "lon"]).copy()
                if not gps_df.empty:
                    gps_df["lat"] = pd.to_numeric(gps_df.lat, errors="coerce")
                    gps_df["lon"] = pd.to_numeric(gps_df.lon, errors="coerce")
                    gps_df = gps_df[gps_df.lat.between(-90,90) & gps_df.lon.between(-180,180)].dropna(subset=["lat","lon"])
                distance_km = 0.0
                if len(gps_df) > 1:
                    import numpy as np
                    lat1 = np.radians(gps_df.lat.to_numpy()[:-1]); lat2 = np.radians(gps_df.lat.to_numpy()[1:])
                    dlat = lat2 - lat1; dlon = np.radians(gps_df.lon.to_numpy()[1:] - gps_df.lon.to_numpy()[:-1])
                    hav = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
                    distance_km = float(np.sum(6371.0 * 2 * np.arcsin(np.sqrt(np.clip(hav,0,1)))))
                speeds = pd.to_numeric(gps_df.speed, errors="coerce") if not gps_df.empty else pd.Series(dtype=float)
                speeds = speeds[speeds >= 0]
                duration_min = max(0.0, (pd.to_datetime(chosen["ended_at"], utc=True) - pd.to_datetime(chosen["started_at"], utc=True)).total_seconds()/60)
                tm1, tm2, tm3, tm4 = st.columns(4)
                tm1.metric("GPS distance (estimate)", f"{distance_km:.2f} km")
                tm2.metric("GPS max speed", fmt(speeds.max() if not speeds.empty else None, " km/h"))
                tm3.metric("GPS average speed", fmt(speeds.mean() if not speeds.empty else None, " km/h"))
                tm4.metric("Trip duration", f"{duration_min:.1f} min")
                if len(gps_df) > 1:
                    st.map(gps_df.rename(columns={"lat":"latitude","lon":"longitude"}), latitude="latitude", longitude="longitude", use_container_width=True)
                st.caption("GPS distance is a point-to-point estimate; it can be inaccurate with poor fixes, gaps or GPS drift.")
                st.download_button("Download trip data CSV", pd.DataFrame(trip_rows, columns=["id","received_at","source","payload_json","cloud_synced"]).to_csv(index=False).encode(),
                                   f"km_autos_trip_{chosen['id']}.csv", "text/csv")
    else: st.info("No trip sessions have been recorded yet.")
    st.caption("Trip readings are associated by their SQL Server UTC timestamps between Start and Stop; raw telemetry remains unchanged.")
    st.stop()

if page == "GPS Route":
    st.markdown('<div class="section-head">GPS route & movement</div>', unsafe_allow_html=True)
    if esp_df.empty: st.info("Waiting for ESP32 GPS packets.")
    else:
        lat, lon = numeric(esp_df,"latitude"), numeric(esp_df,"longitude")
        route = pd.DataFrame({"lat":lat,"lon":lon,"received_at":esp_df.received_at}).dropna()
        route = route[route.lat.between(-90,90) & route.lon.between(-180,180)]
        if route.empty: st.info("No valid GPS fix yet. Check antenna placement and outdoor sky visibility.")
        else:
            st.map(route, latitude="lat", longitude="lon", use_container_width=True)
            st.metric("Valid route points", f"{len(route):,}")
            st.dataframe(route.tail(100), use_container_width=True, hide_index=True)
    st.stop()

if page == "Analytics & Reports":
    st.markdown('<div class="section-head">Telemetry analytics & engineering report</div>', unsafe_allow_html=True)
    if df.empty: st.info("No records available to analyze yet."); st.stop()
    st.write("The following values are calculated from the records currently loaded from SQL Server.")
    report_rows = ["KM AUTOS DIAGNOSTICS — VEHICLE TELEMETRY REPORT", f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
                   f"Records loaded: {len(df)}", f"OBD records: {len(obd_df)}", f"ESP32 records: {len(esp_df)}"]
    for key, label, unit in [("rpm","Latest engine RPM",""),("speed_kmh","Latest OBD speed"," km/h"),("coolant_temp","Latest coolant temperature"," °C"),
                             ("throttle_pct","Latest throttle position"," %"),("engine_load_pct","Latest engine load"," %"),("gps_speed_kmh","Latest GPS speed"," km/h")]:
        val = latest(obd_df if key not in ("gps_speed_kmh",) else esp_df, key)
        report_rows.append(f"{label}: {fmt(val,unit)}")
    report_rows += ["", "Interpretation note: these are observed telemetry values, not a certified vehicle inspection or a diagnosis."]
    csv_data = df.drop(columns=["payload"],errors="ignore").to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Download telemetry CSV", csv_data, "km_autos_telemetry.csv", "text/csv")
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm)
        styles = getSampleStyleSheet(); styles.add(ParagraphStyle(name="KMTitle", parent=styles["Title"], textColor=colors.HexColor("#d71920")))
        story = [Paragraph("KM AUTOS DIAGNOSTICS", styles["KMTitle"]), Paragraph("Vehicle Telemetry Report", styles["Heading2"]), Spacer(1,8)]
        table_data = [["Parameter","Latest observed value"], ["Engine RPM",fmt(latest(obd_df,"rpm"))], ["OBD speed",fmt(latest(obd_df,"speed_kmh")," km/h")],
                      ["Coolant temperature",fmt(latest(obd_df,"coolant_temp")," °C")], ["Throttle position",fmt(latest(obd_df,"throttle_pct")," %")],
                      ["Engine load",fmt(latest(obd_df,"engine_load_pct")," %")], ["GPS speed",fmt(latest(esp_df,"gps_speed_kmh")," km/h")],
                      ["GPS satellites",fmt(latest(esp_df,"satellites"),"",0)], ["Records loaded",str(len(df))], ["OBD records",str(len(obd_df))], ["ESP32 records",str(len(esp_df))]]
        table = Table(table_data, colWidths=[65*mm,95*mm]); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#202326")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.grey),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f1f1f1")]),("PADDING",(0,0),(-1,-1),7)]))
        story += [table, Spacer(1,12), Paragraph("Data note: Values are from actual stored telemetry. Missing or unsupported signals are omitted or shown as unavailable. This report is not a certified inspection, fault diagnosis, or safety certification.", styles["BodyText"]), Spacer(1,8), Paragraph(datetime.now(timezone.utc).isoformat(), styles["Italic"])]
        doc.build(story); st.download_button("⬇ Download diagnostic summary PDF", buffer.getvalue(), "KM_Autos_Telemetry_Report.pdf", "application/pdf")
    except ImportError:
        st.warning("PDF library is not installed. Run `py -m pip install reportlab` to enable PDF reports.")
    st.code("\n".join(report_rows), language="text")
    st.stop()

# Overview and Live Data pages: live connection health and key metrics
st.markdown('<div class="section-head">System health & data acquisition</div>', unsafe_allow_html=True)
health_cols = st.columns(4)
health_cols[0].markdown(status_html("SQL Server", True, "query succeeded"), unsafe_allow_html=True)
health_cols[1].markdown(status_html("OBD-II", obd_online, f"{obd_age:.1f}s ago" if obd_age is not None else "no samples"), unsafe_allow_html=True)
health_cols[2].markdown(status_html("ESP32 UDP", esp_online, f"{esp_age:.1f}s ago" if esp_age is not None else "no packets"), unsafe_allow_html=True)
health_cols[3].markdown(status_html("GPS Fix", latest_health_gps_valid, "valid fix" if latest_health_gps_valid else "no current fix"), unsafe_allow_html=True)

if df.empty:
    st.info("SQL Server is connected, but no telemetry records have arrived yet. Start the UDP receiver and/or OBD collector.")
    st.stop()

st.markdown('<div class="section-head">Telemetry overview</div>', unsafe_allow_html=True)
k1,k2,k3,k4,k5 = st.columns(5)
k1.metric("Records loaded", f"{len(df):,}")
k2.metric("OBD records", f"{len(obd_df):,}")
k3.metric("ESP32 records", f"{len(esp_df):,}")
k4.metric("Cloud synced", f"{int(df.cloud_synced.sum()):,}")
k5.metric("Active trip", f"#{active_trip['id']}" if active_trip else "None")

if page == "Live Data":
    st.markdown('<div class="section-head">Live sensor values</div>', unsafe_allow_html=True)
    if obd_df.empty: st.info("No OBD-II data yet.")
    else:
        st.markdown("**ECU / OBD-II signals**")
        vals = st.columns(4)
        vals[0].metric("Engine RPM",fmt(latest(obd_df,"rpm"),"",0)); vals[1].metric("Vehicle speed",fmt(latest(obd_df,"speed_kmh")," km/h"))
        vals[2].metric("Coolant",fmt(latest(obd_df,"coolant_temp")," °C")); vals[3].metric("Throttle",fmt(latest(obd_df,"throttle_pct")," %"))
        gauges = st.columns(4)
        for col, key, title, low, high, unit in [(gauges[0],"rpm","Engine RPM",0,7000,""),(gauges[1],"speed_kmh","Vehicle speed",0,220," km/h"),
            (gauges[2],"coolant_temp","Coolant temperature",-20,130," °C"),(gauges[3],"throttle_pct","Throttle position",0,100," %")]:
            col.plotly_chart(gauge(title,latest(obd_df,key),low,high,unit,None),use_container_width=True,config={"displayModeBar":False})
        st.caption("Gauge arcs are display scales only, not Volkswagen OEM warning thresholds or calibrated safety limits.")
    if not esp_df.empty:
        st.markdown("**ESP32 independent sensors**")
        e1,e2,e3,e4 = st.columns(4)
        e1.metric("GPS speed",fmt(latest(esp_df,"gps_speed_kmh")," km/h")); e2.metric("Satellites",fmt(latest(esp_df,"satellites"),"",0))
        e3.metric("IMU status", "Ready" if bool(esp_df.iloc[-1].get("imu_ok",False)) else "Check sensor")
        e4.metric("Wi-Fi RSSI",fmt(latest(esp_df,"wifi_rssi_dbm")," dBm",0))
    st.markdown("**Recent raw readings**")
    display = df.drop(columns=["payload"],errors="ignore").tail(300)
    st.dataframe(display,use_container_width=True,hide_index=True,height=420)
    st.stop()

# Overview visualizations
left,right = st.columns([1.05,1.2],gap="medium")
with left:
    st.markdown('<div class="section-head">▣ Engine ECU telemetry</div>',unsafe_allow_html=True)
    if obd_df.empty: st.info("Waiting for OBD-II collector data.")
    else:
        m=st.columns(4); m[0].metric("RPM",fmt(latest(obd_df,"rpm"),"",0)); m[1].metric("Speed",fmt(latest(obd_df,"speed_kmh")," km/h")); m[2].metric("Coolant",fmt(latest(obd_df,"coolant_temp")," °C")); m[3].metric("Throttle",fmt(latest(obd_df,"throttle_pct")," %"))
        keys=[k for k in ["rpm","speed_kmh","coolant_temp","throttle_pct","engine_load_pct","intake_temp"] if k in obd_df and numeric(obd_df,k).notna().any()]
        selected=st.multiselect("Plot ECU channels",keys,default=keys[:3],key="overview_obd_signals")
        if selected:
            plot=obd_df[["received_at"]+selected].melt(id_vars="received_at",var_name="signal",value_name="value").dropna()
            if not plot.empty: st.plotly_chart(chart_style(px.line(plot,x="received_at",y="value",color="signal",title="OBD signals over time",color_discrete_sequence=[RED,"#00c8ff","#ffd400","#a78bfa"]),290),use_container_width=True)
with right:
    st.markdown('<div class="section-head">⌖ GPS & IMU telemetry</div>',unsafe_allow_html=True)
    if esp_df.empty: st.info("Waiting for ESP32 packets.")
    else:
        a,b,c=st.columns(3); a.metric("GPS speed",fmt(latest(esp_df,"gps_speed_kmh")," km/h")); c.metric("Satellites",fmt(latest(esp_df,"satellites"),"",0))
        valid=numeric(esp_df,"latitude").notna() & numeric(esp_df,"longitude").notna()
        c2=int(valid.sum()); b.metric("Valid GPS points",f"{c2:,}")
        mapdata=pd.DataFrame({"lat":numeric(esp_df,"latitude"),"lon":numeric(esp_df,"longitude")}).dropna()
        mapdata=mapdata[mapdata.lat.between(-90,90)&mapdata.lon.between(-180,180)]
        mc,ic=st.columns([1,1.1])
        with mc:
            st.markdown("**GPS route**")
            if not mapdata.empty: st.map(mapdata,latitude="lat",longitude="lon",use_container_width=True)
            else: st.caption("No valid GPS coordinates yet.")
        with ic:
            st.markdown("**IMU acceleration (m/s²)**")
            axes=[k for k in ["ax_mps2","ay_mps2","az_mps2"] if k in esp_df and numeric(esp_df,k).notna().any()]
            if axes:
                imu=esp_df[["received_at"]+axes].melt(id_vars="received_at",var_name="axis",value_name="mps2").dropna()
                st.plotly_chart(chart_style(px.line(imu,x="received_at",y="mps2",color="axis",color_discrete_sequence=[RED,"#00c8ff","#ffd400"]),245),use_container_width=True)
            else: st.caption("Waiting for valid IMU samples.")

st.markdown('<div class="section-head">Recent records</div>',unsafe_allow_html=True)
recent=df[["received_at","source","cloud_synced"]].tail(80).copy()
recent["Cloud status"]=recent.cloud_synced.map({True:"Synced",False:"Pending"})
recent=recent.rename(columns={"received_at":"Received at (UTC)","source":"Source"}).drop(columns=["cloud_synced"])
st.dataframe(recent,use_container_width=True,hide_index=True,height=230)
st.download_button("⬇ Download current data as CSV",df.drop(columns=["payload"],errors="ignore").to_csv(index=False).encode("utf-8"),"km_autos_telemetry.csv","text/csv")
st.markdown("<hr><div style='text-align:center;color:#aeb4ba;font-size:.85rem;letter-spacing:.12em;'>MODERN VEHICLES &nbsp; <b style='color:#ff1717'>SMARTER SOLUTIONS</b> &nbsp; · &nbsp; DRIVEN BY PRECISION</div>",unsafe_allow_html=True)
st.caption("KM Autos Diagnostics · Actual SQL Server telemetry only. Unsupported or unavailable values are shown as —. Not a certified vehicle instrument.")
