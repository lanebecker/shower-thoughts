"""Tests for adapters.registry.get_adapter selection."""

import pytest

from adapters.registry import get_adapter


@pytest.mark.parametrize(
    "adapter_env,expected_class",
    [
        ("apple_notes", "AppleNotesAdapter"),
        ("notion", "NotionAdapter"),
        ("obsidian", "ObsidianAdapter"),
        ("email", "EmailAdapter"),
        ("craft", "CraftAdapter"),
    ],
)
def test_get_adapter_returns_expected_class(monkeypatch, adapter_env, expected_class):
    monkeypatch.setenv("NOTES_ADAPTER", adapter_env)
    adapter = get_adapter()
    assert type(adapter).__name__ == expected_class


def test_get_adapter_unknown_raises_value_error(monkeypatch):
    monkeypatch.setenv("NOTES_ADAPTER", "nope")
    with pytest.raises(ValueError):
        get_adapter()
