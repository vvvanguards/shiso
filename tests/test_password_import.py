"""Tests for password CSV parsing, aggregation, and provider matching."""

import pytest

from shiso.scraper.services.password_import import (
    aggregate_by_domain,
    expand_matches,
    parse_csv,
)
from shiso.scraper.services.provider_matcher import (
    _build_provider_lookup,
    _match_known,
    match_providers_sync,
)


class TestParseCsv:
    def test_parses_chrome_csv_format(self, sample_csv_content):
        rows = parse_csv(sample_csv_content)
        assert len(rows) == 5

        assert rows[0]["name"] == "Chase"
        assert rows[0]["url"] == "https://chase.com"
        assert rows[0]["username"] == "user@example.com"
        assert rows[0]["password"] == "password123"
        assert rows[0]["domain"] == "chase.com"

    def test_deduplicates_by_url_username(self):
        csv_content = """name,url,username,password
Site1,https://example.com,user@example.com,pass1
Site1,https://example.com,user@example.com,pass2
Site2,https://example.com,user2@example.com,pass3
"""
        rows = parse_csv(csv_content)
        # First two rows are duplicates (same URL + username), should be deduped to one
        assert len(rows) == 2
        assert rows[0]["username"] == "user@example.com"
        assert rows[0]["password"] == "pass1"
        assert rows[1]["username"] == "user2@example.com"

    def test_extracts_domain_from_url(self):
        csv_content = """name,url,username,password
My Bank,https://www.bankofamerica.com,user@example.com,pass
"""
        rows = parse_csv(csv_content)
        assert rows[0]["domain"] == "www.bankofamerica.com"

    def test_handles_missing_password(self):
        csv_content = """name,url,username,password
My Bank,https://bank.com,user@example.com,
"""
        rows = parse_csv(csv_content)
        assert len(rows) == 1
        assert rows[0]["password"] == ""
        assert rows[0]["username"] == "user@example.com"

    def test_strips_whitespace_from_username(self):
        csv_content = """name,url,username,password
My Bank,https://bank.com,  user@example.com  ,pass
"""
        rows = parse_csv(csv_content)
        assert rows[0]["username"] == "user@example.com"

    def test_empty_csv_returns_empty_list(self):
        rows = parse_csv("")
        assert rows == []

    def test_preserves_row_id_sequence(self):
        csv_content = """name,url,username,password
Site1,https://a.com,user1@example.com,pass1
Site2,https://b.com,user2@example.com,pass2
Site3,https://c.com,user3@example.com,pass3
"""
        rows = parse_csv(csv_content)
        assert rows[0]["row_id"] == 0
        assert rows[1]["row_id"] == 1
        assert rows[2]["row_id"] == 2


class TestAggregateByDomain:
    def test_groups_rows_by_domain(self):
        csv_content = """name,url,username,password
Chase,https://chase.com,user1@example.com,pass1
Chase,https://chase.com,user2@example.com,pass2
Amex,https://americanexpress.com,user@example.com,pass3
"""
        rows = parse_csv(csv_content)
        aggregated = aggregate_by_domain(rows)

        assert len(aggregated) == 2

        chase = next(a for a in aggregated if a["domain"] == "chase.com")
        assert chase["username_count"] == 2
        assert "user1@example.com" in chase["usernames"]
        assert "user2@example.com" in chase["usernames"]
        assert set(chase["original_row_ids"]) == {0, 1}

        amex = next(a for a in aggregated if a["domain"] == "americanexpress.com")
        assert amex["username_count"] == 1

    def test_handles_single_domain(self):
        csv_content = """name,url,username,password
Site,https://example.com,user1@example.com,pass1
Site,https://example.com,user2@example.com,pass2
"""
        rows = parse_csv(csv_content)
        aggregated = aggregate_by_domain(rows)
        assert len(aggregated) == 1
        assert aggregated[0]["domain"] == "example.com"
        assert aggregated[0]["username_count"] == 2

    def test_picks_most_common_name(self):
        csv_content = """name,url,username,password
Chase Bank,https://chase.com,user@example.com,pass
Chase Online,https://chase.com,user2@example.com,pass
"""
        rows = parse_csv(csv_content)
        aggregated = aggregate_by_domain(rows)
        assert aggregated[0]["name"] in ("Chase Bank", "Chase Online")

    def test_empty_input_returns_empty(self):
        assert aggregate_by_domain([]) == []


class TestExpandMatches:
    def test_expands_matches_to_all_rows(self):
        aggregated_domains = [
            {
                "domain": "chase.com",
                "name": "Chase",
                "username_count": 2,
                "usernames": ["user1@example.com", "user2@example.com"],
                "password": "pass1",
                "original_row_ids": [0, 1],
            },
        ]
        aggregated_matches = [
            {
                "domain": "chase.com",
                "provider_key": "chase",
                "label": "Chase",
                "account_type": "Credit Card",
                "confidence": 0.98,
                "is_new_provider": False,
            },
        ]

        expanded = expand_matches(aggregated_matches, aggregated_domains)

        assert len(expanded) == 2
        assert expanded[0]["row_id"] == 0
        assert expanded[0]["provider_key"] == "chase"
        assert expanded[1]["row_id"] == 1
        assert expanded[1]["provider_key"] == "chase"

    def test_unmatched_domain_gets_empty_match(self):
        aggregated_domains = [
            {
                "domain": "unknown.com",
                "name": "Unknown",
                "username_count": 1,
                "usernames": ["user@example.com"],
                "password": "pass",
                "original_row_ids": [0],
            },
        ]

        expanded = expand_matches([], aggregated_domains)

        assert len(expanded) == 1
        assert expanded[0]["provider_key"] == ""
        assert expanded[0]["confidence"] == 0.0


class TestMatchProvidersSync:
    def test_exact_domain_match(self, sample_csv_content):
        rows = parse_csv(sample_csv_content)
        result = match_providers_sync(rows)

        mappings = {m["domain"]: m for m in result["mappings"]}

        assert mappings["chase.com"]["provider_key"] == "chase"
        assert mappings["chase.com"]["label"] == "Chase"
        assert mappings["chase.com"]["confidence"] == 0.98
        assert mappings["chase.com"]["match_type"] == "exact"
        assert mappings["chase.com"]["is_new_provider"] is False

    def test_subdomain_match(self, sample_csv_content):
        rows = parse_csv(sample_csv_content)
        result = match_providers_sync(rows)

        mappings = {m["domain"]: m for m in result["mappings"]}

        # online.americanexpress.com should match americanexpress.com
        assert mappings["online.americanexpress.com"]["provider_key"] == "amex"
        assert mappings["online.americanexpress.com"]["confidence"] == 0.90
        assert mappings["online.americanexpress.com"]["match_type"] == "subdomain"

    def test_unmatched_domain_keyword_fallback(self, sample_csv_content):
        rows = parse_csv(sample_csv_content)
        result = match_providers_sync(rows)

        mappings = {m["domain"]: m for m in result["mappings"]}

        # someobscuresite.com derives provider_key from name "Unknown Service" not domain
        assert mappings["someobscuresite.com"]["provider_key"] == "unknown_service"
        assert mappings["someobscuresite.com"]["confidence"] == 0.40
        assert mappings["someobscuresite.com"]["match_type"] == "keyword_fallback"
        assert mappings["someobscuresite.com"]["is_new_provider"] is True

    def test_no_rows_returns_empty(self):
        result = match_providers_sync([])
        assert result["mappings"] == []
        assert result["summary"]["total"] == 0
        assert result["summary"]["llm_calls"] == 0

    def test_all_domains_matched_locally(self, sample_csv_content):
        rows = parse_csv(sample_csv_content)
        result = match_providers_sync(rows)

        # match_providers_sync does local-only, no LLM
        assert result["summary"]["llm_calls"] == 0

    def test_mixed_confidence(self, sample_csv_content):
        rows = parse_csv(sample_csv_content)
        result = match_providers_sync(rows)

        high_conf = sum(1 for m in result["mappings"] if m["confidence"] >= 0.9)
        low_conf = sum(1 for m in result["mappings"] if m["confidence"] < 0.9)

        # chase.com (0.98), americanexpress.com (0.98), indianaamericanwater.com (0.98), online.americanexpress.com (0.90) = 4 high
        # someobscuresite.com (0.40) = 1 low
        assert high_conf == 4
        assert low_conf == 1
