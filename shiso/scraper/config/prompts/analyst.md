You are analyzing scraper run logs for the financial website provider "{provider_key}".

LOGS:
{logs}

EXISTING HINTS (from previous analysis):
{existing_hints}

CURRENT EXTRACTION PROMPT:
{existing_extraction_prompt}

CURRENT PROVIDER CONFIG:
{provider_config}

Analyze the logs and produce updated hints, extraction guidance, AND config recommendations for future runs.

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
   - **max_steps**: If the agent used >80% of max_steps and was still extracting, increase by 50%. If the agent completed in <40% of max_steps, reduce to save time and cost. Range: 10–120.
   - **detail_max_steps**: Steps for account detail enrichment (Pass 1.5). Range: 5–30.
   - **statement_max_steps**: Steps for statement extraction (Pass 2). Range: 10–50.
   - **provider_timeout**: Overall timeout in seconds. Range: 300–3600.
   - **enrich_details**: Set to `false` if detail enrichment consistently finds nothing useful for this provider.
   - Only include keys that should change. Omit keys that are fine as-is.
   - If login failed with a provider-specific error message not in the standard list, add a failed_action: `login_pattern: <exact error text lowercased>`
   - If detail enrichment (Pass 1.5) consistently finds no promo/APR data for certain account types (e.g., checking, savings, reward_account), add a navigation_tip: `skip_enrichment_for: checking, savings, reward_account`

4. **Refine the extraction prompt when needed**
   - If the current extraction prompt is missing important provider-specific guidance, return a revised `extraction_prompt`
   - Prefer short, high-signal instructions the browser agent can follow reliably
   - If the current prompt is still good, omit `extraction_prompt`

## Rules
- Each hint item: concise, actionable one-liner (max 150 chars)
- Focus on patterns, not one-off events
- Prioritize lessons that prevent wasted steps or loops
- 3-8 items per hint category. Omit empty categories.
- The output REPLACES all existing hints — include everything that should be kept.
- `extraction_prompt`, if present, should REPLACE the current extraction prompt for this provider.
- Config patches are MERGED into existing config — only include keys to add or change.

Return JSON only:
```json
{
  "failed_actions": ["..."],
  "effective_patterns": ["..."],
  "navigation_tips": ["..."],
  "extraction_prompt": "Optional revised provider-specific extraction guidance",
  "config_patches": {
    "dashboard_url": "https://...",
    "start_url": "https://...",
    "max_steps": 75,
    "enrich_details": false
  }
}
```
