from datetime import datetime

from .runtime_context import LOG_PATH

LAST_LOG_RESET_HOUR: str | None = None


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
