"""Enforce the autonomy policy before a tool reaches the remote."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from harness import ROOT
from harness.clock import now
from harness.reviewer import Reviewer
from harness.roles import action_of, arg
from policy.boundary import crossed_boundary
from policy.disclosure import has_disclosure
from policy.stop import requested as stop_requested, effective as stop_effective

POLICY_FILE = ROOT / "policy" / "autonomy.yaml"
LOG_DIR = ROOT / "logs"
COLUMNS = ("independent", "requires_approval", "prohibited")
APPROVAL_TIMEOUT_S = 1800


def action_class(action: str, facts: dict) -> str:
    """Classify by consequences, using facts from the harness, not the model."""
    if action == "post_comment":
        minutes = facts.get("minutes_since_human_comment")
        if minutes is not None and minutes <= 60:
            return "post_comment/human_active"
        if facts.get("issue_opened_by_agent"):
            return "post_comment/agent_opened"
        return "post_comment/human_quiet"
    if action == "push_commit":
        protected = facts.get("branch_protected")
        if protected is None:
            raise ValueError("cannot determine whether the target branch is protected")
        return "push_commit/protected" if protected else "push_commit/unprotected"
    return action


def place(action: str, facts: dict) -> tuple[str, str]:
    """This same function can be reused by bin/replay_policy."""
    cls = action_class(action, facts)
    policy = yaml.safe_load(POLICY_FILE.read_text())
    matching = [column for column in COLUMNS if cls in policy.get(column, [])]
    if len(matching) != 1:
        raise ValueError(f"action class {cls!r} must be in exactly one policy column")
    return cls, matching[0]


def write_line(name: str, record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / name).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def make_hook(ctx):
    """Bind the required hook(name, args) interface to this run's context."""
    def policy_hook(name: str, args: dict) -> str | None:
        action = action_of(name)
        cls, column = action or name, None

        def refuse(reason: str, detail: str | None = None) -> str:
            row = {
                "at": now(), "run_id": ctx.run_id, "action": action,
                "action_class": cls,
                "column": column if reason in ("prohibited", "declined", "no_answer") else None,
                "reason": reason, "args": args,
            }
            if detail:
                row["detail"] = detail
            write_line("hook.jsonl", row)
            return f"policy refused {cls}: {reason}"

        try:
            if action is None:
                return refuse("error", "tool has no registered autonomy action")
            if stop_requested(ctx.run_id):
                stop_effective(ctx.run_id, action)
                return refuse("stopped")
            facts = ctx.tracker.facts(ctx.run_id, action, args, ctx.issue)
            cls, column = place(action, facts)
            if action == "post_comment" and not has_disclosure(args.get(arg("comment", "body"), "")):
                return refuse("disclosure", "comment is missing the required AI-origin notice")
            if column == "prohibited":
                return refuse("prohibited")
            crossing = crossed_boundary(ctx.run_id, facts.get("paths") or [])
            if crossing is not None:
                return refuse("boundary", f"path {crossing} crosses a user boundary")
            if column == "independent":
                return None

            reviewer = Reviewer.from_env()
            answer = reviewer.ask({
                "run_id": ctx.run_id, "action": action, "action_class": cls,
                "args": args, "facts": facts, "kind": "approval",
            }, timeout_s=APPROVAL_TIMEOUT_S, until=lambda: stop_requested(ctx.run_id))
            if stop_requested(ctx.run_id):
                stop_effective(ctx.run_id, action)
                return refuse("stopped", "stop withdrew the pending approval")
            decision = answer["decision"] if answer else "none"
            write_line("approvals.jsonl", {
                "at": now(), "run_id": ctx.run_id, "action": action,
                "action_class": cls, "facts": facts, "kind": "approval",
                "decision": decision,
                "seconds": answer["seconds"] if answer else None,
                "reviewer": answer["reviewer"] if answer else reviewer.kind,
                "mode": answer["mode"] if answer else reviewer.mode,
            })
            if decision != "approve":
                return refuse("declined" if decision == "deny" else "no_answer")
            # Close the window between the human answer and the remote write.
            if stop_requested(ctx.run_id):
                stop_effective(ctx.run_id, action)
                return refuse("stopped")
            return None
        except Exception as exc:
            # Fail closed, and record why the hook could not enforce the policy.
            return refuse("error", f"{type(exc).__name__}: {exc}")

    return policy_hook
