# Provider Classification Guide

Classify a single password entry to a financial service provider.

## Known Financial Providers

| Domain Pattern | Provider Key | Label | Account Type |
|---------------|--------------|-------|--------------|
{% for p in providers %}
| {{ p.domain_pattern }} | {{ p.provider_key }} | {{ p.label }} | {{ p.account_type }} |
{% endfor %}

## Classification Rules

1. **Exact domain match**: If the domain exactly matches a known pattern, use that provider (confidence ≥ 0.95).
2. **Subdomain match**: If the domain is a subdomain of a known provider (e.g., `secure.chase.com` → `chase`), map to the parent (confidence 0.88–0.94).
3. **Fuzzy name match**: If the site name contains a known provider name, use that provider (confidence 0.80–0.89).
4. **Unknown provider**: Infer based on keywords in the name:
   - Bank keywords (checking, savings, credit union, federal, etc.) → "Bank"
   - Credit card keywords (card, visa, mastercard, amex, etc.) → "Credit Card"
   - Utility keywords (electric, gas, water, energy, internet, phone, mobile) → "Utility"
   - Loan keywords (loan, student, mortgage, refinance) → "Loan"
   - Insurance keywords (insurance, coverage, policy) → "Other"
   - Default → "Bank"

## Provider Key Guidelines

- Use a slug derived from the domain or name (e.g., `mycreditunion` for `mycreditunion.com`)
- Keep it short (≤40 chars), lowercase, underscores for spaces
- Match existing known provider keys when appropriate

## Output Format

Return a JSON object:

```json
{
  "provider_key": "chase",
  "label": "Chase",
  "account_type": "Credit Card",
  "confidence": 0.95,
  "is_new_provider": false
}
```

## Notes

- If this is a genuinely new provider not in the known list, set `is_new_provider: true`
- For generic domains (e.g., `login.mybank.com` with no clear bank name), infer from domain keywords and set `is_new_provider: true`
- Confidence: ≥0.90 for clear matches, 0.70–0.89 for reasonable inference, <0.70 for weak signal
