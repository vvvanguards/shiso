"""Shiso CLI — personal automation platform."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="shiso",
    help="shiso: personal automation platform",
    no_args_is_help=True,
)
console = Console()

PID_FILE = Path("data/.shiso_pids")


def _save_pid(name: str, pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PID_FILE.open("a") as f:
        f.write(f"{name}:{pid}\n")


def _load_pids() -> list[tuple[str, int]]:
    if not PID_FILE.exists():
        return []
    entries = []
    for line in PID_FILE.read_text().splitlines():
        if ":" in line:
            name, pid_str = line.rsplit(":", 1)
            try:
                entries.append((name, int(pid_str)))
            except ValueError:
                pass
    return entries


def _clear_pids() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


# ---------------------------------------------------------------------------
# shiso scrape
# ---------------------------------------------------------------------------

@app.command()
def scrape(
    targets: Optional[list[str]] = typer.Argument(None, help="Provider keys (default: all enabled)"),
    statements: bool = typer.Option(False, "--statements", help="Download statement PDFs"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Pause for 2FA/CAPTCHA instead of skipping"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Filter to specific account name or mask"),
    agent_llm: Optional[str] = typer.Option(None, "--agent-llm", help="LLM preset for browser agent"),
    analyst_llm: Optional[str] = typer.Option("openrouter", "--analyst-llm", help="LLM preset for analyst"),
) -> None:
    """Run the scraper for one or more providers."""
    from dotenv import load_dotenv
    load_dotenv()

    if agent_llm:
        os.environ["AGENT_LLM"] = agent_llm
    if analyst_llm:
        os.environ["ANALYST_LLM"] = analyst_llm

    from shiso.scraper.agent.run import main as run_main
    asyncio.run(run_main(
        targets=targets or None,
        download_statements=statements,
        interactive=interactive,
        account_filter=account,
    ))


# ---------------------------------------------------------------------------
# shiso chrome
# ---------------------------------------------------------------------------

@app.command()
def chrome() -> None:
    """Launch Chrome with the automation profile for manual login."""
    import subprocess
    from shiso.scraper.launch_chrome import load_config
    from pathlib import Path

    config = load_config().get("browser", {})
    chrome_executable = config.get(
        "chrome_executable",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
    user_data_dir = str(
        Path(config.get("user_data_dir", "data/browser-profile")).resolve()
    )
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    subprocess.Popen([chrome_executable, f"--user-data-dir={user_data_dir}"])
    console.print(f"[green]Chrome launched[/green] with profile: {user_data_dir}")
    console.print("[dim]Log into sites here. Sessions persist for future scrapes.[/dim]")


# ---------------------------------------------------------------------------
# shiso providers
# ---------------------------------------------------------------------------

@app.command()
def providers() -> None:
    """List configured providers."""
    from dotenv import load_dotenv
    load_dotenv()

    from shiso.scraper.agent.run import load_accounts

    accounts = load_accounts()
    table = Table(title="Providers")
    table.add_column("Key", style="bold")
    table.add_column("Logins")
    table.add_column("Labels")

    for key, logins in sorted(accounts.items()):
        labels = ", ".join(login.get("label", key) for login in logins)
        table.add_row(key, str(len(logins)), labels)

    console.print(table)


# ---------------------------------------------------------------------------
# shiso auth
# ---------------------------------------------------------------------------

@app.command()
def auth(
    action: str = typer.Argument("status", help="'status' or 'login'"),
    targets: Optional[list[str]] = typer.Argument(None, help="Provider keys"),
    analyst_llm: Optional[str] = typer.Option("openrouter", "--analyst-llm"),
) -> None:
    """Check auth status or interactively log in."""
    from dotenv import load_dotenv
    load_dotenv()

    if analyst_llm:
        os.environ["ANALYST_LLM"] = analyst_llm

    sys.argv = ["shiso-auth", action] + (targets or [])
    from shiso.scraper.agent import auth as auth_module
    auth_module.main()


# ---------------------------------------------------------------------------
# shiso tune
# ---------------------------------------------------------------------------

@app.command()
def tune(
    provider: str = typer.Argument(..., help="Provider key to tune hints for"),
    analyst_llm: Optional[str] = typer.Option("openrouter", "--analyst-llm"),
) -> None:
    """Tune scraper hints for a provider."""
    from dotenv import load_dotenv
    load_dotenv()

    if analyst_llm:
        os.environ["ANALYST_LLM"] = analyst_llm

    sys.argv = ["shiso-tune", provider]
    from shiso.scraper.agent import smart_tune
    asyncio.run(smart_tune.main(provider))


# ---------------------------------------------------------------------------
# shiso start
# ---------------------------------------------------------------------------

@app.command()
def start(
    frontend: bool = typer.Option(True, "--frontend/--no-frontend", help="Start the frontend dev server"),
) -> None:
    """Start all shiso services (API, worker, frontend)."""
    import time

    _clear_pids()

    # Start frontend
    if frontend:
        frontend_dir = Path("shiso/dashboard/frontend")
        if frontend_dir.exists():
            p = subprocess.Popen(
                [sys.executable, "-m", "npm", "run", "dev"],
                cwd=str(frontend_dir),
            )
            _save_pid("frontend", p.pid)
            console.print("[green]Frontend[/green] started on port 5175")

    # Start worker
    p = subprocess.Popen(
        [sys.executable, "-m", "shiso.scraper.worker"],
    )
    _save_pid("worker", p.pid)
    console.print("[green]Worker[/green] started")

    # Start API (block so we can Ctrl+C)
    console.print("[green]API[/green] starting on port 8002...")
    console.print("[dim]Press Ctrl+C to stop all services[/dim]")
    try:
        p = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "shiso.dashboard.main:app", "--reload", "--port", "8002"],
        )
        _save_pid("api", p.pid)
        p.wait()
    except KeyboardInterrupt:
        stop(silent=False)


# ---------------------------------------------------------------------------
# shiso stop
# ---------------------------------------------------------------------------

@app.command()
def stop(silent: bool = typer.Option(False, "--silent", "-s")) -> None:
    """Stop all running shiso services."""
    import psutil

    stopped = 0

    # Kill saved PIDs
    for name, pid in _load_pids():
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=3)
            stopped += 1
            if not silent:
                console.print(f"Stopped {name} (PID {pid})")
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass

    # Kill uvicorn on port 8002
    for conn in psutil.net_connections():
        if conn.laddr.port == 8002 and conn.status == "LISTEN":
            try:
                proc = psutil.Process(conn.pid)
                proc.terminate()
                proc.wait(timeout=3)
                stopped += 1
                if not silent:
                    console.print(f"Stopped API (PID {conn.pid})")
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                pass

    # Kill npm processes (frontend dev server)
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] == "node" and proc.info["cmdline"]:
                cmdline = " ".join(proc.info["cmdline"])
                if "npm" in cmdline and "dev" in cmdline:
                    proc.terminate()
                    proc.wait(timeout=3)
                    stopped += 1
                    if not silent:
                        console.print(f"Stopped frontend (PID {proc.info['pid']})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _clear_pids()
    if not silent:
        console.print(f"[green]Done[/green] - stopped {stopped} service(s)")


def main():
    app()


if __name__ == "__main__":
    main()
