"""Tests for CLI commands."""

from unittest.mock import patch
import pytest

from typer.testing import CliRunner

from shiso.cli import app

runner = CliRunner()


class TestMatchTestCommand:
    def test_local_matching_runs_without_llm(self, tmp_path, sample_csv_content):
        csv_path = tmp_path / "passwords.csv"
        csv_path.write_text(sample_csv_content)

        result = runner.invoke(app, ["match-test", str(csv_path)])

        assert result.exit_code == 0
        assert "Parsed" in result.stdout
        assert "Aggregated into" in result.stdout
        assert "Match complete" in result.stdout
        assert "chase" in result.stdout
        assert "amex" in result.stdout

    def test_unknown_domain_gets_keyword_fallback(self, tmp_path):
        csv_content = """name,url,username,password
Unknown,https://someobscuresite.com,user@example.com,password123
"""
        csv_path = tmp_path / "unknown.csv"
        csv_path.write_text(csv_content)

        result = runner.invoke(app, ["match-test", str(csv_path)])

        assert result.exit_code == 0
        assert "Match complete" in result.stdout
        assert "someobscuresite" in result.stdout

    def test_file_not_found_returns_error(self, tmp_path):
        result = runner.invoke(app, ["match-test", str(tmp_path / "nonexistent.csv")])

        assert result.exit_code == 1
        assert "File not found" in result.stdout

    def test_empty_csv_handled(self, tmp_path):
        csv_content = """name,url,username,password
"""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text(csv_content)

        result = runner.invoke(app, ["match-test", str(csv_path)])

        assert result.exit_code == 0
        assert "Parsed 0 rows" in result.stdout

    def test_shows_match_table(self, tmp_path, sample_csv_content):
        csv_path = tmp_path / "passwords.csv"
        csv_path.write_text(sample_csv_content)

        result = runner.invoke(app, ["match-test", str(csv_path)])

        assert result.exit_code == 0
        assert "Sample Matches" in result.stdout
        assert "Domain" in result.stdout
        assert "Provider" in result.stdout
        assert "Conf" in result.stdout
        assert "Match" in result.stdout

    def test_unmatched_domains_listed(self, tmp_path):
        csv_content = """name,url,username,password
Unknown,https://someobscuresite.com,user@example.com,password123
Another,https://anotherunknown.com,user@example.com,password456
"""
        csv_path = tmp_path / "unknowns.csv"
        csv_path.write_text(csv_content)

        result = runner.invoke(app, ["match-test", str(csv_path)])

        assert result.exit_code == 0
        assert "Unmatched domains" in result.stdout
        assert "someobscuresite.com" in result.stdout
        assert "anotherunknown.com" in result.stdout

    def test_summary_stats_printed(self, tmp_path, sample_csv_content):
        csv_path = tmp_path / "passwords.csv"
        csv_path.write_text(sample_csv_content)

        result = runner.invoke(app, ["match-test", str(csv_path)])

        assert result.exit_code == 0
        assert "Total:" in result.stdout
        assert "High confidence" in result.stdout
        assert "Needs review" in result.stdout
        assert "LLM calls:" in result.stdout
        assert "LLM calls: 0" in result.stdout
