import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

UDP_HOST = os.getenv("UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("UDP_PORT", "5005"))
OBD_PORT = os.getenv("OBD_PORT", "").strip() or None

# Example is in .env.example. Keep credentials out of source control.
SQLSERVER_CONNECTION_STRING = os.getenv("SQLSERVER_CONNECTION_STRING", "").strip()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
CLOUD_BATCH_SIZE = int(os.getenv("CLOUD_BATCH_SIZE", "100"))
CLOUD_POLL_SECONDS = float(os.getenv("CLOUD_POLL_SECONDS", "5"))
