import json
import hashlib
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
from urllib import error, request
import winsound

API_URL = "https://developer-lostark.game.onstove.com/auctions/items"
POLL_SECONDS = int(os.environ.get("LOSTARK_WATCH_INTERVAL", "60"))
TOKEN = os.environ.get("LOSTARK_API_TOKEN", "").strip()
BASE_DIR = (
    Path(sys.executable).resolve().parent
    if bool(getattr(sys, "frozen", False))
    else Path(__file__).resolve().parent
)
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "watch.log"
LAST_LOG_RESET_HOUR: str | None = None
STATE_LOCK = threading.RLock()
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
                "query_option": {"FirstOption": 7, "SecondOption": 42, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "추피 수치",
                "default": 260,
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
                "query_option": {"FirstOption": 7, "SecondOption": 44, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "게이지 수치",
                "default": 600,
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
                "query_option": {"FirstOption": 7, "SecondOption": 45, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "무공퍼 수치",
                "default": 300,
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
                "id": "option_1",
                "label": "치적 수치",
                "default": 155,
                "query_option": {"FirstOption": 7, "SecondOption": 49, "match": "exact"},
            },
            {
                "id": "option_2",
                "label": "치피 수치",
                "default": 400,
                "query_option": {"FirstOption": 7, "SecondOption": 50, "match": "exact"},
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

DEFAULT_UPDATE_REPO = "Jeong-Jin-Yong/LostARKAccessoriesAlarm"
DEFAULT_UPDATE_REF = "main"
DEFAULT_UPDATE_EXE_PATH = "dist/LostArkWatcher.exe"
GITHUB_API_BASE = "https://api.github.com"
UPDATE_MARKER_FILE = "last_update_blob_sha.txt"


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

    return {
        "token": str(settings.get("token", "")).strip(),
        "poll_seconds": saved_interval,
        "installed_exe_blob_sha": str(settings.get("installed_exe_blob_sha", "")).strip(),
        "monitor_values": merge_monitor_values(saved_monitor_values),
    }


def save_app_settings(
    token: str,
    poll_seconds: int,
    monitor_values: dict[str, dict[str, int]] | None = None,
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

        existing_settings.update(
            {
                "token": token.strip(),
                "poll_seconds": poll_seconds,
                "monitor_values": resolved_monitor_values,
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


def default_monitor_values() -> dict[str, dict[str, int]]:
    return {
        monitor["key"]: {
            field["id"]: field["default"] for field in monitor.get("custom_values", [])
        }
        for monitor in DEFAULT_MONITORS
    }


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


def is_frozen_executable() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_dir() -> Path:
    return BASE_DIR


def compute_github_blob_sha(file_path: Path) -> str | None:
    try:
        content = file_path.read_bytes()
    except Exception:
        return None

    header = f"blob {len(content)}\0".encode("utf-8")
    return hashlib.sha1(header + content).hexdigest()


def github_api_get_json(url: str) -> dict:
    req = request.Request(
        url,
        headers={
            "accept": "application/vnd.github+json",
            "user-agent": "LostArkWatcher-updater",
        },
        method="GET",
    )
    with request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def resolve_update_ref(repo: str) -> str:
    env_ref = os.environ.get("LOSTARK_UPDATE_REF", "").strip()
    if env_ref:
        return env_ref

    try:
        repo_meta = github_api_get_json(f"{GITHUB_API_BASE}/repos/{repo}")
        default_branch = str(repo_meta.get("default_branch", "")).strip()
        if default_branch:
            return default_branch
    except Exception as exc:
        log(f"Auto-update: failed to resolve default branch ({exc})")

    return DEFAULT_UPDATE_REF


def fetch_latest_exe_info(repo: str, ref: str, exe_path: str) -> dict | None:
    try:
        encoded_path = exe_path.strip("/")
        payload = github_api_get_json(
            f"{GITHUB_API_BASE}/repos/{repo}/contents/{encoded_path}?ref={ref}"
        )
    except error.HTTPError as exc:
        if exc.code == 404:
            log(
                "Auto-update: executable not found in repository "
                f"({repo}/{ref}/{exe_path})"
            )
            return None
        raise

    blob_sha = str(payload.get("sha", "")).strip()
    download_url = str(payload.get("download_url", "")).strip()
    if not blob_sha or not download_url:
        log("Auto-update: missing download URL or blob SHA")
        return None

    return {
        "blob_sha": blob_sha,
        "download_url": download_url,
    }


def download_file(download_url: str, output_path: Path) -> None:
    req = request.Request(
        download_url,
        headers={"user-agent": "LostArkWatcher-updater"},
        method="GET",
    )
    with request.urlopen(req, timeout=60) as resp:
        payload = resp.read()

    if not payload:
        raise RuntimeError("Downloaded file is empty")
    output_path.write_bytes(payload)


def launch_self_replace_and_restart(
    current_exe: Path,
    new_exe: Path,
    blob_sha: str,
    current_pid: int,
) -> bool:
    updater_path = current_exe.with_name("LostArkWatcher-updater.bat")
    marker_path = runtime_dir() / UPDATE_MARKER_FILE

    escaped_blob_sha = blob_sha.replace("\"", "")

    updater_script = f"""@echo off
setlocal
set \"TARGET={current_exe}\"
set \"NEWFILE={new_exe}\"
set \"MARKER={marker_path}\"
set \"PID={current_pid}\"

:wait_pid
tasklist /FI \"PID eq %PID%\" | find /I \"%PID%\" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_pid
)

for /L %%I in (1,1,20) do (
    move /Y \"%NEWFILE%\" \"%TARGET%\" >nul 2>nul
    if not errorlevel 1 goto launch
    timeout /t 1 /nobreak >nul
)

exit /b 1

:launch
> "%MARKER%" echo {escaped_blob_sha}
start \"\" \"%TARGET%\"
del /Q \"%~f0\" >nul 2>nul
exit /b 0
"""

    updater_path.write_text(updater_script, encoding="utf-8")

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(updater_path)],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception as exc:
        log(f"Auto-update: failed to launch updater script ({exc})")
        return False


def apply_update_marker_if_present() -> None:
    marker_path = runtime_dir() / UPDATE_MARKER_FILE
    if not marker_path.exists():
        return

    try:
        blob_sha = marker_path.read_text(encoding="utf-8").strip()
        if blob_sha:
            save_installed_exe_blob_sha(blob_sha)
    except Exception as exc:
        log(f"Auto-update: failed to apply update marker ({exc})")
    finally:
        marker_path.unlink(missing_ok=True)


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


def is_valid_token(token: str) -> bool:
    normalized = normalize_token(token)
    return normalized.lower().startswith("bearer ") and len(normalized.strip()) > len("bearer ")


def normalize_token(token: str) -> str:
    cleaned = token.strip()
    if not cleaned:
        return ""
    if cleaned.lower().startswith("bearer "):
        return cleaned
    return f"bearer {cleaned}"


def run_watcher_loop(
    stop_event: threading.Event,
    token: str,
    poll_seconds: int,
    monitors: list[dict],
) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

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
    run_watcher_loop(
        stop_event,
        normalize_token(token),
        app_settings["poll_seconds"],
        build_monitor_runtime_config(app_settings["monitor_values"]),
    )
    return 0


class WatcherPopup:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("LostArkWatcher 팝업")
        self.root.geometry("420x240")
        self.root.resizable(False, False)

        app_settings = load_app_settings()
        initial_token = TOKEN if TOKEN else app_settings["token"]
        initial_interval = app_settings["poll_seconds"]

        self.token_var = tk.StringVar(value=initial_token)
        self.interval_var = tk.IntVar(value=initial_interval)
        self.status_var = tk.StringVar(value="대기 중")
        self.monitor_values = app_settings["monitor_values"]
        self.monitor_enabled: dict[str, tk.BooleanVar] = {
            monitor["key"]: tk.BooleanVar(value=True) for monitor in DEFAULT_MONITORS
        }

        self.worker_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.log_window: tk.Toplevel | None = None
        self.log_text: scrolledtext.ScrolledText | None = None
        self.update_thread: threading.Thread | None = None

        self._build_layout()
        self._update_buttons()
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.root.after(1000, self._refresh_runtime_state)
        self.root.after(1500, self._start_auto_update_check)

    def _start_auto_update_check(self) -> None:
        if not is_frozen_executable():
            return
        if self.update_thread is not None and self.update_thread.is_alive():
            return

        self.update_thread = threading.Thread(
            target=self._check_and_apply_auto_update,
            daemon=True,
        )
        self.update_thread.start()

    def _check_and_apply_auto_update(self) -> None:
        apply_update_marker_if_present()

        repo = os.environ.get("LOSTARK_UPDATE_REPO", DEFAULT_UPDATE_REPO).strip()
        exe_path = os.environ.get("LOSTARK_UPDATE_EXE_PATH", DEFAULT_UPDATE_EXE_PATH).strip()
        if not repo:
            log("Auto-update: repository is not configured")
            return

        ref = resolve_update_ref(repo)

        try:
            latest = fetch_latest_exe_info(repo, ref, exe_path)
            if latest is None:
                return

            current_exe = Path(sys.executable)
            installed_blob_sha = compute_github_blob_sha(current_exe)
            if not installed_blob_sha:
                app_settings = load_app_settings()
                installed_blob_sha = app_settings["installed_exe_blob_sha"]
            latest_blob_sha = latest["blob_sha"]

            if installed_blob_sha == latest_blob_sha:
                log("Auto-update: already up to date")
                return

            new_exe = current_exe.with_name("LostArkWatcher.new.exe")
            download_file(latest["download_url"], new_exe)

            def shutdown_for_update() -> None:
                messagebox.showinfo(
                    "업데이트 진행",
                    "최신 버전을 내려받았습니다. 앱을 재시작합니다.",
                )
                if not launch_self_replace_and_restart(
                    current_exe,
                    new_exe,
                    latest_blob_sha,
                    os.getpid(),
                ):
                    if new_exe.exists():
                        new_exe.unlink(missing_ok=True)
                    messagebox.showerror(
                        "업데이트 실패",
                        "업데이트 적용에 실패했습니다. 잠시 후 다시 실행해 주세요.",
                    )
                    return
                self._stop_watch()
                self.root.destroy()

            self.root.after(0, shutdown_for_update)
        except error.HTTPError as exc:
            log(f"Auto-update HTTP error {exc.code}")
        except Exception as exc:
            log(f"Auto-update failed: {exc}")

    def _build_layout(self) -> None:
        frame = tk.Frame(self.root, padx=14, pady=14)
        frame.pack(fill="both", expand=True)

        title = tk.Label(
            frame,
            text="LostArkWatcher 제어 팝업",
            font=("Malgun Gothic", 13, "bold"),
        )
        title.pack(anchor="w")

        description = tk.Label(
            frame,
            text="아래 버튼으로 API, 탐색, 로그, 악세 설정을 관리하세요.",
            font=("Malgun Gothic", 9),
        )
        description.pack(anchor="w", pady=(4, 12))

        button_grid = tk.Frame(frame)
        button_grid.pack(fill="x")

        self.api_button = tk.Button(
            button_grid,
            text="API 설정",
            width=18,
            command=self._open_api_settings,
        )
        self.api_button.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        self.start_button = tk.Button(
            button_grid,
            text="탐색 시작",
            width=18,
            command=self._start_watch,
        )
        self.start_button.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        self.stop_button = tk.Button(
            button_grid,
            text="탐색 종료",
            width=18,
            command=self._stop_watch,
        )
        self.stop_button.grid(row=1, column=0, padx=4, pady=4, sticky="ew")

        self.log_button = tk.Button(
            button_grid,
            text="로그 창",
            width=18,
            command=self._open_log_window,
        )
        self.log_button.grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        self.accessory_button = tk.Button(
            button_grid,
            text="악세 설정",
            width=18,
            command=self._open_accessory_settings,
        )
        self.accessory_button.grid(row=2, column=0, columnspan=2, padx=4, pady=4, sticky="ew")

        button_grid.grid_columnconfigure(0, weight=1)
        button_grid.grid_columnconfigure(1, weight=1)

        status_frame = tk.Frame(frame)
        status_frame.pack(fill="x", pady=(14, 0))
        tk.Label(status_frame, text="상태:", font=("Malgun Gothic", 9, "bold")).pack(side="left")
        tk.Label(status_frame, textvariable=self.status_var, font=("Malgun Gothic", 9)).pack(side="left", padx=(6, 0))

    def _open_api_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("API 설정")
        dialog.geometry("520x180")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        token_var = tk.StringVar(value=self.token_var.get())
        interval_var = tk.StringVar(value=str(self.interval_var.get()))

        container = tk.Frame(dialog, padx=12, pady=12)
        container.pack(fill="both", expand=True)

        tk.Label(container, text="LOSTARK API 키", font=("Malgun Gothic", 9)).pack(anchor="w")
        token_entry = tk.Entry(container, textvariable=token_var, width=70)
        token_entry.pack(fill="x", pady=(4, 10))

        tk.Label(container, text="탐색 주기(초)", font=("Malgun Gothic", 9)).pack(anchor="w")
        interval_entry = tk.Entry(container, textvariable=interval_var, width=20)
        interval_entry.pack(anchor="w", pady=(4, 12))

        def save() -> None:
            raw_interval = interval_var.get().strip()
            try:
                interval = int(raw_interval)
            except ValueError:
                messagebox.showerror("입력 오류", "탐색 주기는 숫자로 입력해주세요.")
                return

            if interval <= 0:
                messagebox.showerror("입력 오류", "탐색 주기는 1초 이상이어야 합니다.")
                return

            self.token_var.set(token_var.get().strip())
            self.interval_var.set(interval)
            save_app_settings(self.token_var.get(), interval, self.monitor_values)
            dialog.destroy()

        button_row = tk.Frame(container)
        button_row.pack(anchor="e")
        tk.Button(button_row, text="저장", width=10, command=save).pack(side="left", padx=4)
        tk.Button(button_row, text="취소", width=10, command=dialog.destroy).pack(side="left", padx=4)

        token_entry.focus_set()
        interval_entry.selection_range(0, tk.END)

    def _open_accessory_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("악세 설정")
        dialog.geometry("520x500")
        dialog.resizable(False, True)
        dialog.transient(self.root)
        dialog.grab_set()

        draft_vars = {
            monitor["key"]: tk.BooleanVar(value=self.monitor_enabled[monitor["key"]].get())
            for monitor in DEFAULT_MONITORS
        }
        draft_value_vars: dict[str, dict[str, tk.StringVar]] = {
            monitor["key"]: {
                field["id"]: tk.StringVar(
                    value=str(self.monitor_values[monitor["key"]][field["id"]])
                )
                for field in monitor.get("custom_values", [])
            }
            for monitor in DEFAULT_MONITORS
        }

        container = tk.Frame(dialog, padx=12, pady=12)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text="탐색할 악세 조건과 수치를 설정하세요.",
            font=("Malgun Gothic", 9),
        ).pack(anchor="w", pady=(0, 8))

        scroll_frame = tk.Frame(container)
        scroll_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_frame, highlightthickness=0)
        scrollbar = tk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        sections_container = tk.Frame(canvas)

        sections_container.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas_window = canvas.create_window((0, 0), window=sections_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def resize_canvas_content(_event: tk.Event) -> None:
            canvas.itemconfigure(canvas_window, width=_event.width)

        def on_mousewheel(event: tk.Event) -> None:
            if event.delta == 0 or not canvas.winfo_exists():
                return
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Configure>", resize_canvas_content)
        for widget in (canvas, sections_container):
            widget.bind("<MouseWheel>", on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for monitor in DEFAULT_MONITORS:
            section = tk.LabelFrame(
                sections_container,
                font=("Malgun Gothic", 9),
                padx=10,
                pady=8,
            )
            section.pack(fill="x", pady=4)

            tk.Checkbutton(
                section,
                text=f"{monitor['label']} 사용",
                variable=draft_vars[monitor["key"]],
                font=("Malgun Gothic", 9, "bold"),
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

            for row_index, field in enumerate(monitor.get("custom_values", []), start=1):
                tk.Label(section, text=field["label"], font=("Malgun Gothic", 9)).grid(
                    row=row_index,
                    column=0,
                    sticky="w",
                    padx=(0, 10),
                    pady=2,
                )
                tk.Entry(
                    section,
                    textvariable=draft_value_vars[monitor["key"]][field["id"]],
                    width=18,
                ).grid(row=row_index, column=1, sticky="w", pady=2)

        def save() -> None:
            if not any(var.get() for var in draft_vars.values()):
                messagebox.showerror("입력 오류", "최소 1개 이상의 악세 조건을 선택해주세요.")
                return

            resolved_monitor_values = default_monitor_values()
            for monitor in DEFAULT_MONITORS:
                for field in monitor.get("custom_values", []):
                    raw_value = draft_value_vars[monitor["key"]][field["id"]].get().strip()
                    try:
                        value = int(raw_value)
                    except ValueError:
                        messagebox.showerror(
                            "입력 오류",
                            f"{monitor['label']}의 {field['label']}은 숫자로 입력해주세요.",
                        )
                        return
                    if value < 0:
                        messagebox.showerror(
                            "입력 오류",
                            f"{monitor['label']}의 {field['label']}은 0 이상이어야 합니다.",
                        )
                        return
                    resolved_monitor_values[monitor["key"]][field["id"]] = value

            for key, var in draft_vars.items():
                self.monitor_enabled[key].set(var.get())
            self.monitor_values = resolved_monitor_values
            save_app_settings(
                self.token_var.get(),
                self.interval_var.get(),
                self.monitor_values,
            )
            dialog.destroy()

        button_row = tk.Frame(container)
        button_row.pack(anchor="e", pady=(10, 0))
        tk.Button(button_row, text="저장", width=10, command=save).pack(side="left", padx=4)
        tk.Button(button_row, text="취소", width=10, command=dialog.destroy).pack(side="left", padx=4)

    def _open_log_window(self) -> None:
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.deiconify()
            self.log_window.lift()
            return

        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("로그 창")
        self.log_window.geometry("860x480")

        self.log_text = scrolledtext.ScrolledText(
            self.log_window,
            wrap="none",
            font=("Consolas", 10),
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_window.protocol("WM_DELETE_WINDOW", self._close_log_window)
        self._refresh_log_window()

    def _close_log_window(self) -> None:
        if self.log_window is None:
            return
        self.log_window.destroy()
        self.log_window = None
        self.log_text = None

    def _refresh_log_window(self) -> None:
        if self.log_window is None or not self.log_window.winfo_exists() or self.log_text is None:
            return

        text = ""
        if LOG_PATH.exists():
            text = LOG_PATH.read_text(encoding="utf-8", errors="replace")

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

        self.log_window.after(1000, self._refresh_log_window)

    def _selected_monitors(self) -> list[dict]:
        selected = []
        for monitor in build_monitor_runtime_config(self.monitor_values):
            if self.monitor_enabled[monitor["key"]].get():
                selected.append(monitor)
        return selected

    def _is_running(self) -> bool:
        return self.worker_thread is not None and self.worker_thread.is_alive()

    def _update_buttons(self) -> None:
        running = self._is_running()
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def _refresh_runtime_state(self) -> None:
        if self._is_running():
            self.status_var.set(f"탐색 중 (주기: {self.interval_var.get()}초)")
        else:
            if self.status_var.get().startswith("탐색 중"):
                self.status_var.set("대기 중")
        self._update_buttons()
        self.root.after(1000, self._refresh_runtime_state)

    def _start_watch(self) -> None:
        if self._is_running():
            return

        token = self.token_var.get().strip()
        normalized_token = normalize_token(token)
        if not is_valid_token(normalized_token):
            messagebox.showerror("토큰 오류", "API 키를 입력해주세요.")
            return

        monitors = self._selected_monitors()
        if not monitors:
            messagebox.showerror("설정 오류", "악세 설정에서 최소 1개를 선택해주세요.")
            return

        poll_seconds = self.interval_var.get()
        if poll_seconds <= 0:
            messagebox.showerror("설정 오류", "탐색 주기는 1초 이상이어야 합니다.")
            return

        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(
            target=run_watcher_loop,
            args=(self.stop_event, normalized_token, poll_seconds, monitors),
            daemon=True,
        )
        self.worker_thread.start()
        self.status_var.set("탐색 시작됨")
        self._update_buttons()

    def _stop_watch(self) -> None:
        if not self._is_running() or self.stop_event is None:
            return

        self.stop_event.set()
        worker = self.worker_thread
        if worker is not None:
            worker.join(timeout=2)
        self.status_var.set("탐색 종료됨")
        self._update_buttons()

    def _handle_close(self) -> None:
        self._stop_watch()
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    if "--cli" in sys.argv:
        return run_cli_watcher()
    app = WatcherPopup()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
