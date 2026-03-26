# Contract-Based Scraping Validation

## Problem

Scrapes are validated only by whether they succeed or fail — not by whether they returned the right data. A scrape can "succeed" (no exceptions, agent completed) but return zero accounts, or miss promo APR fields, or return obviously wrong values. There's no baseline of what a successful scrape for Amex should look like.

The existing extraction prompts (`amex.md`, `chase.md`) define what to extract in prose. The goal is to codify that as machine-readable **contracts** that can validate scrape outputs without being fragile to HTML changes.

## Design Principles

1. **Prompts are the source of truth** — the `.md` extraction prompts are human-readable and updated by humans. The contract JSON is a machine-readable distillation of the same intent.
2. **Validation is per-field, not per-blob** — don't compare HTML snapshots. Compare extracted fields. A CSS class change shouldn't break 50 tests.
3. **Failures are actionable** — validator returns field-level error messages, not just pass/fail.
4. **Contracts live with the code** — committed to the repo, reviewed with code, versioned together.
5. **Live scraping is the source of truth for "expected"** — baseline expected data comes from a scrape run that was manually verified to be correct.

---

## Directory Structure

```
shiso/scraper/
  contracts/
    __init__.py
    validator.py          # Validation engine
    schemas.py            # Pydantic models for contract JSON + StatementData
    generator.py          # StatementData-to-contract auto-generator
    base.json             # Universal fields all providers must return
    amex.json
    chase.json
    discover.json
    american_water.json
    nipsco.json

  # Statement extraction — reuses existing analyst infrastructure
  # pymupdf for text extraction, analyst LLM for structured extraction

tests/
  test_contracts.py       # Test harness
  test_contract_generator.py  # Generator unit tests
  fixtures/
    # Frozen "known good" scrape results for offline testing
    amex_scrape_2026-01-15.json
    chase_scrape_2026-01-20.json
    # Parsed statement data (ground truth for contract generation)
    amex_statement_2026-02_parsed.json
    chase_statement_2026-02_parsed.json
```

---

## Contract JSON Schema

```jsonc
{
  "provider": "amex",
  "description": "American Express credit cards, loans, and rewards programs",
  "version": "1.0.0",
  "auto_generated": false,
  "contract_mode": "current",  // "snapshot" | "current"
  "account_types": ["credit_card", "checking", "savings", "personal_loan", "rewards"],
  // Accounts known to exist for this provider — used for add/close detection
  "known_accounts": [
    { "name": "American Express Gold Card", "account_type": "credit_card" },
    { "name": "American Express Platinum Card", "account_type": "credit_card" }
  ],
  "fields": {
    // Fields that MUST be present and non-null after every successful scrape
    "required": [
      {
        "name": "account_name",
        "type": "string",
        "min_length": 1,
        "description": "Display name e.g. 'American Express Gold Card'"
      },
      {
        "name": "current_balance",
        "type": "float",
        "description": "Current outstanding balance in dollars"
      },
      {
        "name": "account_type",
        "type": "string",
        "description": "One of: checking, savings, credit_card, personal_loan, rewards"
      }
    ],
    // Fields that MAY be present. If present, must pass type check.
    "optional": [
      {
        "name": "account_mask",
        "type": "string",
        "pattern": "^[0-9]{4}$",
        "description": "Last 4 digits of account number"
      },
      {
        "name": "due_date",
        "type": "string",
        "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
        "description": "ISO date string"
      },
      {
        "name": "minimum_payment",
        "type": "float",
        "description": "Minimum payment due"
      },
      {
        "name": "credit_limit",
        "type": "float",
        "description": "Credit limit for credit card accounts"
      },
      {
        "name": "intro_apr_rate",
        "type": "float",
        "nullable": true,
        "description": "Promotional APR percentage (e.g. 0.0 for 0% intro)"
      },
      {
        "name": "intro_apr_end_date",
        "type": "string",
        "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
        "nullable": true,
        "description": "ISO date when intro APR expires"
      },
      {
        "name": "regular_apr",
        "type": "float",
        "nullable": true,
        "description": "Standard APR after promo period"
      },
      {
        "name": "promo_type",
        "type": "string",
        "nullable": true,
        "description": "e.g. 'balance_transfer', 'purchase', 'dual'"
      },
      {
        "name": "rewards_balance",
        "type": "float",
        "nullable": true,
        "description": "Rewards points/miles balance"
      },
      {
        "name": "rewards_unit",
        "type": "string",
        "nullable": true,
        "description": "e.g. 'points', 'miles', '%'"
      }
    ]
  },
  // Semantic rules — constraints beyond type checking
  "semantic_rules": [
    {
      "description": "current_balance should be non-negative for credit cards",
      "condition": "account_type == 'credit_card'",
      "field": "current_balance",
      "rule": "value >= 0"
    },
    {
      "description": "intro_apr_end_date must be in the future if intro_apr_rate is set",
      "condition": "intro_apr_rate is not null",
      "field": "intro_apr_end_date",
      "rule": "parsed_date > today"
    },
    {
      "description": "rewards_balance must be non-negative",
      "field": "rewards_balance",
      "rule": "value >= 0"
    }
  ],
  // Provider-specific expectations
  "expectations": {
    "min_accounts": 1,
    "account_types_that_must_have_promo_apr": ["credit_card"],
    "at_least_one_field_from": ["rewards_balance", "credit_limit"]
  },
  // Contract mode behavior
  "contract_mode": {
    "mode": "current",   // "snapshot" | "current"
    // snapshot: known_accounts is the authoritative list; missing accounts = failure
    // current: missing accounts = warning (may be closed), new accounts = warning (review)
    "account_count_strict": false  // true only in snapshot mode
  }
}
```

### Field Type Mappings

| `type` in JSON | Python/Pydantic type |
|----------------|---------------------|
| `string` | `str` |
| `float` | `float` |
| `int` | `int` |
| `bool` | `bool` |
| `date` | `str` (ISO 8601 format enforced via `pattern`) |

---

## Validator Service (`validator.py`)

### Public API

```python
from .validator import ContractValidator, ValidationResult, FieldError

# Simple usage
validator = ContractValidator()
result = validator.validate(scrape_result: ScrapeResult, contract_path: str) -> ValidationResult

# Per-field errors
for field_error in result.field_errors:
    print(f"{field_error.field}: {field_error.message}")

# Summary
print(result.is_valid)
print(result.summary)
```

### `ValidationResult`

```python
@dataclass
class ValidationResult:
    is_valid: bool
    provider: str
    contract_version: str
    accounts_validated: int
    field_errors: list[FieldError]
    semantic_errors: list[SemanticError]
    warnings: list[str]           # e.g. "expected at least 1 account, got 0"
    account_events: list[AccountEvent]  # new/missing account discoveries

    @property
    def summary(self) -> str: ...

@dataclass
class AccountEvent:
    kind: str           # "new_account_discovered" | "account_missing" | "account_closed"
    account_name: str
    message: str        # human-readable: "American Express Gold Card appeared in scrape but not in known_accounts"

@dataclass
class FieldError:
    account_index: int
    field: str
    expected_type: str
    actual_value: Any
    message: str

@dataclass
class SemanticError:
    account_index: int
    rule: str
    field: str
    actual_value: Any
    message: str
```

### Validation Steps

1. **Load contract** — read JSON, validate schema with Pydantic model
2. **Check account count** — `expectations.min_accounts`
3. **For each account returned:**
   - Check required fields present and non-null
   - Type-check all present fields against `field.type`
   - Pattern-check string fields (e.g. date format)
   - Evaluate semantic rules in dependency order
4. **Return `ValidationResult`** with all errors and warnings

### Validation Modes

The validator supports two modes:

**`mode='strict'`** (default) — fail on any missing required field or type mismatch.

**`mode='lenient'`** — collect all errors but only fail on:
- Missing `account_name` or `current_balance` (the two core fields)
- `current_balance` being non-numeric

This allows the scraper to return partial data without the whole scrape being marked failed.

---

## Test Harness (`tests/test_contracts.py`)

### Test Structure

```python
class TestContractValidation:
    """Validate live scrape results against contracts."""

    @pytest.mark.parametrize("provider", ["amex", "chase", "discover"])
    def test_scrape_result_conforms_to_contract(self, provider):
        """
        Run a live scrape and validate the result against the contract.
        Uses the existing scraper infrastructure — no mocking.
        """
        result = scrape_provider(provider)  # actual scrape
        contract = load_contract(provider)

        validator = ContractValidator(mode="lenient")
        validation = validator.validate(result, contract)

        assert validation.is_valid, (
            f"{provider} scrape failed contract validation:\n"
            + "\n".join(f"  - {e.field}: {e.message}" for e in validation.field_errors)
        )

    @pytest.mark.parametrize("provider", ["amex", "chase", "discover"])
    def test_required_fields_are_present(self, provider):
        """Each account must have account_name, current_balance, account_type."""
        result = scrape_provider(provider)
        contract = load_contract(provider)

        for i, account in enumerate(result.accounts):
            for field_spec in contract["fields"]["required"]:
                assert account.get(field_spec["name"]) is not None, (
                    f"Account {i} missing required field: {field_spec['name']}"
                )

    @pytest.mark.parametrize("provider", ["amex", "chase"])
    def test_credit_cards_have_balance_and_apr(self, provider):
        """Credit card accounts should have current_balance and some APR field."""
        result = scrape_provider(provider)
        contract = load_contract(provider)

        credit_cards = [a for a in result.accounts if a.get("account_type") == "credit_card"]
        for card in credit_cards:
            assert card.get("current_balance") is not None
            # At least one of regular_apr or intro_apr_rate should be present
            assert card.get("regular_apr") is not None or card.get("intro_apr_rate") is not None
```

### Baseline Fixtures (Optional Offline Mode)

For CI / offline testing, store a "manually verified correct" scrape result:

```python
class TestContractValidationOffline:
    """Use frozen baseline fixtures instead of live scraping."""

    @pytest.fixture(params=["amex_baseline.json", "chase_baseline.json"])
    def baseline_result(self, request):
        return json.load(open(f"tests/fixtures/{request.param}"))

    def test_baseline_conforms_to_contract(self, baseline_result):
        ...
```

The baseline is updated when a scrape is manually verified as correct — this is the "known good" state. It's versioned in git so PRs can show what changed in the expected output.

---

## Adding a New Provider Contract

```
1. Write extraction prompt (config/prompts/extraction/amex.md)
      ↓
2. Download 2-3 months of statements
      ↓
3. pymupdf → raw text → analyst.extract_from_statement() → StatementData
      ↓
4. ContractGenerator.from_directory() → amex.json (auto-generated, contract_mode="current")
      ↓
5. Human review — adjust required/optional, tighten/widen tolerances, set known_accounts
      ↓
6. Run live scrape → validate against contract
      ↓
7. If scrape passes and values in range → contract confirmed
      ↓
8. Add to test_contracts.py — amex is now in the regression suite
      ↓
9. Commit: extraction prompt + contract + tests reviewed together
```

**Contract modes explained:**

| Mode | When to use | Account matching |
|------|------------|-----------------|
| `snapshot` | Pinning against a specific month's view | Exact match — missing accounts = failure |
| `current` | Ongoing regression testing | Best effort — missing accounts = warning, new accounts = warning |

Start in `current` mode. Switch to `snapshot` when you want a fixed reference point (e.g., "this is what we saw as of February 2026").

---

## Semantic Rules Engine

Semantic rules are simple expression strings evaluated per-account:

| Rule syntax | Example | Evaluation |
|-------------|---------|------------|
| `value >= 0` | `current_balance >= 0` | Pass if true |
| `value > other` | `due_date > today` | Pass if date is in future |
| `value in [...]` | `account_type in ['credit_card', 'checking']` | Pass if in list |
| `value implies` | `intro_apr_rate implies intro_apr_end_date` | If A is set, B must also be set |

Rules are evaluated after all type/required checks pass (no point evaluating semantics on null values).

Implementation: a simple `eval()` on a sandboxed dict of field values + built-in functions (`today()`, `parsed_date()`). No arbitrary code execution — just the rule expressions defined in the contract JSON.

---

## What This Does NOT Do

- **Does NOT compare HTML** — no DOM snapshot maintenance
- **Does NOT mock the scraper** — tests run against real scrape output (or frozen baselines)
- **Does NOT guarantee correctness** — if the contract says `current_balance: float` and the scraper invents a float, that's valid per-contract even if the number is wrong
- **Does NOT replace integration tests** — it's a complementary layer that catches "wrong shape" errors that unit tests miss

## What This DOES Do

- **Catches field-level regressions** — if Amex changes their page and `account_name` goes missing, the contract catches it immediately
- **Enforces provider contracts** — each provider's contract is the definition of "a successful scrape for that provider"
- **Documents expected output** — the contract JSON is the canonical answer to "what should Amex return?"
- **Enables confident refactoring** — change the scraper, run contracts, if they pass the shape is right

---

## Relationship to Extraction Prompts and the Analyst

The contract is driven by three converging sources:

```
Extraction prompt (amex.md)          Statement (stmt_amex_2026-02.pdf)
    ↓ human intent                       ↓ analyst.extract_from_statement()
Schema intent                       Actual values from statement
    ↓                                    ↓
    ──────────→ Contract (amex.json) ←─────────
                      ↓
              Validated against
                      ↓
               ScrapeResult
                      ↓
               Analyst agent runs
                      ↓
              Refined extraction_prompt (fed back into amex.md prompt)
```

The **analyst's feedback loop** is the third source:

After each scrape, the analyst agent reviews the run log and returns a refined `extraction_prompt` — specifically improved instructions for how to extract that provider's accounts. Over successive runs this converges toward the optimal extraction behavior for each provider.

This refined prompt is the best possible answer to "what should Amex return?" — it's derived from actual scrape experience, not just human intuition. The `contract_mode: "current"` contract uses the analyst's accumulated extraction knowledge alongside statement ground truth to define what correct looks like.

The flow for a mature provider:
1. Initial extraction prompt (`amex.md`) written by hand
2. Statement parsed → `StatementData` → contract with initial `known_accounts`
3. Scrape runs → analyst refines `extraction_prompt`
4. After each run, analyst's refined prompt feeds back into the extraction prompt
5. Contract `known_accounts` grows as new accounts are discovered
6. Periodic statement re-parse updates `observed_value` ranges
7. Contract converges — less changes needed over time

---

## Auto-Generate Contracts from Statements

Statements are the ground truth. They contain the actual data — balances, APRs, due dates — in a stable, human-readable format. A parsed statement tells us:
1. **What fields exist** for a given provider
2. **What values are plausible** for each field

So instead of writing `amex.json` by hand, run the statement parser on a downloaded PDF → the output is the contract (or the basis for it).

### The Two-Level Contract

```
Statement (ground truth)
    ↓ parsed
StatementData: { balance: 4231.17, apr: 29.99, due_date: "2026-04-15", ... }
    ↓ contract generator
Contract:
    - field schema (from observed keys + inferred types)
    - expected_value ranges (balance: 4231 ± 2%, apr: 29.99 ± 0.1)
    ↓ used to validate
ScrapeResult: { balance: 4231.17, apr: 29.99, ... }
```

### `generator.py` — Statement to Contract

```python
from .generator import ContractGenerator, StatementData

class ContractGenerator:
    """Convert parsed statement data into a provider contract."""

    def from_statement(
        self,
        statement_data: StatementData,
        provider: str,
        tolerance: float = 0.02,
    ) -> dict:
        """
        Generate a contract from parsed statement data.

        tolerance: acceptable variance from observed values for
        numeric fields (0.02 = 2% by default).
        """

    def from_directory(
        self,
        statement_dir: Path,
        provider: str,
    ) -> dict:
        """Merge multiple statement parses for the same provider."""
```

### `StatementData` — Parsed Output from PDF

Statements are already downloaded per-account (`b7b8a9a`) with consistent naming. The parser extracts the structured fields:

```python
@dataclass
class StatementData:
    provider: str
    account_name: str
    statement_date: str          # YYYY-MM-DD
    current_balance: float
    minimum_payment: float | None = None
    due_date: str | None = None
    intro_apr_rate: float | None = None
    intro_apr_end_date: str | None = None
    regular_apr: float | None = None
    promo_type: str | None = None
    credit_limit: float | None = None
    last_payment_amount: float | None = None
    last_payment_date: str | None = None
    rewards_balance: float | None = None
    rewards_unit: str | None = None
    raw_text: str = ""          # full parsed text for debugging
```

### Auto-Generated Contract Shape

```jsonc
{
  "provider": "amex",
  "auto_generated": true,
  "source_statement": "stmt_amex_2026-02.pdf",
  "generated_at": "2026-03-25",
  "version": "1.0.0",
  "account_types": ["credit_card"],
  "fields": {
    "required": [
      {
        "name": "current_balance",
        "type": "float",
        "observed_value": 4231.17,
        "expected_range": [4150.0, 4310.0],
        "tolerance": 0.02
      },
      {
        "name": "account_type",
        "type": "string",
        "observed_value": "credit_card"
      }
    ],
    "optional": [
      {
        "name": "due_date",
        "type": "date",
        "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
        "observed_value": "2026-04-15"
      },
      {
        "name": "regular_apr",
        "type": "float",
        "observed_value": 29.99,
        "expected_range": [29.0, 31.0]
      },
      {
        "name": "minimum_payment",
        "type": "float",
        "observed_value": 135.0,
        "nullable": true
      }
    ]
  },
  "semantic_rules": [
    {
      "field": "current_balance",
      "rule": "value >= 0",
      "observed": true
    },
    {
      "description": "intro_apr_end_date must be in the future if intro_apr_rate is set",
      "condition": "intro_apr_rate is not null",
      "field": "intro_apr_end_date",
      "rule": "parsed_date > today"
    }
  ]
}
```

Key addition: `observed_value` and `expected_range`. The contract encodes not just the schema but the **plausible range** of each numeric value, derived from the statement. A scrape that returns `current_balance = 100.00` for an account that showed `$4,231.17` on the statement would fail even if the type/required checks pass.

### Tolerance and Drift

The tolerance window (default 2%) handles:
- Minor rounding differences between scrape and statement
- Interest accrual between statement date and scrape date
- Small balance fluctuations

If tolerance is exceeded, the validator emits a **warning** (not a failure) in `lenient` mode, or a **failure** in `strict` mode. A 10% discrepancy is worth flagging but might be legitimate (payments posted since statement).

For providers with multiple accounts, run `from_directory()` to merge observations across several months of statements — the union of all observed fields becomes the contract, and ranges widen to cover seasonal variation.

### Statement Extraction via Existing Analyst

The existing dual-agent infrastructure handles statement extraction with no new LLM setup needed:

```
Statement PDF
    → pymupdf extracts raw text (or OCR for image-based PDFs)
    → Raw text fed to the existing analyst LLM (same ANALYST_LLM used for scrape runs)
    → analyst.run() returns structured extraction (reuses the same prompt template system)

StatementData
    → analyst.extraction_prompt is reused/reprompted for statement context
```

The analyst was already designed to extract structured data from unstructured text. Statement parsing is the same task — same model, same pattern — just with statement text instead of DOM output. The existing `analyze_run` / `AnalystResult` flow handles it.

```python
from .analyst import extract_from_statement_text

# Use the existing analyst with a statement-specific task
data = extract_from_statement_text(
    raw_text=pdf_text,
    provider="amex",
    model=os.environ.get("ANALYST_LLM"),
)
# Returns StatementData
```

The analyst returns `StatementData` directly — same flow as `ScrapeResult`, just a different input source.
### Workflow: New Provider Onboarding

```
1. Download 2-3 months of statements for the new provider
2. Run statement_parser on each → StatementData
3. Run ContractGenerator.from_directory() → provider.json (auto-generated)
4. Human review → adjust required/optional fields, tighten/widen tolerances
5. Run a live scrape → validate against the contract
6. If scrape passes and values are in range → contract is confirmed
7. Commit provider.json alongside extraction prompt (amex.md)
```

This makes adding a new provider almost mechanical — no guesswork about what fields to expect.

### Workflow: Existing Provider — Detecting Regression

```
1. Monthly: re-parse latest statement → updated StatementData
2. Compare against existing contract:
   - New field observed? → add to optional, flag for review
   - Field disappeared? → remove from optional, warn
   - Value drifted significantly? → widen tolerance or investigate
3. Run live scrape → validate against updated contract
4. If scrape fails value check → investigate (site redesign? scraper bug?)
```

---

## Implementation Order

1. **`schemas.py`** — Pydantic models for contract JSON + `StatementData` dataclass.
2. **`analyst.extract_from_statement()`** — add statement extraction method to existing analyst. Uses pymupdf for text, analyst LLM for structured extraction. Test against existing downloaded statements.
3. **`generator.py`** — `ContractGenerator.from_statement()`. Converts `StatementData` to contract JSON with `observed_value`, `expected_range`, `known_accounts`, `contract_mode`.
4. **`validator.py`** — core `ContractValidator` with type checking, required field checking, value range checking, `account_events` (new/missing accounts).
5. **`amex.json`** via generator — parse Amex statements → auto-generate contract → human review → commit. Set `contract_mode="current"`.
6. **`test_contracts.py`** — basic validation tests. Start with `amex.json` only.
7. **`chase.json`**, **`discover.json`**, **`american_water.json`**, **`nipsco.json`** — remaining providers via generator.
8. **Semantic rules** — add progressively as patterns emerge (e.g. `due_date > today`).
9. **Baseline fixtures** — save parsed statement data (`amex_statement_2026-02_parsed.json`) for offline testing.
10. **Analyst feedback loop** — wire `analyst.extraction_prompt` back into the contract's `known_fields` over time.
