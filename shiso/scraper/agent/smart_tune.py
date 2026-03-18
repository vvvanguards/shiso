"""Smart tuning — asks the LLM to decide when to stop tuning.

Instead of hardcoded convergence detection, we let the LLM look at each
run's logs and decide if more iterations would help.
"""

import asyncio
import logging
from pathlib import Path

from .analyst import analyze_run, load_provider_hints
from .llm import llm_chat
from .run import run_scrapers

logger = logging.getLogger(__name__)

DECISION_PROMPT = """You are helping decide if we should continue tuning a web scraper.

Recent tuning runs:
{run_summary}

Look at the trend. Have we hit a plateau? Are we still seeing failures that could be fixed?

Respond with ONLY a JSON object:
{{
  "should_continue": true/false,
  "reason": "brief explanation",
  "what_would_help": "what the next iteration should try, or null if converged"
}}
"""


def _format_run_summary(run_history: list[dict]) -> str:
    lines = []
    for r in run_history:
        if "error" in r:
            lines.append(f"  Run {r['run']}: ERROR — {r['error']}")
        else:
            lines.append(
                f"  Run {r['run']}: {r.get('accounts_found', 0)} accounts "
                f"({r.get('accounts_complete', 0)} complete), "
                f"{r.get('steps_taken', 0)} steps, "
                f"{r.get('failed_actions', 0)} failures, "
                f"{r.get('crises_hit', 0)} crises"
            )
            if r.get("analyst_note"):
                lines.append(f"    → analyst: {r['analyst_note']}")
    return "\n".join(lines)


async def smart_tune(
    provider_key: str,
    max_runs: int = 5,
    llm_chat_fn=None,
) -> dict:
    """Tune until the LLM says we're done, or max_runs reached."""
    if llm_chat_fn is None:
        llm_chat_fn = llm_chat

    run_history = []
    should_continue = True
    previous_metrics = None

    for i in range(1, max_runs + 1):
        print(f"\n{'='*60}")
        print(f"  TUNE RUN {i}/{max_runs} — {provider_key}")
        print(f"{'='*60}")

        hints = load_provider_hints(provider_key)
        if hints:
            hint_count = sum(len(v) for v in hints.values() if isinstance(v, list))
            print(f"  Active hints: {hint_count}")

        try:
            payload = await run_scrapers(
                targets=[provider_key],
            )
            metrics = payload.get("metrics", {}).get(provider_key, {})

            record = {"run": i, **metrics}

            print(f"\n  Run {i}: {metrics.get('accounts_found', 0)} accounts, "
                  f"{metrics.get('steps_taken', 0)} steps, "
                  f"{metrics.get('failed_actions', 0)} failures")

            run_history.append(record)

        except Exception as e:
            print(f"\n  Run {i} ERROR: {e}")
            run_history.append({"run": i, "error": str(e)})

        # Ask LLM if we should continue
        if i < max_runs:
            run_summary = _format_run_summary(run_history)
            messages = [
                {"role": "system", "content": DECISION_PROMPT.format(run_summary=run_summary)},
                {"role": "user", "content": "Should we continue tuning?"},
            ]

            print(f"\n  Asking LLM if we should continue...")
            decision = await llm_chat_fn(messages)

            if decision:
                should_continue = decision.get("should_continue", True)
                reason = decision.get("reason", "")
                what_would_help = decision.get("what_would_help")
                print(f"  LLM says: {reason}")
                if what_would_help:
                    print(f"  Next focus: {what_would_help}")
                if not should_continue:
                    print(f"  Stopping early.")
                    break

        # Brief pause between runs
        if i < max_runs and should_continue:
            print(f"\n  Waiting 5s before next run...")
            await asyncio.sleep(5)

    # Summary
    print(f"\n{'='*60}")
    print(f"  TUNING COMPLETE — {provider_key} ({len(run_history)} runs)")
    print(f"{'='*60}")
    for record in run_history:
        if "error" in record:
            print(f"  Run {record['run']}: ERROR")
        else:
            print(f"  Run {record['run']}: {record['accounts_found']} accounts, "
                  f"{record['failed_actions']} failures")

    final_hints = load_provider_hints(provider_key)
    if final_hints:
        print(f"\n  Final hints:")
        for category in ("failed_actions", "effective_patterns", "navigation_tips"):
            items = final_hints.get(category, [])
            if items:
                print(f"    {category}: {len(items)}")

    return {
        "runs": run_history,
        "total_runs": len(run_history),
        "best_run": max(run_history, key=lambda r: r.get("accounts_found", 0)),
    }


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Smart tune scraper with LLM-guided stopping")
    parser.add_argument("provider", help="Provider key to tune")
    parser.add_argument("--runs", type=int, default=5, help="Max runs (default: 5)")
    parser.add_argument("--analyst-llm", default=None, help="LLM preset")
    args = parser.parse_args()

    if args.analyst_llm:
        os.environ["ANALYST_LLM"] = args.analyst_llm

    asyncio.run(smart_tune(args.provider, args.runs))
