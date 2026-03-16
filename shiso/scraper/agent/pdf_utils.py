"""
PDF text extraction and LLM-based APR parsing for statement PDFs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

PDF_TEXT_LIMIT = 32000

STATEMENT_EXTRACTION_PROMPT = """\
You are analyzing text extracted from a credit card or loan monthly statement PDF.

Extract ALL of the following fields. Return JSON only:
{
  "statement_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "minimum_payment": 0.0 or null,
  "statement_balance": 0.0 or null,
  "last_payment_amount": 0.0 or null,
  "last_payment_date": "YYYY-MM-DD or null",
  "credit_limit": 0.0 or null,
  "intro_apr_rate": 0.0 or null,
  "intro_apr_end_date": "YYYY-MM-DD or null",
  "regular_apr": 0.0 or null
}

Rules:

## due_date (CRITICAL)
Payment due date for this billing cycle. Look for:
- "Payment Due Date", "Due Date", "Minimum Payment Due By"
- "Please pay by", "Pay by"
- Usually prominently displayed near the top or in payment summary
- Convert to YYYY-MM-DD format.

## minimum_payment (CRITICAL)
Minimum amount due this cycle. Look for:
- "Minimum Payment Due", "Minimum Due", "Min Payment"
- "Minimum Amount Due", "Amount Due"
- Often near the due date in the payment summary section.

## statement_balance
Total new balance for this statement period. Look for:
- "New Balance", "Statement Balance", "Total Balance"
- "Total New Balance", "Balance Due", "Total Amount Due"
- "Closing Balance", "Total Balance as of"

## last_payment_amount / last_payment_date
Most recent payment received. Look for:
- "Payment Received", "Payments and Credits", "Payment Thank You"
- "Last Payment", "Payment(s) Received"
- The amount and date of the most recent payment in the transaction list.

## credit_limit
Total credit limit or credit line. Look for:
- "Credit Limit", "Credit Line", "Total Credit Limit", "Credit Access Line"
- "Monthly Spending Cap", "Spending Limit", "Spending Power"

## statement_date
The statement closing date. Look for:
- "Statement Closing Date", "Statement Date", "Closing Date"
- "Statement Period ... to MM/DD/YYYY" (use the end date)
- "Billing Cycle ... to MM/DD/YYYY" (use the end date)

## intro_apr_rate (CRITICAL)
The introductory/promotional APR percentage as a number (e.g. 0.00 for 0% intro APR). Search the ENTIRE text for ANY of these indicators:
- "Introductory APR", "Promotional APR", "Intro APR", "Introductory Rate"
- "0.00%", "0.000%", "0.00% introductory"
- "Rate scheduled to end" — the rate on that same line or row IS the intro rate
- Any rate alongside "scheduled to end", "through", "until", "expires", "valid through", "ends on"
- A rate in a table row where another column says "scheduled to end" or has an end date
- IMPORTANT: 0.000% or 0.00% WITH an expiration date IS a valid intro APR — return 0.0, do NOT return null.

## intro_apr_end_date (CRITICAL)
When the intro APR period ends. Look for:
- "Rate scheduled to end MM/DD/YY" or "Rate scheduled to end MM/DD/YYYY"
- "through MM/DD/YYYY", "until MM/DD/YYYY", "expires MM/DD/YYYY"
- "ends on", "valid through", "promotional period ends"
- Convert ALL dates to YYYY-MM-DD format.

## regular_apr
The standard/variable purchase APR that applies AFTER any intro period. Look for:
- "Variable APR", "Purchase APR", "Standard APR", "Regular APR"
- "Prime Rate + X.XX%", "currently XX.XX%"

## General
- APR values should be the percentage number (e.g. 29.99 not 0.2999).
- Dollar amounts should be plain numbers (e.g. 1234.56 not "$1,234.56").
- IMPORTANT: A 0.000% rate with "Rate scheduled to end" IS an intro APR. Return intro_apr_rate: 0.0, NOT null.
- PDF table extraction may garble column alignment. Look at the ENTIRE text for patterns.
- If a field is not found in the text, return null for that field.
- Return ONLY valid JSON, no explanation.
"""


def _format_table(table: list[list[str | None]]) -> str:
    """Format a pdfplumber table as a readable markdown-style table."""
    if not table:
        return ""
    rows = []
    for row in table:
        cells = [str(c).replace("\n", " ") if c else "" for c in row]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract_pdf_text(path: str | Path) -> str:
    """Extract text + tables from a PDF using pdfplumber, truncated to PDF_TEXT_LIMIT chars.

    Tables are extracted separately and appended after the page text for cleaner
    structured data (APR tables, payment summaries, etc.).
    """
    import pdfplumber

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    text_parts: list[str] = []
    total_len = 0

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
            total_len += len(page_text)

            # Extract tables separately for cleaner structured data
            tables = page.extract_tables()
            if tables:
                for j, table in enumerate(tables):
                    formatted = _format_table(table)
                    if formatted:
                        header = f"[Table page {i+1}, table {j+1}]"
                        text_parts.append(f"{header}\n{formatted}")
                        total_len += len(formatted) + len(header) + 2

            if total_len >= PDF_TEXT_LIMIT:
                break

    full_text = "\n\n".join(text_parts)
    if len(full_text) > PDF_TEXT_LIMIT:
        full_text = full_text[:PDF_TEXT_LIMIT] + "\n...(truncated)"

    logger.info("Extracted %d chars (%d pages) from PDF %s", len(full_text), min(len(text_parts), i + 1), path.name)
    return full_text


STATEMENT_FIELDS = (
    "statement_date", "due_date", "minimum_payment", "statement_balance",
    "last_payment_amount", "last_payment_date", "credit_limit",
    "intro_apr_rate", "intro_apr_end_date", "regular_apr",
)


async def extract_statement_data(
    path: str | Path,
    llm_chat_fn: Callable[..., Awaitable[dict[str, Any] | None]],
) -> dict[str, Any]:
    """Extract billing fields from a statement PDF via text extraction + LLM parsing."""
    pdf_text = extract_pdf_text(path)

    if not pdf_text.strip():
        logger.warning("PDF text is empty for %s", path)
        return {}

    messages = [
        {"role": "system", "content": STATEMENT_EXTRACTION_PROMPT},
        {"role": "user", "content": f"Statement text:\n\n{pdf_text}"},
    ]

    result = await llm_chat_fn(messages)
    if not result:
        logger.warning("LLM returned no parseable result for PDF %s", path)
        return {}

    fields = {k: result.get(k) for k in STATEMENT_FIELDS}

    logger.info("Statement extraction for %s: %s", Path(path).name, json.dumps(fields, default=str))
    return fields


# Backward compat alias
extract_apr_from_pdf = extract_statement_data
