This is an American Express account dashboard.

Amex-specific tips:
- Product names include "Gold Card", "Hilton Honors", "Blue Cash", "Personal Loan", etc.
- Use the `/overview` page as the source of truth for the account list
- The overview may group cards vs loans — check both sections
- During this extraction pass, stay on the overview page and do not click into individual account detail pages
- Expand hidden accounts with "View more accounts", tabs, collapsed sections, carousels, or pagination before extracting
- If a field is only visible on detail pages or statements, leave it null here and let later enrichment passes fill it in

Promo APR:
- Capture promo APR fields only when they are already visible on the overview page
- If the overview does not show promo APR details, leave them null so detail enrichment or statement parsing can populate them later
