import json
import os
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
BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "watch.log"
LAST_LOG_RESET_HOUR: str | None = None
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
    for _ in range(3):
        winsound.MessageBeep()
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
    run_watcher_loop(stop_event, normalize_token(TOKEN), POLL_SECONDS, DEFAULT_MONITORS)
    return 0


class WatcherPopup:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("LostArkWatcher 팝업")
        self.root.geometry("420x240")
        self.root.resizable(False, False)

        self.token_var = tk.StringVar(value=TOKEN)
        self.interval_var = tk.IntVar(value=POLL_SECONDS)
        self.status_var = tk.StringVar(value="대기 중")
        self.monitor_enabled: dict[str, tk.BooleanVar] = {
            monitor["key"]: tk.BooleanVar(value=True) for monitor in DEFAULT_MONITORS
        }

        self.worker_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.log_window: tk.Toplevel | None = None
        self.log_text: scrolledtext.ScrolledText | None = None

        self._build_layout()
        self._update_buttons()
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.root.after(1000, self._refresh_runtime_state)

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

        tk.Label(container, text="LOSTARK API 키 (Bearer 없이 입력 가능)", font=("Malgun Gothic", 9)).pack(anchor="w")
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
        dialog.geometry("380x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        draft_vars = {
            monitor["key"]: tk.BooleanVar(value=self.monitor_enabled[monitor["key"]].get())
            for monitor in DEFAULT_MONITORS
        }

        container = tk.Frame(dialog, padx=12, pady=12)
        container.pack(fill="both", expand=True)

        tk.Label(container, text="탐색할 악세 조건을 선택하세요.", font=("Malgun Gothic", 9)).pack(anchor="w", pady=(0, 8))

        for monitor in DEFAULT_MONITORS:
            tk.Checkbutton(
                container,
                text=monitor["label"],
                variable=draft_vars[monitor["key"]],
                font=("Malgun Gothic", 9),
            ).pack(anchor="w", pady=3)

        def save() -> None:
            if not any(var.get() for var in draft_vars.values()):
                messagebox.showerror("입력 오류", "최소 1개 이상의 악세 조건을 선택해주세요.")
                return
            for key, var in draft_vars.items():
                self.monitor_enabled[key].set(var.get())
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
        for monitor in DEFAULT_MONITORS:
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
