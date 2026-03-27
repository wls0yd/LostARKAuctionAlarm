import sys

from lostark_watcher.core import run_cli_watcher
from lostark_watcher.ui import WatcherPopup


def main() -> int:
    if "--cli" in sys.argv:
        return run_cli_watcher()
    app = WatcherPopup()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
