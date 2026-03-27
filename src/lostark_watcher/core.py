import json
import threading
import time
from urllib import error, request

import winsound

from .app_logging import log
from .monitors import build_monitor_runtime_config
from .runtime_context import API_URL, DATA_DIR, TOKEN
from .state import load_app_settings, load_state, save_state


def fetch_items(query: dict, token: str) -> list[dict]:
    headers = {
        "accept": "application/json",
        "authorization": token,
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


def normalize_option_match_key(name: str) -> str:
    normalized = normalize_option_name(name)
    normalized = normalized.replace(",", "").replace(" ", "")
    if normalized.endswith("증가"):
        normalized = normalized.removesuffix("증가")
    return normalized


def format_option_value(option: dict) -> str:
    value = option.get("Value")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}%" if option.get("IsValuePercentage") else str(value)


def extra_option_text(item: dict, fixed_options: set[str]) -> str:
    normalized_fixed = {normalize_option_match_key(name) for name in fixed_options}
    extra_options: list[str] = []
    for option in item.get("Options", []):
        if option.get("Type") != "ACCESSORY_UPGRADE":
            continue
        option_name = normalize_option_name(option.get("OptionName", ""))
        if normalize_option_match_key(option_name) in normalized_fixed:
            continue
        extra_options.append(f"{option_name} {format_option_value(option)}")

    if not extra_options:
        return "없음"
    return ", ".join(extra_options)


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
    def play_alert_sound() -> None:
        try:
            winsound.PlaySound(
                "SystemExclamation",
                winsound.SND_ALIAS | winsound.SND_ASYNC,
            )
            return
        except RuntimeError:
            pass

        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
        except RuntimeError:
            pass

        try:
            winsound.Beep(1200, 250)
        except RuntimeError:
            log("Sound alert unavailable on this system")

    for _ in range(3):
        play_alert_sound()
        time.sleep(0.2)
    log(f"NEW_LISTINGS [{label}] {len(new_items)} found")
    for item in new_items:
        log("  " + summarize(item, fixed_options))


def normalize_token(token: str) -> str:
    cleaned = token.strip()
    if not cleaned:
        return ""
    if cleaned.lower().startswith("bearer "):
        return cleaned
    return f"bearer {cleaned}"


def is_valid_token(token: str) -> bool:
    normalized = normalize_token(token)
    return normalized.lower().startswith("bearer ") and len(normalized.strip()) > len("bearer ")


def run_watcher_loop(
    stop_event: threading.Event,
    token: str,
    poll_seconds: int,
    monitors: list[dict],
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not is_valid_token(token):
        log("Startup error: LOSTARK_API_TOKEN missing or invalid")
        return

    state = load_state()
    seen_by_monitor = {
        monitor["key"]: set(state.get("seen_by_monitor", {}).get(monitor["key"], []))
        for monitor in monitors
    }
    log(
        f"Starting watcher. Poll interval: {poll_seconds}s. "
        f"Monitors: {', '.join(monitor['label'] for monitor in monitors)}"
    )

    while not stop_event.is_set():
        try:
            for monitor in monitors:
                items = fetch_items(monitor["query"], token)
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

        if stop_event.wait(poll_seconds):
            break

    log("Watcher stopped")


def run_cli_watcher() -> int:
    stop_event = threading.Event()
    app_settings = load_app_settings()
    token = TOKEN if TOKEN else app_settings["token"]
    monitors = [
        monitor
        for monitor in build_monitor_runtime_config(app_settings["monitor_values"])
        if app_settings["monitor_enabled"].get(monitor["key"], True)
    ]
    run_watcher_loop(
        stop_event,
        normalize_token(token),
        app_settings["poll_seconds"],
        monitors,
    )
    return 0
