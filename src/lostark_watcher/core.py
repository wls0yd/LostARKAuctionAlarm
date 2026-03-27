import json
import subprocess
import threading
import time
from urllib import error, request

import winsound

from .app_logging import log
from .monitors import build_monitor_runtime_config
from .runtime_context import API_URL, DATA_DIR, OPEN_LOG_SIGNAL_PATH, TOKEN
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
        f"{item.get('Name')} | price={info.get('BuyPrice')} "
        f"| trades={info.get('TradeAllowCount')} "
        f"| stat={stat_value(item)} | extra={extra_option_text(item, fixed_options)} "
    )


def _to_powershell_single_quoted_literal(value: str) -> str:
    return (value or "").replace("'", "''")


def send_windows_notification(label: str, new_items: list[dict]) -> None:
    count = len(new_items)
    if count <= 0:
        return

    title = "LostArkWatcher 새 악세 발견"
    first_item = new_items[0]
    first_name = str(first_item.get("Name", "알 수 없는 악세"))
    first_price = first_item.get("AuctionInfo", {}).get("BuyPrice", "?")
    extra_count = count - 1
    if extra_count > 0:
        message = (
            f"[{label}] {first_name} (즉구 {first_price}) 외 {extra_count}개"
        )
    else:
        message = f"[{label}] {first_name} (즉구 {first_price})"

    safe_title = _to_powershell_single_quoted_literal(title)
    safe_message = _to_powershell_single_quoted_literal(message)
    safe_signal_path = _to_powershell_single_quoted_literal(str(OPEN_LOG_SIGNAL_PATH))
    balloon_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$title = '{safe_title}'; "
        f"$body = '{safe_message}'; "
        f"$signalPath = '{safe_signal_path}'; "
        "$signalDir = Split-Path -Parent $signalPath; "
        "if ($signalDir -and -not (Test-Path -LiteralPath $signalDir)) { "
        "  New-Item -ItemType Directory -Path $signalDir -Force | Out-Null "
        "}; "
        "$notify = New-Object System.Windows.Forms.NotifyIcon; "
        "$notify.Icon = [System.Drawing.SystemIcons]::Information; "
        "$notify.BalloonTipTitle = $title; "
        "$notify.BalloonTipText = $body; "
        "$notify.Visible = $true; "
        "$clicked = $false; "
        "$handler = [System.EventHandler]{ param($sender, $eventArgs) "
        "  $script:clicked = $true; "
        "  [System.IO.File]::WriteAllText(" 
        "    $signalPath, "
        "    (Get-Date -Format o), "
        "    [System.Text.Encoding]::UTF8"
        "  ) "
        "}; "
        "$notify.add_BalloonTipClicked($handler); "
        "$notify.ShowBalloonTip(5000); "
        "for ($i = 0; $i -lt 260; $i++) { "
        "  [System.Windows.Forms.Application]::DoEvents(); "
        "  if ($script:clicked) { break }; "
        "  Start-Sleep -Milliseconds 20 "
        "}; "
        "$notify.remove_BalloonTipClicked($handler); "
        "$notify.Dispose()"
    )

    def run_powershell_async(command_script: str) -> None:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command_script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    try:
        run_powershell_async(balloon_script)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"Windows balloon notification failed: {exc}")


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

    send_windows_notification(label, new_items)

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
    reset_event: threading.Event | None = None,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not is_valid_token(token):
        log("Startup error: LOSTARK_API_TOKEN missing or invalid")
        return

    state = load_state()
    pending_baseline_alert = bool(state.get("alert_on_next_baseline", False))
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
            if reset_event is not None and reset_event.is_set():
                for seen in seen_by_monitor.values():
                    seen.clear()
                pending_baseline_alert = True
                save_state(seen_by_monitor, alert_on_next_baseline=True)
                reset_event.clear()
                log("Found accessory cache reset requested by user")

            for monitor in monitors:
                items = fetch_items(monitor["query"], token)
                signatures = {item_signature(item) for item in items}
                seen = seen_by_monitor[monitor["key"]]
                if not seen:
                    if pending_baseline_alert and items:
                        notify(monitor["label"], monitor["fixed_options"], items)
                    seen_by_monitor[monitor["key"]] = signatures
                    save_state(seen_by_monitor, alert_on_next_baseline=pending_baseline_alert)
                    if pending_baseline_alert and items:
                        log(
                            f"Baseline captured with alert [{monitor['label']}]: {len(signatures)} listing(s)"
                        )
                    else:
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

            if pending_baseline_alert:
                pending_baseline_alert = False
                save_state(seen_by_monitor, alert_on_next_baseline=False)
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
        for monitor in build_monitor_runtime_config(
            app_settings["custom_monitors"],
            app_settings["monitor_slot_count"],
        )
        if bool(monitor.get("enabled", True))
    ]
    if not monitors:
        log("Startup error: no accessory slots enabled. Configure at least one slot.")
        return 1

    run_watcher_loop(
        stop_event,
        normalize_token(token),
        app_settings["poll_seconds"],
        monitors,
    )
    return 0
