import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
from urllib import error

from .app_logging import log
from .core import is_valid_token, normalize_token, run_watcher_loop
from .monitors import DEFAULT_MONITORS, build_monitor_runtime_config, default_monitor_values
from .runtime_context import (
    DEFAULT_UPDATE_EXE_PATH,
    DEFAULT_UPDATE_REPO,
    LOG_PATH,
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
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("LostArkWatcher 팝업")
        self.root.geometry("420x290")
        self.root.resizable(False, False)

        app_settings = load_app_settings()
        initial_token = TOKEN if TOKEN else app_settings["token"]
        initial_interval = app_settings["poll_seconds"]

        self.token_var = tk.StringVar(value=initial_token)
        self.interval_var = tk.IntVar(value=initial_interval)
        self.status_var = tk.StringVar(value="대기 중")
        self.monitor_values = app_settings["monitor_values"]
        self.monitor_enabled: dict[str, tk.BooleanVar] = {
            monitor["key"]: tk.BooleanVar(
                value=app_settings["monitor_enabled"][monitor["key"]]
            )
            for monitor in DEFAULT_MONITORS
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

        self.clear_button = tk.Button(
            button_grid,
            text="탐색 기록 초기화",
            width=18,
            command=self._clear_seen_history,
        )
        self.clear_button.grid(row=3, column=0, columnspan=2, padx=4, pady=4, sticky="ew")

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
                self.monitor_values,
                {
                    key: var.get()
                    for key, var in self.monitor_enabled.items()
                },
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
        dialog.geometry("520x500")
        dialog.resizable(False, True)
        dialog.transient(self.root)
        dialog.grab_set()

        def preset_label_for_value(field: dict, value: int) -> str:
            for preset in field.get("preset_levels", []):
                if preset["value"] == value:
                    return str(preset["label"])
            preset_levels = field.get("preset_levels", [])
            if preset_levels:
                return str(preset_levels[0]["label"])
            return str(field["default"])

        def preset_value_for_label(field: dict, label: str) -> int | None:
            for preset in field.get("preset_levels", []):
                if preset["label"] == label:
                    return int(preset["value"])
            return None

        draft_vars = {
            monitor["key"]: tk.BooleanVar(value=self.monitor_enabled[monitor["key"]].get())
            for monitor in DEFAULT_MONITORS
        }
        draft_value_vars: dict[str, dict[str, tk.StringVar]] = {
            monitor["key"]: {
                field["id"]: tk.StringVar(
                    value=(
                        preset_label_for_value(
                            field,
                            self.monitor_values[monitor["key"]][field["id"]],
                        )
                        if field.get("preset_levels")
                        else str(self.monitor_values[monitor["key"]][field["id"]])
                    )
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
                if field.get("preset_levels"):
                    preset_labels = [preset["label"] for preset in field["preset_levels"]]
                    tk.OptionMenu(
                        section,
                        draft_value_vars[monitor["key"]][field["id"]],
                        *preset_labels,
                    ).grid(row=row_index, column=1, sticky="w", pady=2)
                else:
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
                    if field.get("preset_levels"):
                        value = preset_value_for_label(field, raw_value)
                        if value is None:
                            messagebox.showerror(
                                "입력 오류",
                                f"{monitor['label']}의 {field['label']}은 상, 중, 하 중에서 선택해주세요.",
                            )
                            return
                    else:
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
                {key: var.get() for key, var in self.monitor_enabled.items()},
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

    def _clear_seen_history(self) -> None:
        if self._is_running():
            messagebox.showerror(
                "실행 중",
                "탐색 기록을 초기화하려면 먼저 탐색을 종료해주세요.",
            )
            return

        confirmed = messagebox.askyesno(
            "탐색 기록 초기화",
            "저장된 탐색 기록을 초기화할까요?\nAPI 설정과 악세 설정은 유지됩니다.",
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
            "탐색 기록을 초기화했습니다. 다음 탐색부터 새 기준으로 저장됩니다.",
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
