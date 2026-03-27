import json
import os
import threading

from .monitors import (
    clamp_monitor_slots,
    default_custom_monitors,
    merge_custom_monitors,
)
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

    if isinstance(raw_state, dict) and "seen_by_monitor" in raw_state:
        seen_payload = raw_state.get("seen_by_monitor")
        if not isinstance(seen_payload, dict):
            return {"seen_by_monitor": {}}

        normalized_seen = dict(seen_payload)
        legacy_seen_key_map = {
            "necklace_damage": "slot_1",
            "necklace_brand_gauge": "slot_2",
            "earring_attack": "slot_3",
            "ring_crit": "slot_4",
            "ring_party_buff": "slot_5",
        }
        for legacy_key, slot_key in legacy_seen_key_map.items():
            if legacy_key in normalized_seen and slot_key not in normalized_seen:
                normalized_seen[slot_key] = normalized_seen[legacy_key]

        normalized_state = dict(raw_state)
        normalized_state["seen_by_monitor"] = normalized_seen
        return normalized_state

    legacy_seen = raw_state.get("seen", []) if isinstance(raw_state, dict) else []
    return {"seen_by_monitor": {"slot_1": legacy_seen}}


def save_state(
    signatures_by_monitor: dict[str, set[str]],
    alert_on_next_baseline: bool | None = None,
) -> None:
    with STATE_LOCK:
        state = load_state()
        app_settings = state.get("app_settings") if isinstance(state, dict) else None
        existing_alert_flag = bool(
            state.get("alert_on_next_baseline", False)
        ) if isinstance(state, dict) else False
        payload: dict[str, object] = {
            "seen_by_monitor": {
                key: sorted(values) for key, values in signatures_by_monitor.items()
            }
        }
        if isinstance(app_settings, dict):
            payload["app_settings"] = app_settings

        resolved_alert_flag = (
            existing_alert_flag
            if alert_on_next_baseline is None
            else bool(alert_on_next_baseline)
        )
        if resolved_alert_flag:
            payload["alert_on_next_baseline"] = True

        write_state(payload)


def clear_seen_by_monitor() -> None:
    with STATE_LOCK:
        state = load_state()
        app_settings = state.get("app_settings") if isinstance(state, dict) else None
        payload: dict[str, object] = {"seen_by_monitor": {}}
        if isinstance(app_settings, dict):
            payload["app_settings"] = app_settings
        payload["alert_on_next_baseline"] = True

        write_state(payload)


def load_app_settings() -> dict:
    state = load_state()
    settings = state.get("app_settings", {}) if isinstance(state, dict) else {}
    if not isinstance(settings, dict):
        settings = {}

    saved_interval = settings.get("poll_seconds", POLL_SECONDS)
    if not isinstance(saved_interval, int) or saved_interval <= 0:
        saved_interval = POLL_SECONDS

    saved_monitor_slot_count = clamp_monitor_slots(settings.get("monitor_slot_count"))
    saved_custom_monitors = settings.get("custom_monitors")
    if not isinstance(saved_custom_monitors, list):
        saved_custom_monitors = _legacy_custom_monitors_from_settings(settings)

    merged_custom_monitors = merge_custom_monitors(
        saved_custom_monitors,
        saved_monitor_slot_count,
    )

    return {
        "token": str(settings.get("token", "")).strip(),
        "poll_seconds": saved_interval,
        "installed_exe_blob_sha": str(settings.get("installed_exe_blob_sha", "")).strip(),
        "monitor_slot_count": saved_monitor_slot_count,
        "custom_monitors": merged_custom_monitors,
    }


def save_app_settings(
    token: str,
    poll_seconds: int,
    custom_monitors: list[dict] | None = None,
    monitor_slot_count: int | None = None,
) -> None:
    with STATE_LOCK:
        state = load_state()
        existing_settings = state.get("app_settings") if isinstance(state, dict) else None
        if not isinstance(existing_settings, dict):
            existing_settings = {}

        resolved_slot_count = clamp_monitor_slots(
            monitor_slot_count
            if monitor_slot_count is not None
            else existing_settings.get("monitor_slot_count")
        )
        resolved_custom_monitors = merge_custom_monitors(
            custom_monitors
            if custom_monitors is not None
            else existing_settings.get("custom_monitors"),
            resolved_slot_count,
        )

        existing_settings.update(
            {
                "token": token.strip(),
                "poll_seconds": poll_seconds,
                "monitor_slot_count": resolved_slot_count,
                "custom_monitors": resolved_custom_monitors,
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
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, STATE_PATH)


def _legacy_custom_monitors_from_settings(settings: dict) -> list[dict]:
    if not isinstance(settings, dict):
        return default_custom_monitors()

    legacy_values = settings.get("monitor_values", {})
    if not isinstance(legacy_values, dict):
        legacy_values = {}
    legacy_enabled = settings.get("monitor_enabled", {})
    if not isinstance(legacy_enabled, dict):
        legacy_enabled = {}

    legacy_key_map = {
        "necklace_damage": 0,
        "necklace_brand_gauge": 1,
        "earring_attack": 2,
        "ring_crit": 3,
        "ring_party_buff": 4,
    }

    monitors = default_custom_monitors(5)
    for legacy_key, monitor_index in legacy_key_map.items():
        if monitor_index >= len(monitors):
            continue
        if isinstance(legacy_enabled.get(legacy_key), bool):
            monitors[monitor_index]["enabled"] = legacy_enabled[legacy_key]

        monitor_values = legacy_values.get(legacy_key, {})
        if not isinstance(monitor_values, dict):
            continue

        option_1 = monitor_values.get("option_1")
        option_2 = monitor_values.get("option_2")
        quality_min = monitor_values.get("quality_min")
        if isinstance(option_1, int):
            monitors[monitor_index]["value_1"] = option_1
        if isinstance(option_2, int):
            monitors[monitor_index]["value_2"] = option_2
        if isinstance(quality_min, int):
            monitors[monitor_index]["quality_value"] = quality_min

    return monitors
