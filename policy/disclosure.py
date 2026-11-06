"""Attach and verify an AI-origin notice without relying on the model."""

from __future__ import annotations

DISCLOSURE_LINE = (
    "This comment was written by RepoMind, an automated AI agent. "
    "To reach a human, reply to this issue and request a Ledgerline maintainer."
)


def has_disclosure(body: str) -> bool:
    """A disclosure must appear after the required label and file lines."""
    lines = str(body or "").splitlines()
    return any(line.strip() == DISCLOSURE_LINE for line in lines[2:])


def add_disclosure(body: str) -> str:
    """Insert the notice after the two triage headers, without duplicating it."""
    lines = str(body or "").splitlines()
    if len(lines) < 2:
        raise ValueError("triage comment must start with label: and file: lines")
    if has_disclosure(body):
        return str(body)
    return "\n".join(lines[:2] + [DISCLOSURE_LINE] + lines[2:])
