"""Tests for CLI helpers."""

from __future__ import annotations


def test_frontend_dev_command_uses_npm_cmd_on_windows(monkeypatch):
    import shiso.cli as cli

    monkeypatch.setattr(cli.os, "name", "nt")

    assert cli._frontend_dev_command() == ["npm.cmd", "run", "dev"]


def test_frontend_dev_command_uses_npm_elsewhere(monkeypatch):
    import shiso.cli as cli

    monkeypatch.setattr(cli.os, "name", "posix")

    assert cli._frontend_dev_command() == ["npm", "run", "dev"]
