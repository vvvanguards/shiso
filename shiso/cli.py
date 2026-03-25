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
    sync_type: str = typer.Option("auto", "--sync-type", "-t", help="Sync type: auto, full, balance, statements"),
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

    from shiso.scraper.models.sync_type import SyncType
    from shiso.scraper.agent.run import main as run_main
    asyncio.run(run_main(
        targets=targets or None,
        download_statements=statements,
        interactive=interactive,
        account_filter=account,
        sync_type=SyncType(sync_type),
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
# shiso match-test
# ---------------------------------------------------------------------------

@app.command()
def match_test(
    csv_path: str = typer.Argument(..., help="Path to Chrome passwords CSV"),
    use_llm: bool = typer.Option(False, "--llm", help="Use LLM for unmatched domains"),
    limit: int = typer.Option(0, "--limit", "-n", help="Limit LLM calls to N domains (0 = all)"),
    analyst_llm: Optional[str] = typer.Option(None, "--analyst-llm"),
) -> None:
    """Test provider matching on a CSV file.

    Use --llm to also call LLM for unmatched domains.
    Use --limit to cap LLM calls (e.g., -n 5 to test just 5 domains).
    """
    from dotenv import load_dotenv
    load_dotenv()

    if analyst_llm:
        os.environ["ANALYST_LLM"] = analyst_llm

    console.print(f"[cyan]ANALYST_LLM = {os.environ.get('ANALYST_LLM', 'not set')}[/cyan]")

    from pathlib import Path
    from shiso.scraper.services.password_import import parse_csv, aggregate_by_domain
    from shiso.scraper.services.provider_matcher import match_providers_sync, match_providers

    path = Path(csv_path)
    if not path.exists():
        console.print(f"[red]File not found: {csv_path}[/red]")
        raise typer.Exit(1)

    content = path.read_text(encoding="utf-8-sig")
    rows = parse_csv(content)
    console.print(f"[cyan]Parsed {len(rows)} rows from CSV[/cyan]")

    aggregated = aggregate_by_domain(rows)
    console.print(f"[cyan]Aggregated into {len(aggregated)} unique domains[/cyan]")

    if use_llm:
        console.print(f"[cyan]Matching with LLM (limit={limit or 'all'})...[/cyan]")
        result = asyncio.run(match_providers(rows, llm_limit=limit if limit > 0 else None))
    else:
        console.print(f"[cyan]Local-only matching...[/cyan]")
        result = match_providers_sync(rows)

    mappings = result.get("mappings", [])
    summary = result.get("summary", {})
    console.print(f"\n[green]Match complete![/green]")
    console.print(f"  Total: {summary.get('total', len(mappings))}")
    console.print(f"  High confidence (>=90%): {summary.get('high_confidence', 0)}")
    console.print(f"  Needs review: {summary.get('needs_review', 0)}")
    console.print(f"  LLM calls: {summary.get('llm_calls', 0)}")

    table = Table(title="Sample Matches (first 15)")
    table.add_column("Row", style="dim")
    table.add_column("Domain", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Conf", style="magenta")
    table.add_column("Match", style="dim")

    for m in mappings[:15]:
        table.add_row(
            str(m.get("row_id", "")),
            m.get("domain", ""),
            f"{m.get('provider_key', '')} ({m.get('label', '')})",
            m.get("account_type", ""),
            f"{m.get('confidence', 0):.0%}",
            m.get("match_type", ""),
        )

    console.print(table)

    unmatched = [m for m in mappings if m.get("is_new_provider")]
    if unmatched:
        console.print(f"\n[yellow]Unmatched domains ({len(unmatched)}):[/yellow]")
        unmatched_domains = sorted(set(m.get("domain", "") for m in unmatched))
        for d in unmatched_domains[:20]:
            console.print(f"  [dim]{d}[/dim]")
        if len(unmatched_domains) > 20:
            console.print(f"  [dim]... and {len(unmatched_domains) - 20} more[/dim]")


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
