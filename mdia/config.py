"""Central configuration (environment-driven, safe local defaults)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MDIA_DATA_DIR", ROOT / "data"))
FONT_DIRS = [ROOT / "fonts", Path("/usr/share/fonts"), Path("C:/Windows/Fonts")]
HOST = os.environ.get("MDIA_HOST", "127.0.0.1")      # local only by default
PORT = int(os.environ.get("MDIA_PORT", "8000"))
API_TOKEN = os.environ.get("MDIA_API_TOKEN", "")     # optional bearer token
MAX_UPLOAD_MB = int(os.environ.get("MDIA_MAX_UPLOAD_MB", "100"))
OCR_LANG = os.environ.get("MDIA_OCR_LANG", "ara+eng")
OCR_DPI = int(os.environ.get("MDIA_OCR_DPI", "300"))
PREVIEW_SCALE = float(os.environ.get("MDIA_PREVIEW_SCALE", "2.0"))
WORKERS = int(os.environ.get("MDIA_WORKERS", "2"))
LOW_CONF = 0.70          # below this a field needs human review
MIN_TEXT_CHARS = 25      # fewer text-layer chars than this -> page is treated as scanned
SCHEMA_VERSION = "1.0"
