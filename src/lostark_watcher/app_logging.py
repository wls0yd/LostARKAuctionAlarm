from datetime import datetime

from .runtime_context import LOG_PATH

LAST_LOG_RESET_BUCKET: str | None = None


def _current_three_hour_bucket(now: datetime) -> str:
    date_part = now.strftime("%Y-%m-%d")
    bucket = now.hour // 3
    return f"{date_part} {bucket:02d}"


def log(message: str) -> None:
    global LAST_LOG_RESET_BUCKET

    now = datetime.now()
    current_bucket = _current_three_hour_bucket(now)
    if LAST_LOG_RESET_BUCKET is None:
        LAST_LOG_RESET_BUCKET = current_bucket
    elif current_bucket != LAST_LOG_RESET_BUCKET:
        LOG_PATH.write_text("", encoding="utf-8")
        LAST_LOG_RESET_BUCKET = current_bucket

    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
