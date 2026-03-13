import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import error, request
import winsound

API_URL = "https://developer-lostark.game.onstove.com/auctions/items"
POLL_SECONDS = int(os.environ.get("LOSTARK_WATCH_INTERVAL", "60"))
TOKEN = os.environ.get("LOSTARK_API_TOKEN", "").strip()
BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "watch.log"
LAST_LOG_RESET_HOUR: str | None = None
MONITORS = [
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
            "EtcOptions": [
                {"FirstOption": 7, "SecondOption": 42, "MinValue": 200, "MaxValue": 200},
                {"FirstOption": 7, "SecondOption": 41, "MinValue": 260, "MaxValue": 260},
                {"FirstOption": 1, "SecondOption": 11, "MinValue": 17500, "MaxValue": 99999},
            ],
        },
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
            "EtcOptions": [
                {"FirstOption": 7, "SecondOption": 45, "MinValue": 155, "MaxValue": 155},
                {"FirstOption": 7, "SecondOption": 46, "MinValue": 300, "MaxValue": 300},
                {"FirstOption": 1, "SecondOption": 11, "MinValue": 13500, "MaxValue": 99999},
            ],
        },
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
            "EtcOptions": [
                {"FirstOption": 7, "SecondOption": 49, "MinValue": 155, "MaxValue": 155},
                {"FirstOption": 7, "SecondOption": 50, "MinValue": 400, "MaxValue": 400},
                {"FirstOption": 1, "SecondOption": 11, "MinValue": 12500, "MaxValue": 99999},
            ],
        },
    },
]


def log(message: str) -> None:
    global LAST_LOG_RESET_HOUR

    current_hour = datetime.now().strftime("%Y-%m-%d %H")
    if LAST_LOG_RESET_HOUR is None:
        LAST_LOG_RESET_HOUR = current_hour
    elif current_hour != LAST_LOG_RESET_HOUR:
        LOG_PATH.write_text("", encoding="utf-8")
        LAST_LOG_RESET_HOUR = current_hour

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_state() -> dict:
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
    STATE_PATH.write_text(
        json.dumps(
            {
                "seen_by_monitor": {
                    key: sorted(values) for key, values in signatures_by_monitor.items()
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def fetch_items(query: dict) -> list[dict]:
    headers = {
        "accept": "application/json",
        "authorization": TOKEN,
        "content-type": "application/json",
    }
    all_items: list[dict] = []
    page_no = 1

    while True:
        payload_query = dict(query)
        payload_query["PageNo"] = page_no
        body = json.dumps(payload_query, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            API_URL,
            data=body,
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)

        items = payload.get("Items") or []
        all_items.extend(items)

        page_size = int(payload.get("PageSize", len(items) or 1))
        total_count = int(payload.get("TotalCount", len(items)))
        if page_no * page_size >= total_count:
            break
        page_no += 1

    return all_items


def stat_value(item: dict) -> int:
    for opt in item.get("Options", []):
        if opt.get("Type") == "STAT" and opt.get("OptionName") == "힘":
            return int(opt.get("Value", 0))
    return 0


def normalize_option_name(name: str) -> str:
    return (name or "").strip()


def format_option_value(option: dict) -> str:
    value = option.get("Value")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}%" if option.get("IsValuePercentage") else str(value)


def extra_option_text(item: dict, fixed_options: set[str]) -> str:
    normalized_fixed = {normalize_option_name(name) for name in fixed_options}
    for option in item.get("Options", []):
        if option.get("Type") != "ACCESSORY_UPGRADE":
            continue
        option_name = normalize_option_name(option.get("OptionName", ""))
        if option_name in normalized_fixed:
            continue
        return f"{option_name} {format_option_value(option)}"
    return "없음"


def item_signature(item: dict) -> str:
    info = item.get("AuctionInfo", {})
    return "|".join(
        [
            item.get("Name", ""),
            str(item.get("GradeQuality", "")),
            str(info.get("BuyPrice", "")),
            str(info.get("TradeAllowCount", "")),
            str(info.get("UpgradeLevel", "")),
            info.get("EndDate", ""),
            str(stat_value(item)),
        ]
    )


def summarize(item: dict, fixed_options: set[str]) -> str:
    info = item.get("AuctionInfo", {})
    return (
        f"{item.get('Name')} | price={info.get('BuyPrice')} | quality={item.get('GradeQuality')} "
        f"| trades={info.get('TradeAllowCount')} | upgrade={info.get('UpgradeLevel')} "
        f"| stat={stat_value(item)} | extra={extra_option_text(item, fixed_options)} "
        f"| ends={info.get('EndDate')}"
    )


def notify(label: str, fixed_options: set[str], new_items: list[dict]) -> None:
    for _ in range(3):
        winsound.MessageBeep()
        time.sleep(0.2)
    log(f"NEW_LISTINGS [{label}] {len(new_items)} found")
    for item in new_items:
        log("  " + summarize(item, fixed_options))


def main() -> int:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    if not TOKEN.startswith("bearer "):
        log("Startup error: LOSTARK_API_TOKEN missing or invalid")
        return 1

    state = load_state()
    seen_by_monitor = {
        monitor["key"]: set(state.get("seen_by_monitor", {}).get(monitor["key"], []))
        for monitor in MONITORS
    }
    log(
        f"Starting watcher. Poll interval: {POLL_SECONDS}s. "
        f"Monitors: {', '.join(monitor['label'] for monitor in MONITORS)}"
    )

    while True:
        try:
            for monitor in MONITORS:
                items = fetch_items(monitor["query"])
                signatures = {item_signature(item) for item in items}
                seen = seen_by_monitor[monitor["key"]]
                if not seen:
                    seen_by_monitor[monitor["key"]] = signatures
                    save_state(seen_by_monitor)
                    log(
                        f"Baseline captured [{monitor['label']}]: {len(signatures)} listing(s)"
                    )
                    continue

                new_items = [item for item in items if item_signature(item) not in seen]
                if new_items:
                    notify(monitor["label"], monitor["fixed_options"], new_items)
                    seen_by_monitor[monitor["key"]] |= {
                        item_signature(item) for item in new_items
                    }
                    save_state(seen_by_monitor)
                else:
                    log(
                        f"No new listings [{monitor['label']}]. "
                        f"Current matching count: {len(items)}"
                    )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            log(f"HTTP error {exc.code}: {detail}")
        except Exception as exc:
            log(f"Watcher error: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
