"""Launch a dedicated Chrome automation profile with CDP enabled."""

from __future__ import annotations

import argparse
import subprocess
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
    parser = argparse.ArgumentParser(description="Launch Chrome for dashboard scraping")
    parser.add_argument("--port", type=int, default=9222, help="Remote debugging port")
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Override automation profile directory",
    )
    args = parser.parse_args()

    config = load_config().get("browser", {})
    chrome_executable = config.get("chrome_executable", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    user_data_dir = args.user_data_dir or config.get(
        "automation_user_data_dir",
        str(Path.home() / "AppData/Local/Google/Chrome/Automation"),
    )

    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    command = [
        chrome_executable,
        f"--remote-debugging-port={args.port}",
        f"--user-data-dir={user_data_dir}",
    ]

    subprocess.Popen(command)
    print(f"[chrome] launched: {chrome_executable}")
    print(f"[chrome] profile: {user_data_dir}")
    print(f"[chrome] cdp: http://127.0.0.1:{args.port}")
    print("[chrome] sign into sites once in this profile, then reuse it for future scrapes")


if __name__ == "__main__":
    main()
