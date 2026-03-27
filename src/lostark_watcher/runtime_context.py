import os
import sys
from pathlib import Path

API_URL = "https://developer-lostark.game.onstove.com/auctions/items"
POLL_SECONDS = int(os.environ.get("LOSTARK_WATCH_INTERVAL", "60"))
TOKEN = os.environ.get("LOSTARK_API_TOKEN", "").strip()
DEFAULT_UPDATE_REPO = "Jeong-Jin-Yong/LostARKAccessoriesAlarm"
DEFAULT_UPDATE_REF = "main"
DEFAULT_UPDATE_EXE_PATH = "exe/LostArkWatcher.exe"
GITHUB_API_BASE = "https://api.github.com"
UPDATE_MARKER_FILE = "last_update_blob_sha.txt"


def is_frozen_executable() -> bool:
    return bool(getattr(sys, "frozen", False))


def _project_root() -> Path:
    if is_frozen_executable():
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "exe":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parents[2]


BASE_DIR = _project_root()
DATA_DIR = BASE_DIR / "data"
RESOURCE_DIR = (
    Path(getattr(sys, "_MEIPASS"))
    if is_frozen_executable() and hasattr(sys, "_MEIPASS")
    else BASE_DIR
)
MONITORS_PATH = RESOURCE_DIR / "data" / "monitors.json"
STATE_PATH = DATA_DIR / "state.json"
TEST_DUMMY_ITEMS_PATH = DATA_DIR / "test_dummy_items.json"
LOG_PATH = BASE_DIR / "watch.log"


def runtime_dir() -> Path:
    return BASE_DIR
