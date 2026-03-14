import json
import os
import threading

from .monitors import merge_monitor_enabled, merge_monitor_values
from .runtime_context import POLL_SECONDS, STATE_PATH

STATE_LOCK = threading.RLock()


def load_state() -> dict:
    with STATE_LOCK:
        if not STATE_PATH.exists():
            return {"seen_by_monitor": {}}
        try:
            raw_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"seen_by_monitor": {}}

    if "seen_by_monitor" in raw_state:
        return raw_state

    legacy_seen = raw_state.get("seen", []) if isinstance(raw_state, dict) else []
    return {"seen_by_monitor": {"necklace_damage": legacy_seen}}


def save_state(signatures_by_monitor: dict[str, set[str]]) -> None:
    with STATE_LOCK:
        state = load_state()
        app_settings = state.get("app_settings") if isinstance(state, dict) else None
        payload = {
            "seen_by_monitor": {
                key: sorted(values) for key, values in signatures_by_monitor.items()
            }
        }
        if isinstance(app_settings, dict):
            payload["app_settings"] = app_settings

        write_state(payload)


def load_app_settings() -> dict:
    state = load_state()
    settings = state.get("app_settings", {}) if isinstance(state, dict) else {}
    if not isinstance(settings, dict):
        settings = {}

    saved_interval = settings.get("poll_seconds", POLL_SECONDS)
    if not isinstance(saved_interval, int) or saved_interval <= 0:
        saved_interval = POLL_SECONDS

    saved_monitor_values = settings.get("monitor_values", {})
    if not isinstance(saved_monitor_values, dict):
        saved_monitor_values = {}

    saved_monitor_enabled = settings.get("monitor_enabled", {})
    if not isinstance(saved_monitor_enabled, dict):
        saved_monitor_enabled = {}

    return {
        "token": str(settings.get("token", "")).strip(),
        "poll_seconds": saved_interval,
        "installed_exe_blob_sha": str(settings.get("installed_exe_blob_sha", "")).strip(),
        "monitor_values": merge_monitor_values(saved_monitor_values),
        "monitor_enabled": merge_monitor_enabled(saved_monitor_enabled),
    }


def save_app_settings(
    token: str,
    poll_seconds: int,
    monitor_values: dict[str, dict[str, int]] | None = None,
    monitor_enabled: dict[str, bool] | None = None,
) -> None:
    with STATE_LOCK:
        state = load_state()
        existing_settings = state.get("app_settings") if isinstance(state, dict) else None
        if not isinstance(existing_settings, dict):
            existing_settings = {}

        resolved_monitor_values = merge_monitor_values(
            monitor_values
            if monitor_values is not None
            else existing_settings.get("monitor_values", {})
        )
        resolved_monitor_enabled = merge_monitor_enabled(
            monitor_enabled
            if monitor_enabled is not None
            else existing_settings.get("monitor_enabled", {})
        )

        existing_settings.update(
            {
                "token": token.strip(),
                "poll_seconds": poll_seconds,
                "monitor_values": resolved_monitor_values,
                "monitor_enabled": resolved_monitor_enabled,
            }
        )
        state["app_settings"] = existing_settings
        state.setdefault("seen_by_monitor", {})
        write_state(state)


def save_installed_exe_blob_sha(blob_sha: str) -> None:
    with STATE_LOCK:
        state = load_state()
        app_settings = state.get("app_settings") if isinstance(state, dict) else None
        if not isinstance(app_settings, dict):
            app_settings = {}
        app_settings["installed_exe_blob_sha"] = blob_sha.strip()
        state["app_settings"] = app_settings
        state.setdefault("seen_by_monitor", {})
        write_state(state)


def write_state(state: dict) -> None:
    temp_path = STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, STATE_PATH)
