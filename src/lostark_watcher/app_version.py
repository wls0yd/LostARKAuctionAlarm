import os

from .runtime_context import RESOURCE_DIR

APP_VERSION_FILE = RESOURCE_DIR / "data" / "app_version.txt"
DEFAULT_APP_VERSION = "dev"


def get_app_version() -> str:
    env_version = os.environ.get("LOSTARK_WATCHER_VERSION", "").strip()
    if env_version:
        return env_version

    try:
        file_version = APP_VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return DEFAULT_APP_VERSION

    if file_version:
        return file_version
    return DEFAULT_APP_VERSION
