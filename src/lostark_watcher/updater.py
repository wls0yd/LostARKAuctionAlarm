import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib import error, request

from .app_logging import log
from .runtime_context import (
    DEFAULT_UPDATE_REF,
    GITHUB_API_BASE,
    UPDATE_MARKER_FILE,
    runtime_dir,
)
from .state import save_installed_exe_blob_sha


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
    _ = repo
    env_ref = os.environ.get("LOSTARK_UPDATE_REF", "").strip()
    if env_ref:
        return env_ref
    return DEFAULT_UPDATE_REF


def fetch_latest_exe_info(repo: str, ref: str, exe_path: str) -> dict | None:
    release_api_path = "latest"
    if ref and ref.lower() != "latest":
        release_api_path = f"tags/{ref}"

    try:
        payload = github_api_get_json(
            f"{GITHUB_API_BASE}/repos/{repo}/releases/{release_api_path}"
        )
    except error.HTTPError as exc:
        if exc.code == 404:
            log(
                "Auto-update: release or tag not found "
                f"({repo}, ref={ref})"
            )
            return None
        raise

    assets = payload.get("assets")
    if not isinstance(assets, list):
        log("Auto-update: release assets payload is invalid")
        return None

    normalized_asset_name = exe_path.strip()
    for asset in assets:
        if not isinstance(asset, dict):
            continue

        asset_name = str(asset.get("name", "")).strip()
        if asset_name != normalized_asset_name:
            continue

        download_url = str(asset.get("browser_download_url", "")).strip()
        asset_id = str(asset.get("id", "")).strip()
        if not download_url or not asset_id:
            log("Auto-update: release asset is missing download URL or id")
            return None

        return {
            "blob_sha": asset_id,
            "download_url": download_url,
        }

    log(
        "Auto-update: release asset not found "
        f"({repo}, ref={ref}, asset={normalized_asset_name})"
    )
    return None


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

    escaped_blob_sha = blob_sha.replace('"', "")

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
start "" "%TARGET%"
del /Q "%~f0" >nul 2>nul
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
