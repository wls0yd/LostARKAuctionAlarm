import json
from pathlib import Path


METADATA_PATH = Path(__file__).with_suffix(".json")


def _load_metadata() -> dict:
    payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Accessory metadata JSON must be an object")
    return payload


_METADATA = _load_metadata()

MAX_MONITOR_SLOTS = int(_METADATA["max_monitor_slots"])
DEFAULT_MONITOR_SLOTS = int(_METADATA["default_monitor_slots"])

PART_DEFINITIONS = dict(_METADATA["part_definitions"])
OPTION_DEFINITIONS = dict(_METADATA["option_definitions"])
PART_OPTION_KEYS = dict(_METADATA["part_option_keys"])
QUALITY_VALUE_OPTIONS = dict(_METADATA["quality_value_options"])
