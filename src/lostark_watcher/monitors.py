from .metadata.accessory_metadata import (
    DEFAULT_MONITOR_SLOTS,
    MAX_MONITOR_SLOTS,
    OPTION_DEFINITIONS,
    PART_DEFINITIONS,
    PART_OPTION_KEYS,
    QUALITY_VALUE_OPTIONS,
)


def clamp_monitor_slots(raw_slots: int | None) -> int:
    if not isinstance(raw_slots, int):
        return DEFAULT_MONITOR_SLOTS
    if raw_slots < 1:
        return 1
    if raw_slots > MAX_MONITOR_SLOTS:
        return MAX_MONITOR_SLOTS
    return raw_slots


def _default_option_key(part_key: str, skip_keys: set[str] | None = None) -> str:
    excluded = skip_keys if isinstance(skip_keys, set) else set()
    options = PART_OPTION_KEYS.get(part_key, [])
    for option_key in options:
        if option_key not in excluded:
            return option_key
    raise ValueError(f"No option definition found for part: {part_key}")


def _default_option_value(part_key: str, option_key: str) -> int:
    if option_key not in PART_OPTION_KEYS[part_key]:
        raise ValueError(f"Invalid option '{option_key}' for part '{part_key}'")
    values = OPTION_DEFINITIONS[option_key]["values"]
    return int(values[0])


def _default_quality_value(part_key: str) -> int:
    _ = part_key
    return int(QUALITY_VALUE_OPTIONS["none"]["value"])


def default_custom_monitor(slot_index: int) -> dict:
    part_key = "necklace"
    option_1 = _default_option_key(part_key)
    option_2 = _default_option_key(part_key, skip_keys={option_1})
    option_3 = _default_option_key(part_key, skip_keys={option_1, option_2})
    return {
        "id": f"slot_{slot_index + 1}",
        "enabled": True,
        "part": part_key,
        "option_1": option_1,
        "option_2": option_2,
        "option_3": option_3,
        "value_1": _default_option_value(part_key, option_1),
        "value_2": _default_option_value(part_key, option_2),
        "value_3": _default_option_value(part_key, option_3),
        "quality_value": _default_quality_value(part_key),
    }


def default_custom_monitors(slot_count: int | None = None) -> list[dict]:
    resolved_count = clamp_monitor_slots(slot_count)
    return [default_custom_monitor(index) for index in range(resolved_count)]


def _sanitize_part_key(part_key: str) -> str:
    if part_key in PART_DEFINITIONS:
        return part_key
    return "necklace"


def _sanitize_option_key(part_key: str, option_key: str, skip_keys: set[str] | None = None) -> str:
    excluded = skip_keys if isinstance(skip_keys, set) else set()
    if option_key == "none":
        return "none"
    if option_key in PART_OPTION_KEYS[part_key] and option_key not in excluded:
        return option_key
    return _default_option_key(part_key, skip_keys=excluded)


def _sanitize_option_value(part_key: str, option_key: str, raw_value: object) -> int:
    if option_key == "none":
        return 0
    if option_key not in PART_OPTION_KEYS[part_key]:
        return _default_option_value(part_key, _default_option_key(part_key))
    values = OPTION_DEFINITIONS[option_key]["values"]
    if isinstance(raw_value, int) and raw_value in values:
        return raw_value
    return int(values[0])


def _sanitize_quality_value(part_key: str, raw_value: object) -> int:
    _ = part_key
    if isinstance(raw_value, int) and raw_value >= 0:
        return int(raw_value)
    return _default_quality_value(part_key)


def normalize_custom_monitor(raw_monitor: dict, fallback_id: str) -> dict:
    monitor = raw_monitor if isinstance(raw_monitor, dict) else {}
    monitor_id = str(monitor.get("id", fallback_id)).strip() or fallback_id
    part_key = _sanitize_part_key(str(monitor.get("part", "necklace")))
    option_1 = _sanitize_option_key(
        part_key,
        str(monitor.get("option_1", monitor.get("special_option_1", ""))),
    )
    option_2 = _sanitize_option_key(
        part_key,
        str(monitor.get("option_2", monitor.get("special_option_2", ""))),
        skip_keys={option_1},
    )
    option_3 = _sanitize_option_key(
        part_key,
        str(monitor.get("option_3", "")),
        skip_keys={option_1, option_2},
    )

    raw_quality_value = monitor.get("quality_value")
    if raw_quality_value is None:
        common_option = str(monitor.get("common_option", "quality_min"))
        if common_option == "none":
            raw_quality_value = 0
        else:
            raw_quality_value = monitor.get("common_value")

    return {
        "id": monitor_id,
        "enabled": bool(monitor.get("enabled", True)),
        "part": part_key,
        "option_1": option_1,
        "option_2": option_2,
        "option_3": option_3,
        "value_1": _sanitize_option_value(
            part_key,
            option_1,
            monitor.get("value_1", monitor.get("special_value_1")),
        ),
        "value_2": _sanitize_option_value(
            part_key,
            option_2,
            monitor.get("value_2", monitor.get("special_value_2")),
        ),
        "value_3": _sanitize_option_value(
            part_key,
            option_3,
            monitor.get("value_3"),
        ),
        "quality_value": _sanitize_quality_value(part_key, raw_quality_value),
    }


def merge_custom_monitors(saved_monitors: list | None, slot_count: int | None = None) -> list[dict]:
    resolved_count = clamp_monitor_slots(slot_count)
    defaults = default_custom_monitors(resolved_count)
    if not isinstance(saved_monitors, list):
        return defaults

    merged: list[dict] = []
    for index in range(resolved_count):
        fallback_id = defaults[index]["id"]
        raw_monitor = saved_monitors[index] if index < len(saved_monitors) else defaults[index]
        normalized = normalize_custom_monitor(raw_monitor, fallback_id)
        normalized["id"] = fallback_id
        merged.append(normalized)
    return merged


def _option_value_label(option_key: str, value: int) -> str:
    option_payload = OPTION_DEFINITIONS[option_key]
    values = option_payload["values"]
    value_labels = option_payload["value_labels"]
    for index, candidate in enumerate(values):
        if int(candidate) == value:
            return str(value_labels[index])
    return str(value)


def _monitor_option_label(option_key: str, value: int) -> str:
    option_label = str(OPTION_DEFINITIONS[option_key]["label"])
    if option_key == "none":
        return option_label
    return f"{option_label}({_option_value_label(option_key, value)})"


def monitor_label(custom_monitor: dict) -> str:
    part_key = custom_monitor["part"]
    option_1 = custom_monitor["option_1"]
    option_2 = custom_monitor["option_2"]
    option_3 = custom_monitor["option_3"]
    part_label = PART_DEFINITIONS[part_key]["label"]
    labels = [
        _monitor_option_label(option_1, int(custom_monitor["value_1"])),
        _monitor_option_label(option_2, int(custom_monitor["value_2"])),
        _monitor_option_label(option_3, int(custom_monitor["value_3"])),
    ]
    quality_value = int(custom_monitor["quality_value"])
    if quality_value > 0:
        labels.append(f"품질≥{quality_value}")
    return f"{part_label} {'/'.join(labels)}"


def monitor_fixed_options(custom_monitor: dict) -> set[str]:
    labels = []
    for option_key in (
        custom_monitor["option_1"],
        custom_monitor["option_2"],
        custom_monitor["option_3"],
    ):
        option_payload = OPTION_DEFINITIONS[option_key]
        if bool(option_payload.get("skip_query", False)):
            continue
        labels.append(str(option_payload["label"]))
    return set(labels)


def build_monitor_query(custom_monitor: dict) -> dict:
    part_key = custom_monitor["part"]
    category_code = PART_DEFINITIONS[part_key]["category_code"]
    option_filters = [
        (custom_monitor["option_1"], custom_monitor["value_1"]),
        (custom_monitor["option_2"], custom_monitor["value_2"]),
        (custom_monitor["option_3"], custom_monitor["value_3"]),
    ]
    etc_options: list[dict] = []
    for option_key, option_value in option_filters:
        option_payload = OPTION_DEFINITIONS[option_key]
        if bool(option_payload.get("skip_query", False)):
            continue
        etc_options.append(
            {
                "FirstOption": 7,
                "SecondOption": option_payload["second_option"],
                "MinValue": int(option_value),
                "MaxValue": int(option_value),
            }
        )

    if custom_monitor["quality_value"] > 0:
        etc_options.append(
            {
                "FirstOption": 1,
                "SecondOption": 11,
                "MinValue": custom_monitor["quality_value"],
                "MaxValue": 99999,
            }
        )

    return {
        "ItemTier": 4,
        "ItemGrade": "고대",
        "CategoryCode": category_code,
        "PageNo": 1,
        "Sort": "BUY_PRICE",
        "SortCondition": "ASC",
        "EtcOptions": etc_options,
    }


def build_monitor_runtime_config(
    custom_monitors: list[dict] | None = None,
    slot_count: int | None = None,
) -> list[dict]:
    resolved_slot_count = slot_count
    if resolved_slot_count is None and isinstance(custom_monitors, list):
        resolved_slot_count = len(custom_monitors)

    resolved_monitors = merge_custom_monitors(custom_monitors, resolved_slot_count)
    runtime_monitors: list[dict] = []
    for custom_monitor in resolved_monitors:
        runtime_monitors.append(
            {
                "key": custom_monitor["id"],
                "label": monitor_label(custom_monitor),
                "fixed_options": monitor_fixed_options(custom_monitor),
                "query": build_monitor_query(custom_monitor),
                "enabled": custom_monitor["enabled"],
            }
        )
    return runtime_monitors
