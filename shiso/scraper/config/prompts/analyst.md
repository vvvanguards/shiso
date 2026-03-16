You are analyzing scraper run logs for the financial website provider "{provider_key}".

LOGS:
{logs}

EXISTING HINTS (from previous analysis):
{existing_hints}

CURRENT PROVIDER CONFIG:
{provider_config}

Analyze the logs and produce updated hints AND config recommendations for future runs.

## Your tasks

1. **Review existing hints** — Are they still accurate? Did the scraper follow them? Did they help?
   - If a hint prevented a known failure → keep it
   - If the same failure repeated despite a hint → rewrite it more forcefully or specifically
   - If a hint is no longer relevant (the problem was fixed elsewhere) → drop it

2. **Extract new lessons** from the logs:
   - **failed_actions**: Actions that failed (clicking non-existent elements, pages that redirect, etc.)
   - **effective_patterns**: Navigation that worked (specific link text, strategies that yielded data)
   - **navigation_tips**: Provider-specific advice (where data lives, what triggers re-auth, etc.)

3. **Suggest config changes** — Based on patterns in the logs, suggest updates to the provider config:
   - **dashboard_url**: If the scraper repeatedly fails to find the account overview page, suggest the correct URL (look at URLs in the logs where multiple accounts were discovered)
   - **start_url**: If the login page URL should change
   - Only include keys that should change. Omit keys that are fine as-is.

## Rules
- Each hint item: concise, actionable one-liner (max 150 chars)
- Focus on patterns, not one-off events
- Prioritize lessons that prevent wasted steps or loops
- 3-8 items per hint category. Omit empty categories.
- The output REPLACES all existing hints — include everything that should be kept.
- Config patches are MERGED into existing config — only include keys to add or change.

Return JSON only:
```json
{
  "failed_actions": ["..."],
  "effective_patterns": ["..."],
  "navigation_tips": ["..."],
  "config_patches": {
    "dashboard_url": "https://...",
    "start_url": "https://..."
  }
}
```