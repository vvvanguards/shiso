"""Shiso CLI — personal automation platform."""

from __future__ import annotations

import asyncio
import os
import sys
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


def main():
    app()


if __name__ == "__main__":
    main()
