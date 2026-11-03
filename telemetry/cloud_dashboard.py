"""Private Streamlit Community Cloud dashboard backed by Supabase Auth + RLS.

This is separate from dashboard.py: the local dashboard keeps using Windows
Authentication and SQL Server. The cloud app never connects to the laptop.
"""
from datetime import datetime, timezone
import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


st.set_page_config(page_title="KM Autos | Secure Cloud Telemetry", page_icon="🏎️", layout="wide")


def setting(name):
    try:
        value = st.secrets.get(name)
        if value:
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, "").strip()


SUPABASE_URL = setting("SUPABASE_URL").rstrip("/")
SUPABASE_ANON_KEY = setting("SUPABASE_ANON_KEY")


def api_headers(access_token):
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def sign_in(email, password):
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def refresh_session(refresh_token):
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/token",
        params={"grant_type": "refresh_token"},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"refresh_token": refresh_token},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def ensure_session():
    session = st.session_state.get("cloud_auth")
    if not session:
        return None
    if int(session.get("expires_at", 0)) <= int(datetime.now(timezone.utc).timestamp()) + 60:
        try:
            session = refresh_session(session["refresh_token"])
            session["expires_at"] = int(datetime.now(timezone.utc).timestamp()) + int(session.get("expires_in", 3600))
            st.session_state["cloud_auth"] = session
        except (requests.RequestException, KeyError, ValueError):
            st.session_state.pop("cloud_auth", None)
            return None
    return session


def load_events(access_token, limit):
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/telemetry_events",
        headers=api_headers(access_token),
        params={
            "select": "id,created_at,source,payload",
            "order": "created_at.desc",
            "limit": str(limit),
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


st.markdown("""
<style>
.stApp {background:linear-gradient(145deg,#090b0d,#15191d);color:#f4f4f4}
[data-testid="stMetric"] {background:#15191d;border:1px solid #ed252d;border-radius:10px;padding:12px}
h1,h2,h3,p,label {color:#f4f4f4}
</style>
""", unsafe_allow_html=True)

st.title("🏎️ KM Autos Diagnostics")
st.caption("Private cloud telemetry · Supabase Auth · Row Level Security")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Cloud app configuration is incomplete. Add SUPABASE_URL and SUPABASE_ANON_KEY in Streamlit Cloud → App settings → Secrets.")
    st.stop()

session = ensure_session()
if not session:
    st.subheader("Sign in")
    st.info("Use the email and password for the account created in your Supabase project's Authentication → Users.")
    with st.form("cloud_login"):
        email = st.text_input("Email", autocomplete="email")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted:
        try:
            auth = sign_in(email.strip(), password)
            auth["expires_at"] = int(datetime.now(timezone.utc).timestamp()) + int(auth.get("expires_in", 3600))
            st.session_state["cloud_auth"] = auth
            st.rerun()
        except requests.HTTPError:
            st.error("Sign-in failed. Check the email/password and that the Supabase Auth user is enabled.")
        except requests.RequestException:
            st.error("Could not reach the cloud authentication service. Check the Supabase URL and network.")
    st.stop()

with st.sidebar:
    st.success("Authenticated cloud session")
    st.caption(session.get("user", {}).get("email", "Signed-in user"))
    limit = st.slider("Latest cloud records", 100, 5000, 1000, 100)
    if st.button("Sign out", use_container_width=True):
        st.session_state.pop("cloud_auth", None)
        st.rerun()

try:
    events = load_events(session["access_token"], limit)
except requests.HTTPError:
    st.error("Cloud data request was rejected. Verify the telemetry_events SELECT policy and owner_id mapping.")
    st.stop()
except requests.RequestException:
    st.error("Could not load cloud telemetry. Check Supabase availability and network.")
    st.stop()

records = []
for event in events:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    row = {"created_at": event.get("created_at"), "source": event.get("source"), "cloud_id": event.get("id")}
    if event.get("source") == "obd":
        pids = payload.get("pids") if isinstance(payload.get("pids"), dict) else {}
        for key, value in pids.items():
            row[key] = value.get("value") if isinstance(value, dict) else value
    elif event.get("source") == "esp32":
        gps = payload.get("gps") if isinstance(payload.get("gps"), dict) else {}
        imu = payload.get("imu") if isinstance(payload.get("imu"), dict) else {}
        row.update({
            "gps_speed_kmh": gps.get("speed_kmh"),
            "latitude": gps.get("lat"),
            "longitude": gps.get("lon"),
            "gps_valid": gps.get("valid", False),
            "ax_mps2": imu.get("ax_mps2"),
            "ay_mps2": imu.get("ay_mps2"),
            "az_mps2": imu.get("az_mps2"),
        })
    records.append(row)

df = pd.DataFrame(records)
if not df.empty:
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["created_at"]).sort_values("created_at")

total = len(df)
obd_count = int((df["source"] == "obd").sum()) if total else 0
esp_count = int((df["source"] == "esp32").sum()) if total else 0
latest_time = df["created_at"].max() if total else None
m1, m2, m3, m4 = st.columns(4)
m1.metric("Cloud records loaded", f"{total:,}")
m2.metric("OBD-II records", f"{obd_count:,}")
m3.metric("ESP32 records", f"{esp_count:,}")
m4.metric("Latest sync time", latest_time.strftime("%H:%M:%S UTC") if latest_time is not None else "—")

if df.empty:
    st.info("No cloud records yet. Start the local cloud sync worker after completing the Supabase setup.")
else:
    obd = df[df["source"] == "obd"].copy()
    esp = df[df["source"] == "esp32"].copy()
    if not obd.empty and "rpm" in obd.columns:
        obd["rpm"] = pd.to_numeric(obd["rpm"], errors="coerce")
        st.subheader("Engine RPM history")
        chart = obd.dropna(subset=["rpm"])
        if not chart.empty:
            st.line_chart(chart.set_index("created_at")["rpm"], height=240)
    if not esp.empty and "gps_speed_kmh" in esp.columns:
        esp["gps_speed_kmh"] = pd.to_numeric(esp["gps_speed_kmh"], errors="coerce")
        st.subheader("GPS speed history")
        chart = esp.dropna(subset=["gps_speed_kmh"])
        if not chart.empty:
            st.line_chart(chart.set_index("created_at")["gps_speed_kmh"], height=240)
    if not esp.empty and {"latitude", "longitude"}.issubset(esp.columns):
        esp["latitude"] = pd.to_numeric(esp["latitude"], errors="coerce")
        esp["longitude"] = pd.to_numeric(esp["longitude"], errors="coerce")
        route = esp.dropna(subset=["latitude", "longitude"])
        route = route[(route["latitude"].between(-90, 90)) & (route["longitude"].between(-180, 180))]
        if not route.empty:
            st.subheader("GPS route points")
            st.map(route.rename(columns={"latitude": "lat", "longitude": "lon"}), size=8)
    st.subheader("Recent cloud telemetry")
    st.dataframe(df.drop(columns=["cloud_id"], errors="ignore").sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)

st.caption("Cloud data is read-only here. ECU commands, vehicle control and OBD writes are not available.")
