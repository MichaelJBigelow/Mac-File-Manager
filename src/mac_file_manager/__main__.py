"""Start the app: python3 -m mac_file_manager (with src on PYTHONPATH)."""

from __future__ import annotations

import subprocess
import sys
import traceback

from . import APP_NAME

_ALERT_SCRIPT = """
on run argv
    display alert (item 1 of argv) message (item 2 of argv) as critical
end run
"""


def _show_startup_error(details: str) -> None:
    """Tell the user why the app didn't start; there is no Terminal window to show it in."""
    last_line = details.strip().splitlines()[-1] if details.strip() else "Unknown error"
    message = f"{last_line}\n\nDetails are in ~/Library/Logs/{APP_NAME}/launcher.log."
    try:
        subprocess.run(
            ["/usr/bin/osascript", "-e", _ALERT_SCRIPT, f"{APP_NAME} could not start", message],
            check=False,
            capture_output=True,
        )
    except OSError:
        pass


def run() -> None:
    try:
        from .app import main

        main()
    except Exception:
        details = traceback.format_exc()
        sys.stderr.write(details)
        _show_startup_error(details)
        sys.exit(1)


if __name__ == "__main__":
    run()
