"""Escalate a failed verification before an irreversible downstream push."""
from __future__ import annotations

import json
from pathlib import Path

from harness.clock import now
from harness.reviewer import Reviewer
from harness.roles import arg
from policy.hook import write_line
from policy.stop import requested as stop_requested, effective as stop_effective

ESCALATION_TIMEOUT_S = 1800


def ask_failed_verification(ctx, step: dict, args: dict, failed: list[str]) -> str:
    """Ask about a verified failure; never infer approval from silence.

    Returns "approve", "deny" or "none". The caller ends held/escalated when
    no permission was granted and never performs the push in that case.
    """
    branch = str(args.get(arg("push_commit", "branch"), "unknown branch"))
    description = ", ".join(failed[:5]) or "the suite reported passed: false without naming individual failures"
    packet = {
        "attempted": f"Push a commit to branch {branch} (plan step {step.get('id')})",
        "why_stopped": f"This run's run_tests on {branch} failed: {description}",
        "needs_from_human": "Should RepoMind push despite the failed tests, or stop and revise the change?",
        "signal": "failed_verification",
        "at": now(),
    }
    rel = Path("escalations") / f"{ctx.run_id}.json"
    target = ctx.root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(packet, indent=2) + "\n")
    ctx.trace.event("escalation", signal="failed_verification", packet=rel.as_posix())

    facts = ctx.tracker.facts(ctx.run_id, "push_commit", args, ctx.issue_number)
    reviewer = Reviewer.from_env()
    answer = reviewer.ask({
        "run_id": ctx.run_id, "kind": "escalation", "action": "push_commit",
        "action_class": "push_commit/unprotected", "args": args,
        "facts": facts, "packet": packet,
    }, timeout_s=ESCALATION_TIMEOUT_S, until=lambda: stop_requested(ctx.run_id))
    if stop_requested(ctx.run_id):
        stop_effective(ctx.run_id, "push_commit")
        return "stopped"
    decision = answer["decision"] if answer else "none"
    write_line("approvals.jsonl", {
        "at": now(), "run_id": ctx.run_id, "kind": "escalation",
        "action": "push_commit", "action_class": "push_commit/unprotected",
        "facts": facts, "decision": decision,
        "seconds": answer["seconds"] if answer else None,
        "reviewer": answer["reviewer"] if answer else reviewer.kind,
        "mode": answer["mode"] if answer else reviewer.mode,
    })
    return decision
