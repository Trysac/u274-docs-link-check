"""Behavior tests for the public API of docs_link_check."""

from __future__ import annotations

import pytest

import docs_link_check


def test_normalize_trims_and_lowercases() -> None:
    assert docs_link_check.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        docs_link_check.normalize(value)


def test_version_is_semver() -> None:
    parts = docs_link_check.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
