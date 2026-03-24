You are on the {{ institution }} dashboard.
Open the most recent BILLING STATEMENT for this account: {{ account_name }}{{ mask_hint }}

Steps:
1. Click on the account named "{{ account_name }}" to open it
2. Find "Statements & Activity" or "Statements" link/tab and click it
3. Find the most recent monthly billing statement (has a date like "Feb 26, 2026")
4. Click to view/open the statement — it may open in browser or download
5. If it opens in browser: navigate through pages to find billing details
6. If it downloads instead: note that the file was downloaded

When viewing the statement, extract these fields (use null if not found):
- due_date: Payment due date (YYYY-MM-DD)
- minimum_payment: Minimum payment due
- statement_balance: New balance / statement balance
- credit_limit: Credit line / spending limit
- intro_apr_rate: Promotional/intro APR rate (e.g. 0.0 for 0%)
- intro_apr_end_date: When intro APR ends (YYYY-MM-DD)
- regular_apr: Standard APR after promo ends
- statement_date: Statement closing date (YYYY-MM-DD)

Look for sections like:
- "Interest Charge Calculation", "Rate Information", "APR Summary"
- Payment summary showing due date, minimum payment, balance

Return a JSON object with all found fields:
```json
{
  "due_date": "<YYYY-MM-DD or null>",
  "minimum_payment": <float or null>,
  "statement_balance": <float or null>,
  "credit_limit": <float or null>,
  "intro_apr_rate": <float or null>,
  "intro_apr_end_date": "<YYYY-MM-DD or null>",
  "regular_apr": <float or null>,
  "statement_date": "<YYYY-MM-DD or null>",
  "file_downloaded": <true if file saved to disk, false if viewed in browser>
}
```

IMPORTANT:
- Open ONE statement — the MOST RECENT billing statement only
- Skip "Important Notices" or "Account Agreement Changes" — not statements
- When done extracting, call done_action
