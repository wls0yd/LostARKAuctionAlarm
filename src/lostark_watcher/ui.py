import json
import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import ttk
from urllib import error

from .app_version import get_app_version
from .app_logging import log
from .core import is_valid_token, normalize_token, run_watcher_loop, summarize
from .monitors import (
    OPTION_DEFINITIONS,
    PART_DEFINITIONS,
    PART_OPTION_KEYS,
    QUALITY_VALUE_OPTIONS,
    build_monitor_runtime_config,
    clamp_monitor_slots,
    merge_custom_monitors,
)
from .runtime_context import (
    DEFAULT_UPDATE_EXE_PATH,
    DEFAULT_UPDATE_REPO,
    TEST_DUMMY_ITEMS_PATH,
    LOG_PATH,
    OPEN_LOG_SIGNAL_PATH,
    TOKEN,
    is_frozen_executable,
)
from .state import clear_seen_by_monitor, load_app_settings, save_app_settings
from .updater import (
    apply_update_marker_if_present,
    compute_github_blob_sha,
    download_file,
    fetch_latest_exe_info,
    launch_self_replace_and_restart,
    resolve_update_ref,
)


class WatcherPopup:
    LOG_WINDOW_INITIAL_READ_MAX_BYTES = 200_000
    OPEN_LOG_SIGNAL_POLL_MS = 50
    DEFAULT_TEST_DUMMY_ITEMS = {
        "monitor": {
            "key": "necklace_damage",
            "label": "목걸이 적주피/추피",
            "fixed_options": [
                "적에게 주는 피해 증가",
                "추가 피해",
            ],
            "query": {
                "ItemTier": 4,
                "ItemGrade": "고대",
                "CategoryCode": 200010,
                "PageNo": 1,
                "Sort": "BUY_PRICE",
                "SortCondition": "ASC",
                "EtcOptions": [
                    {
                        "FirstOption": 7,
                        "SecondOption": 42,
                        "MinValue": 200,
                        "MaxValue": 200,
                    },
                    {
                        "FirstOption": 7,
                        "SecondOption": 41,
                        "MinValue": 260,
                        "MaxValue": 260,
                    },
                    {
                        "FirstOption": 1,
                        "SecondOption": 11,
                        "MinValue": 17500,
                        "MaxValue": 99999,
                    },
                ],
            },
        },
        "items": [
            {
                "Name": "고대 목걸이",
                "GradeQuality": 95,
                "AuctionInfo": {
                    "BuyPrice": 185000,
                    "TradeAllowCount": 2,
                    "UpgradeLevel": 3,
                    "EndDate": "2026-03-27T23:59:59",
                },
                "Options": [
                    {
                        "Type": "STAT",
                        "OptionName": "힘",
                        "Value": 8123,
                        "IsValuePercentage": False,
                    },
                    {
                        "Type": "ACCESSORY_UPGRADE",
                        "OptionName": "추가 피해",
                        "Value": 2.4,
                        "IsValuePercentage": True,
                    },
                    {
                        "Type": "ACCESSORY_UPGRADE",
                        "OptionName": "치명타 피해",
                        "Value": 3.6,
                        "IsValuePercentage": True,
                    },
                ],
            }
        ],
    }

    def __init__(self) -> None:
        self.app_version = get_app_version()
        self.root = tk.Tk()
        self.root.title(f"LostArkWatcher 팝업 ({self.app_version})")
        self.root.geometry("420x290")
        self.root.resizable(False, False)

        app_settings = load_app_settings()
        initial_token = TOKEN if TOKEN else app_settings["token"]
        initial_interval = app_settings["poll_seconds"]

        self.token_var = tk.StringVar(value=initial_token)
        self.interval_var = tk.IntVar(value=initial_interval)
        self.status_var = tk.StringVar(value="대기 중")
        self.monitor_slot_count = app_settings["monitor_slot_count"]
        self.custom_monitors = app_settings["custom_monitors"]

        self.worker_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.reset_event: threading.Event | None = None
        self.log_window: tk.Toplevel | None = None
        self.log_text: scrolledtext.ScrolledText | None = None
        self.log_force_scroll_bottom_once = False
        self.log_read_position = 0
        self.log_initial_tail_loaded = False
        self.update_thread: threading.Thread | None = None

        self._build_layout()
        self._update_buttons()
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.root.after(1000, self._refresh_runtime_state)
        self.root.after(self.OPEN_LOG_SIGNAL_POLL_MS, self._poll_open_log_signal)
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
        exe_asset_name = os.environ.get(
            "LOSTARK_UPDATE_EXE_PATH",
            DEFAULT_UPDATE_EXE_PATH,
        ).strip()
        if not repo:
            log("Auto-update: repository is not configured")
            return

        ref = resolve_update_ref(repo)

        try:
            latest = fetch_latest_exe_info(repo, ref, exe_asset_name)
            if latest is None:
                return

            current_exe = Path(sys.executable)
            app_settings = load_app_settings()
            installed_version_token = app_settings["installed_exe_blob_sha"]
            if not installed_version_token:
                installed_version_token = compute_github_blob_sha(current_exe) or ""
            latest_version_token = latest["blob_sha"]

            if installed_version_token == latest_version_token:
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
                    latest_version_token,
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
            text=(
                "아래 버튼으로 API, 탐색, 로그, 악세 설정을 관리하세요.\n"
                f"현재 버전: {self.app_version}"
            ),
            font=("Malgun Gothic", 9),
            justify="left",
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

        self.clear_button = tk.Button(
            button_grid,
            text="찾은 악세 초기화",
            width=18,
            command=self._clear_seen_history,
        )
        self.clear_button.grid(row=3, column=0, padx=4, pady=4, sticky="ew")

        self.clear_log_button = tk.Button(
            button_grid,
            text="로그 초기화",
            width=18,
            command=self._clear_log_history,
        )
        self.clear_log_button.grid(row=3, column=1, padx=4, pady=4, sticky="ew")

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
            save_app_settings(
                self.token_var.get(),
                interval,
                self.custom_monitors,
                self.monitor_slot_count,
            )
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
        dialog.geometry("860x650")
        dialog.resizable(False, True)
        dialog.transient(self.root)
        dialog.grab_set()

        def part_label(part_key: str) -> str:
            return str(PART_DEFINITIONS[part_key]["label"])

        def part_key_from_label(label: str) -> str:
            for key, payload in PART_DEFINITIONS.items():
                if payload["label"] == label:
                    return key
            return "necklace"

        def part_option_labels(part_key: str) -> list[str]:
            return [
                OPTION_DEFINITIONS["none"]["label"],
                *[OPTION_DEFINITIONS[key]["label"] for key in PART_OPTION_KEYS[part_key]],
            ]

        def option_key_from_label(part_key: str, label: str) -> str:
            if label == OPTION_DEFINITIONS["none"]["label"]:
                return "none"
            for key in PART_OPTION_KEYS[part_key]:
                if OPTION_DEFINITIONS[key]["label"] == label:
                    return key
            return PART_OPTION_KEYS[part_key][0]

        def option_value_labels(option_key: str) -> list[str]:
            payload = OPTION_DEFINITIONS[option_key]
            if option_key == "none":
                return [OPTION_DEFINITIONS["none"]["label"]]

            def format_value(raw_value: int) -> str:
                if bool(payload.get("display_percent", False)):
                    percent_value = raw_value / 100
                    return f"+{percent_value:g}%"
                return f"+{raw_value}"

            return [
                f"{level} ({format_value(int(value))})"
                for level, value in zip(payload["value_labels"], payload["values"])
            ]

        def option_value_from_label(option_key: str, label: str) -> int:
            if option_key == "none":
                return 0
            payload = OPTION_DEFINITIONS[option_key]
            labels = option_value_labels(option_key)
            if label in labels:
                return int(payload["values"][labels.index(label)])
            return int(payload["values"][0])

        def option_value_label_for_value(option_key: str, value: int) -> str:
            if option_key == "none":
                return OPTION_DEFINITIONS["none"]["label"]
            payload = OPTION_DEFINITIONS[option_key]
            labels = option_value_labels(option_key)
            for index, candidate in enumerate(payload["values"]):
                if candidate == value:
                    return labels[index]
            return labels[0]

        def quality_mode_labels() -> list[str]:
            return [str(QUALITY_VALUE_OPTIONS["none"]["label"]), "직접입력"]

        def quality_mode_for_value(value: int) -> str:
            if value <= 0:
                return str(QUALITY_VALUE_OPTIONS["none"]["label"])
            return "직접입력"

        def quality_value_from_inputs(mode_label: str, raw_value: str) -> int:
            if mode_label == str(QUALITY_VALUE_OPTIONS["none"]["label"]):
                return 0
            try:
                parsed = int(raw_value.strip())
            except ValueError as exc:
                raise ValueError("품질수치는 숫자로 입력해주세요.") from exc
            if parsed <= 0:
                raise ValueError("품질수치는 1 이상의 숫자로 입력해주세요.")
            return parsed

        current_slot_count = clamp_monitor_slots(self.monitor_slot_count)
        slot_count_var = tk.StringVar(value=str(current_slot_count))
        draft_monitors = merge_custom_monitors(self.custom_monitors, current_slot_count)
        row_states: list[dict] = []

        container = tk.Frame(dialog, padx=12, pady=12)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text=(
                "4티어 고대 기준 악세 조건을 설정하세요.\n"
                "부위 / 옵션1 수치 / 옵션2 수치 / 옵션3 수치 / 품질수치를 직접 선택합니다."
            ),
            font=("Malgun Gothic", 9),
        ).pack(anchor="w", pady=(0, 8))

        slot_count_row = tk.Frame(container)
        slot_count_row.pack(fill="x", pady=(0, 8))
        tk.Label(slot_count_row, text="검색할 악세 개수", font=("Malgun Gothic", 9)).pack(side="left")
        decrease_slot_button = tk.Button(slot_count_row, text="-", width=3)
        decrease_slot_button.pack(side="left", padx=(8, 4))
        tk.Label(slot_count_row, textvariable=slot_count_var, width=4, font=("Malgun Gothic", 10, "bold")).pack(side="left")
        increase_slot_button = tk.Button(slot_count_row, text="+", width=3)
        increase_slot_button.pack(side="left", padx=(4, 6))
        tk.Label(slot_count_row, text="(1~10)", font=("Malgun Gothic", 8), fg="#666666").pack(side="left")

        scroll_frame = tk.Frame(container)
        scroll_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll_frame, highlightthickness=0)
        scrollbar = tk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        sections_container = tk.Frame(canvas)

        sections_container.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=sections_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def resize_canvas_content(event: tk.Event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        def can_scroll_canvas() -> bool:
            bbox = canvas.bbox("all")
            if bbox is None:
                return False
            content_height = bbox[3] - bbox[1]
            viewport_height = canvas.winfo_height()
            return content_height > viewport_height

        def refresh_scroll_state() -> None:
            if not can_scroll_canvas():
                canvas.yview_moveto(0.0)

        def on_mousewheel(event: tk.Event) -> None:
            if event.delta == 0 or not canvas.winfo_exists():
                return
            if not can_scroll_canvas():
                return
            canvas.yview_scroll(int(-event.delta / 120), "units")

        def scroll_canvas_mousewheel(event: tk.Event) -> str:
            on_mousewheel(event)
            return "break"

        canvas.bind("<Configure>", resize_canvas_content)
        dialog.bind("<MouseWheel>", scroll_canvas_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def refresh_row(row_state: dict) -> None:
            selected_part = part_key_from_label(row_state["part_var"].get())
            all_option_labels = part_option_labels(selected_part)

            row_state["option_1_combo"]["values"] = all_option_labels
            if row_state["option_1_var"].get() not in all_option_labels:
                row_state["option_1_var"].set(all_option_labels[0])

            option_1_key = option_key_from_label(selected_part, row_state["option_1_var"].get())
            row_state["option_2_combo"]["values"] = all_option_labels
            if row_state["option_2_var"].get() not in all_option_labels:
                row_state["option_2_var"].set(all_option_labels[0])

            option_2_key = option_key_from_label(selected_part, row_state["option_2_var"].get())
            row_state["option_3_combo"]["values"] = all_option_labels
            if row_state["option_3_var"].get() not in all_option_labels:
                row_state["option_3_var"].set(all_option_labels[0])

            option_3_key = option_key_from_label(selected_part, row_state["option_3_var"].get())

            value_1_labels = option_value_labels(option_1_key)
            row_state["value_1_combo"]["values"] = value_1_labels
            if row_state["value_1_var"].get() not in value_1_labels:
                row_state["value_1_var"].set(value_1_labels[0])

            value_2_labels = option_value_labels(option_2_key)
            row_state["value_2_combo"]["values"] = value_2_labels
            if row_state["value_2_var"].get() not in value_2_labels:
                row_state["value_2_var"].set(value_2_labels[0])

            value_3_labels = option_value_labels(option_3_key)
            row_state["value_3_combo"]["values"] = value_3_labels
            if row_state["value_3_var"].get() not in value_3_labels:
                row_state["value_3_var"].set(value_3_labels[0])

            _ = selected_part
            quality_modes = quality_mode_labels()
            row_state["quality_mode_combo"]["values"] = quality_modes
            if row_state["quality_mode_var"].get() not in quality_modes:
                row_state["quality_mode_var"].set(quality_modes[0])
            if row_state["quality_mode_var"].get() == str(QUALITY_VALUE_OPTIONS["none"]["label"]):
                row_state["quality_value_var"].set("")
                row_state["quality_value_entry"].configure(state="disabled")
            else:
                if not row_state["quality_value_var"].get().strip():
                    row_state["quality_value_var"].set("1")
                row_state["quality_value_entry"].configure(state="normal")

        def render_sections(slot_count: int) -> None:
            nonlocal draft_monitors
            for child in sections_container.winfo_children():
                child.destroy()

            draft_monitors = merge_custom_monitors(draft_monitors, slot_count)
            row_states.clear()

            for index, monitor in enumerate(draft_monitors):
                section = tk.LabelFrame(
                    sections_container,
                    text=f"검색 슬롯 {index + 1}",
                    font=("Malgun Gothic", 9),
                    padx=10,
                    pady=8,
                )
                section.pack(fill="x", pady=4)

                enabled_var = tk.BooleanVar(value=bool(monitor["enabled"]))
                part_var = tk.StringVar(value=part_label(monitor["part"]))

                option_1_var = tk.StringVar(value=OPTION_DEFINITIONS[monitor["option_1"]]["label"])
                option_2_var = tk.StringVar(value=OPTION_DEFINITIONS[monitor["option_2"]]["label"])
                option_3_var = tk.StringVar(value=OPTION_DEFINITIONS[monitor["option_3"]]["label"])
                value_1_var = tk.StringVar(value=option_value_label_for_value(monitor["option_1"], int(monitor["value_1"])))
                value_2_var = tk.StringVar(value=option_value_label_for_value(monitor["option_2"], int(monitor["value_2"])))
                value_3_var = tk.StringVar(value=option_value_label_for_value(monitor["option_3"], int(monitor["value_3"])))
                monitor_quality_value = int(monitor["quality_value"])
                quality_mode_var = tk.StringVar(value=quality_mode_for_value(monitor_quality_value))
                quality_value_var = tk.StringVar(value="" if monitor_quality_value <= 0 else str(monitor_quality_value))

                tk.Checkbutton(section, text="사용", variable=enabled_var, font=("Malgun Gothic", 9, "bold")).grid(
                    row=0, column=0, columnspan=4, sticky="w", pady=(0, 8)
                )

                tk.Label(section, text="부위", font=("Malgun Gothic", 9)).grid(row=1, column=0, sticky="w", pady=2)
                part_combo = ttk.Combobox(
                    section,
                    textvariable=part_var,
                    state="readonly",
                    values=[part_label(key) for key in PART_DEFINITIONS],
                    width=24,
                )
                part_combo.grid(row=1, column=1, sticky="w", pady=2)

                tk.Label(section, text="옵션1", font=("Malgun Gothic", 9)).grid(row=2, column=0, sticky="w", pady=2)
                option_1_combo = ttk.Combobox(section, textvariable=option_1_var, state="readonly", width=28)
                option_1_combo.grid(row=2, column=1, sticky="w", pady=2)
                tk.Label(section, text="옵션1 수치", font=("Malgun Gothic", 9)).grid(row=2, column=2, sticky="w", padx=(12, 0), pady=2)
                value_1_combo = ttk.Combobox(section, textvariable=value_1_var, state="readonly", width=22)
                value_1_combo.grid(row=2, column=3, sticky="w", pady=2)

                tk.Label(section, text="옵션2", font=("Malgun Gothic", 9)).grid(row=3, column=0, sticky="w", pady=2)
                option_2_combo = ttk.Combobox(section, textvariable=option_2_var, state="readonly", width=28)
                option_2_combo.grid(row=3, column=1, sticky="w", pady=2)
                tk.Label(section, text="옵션2 수치", font=("Malgun Gothic", 9)).grid(row=3, column=2, sticky="w", padx=(12, 0), pady=2)
                value_2_combo = ttk.Combobox(section, textvariable=value_2_var, state="readonly", width=22)
                value_2_combo.grid(row=3, column=3, sticky="w", pady=2)

                tk.Label(section, text="옵션3", font=("Malgun Gothic", 9)).grid(row=4, column=0, sticky="w", pady=2)
                option_3_combo = ttk.Combobox(section, textvariable=option_3_var, state="readonly", width=28)
                option_3_combo.grid(row=4, column=1, sticky="w", pady=2)
                tk.Label(section, text="옵션3 수치", font=("Malgun Gothic", 9)).grid(row=4, column=2, sticky="w", padx=(12, 0), pady=2)
                value_3_combo = ttk.Combobox(section, textvariable=value_3_var, state="readonly", width=22)
                value_3_combo.grid(row=4, column=3, sticky="w", pady=2)

                tk.Label(section, text="품질수치", font=("Malgun Gothic", 9)).grid(row=5, column=0, sticky="w", pady=2)
                quality_mode_combo = ttk.Combobox(section, textvariable=quality_mode_var, state="readonly", width=16)
                quality_mode_combo.grid(row=5, column=1, sticky="w", pady=2)
                quality_value_entry = tk.Entry(section, textvariable=quality_value_var, width=16)
                quality_value_entry.grid(row=5, column=2, sticky="w", padx=(12, 0), pady=2)

                for combo_widget in (
                    part_combo,
                    option_1_combo,
                    value_1_combo,
                    option_2_combo,
                    value_2_combo,
                    option_3_combo,
                    value_3_combo,
                    quality_mode_combo,
                ):
                    combo_widget.bind("<MouseWheel>", scroll_canvas_mousewheel)

                row_state = {
                    "id": monitor["id"],
                    "enabled_var": enabled_var,
                    "part_var": part_var,
                    "option_1_var": option_1_var,
                    "option_2_var": option_2_var,
                    "option_3_var": option_3_var,
                    "value_1_var": value_1_var,
                    "value_2_var": value_2_var,
                    "value_3_var": value_3_var,
                    "quality_mode_var": quality_mode_var,
                    "quality_value_var": quality_value_var,
                    "option_1_combo": option_1_combo,
                    "option_2_combo": option_2_combo,
                    "option_3_combo": option_3_combo,
                    "value_1_combo": value_1_combo,
                    "value_2_combo": value_2_combo,
                    "value_3_combo": value_3_combo,
                    "quality_mode_combo": quality_mode_combo,
                    "quality_value_entry": quality_value_entry,
                }
                row_states.append(row_state)

                refresh_row(row_state)
                for widget in (part_combo, option_1_combo, option_2_combo, option_3_combo, quality_mode_combo):
                    widget.bind("<<ComboboxSelected>>", lambda _event, current=row_state: refresh_row(current))

            canvas.after_idle(refresh_scroll_state)

        def build_empty_slot_monitor(slot_index: int) -> dict:
            return {
                "id": f"slot_{slot_index + 1}",
                "enabled": True,
                "part": "necklace",
                "option_1": "none",
                "option_2": "none",
                "option_3": "none",
                "value_1": 0,
                "value_2": 0,
                "value_3": 0,
                "quality_value": 0,
            }

        def collect_resolved_monitors(require_enabled: bool) -> list[dict] | None:
            if not row_states:
                messagebox.showerror("입력 오류", "검색 슬롯을 1개 이상 설정해주세요.")
                return None

            resolved_monitors: list[dict] = []
            for row_state in row_states:
                selected_part = part_key_from_label(row_state["part_var"].get())
                option_1 = option_key_from_label(selected_part, row_state["option_1_var"].get())
                option_2 = option_key_from_label(selected_part, row_state["option_2_var"].get())
                option_3 = option_key_from_label(selected_part, row_state["option_3_var"].get())

                selected_real_options = [key for key in (option_1, option_2, option_3) if key != "none"]
                if len(set(selected_real_options)) < len(selected_real_options):
                    messagebox.showerror("입력 오류", "옵션1/2/3은 서로 달라야 합니다.")
                    return None

                try:
                    quality_value = quality_value_from_inputs(
                        row_state["quality_mode_var"].get(),
                        row_state["quality_value_var"].get(),
                    )
                except ValueError as exc:
                    messagebox.showerror("입력 오류", str(exc))
                    return None

                resolved_monitors.append(
                    {
                        "id": row_state["id"],
                        "enabled": bool(row_state["enabled_var"].get()),
                        "part": selected_part,
                        "option_1": option_1,
                        "option_2": option_2,
                        "option_3": option_3,
                        "value_1": option_value_from_label(option_1, row_state["value_1_var"].get()),
                        "value_2": option_value_from_label(option_2, row_state["value_2_var"].get()),
                        "value_3": option_value_from_label(option_3, row_state["value_3_var"].get()),
                        "quality_value": quality_value,
                    }
                )

            if require_enabled and not any(monitor["enabled"] for monitor in resolved_monitors):
                messagebox.showerror("입력 오류", "최소 1개 이상의 악세 조건을 선택해주세요.")
                return None

            return resolved_monitors

        def update_slot_buttons() -> None:
            decrease_slot_button.configure(state="disabled" if current_slot_count <= 1 else "normal")
            increase_slot_button.configure(state="disabled" if current_slot_count >= 10 else "normal")

        def adjust_slot_count(delta: int) -> None:
            nonlocal current_slot_count, draft_monitors
            next_count = clamp_monitor_slots(current_slot_count + delta)
            if next_count == current_slot_count:
                return

            resolved_monitors = collect_resolved_monitors(require_enabled=False)
            if resolved_monitors is None:
                return

            draft_monitors = merge_custom_monitors(resolved_monitors, current_slot_count)

            if next_count > current_slot_count:
                while len(draft_monitors) < next_count:
                    draft_monitors.append(build_empty_slot_monitor(len(draft_monitors)))

            current_slot_count = next_count
            slot_count_var.set(str(current_slot_count))
            self.monitor_slot_count = current_slot_count
            self.custom_monitors = merge_custom_monitors(draft_monitors, self.monitor_slot_count)
            save_app_settings(
                self.token_var.get(),
                self.interval_var.get(),
                self.custom_monitors,
                self.monitor_slot_count,
            )
            render_sections(current_slot_count)
            update_slot_buttons()

        decrease_slot_button.configure(command=lambda: adjust_slot_count(-1))
        increase_slot_button.configure(command=lambda: adjust_slot_count(1))
        render_sections(current_slot_count)
        update_slot_buttons()

        def save() -> None:
            parsed_count = current_slot_count
            resolved_monitors = collect_resolved_monitors(require_enabled=True)
            if resolved_monitors is None:
                return

            self.monitor_slot_count = parsed_count
            self.custom_monitors = merge_custom_monitors(resolved_monitors, self.monitor_slot_count)
            save_app_settings(
                self.token_var.get(),
                self.interval_var.get(),
                self.custom_monitors,
                self.monitor_slot_count,
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
        self.log_window.geometry("960x480")

        self.log_text = scrolledtext.ScrolledText(
            self.log_window,
            wrap="none",
            font=("Consolas", 10),
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_window.bind("<Control-t>", self._emit_test_listing_log)
        self.log_text.bind("<Control-t>", self._emit_test_listing_log)

        self.log_window.protocol("WM_DELETE_WINDOW", self._close_log_window)
        self.log_force_scroll_bottom_once = True
        self.log_read_position = 0
        self.log_initial_tail_loaded = False
        self._refresh_log_window()

    def _emit_test_listing_log(self, _event: tk.Event) -> str:
        payload = self._load_or_init_test_dummy_items()
        monitor_payload = payload.get("monitor", {})
        if not isinstance(monitor_payload, dict):
            monitor_payload = {}

        label = str(
            monitor_payload.get("label", payload.get("label", "Ctrl+T"))
        ).strip() or "Ctrl+T"
        fixed_options = [
            str(option_name)
            for option_name in monitor_payload.get(
                "fixed_options",
                payload.get("fixed_options", []),
            )
            if isinstance(option_name, str) and option_name.strip()
        ]
        items = payload.get("items", [])
        if not isinstance(items, list):
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            log("TEST_DUMMY_LISTING | " + summarize(item, fixed_options))

        self._refresh_log_window()
        return "break"

    def _load_or_init_test_dummy_items(self) -> dict:
        default_payload = self.DEFAULT_TEST_DUMMY_ITEMS
        TEST_DUMMY_ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)

        if not TEST_DUMMY_ITEMS_PATH.exists():
            TEST_DUMMY_ITEMS_PATH.write_text(
                json.dumps(default_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log(f"Test dummy data initialized: {TEST_DUMMY_ITEMS_PATH}")
            return default_payload

        try:
            loaded = json.loads(TEST_DUMMY_ITEMS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            log(f"Test dummy data load failed: {exc}")
            TEST_DUMMY_ITEMS_PATH.write_text(
                json.dumps(default_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log(f"Test dummy data reset to default: {TEST_DUMMY_ITEMS_PATH}")
            return default_payload

        if not isinstance(loaded, dict):
            TEST_DUMMY_ITEMS_PATH.write_text(
                json.dumps(default_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log(f"Test dummy data format invalid. Reset: {TEST_DUMMY_ITEMS_PATH}")
            return default_payload

        return loaded

    def _close_log_window(self) -> None:
        if self.log_window is None:
            return
        self.log_window.destroy()
        self.log_window = None
        self.log_text = None
        self.log_read_position = 0
        self.log_initial_tail_loaded = False

    def _refresh_log_window(self) -> None:
        if self.log_window is None or not self.log_window.winfo_exists() or self.log_text is None:
            return

        yview_before = self.log_text.yview()
        should_follow_tail = True
        if len(yview_before) == 2:
            should_follow_tail = yview_before[1] >= 0.999
        if self.log_force_scroll_bottom_once:
            should_follow_tail = True

        if not LOG_PATH.exists():
            self.log_read_position = 0
            self.log_initial_tail_loaded = True
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", tk.END)
            self.log_text.configure(state="disabled")
            self.log_window.after(1000, self._refresh_log_window)
            return

        current_size = LOG_PATH.stat().st_size
        if not self.log_initial_tail_loaded:
            start_offset = max(
                0,
                current_size - self.LOG_WINDOW_INITIAL_READ_MAX_BYTES,
            )
            with LOG_PATH.open("rb") as log_fp:
                log_fp.seek(start_offset)
                chunk = log_fp.read()
            text = chunk.decode("utf-8", errors="replace")
            if start_offset > 0:
                text = "...(최근 로그만 표시 중)\n" + text

            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", tk.END)
            self.log_text.insert(tk.END, text)
            self.log_text.configure(state="disabled")
            self.log_read_position = current_size
            self.log_initial_tail_loaded = True
        else:
            if current_size < self.log_read_position:
                self.log_read_position = 0
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", tk.END)
                self.log_text.configure(state="disabled")

            if current_size > self.log_read_position:
                with LOG_PATH.open("rb") as log_fp:
                    log_fp.seek(self.log_read_position)
                    chunk = log_fp.read()
                append_text = chunk.decode("utf-8", errors="replace")
                if append_text:
                    self.log_text.configure(state="normal")
                    self.log_text.insert(tk.END, append_text)
                    self.log_text.configure(state="disabled")
                self.log_read_position = current_size

        if should_follow_tail:
            self.log_text.see(tk.END)
        elif len(yview_before) == 2:
            self.log_text.yview_moveto(yview_before[0])
        self.log_force_scroll_bottom_once = False

        self.log_window.after(1000, self._refresh_log_window)

    def _selected_monitors(self) -> list[dict]:
        selected = []
        for monitor in build_monitor_runtime_config(
            self.custom_monitors,
            self.monitor_slot_count,
        ):
            if bool(monitor.get("enabled", True)):
                selected.append(monitor)
        return selected

    def _is_running(self) -> bool:
        return self.worker_thread is not None and self.worker_thread.is_alive()

    def _clear_seen_history(self) -> None:
        if self._is_running():
            if self.reset_event is None:
                messagebox.showerror(
                    "초기화 실패",
                    "초기화 이벤트를 준비하지 못했습니다. 탐색을 다시 시작해주세요.",
                )
                return

            self.reset_event.set()
            self.status_var.set("찾은 악세 초기화 요청됨")
            log("Found accessory cache reset requested from UI")
            messagebox.showinfo(
                "초기화 요청 완료",
                "현재 파악된/찾은 악세를 초기화 요청했습니다.\n"
                "다음 탐색 주기에 새 기준으로 다시 저장됩니다.",
            )
            return

        confirmed = messagebox.askyesno(
            "찾은 악세 초기화",
            "현재까지 저장된 찾은 악세 기록을 초기화할까요?\n"
            "API 설정과 악세 설정은 유지됩니다.",
        )
        if not confirmed:
            return

        try:
            clear_seen_by_monitor()
        except OSError as exc:
            log(f"Failed to clear saved watch history: {exc}")
            messagebox.showerror(
                "초기화 실패",
                "탐색 기록 초기화에 실패했습니다. 파일 권한이나 사용 중 여부를 확인해주세요.",
            )
            return

        self.status_var.set("탐색 기록 초기화됨")
        log("Saved watch history cleared by user")
        messagebox.showinfo(
            "초기화 완료",
            "찾은 악세 기록을 초기화했습니다. 다음 탐색부터 새 기준으로 저장됩니다.",
        )

    def _clear_log_history(self) -> None:
        confirmed = messagebox.askyesno(
            "로그 초기화",
            "watch.log 내용을 초기화할까요?",
        )
        if not confirmed:
            return

        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOG_PATH.write_text("", encoding="utf-8")
        except OSError as exc:
            log(f"Failed to clear watch log: {exc}")
            messagebox.showerror(
                "초기화 실패",
                "로그 초기화에 실패했습니다. 파일 권한이나 사용 중 여부를 확인해주세요.",
            )
            return

        self.status_var.set("로그 초기화됨")
        self._refresh_log_window()
        messagebox.showinfo(
            "초기화 완료",
            "로그를 초기화했습니다.",
        )

    def _update_buttons(self) -> None:
        running = self._is_running()
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.clear_button.configure(state="disabled" if running else "normal")

    def _refresh_runtime_state(self) -> None:
        if self._is_running():
            self.status_var.set(f"탐색 중 (주기: {self.interval_var.get()}초)")
        else:
            if self.status_var.get().startswith("탐색 중"):
                self.status_var.set("대기 중")
        self._update_buttons()
        self.root.after(1000, self._refresh_runtime_state)

    def _poll_open_log_signal(self) -> None:
        self._consume_open_log_signal()
        self.root.after(self.OPEN_LOG_SIGNAL_POLL_MS, self._poll_open_log_signal)

    def _consume_open_log_signal(self) -> None:
        if not OPEN_LOG_SIGNAL_PATH.exists():
            return

        try:
            OPEN_LOG_SIGNAL_PATH.unlink(missing_ok=True)
        except OSError as exc:
            log(f"Failed to consume open-log signal: {exc}")
            return

        self._open_log_window()
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.deiconify()
            self.log_window.lift()
            self.log_window.focus_force()
        self.status_var.set("알림 클릭으로 로그 창 열림")

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
        self.reset_event = threading.Event()
        self.worker_thread = threading.Thread(
            target=run_watcher_loop,
            args=(self.stop_event, normalized_token, poll_seconds, monitors, self.reset_event),
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
        self.reset_event = None
        self.status_var.set("탐색 종료됨")
        self._update_buttons()

    def _handle_close(self) -> None:
        self._stop_watch()
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0
