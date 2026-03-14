import os
import sys
from pathlib import Path

API_URL = "https://developer-lostark.game.onstove.com/auctions/items"
POLL_SECONDS = int(os.environ.get("LOSTARK_WATCH_INTERVAL", "60"))
TOKEN = os.environ.get("LOSTARK_API_TOKEN", "").strip()
DEFAULT_UPDATE_REPO = "Jeong-Jin-Yong/LostARKAccessoriesAlarm"
DEFAULT_UPDATE_REF = "main"
DEFAULT_UPDATE_EXE_PATH = "dist/LostArkWatcher.exe"
GITHUB_API_BASE = "https://api.github.com"
UPDATE_MARKER_FILE = "last_update_blob_sha.txt"


def is_frozen_executable() -> bool:
    return bool(getattr(sys, "frozen", False))


BASE_DIR = (
    Path(sys.executable).resolve().parent
    if is_frozen_executable()
    else Path(__file__).resolve().parent.parent
)
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "watch.log"


def runtime_dir() -> Path:
    return BASE_DIR
