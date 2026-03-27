import json

from .runtime_context import DATA_DIR, MONITORS_PATH


def _load_default_monitors() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.loads(MONITORS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Monitor data must be a list")

    normalized: list[dict] = []
    for raw_monitor in payload:
        if not isinstance(raw_monitor, dict):
            continue

        monitor = dict(raw_monitor)
        raw_fixed_options = monitor.get("fixed_options", [])
        if isinstance(raw_fixed_options, list):
            monitor["fixed_options"] = {str(name) for name in raw_fixed_options}
        else:
            monitor["fixed_options"] = set()

        normalized.append(monitor)

    return normalized


DEFAULT_MONITORS = _load_default_monitors()


def default_monitor_values() -> dict[str, dict[str, int]]:
    return {
        monitor["key"]: {
            field["id"]: field["default"] for field in monitor.get("custom_values", [])
        }
        for monitor in DEFAULT_MONITORS
    }


def default_monitor_enabled() -> dict[str, bool]:
    return {monitor["key"]: True for monitor in DEFAULT_MONITORS}


def merge_monitor_enabled(saved_enabled: dict) -> dict[str, bool]:
    merged_enabled = default_monitor_enabled()
    for monitor in DEFAULT_MONITORS:
        monitor_key = monitor["key"]
        raw_value = saved_enabled.get(monitor_key)
        if isinstance(raw_value, bool):
            merged_enabled[monitor_key] = raw_value
    return merged_enabled


def merge_monitor_values(saved_values: dict) -> dict[str, dict[str, int]]:
    merged_values = default_monitor_values()
    for monitor in DEFAULT_MONITORS:
        monitor_key = monitor["key"]
        monitor_saved_values = saved_values.get(monitor_key, {})
        if not isinstance(monitor_saved_values, dict):
            continue
        for field in monitor.get("custom_values", []):
            raw_value = monitor_saved_values.get(field["id"])
            if isinstance(raw_value, int) and raw_value >= 0:
                merged_values[monitor_key][field["id"]] = raw_value
    return merged_values


def build_monitor_query(monitor: dict, monitor_values: dict[str, int] | None = None) -> dict:
    query = dict(monitor["query"])
    resolved_values = monitor_values if isinstance(monitor_values, dict) else {}
    etc_options = []
    for field in monitor.get("custom_values", []):
        value = resolved_values.get(field["id"], field["default"])
        option = dict(field["query_option"])
        match_type = option.pop("match", "exact")
        if match_type == "minimum":
            option["MinValue"] = value
            option["MaxValue"] = 99999
        else:
            option["MinValue"] = value
            option["MaxValue"] = value
        etc_options.append(option)
    query["EtcOptions"] = etc_options
    return query


def build_monitor_runtime_config(
    monitor_values_by_key: dict[str, dict[str, int]] | None = None,
) -> list[dict]:
    resolved_values = merge_monitor_values(
        monitor_values_by_key if isinstance(monitor_values_by_key, dict) else {}
    )
    runtime_monitors = []
    for monitor in DEFAULT_MONITORS:
        runtime_monitor = dict(monitor)
        runtime_monitor["query"] = build_monitor_query(
            monitor,
            resolved_values.get(monitor["key"], {}),
        )
        runtime_monitors.append(runtime_monitor)
    return runtime_monitors
