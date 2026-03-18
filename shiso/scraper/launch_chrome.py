"""Launch the dedicated Chrome automation profile.

Opens a Chrome window using the automation profile directory from scraper.toml.
Log into sites manually in this window — sessions persist across scraper runs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib


CONFIG_PATH = Path(__file__).parent / "config" / "scraper.toml"


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch Chrome automation profile")
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Override automation profile directory",
    )
    args = parser.parse_args()

    config = load_config().get("browser", {})
    chrome_executable = config.get(
        "chrome_executable",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
    user_data_dir = args.user_data_dir or str(
        Path(config.get("user_data_dir", "data/browser-profile")).resolve()
    )

    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    command = [chrome_executable, f"--user-data-dir={user_data_dir}"]
    subprocess.Popen(command)

    print(f"[chrome] launched: {chrome_executable}")
    print(f"[chrome] profile: {user_data_dir}")
    print("[chrome] Log into sites in this window. Sessions persist for future scrapes.")


if __name__ == "__main__":
    main()
