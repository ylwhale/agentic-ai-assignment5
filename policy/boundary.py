"""Persist inbox boundaries outside the conversation and match paths in the hook."""

from __future__ import annotations

import json
import re

from harness import ROOT
from harness.formats import BOUNDARY
from harness.inbox import drain

RULES = ROOT / "policy" / "rules.jsonl"


def incoming_user_messages(ctx) -> list[str]:
    """Drain before one model call; return non-boundary messages for the model."""
    messages = []
    for message in drain(ctx):
        text = message["text"]
        match = BOUNDARY.fullmatch(text)
        if match:
            RULES.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "run_id": ctx.run_id,
                "effect": "deny",
                "path": match.group(1),
                "stated_at": message["delivered_at"],
                "message": text,
            }
            with RULES.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        else:
            messages.append(text)
    return messages


def matches_path(pattern: str, path: str) -> bool:
    """Glob semantics: * stays within one directory, ** crosses directories."""
    path = str(path).replace("\\", "/").removeprefix("./")
    pattern = str(pattern).replace("\\", "/").removeprefix("./")
    regex = ["^"]
    i = 0
    while i < len(pattern):
        if pattern[i:i + 2] == "**":
            if pattern[i + 2:i + 3] == "/":
                regex.append("(?:.*/)?")
                i += 3
            else:
                regex.append(".*")
                i += 2
        elif pattern[i] == "*":
            regex.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            regex.append("[^/]")
            i += 1
        else:
            regex.append(re.escape(pattern[i]))
            i += 1
    return re.fullmatch("".join(regex) + "$", path) is not None


def crossed_boundary(run_id: str, paths: list[str]) -> str | None:
    """Return the path that violates a rule stated to this run, if one exists."""
    if not paths or not RULES.exists():
        return None
    for line in RULES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rule = json.loads(line)
        if rule.get("run_id") != run_id or rule.get("effect") != "deny":
            continue
        for path in paths:
            if matches_path(rule["path"], path):
                return str(path)
    return None
