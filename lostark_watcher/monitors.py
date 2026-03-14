def level_options(high: float, medium: float, low: float) -> list[dict[str, int | str]]:
    return [
        {"label": f"상 ({high:g})", "value": int(high * 100)},
        {"label": f"중 ({medium:g})", "value": int(medium * 100)},
        {"label": f"하 ({low:g})", "value": int(low * 100)},
    ]


DEFAULT_MONITORS = [
    {
        "key": "necklace_damage",
        "label": "목걸이 적주피/추피",
        "fixed_options": {"적에게 주는 피해 증가", "추가 피해"},
        "query": {
            "ItemTier": 4,
            "ItemGrade": "고대",
            "CategoryCode": 200010,
            "PageNo": 1,
            "Sort": "BUY_PRICE",
            "SortCondition": "ASC",
        },
        "custom_values": [
            {
                "id": "option_1",
                "label": "적주피 수치",
                "default": 200,
                "preset_levels": level_options(2, 1.2, 0.55),
                "query_option": {"FirstOption": 7, "SecondOption": 42, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "추피 수치",
                "default": 260,
                "preset_levels": level_options(2.6, 1.6, 0.6),
                "query_option": {"FirstOption": 7, "SecondOption": 41, "match": "exact"},
            },
            {
                "id": "quality_min",
                "label": "최소 품질",
                "default": 17500,
                "query_option": {"FirstOption": 1, "SecondOption": 11, "match": "minimum"},
            },
        ],
    },
    {
        "key": "necklace_brand_gauge",
        "label": "목걸이 낙인력/게이지",
        "fixed_options": {
            "낙인력",
            "세레나데, 신성, 조화 게이지 획득량 증가",
            "세레나데, 신앙, 조화 게이지 획득량",
        },
        "query": {
            "ItemTier": 4,
            "ItemGrade": "고대",
            "CategoryCode": 200010,
            "PageNo": 1,
            "Sort": "BUY_PRICE",
            "SortCondition": "ASC",
        },
        "custom_values": [
            {
                "id": "option_1",
                "label": "낙인력 수치",
                "default": 800,
                "preset_levels": level_options(8, 4.8, 2.15),
                "query_option": {"FirstOption": 7, "SecondOption": 44, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "게이지 수치",
                "default": 600,
                "preset_levels": level_options(6, 3.6, 1.6),
                "query_option": {"FirstOption": 7, "SecondOption": 43, "match": "exact"},
            },
            {
                "id": "quality_min",
                "label": "최소 품질",
                "default": 17300,
                "query_option": {"FirstOption": 1, "SecondOption": 11, "match": "minimum"},
            },
        ],
    },
    {
        "key": "earring_attack",
        "label": "귀걸이 공퍼/무공퍼",
        "fixed_options": {"공격력", "무기 공격력"},
        "query": {
            "ItemTier": 4,
            "ItemGrade": "고대",
            "CategoryCode": 200020,
            "PageNo": 1,
            "Sort": "BUY_PRICE",
            "SortCondition": "ASC",
        },
        "custom_values": [
            {
                "id": "option_1",
                "label": "공퍼 수치",
                "default": 155,
                "preset_levels": level_options(1.55, 0.95, 0.4),
                "query_option": {"FirstOption": 7, "SecondOption": 45, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "무공퍼 수치",
                "default": 300,
                "preset_levels": level_options(3, 1.8, 0.8),
                "query_option": {"FirstOption": 7, "SecondOption": 46, "match": "exact"},
            },
            {
                "id": "quality_min",
                "label": "최소 품질",
                "default": 13500,
                "query_option": {"FirstOption": 1, "SecondOption": 11, "match": "minimum"},
            },
        ],
    },
    {
        "key": "ring_crit",
        "label": "반지 치적/치피",
        "fixed_options": {"치명타 적중률", "치명타 피해"},
        "query": {
            "ItemTier": 4,
            "ItemGrade": "고대",
            "CategoryCode": 200030,
            "PageNo": 1,
            "Sort": "BUY_PRICE",
            "SortCondition": "ASC",
        },
        "custom_values": [
            {
                "id": "option_2",
                "label": "치피 수치",
                "default": 400,
                "preset_levels": level_options(4, 2.4, 1.1),
                "query_option": {"FirstOption": 7, "SecondOption": 50, "match": "exact"},
            },
            {
                "id": "option_1",
                "label": "치적 수치",
                "default": 155,
                "preset_levels": level_options(1.55, 0.95, 0.4),
                "query_option": {"FirstOption": 7, "SecondOption": 49, "match": "exact"},
            },
            {
                "id": "quality_min",
                "label": "최소 품질",
                "default": 12500,
                "query_option": {"FirstOption": 1, "SecondOption": 11, "match": "minimum"},
            },
        ],
    },
    {
        "key": "ring_party_buff",
        "label": "반지 아공강/아피강",
        "fixed_options": {"아군 공격력 강화 효과", "아군 피해량 강화 효과"},
        "query": {
            "ItemTier": 4,
            "ItemGrade": "고대",
            "CategoryCode": 200030,
            "PageNo": 1,
            "Sort": "BUY_PRICE",
            "SortCondition": "ASC",
        },
        "custom_values": [
            {
                "id": "option_1",
                "label": "아공강 수치",
                "default": 500,
                "preset_levels": level_options(5, 3, 1.35),
                "query_option": {"FirstOption": 7, "SecondOption": 51, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "아피강 수치",
                "default": 750,
                "preset_levels": level_options(7.5, 4.5, 2),
                "query_option": {"FirstOption": 7, "SecondOption": 52, "match": "exact"},
            },
            {
                "id": "quality_min",
                "label": "최소 품질",
                "default": 12500,
                "query_option": {"FirstOption": 1, "SecondOption": 11, "match": "minimum"},
            },
        ],
    },
]


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
