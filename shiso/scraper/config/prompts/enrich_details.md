You are on the {{ institution }} dashboard.
Navigate to the account "{{ card_name }}"{{ mask_hint }} and extract detailed information.

Steps:
1. Click on the account named "{{ card_name }}" to open its details
2. Look for promotional APR information (intro APR, promo end date, regular APR after promo)
3. Find the credit limit or spending power
4. Find the current interest rate/APR
5. Return the extracted information

Look for fields like:
- "Intro APR", "Promotional APR", "0% intro", "0% APR for X months"
- "Go-to rate", "Standard APR", "Regular APR", "APR after promo"
- "Promo end date", "Rate valid until", "Offer expires"
- "Credit limit", "Spending power", "Credit line"
- "Interest rate", "APR", "Annual percentage rate"

Return a JSON object with these fields (use null if not found):
```json
{
  "intro_apr_rate": <float or null>,
  "intro_apr_end_date": "<YYYY-MM-DD or null>",
  "regular_apr": <float or null>,
  "promo_type": "<purchase|balance_transfer|general|null>",
  "credit_limit": <float or null>,
  "interest_rate": <float or null>
}
```

IMPORTANT:
- Stay on the account detail/summary page only — do NOT open statements, PDFs, or external pages.
- Do NOT navigate to any URL outside the dashboard.
- After extracting, navigate back to the dashboard/account summary and call done.
