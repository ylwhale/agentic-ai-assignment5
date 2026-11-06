"""Human approval screen for Assignment 5.

Shows the exact proposed effect and independently sourced context. It does not
show an AI-generated recommendation or rationale for approving the action.
"""

from __future__ import annotations

import json
from pathlib import Path

from harness import ROOT
from harness.roles import action_of, arg
from harness.trace import read_trace
from harness.tracker import Tracker


WRITES = {"apply_label", "post_comment", "close_issue", "open_pr", "push_commit", "merge_pr"}


def _show(value) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _field(args: dict, role: str, field: str):
    try:
        return args.get(arg(role, field))
    except (KeyError, ValueError, OSError):
        return None


def _issue_number(facts: dict, args: dict) -> int | None:
    value = facts.get("issue", args.get("issue"))
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    value = str(value or "").strip().lower().removeprefix("issue-").removeprefix("#")
    return int(value) if value.isdigit() else None


def _dry_run(action: str, args: dict, facts: dict) -> list[str]:
    """Describe precisely what would be sent to the remote if approved."""
    if action == "post_comment":
        return [
            "Operation: Post this public comment exactly as written:",
            "----- COMMENT START -----",
            _show(_field(args, "comment", "body")),
            "----- COMMENT END -----",
        ]
    if action == "open_pr":
        return [
            "Operation: Open a public draft pull request",
            "Source branch: " + _show(_field(args, "open_pr", "branch")),
            "Base branch: " + _show(facts.get("base")),
            "Title: " + _show(_field(args, "open_pr", "title")),
            "----- PR BODY START -----",
            _show(_field(args, "open_pr", "body")),
            "----- PR BODY END -----",
        ]
    if action == "push_commit":
        return [
            "Operation: Push one commit to an existing branch",
            "Branch: " + _show(_field(args, "push_commit", "branch")),
            "Commit message: " + _show(_field(args, "push_commit", "message")),
            "Files to change:",
            _show(_field(args, "push_commit", "files")),
        ]
    if action == "apply_label":
        return ["Operation: Add label", "Label: " + _show(_field(args, "apply_label", "label"))]
    if action == "close_issue":
        return ["Operation: Close issue", "Reason: " + _show(_field(args, "close_issue", "reason"))]
    if action == "merge_pr":
        return ["Operation: Merge pull request", "Pull request: " + _show(_field(args, "merge_pr", "pr")),
                "Base branch: " + _show(facts.get("base"))]
    return ["Operation: " + (action or "Unknown"), "Exact arguments:", _show(args)]


def _latest_test_result(run_id: str, target_branch) -> str:
    """Read test-tool results from this run's trace, not the agent's claims."""
    if not run_id or Path(run_id).name != run_id:
        return "No verified run ID supplied"
    path = ROOT / "runs" / f"{run_id}.jsonl"
    if not path.is_file():
        return "No completed run_tests result recorded for this run"
    try:
        records = read_trace(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return "Run trace could not be read"
    results = []
    for line in records:
        if line.get("type") != "tool_call" or action_of(line.get("name", "")) != "run_tests":
            continue
        try:
            result = json.loads(line.get("result_excerpt") or "")
        except (TypeError, ValueError):
            continue
        if not line.get("is_error") and isinstance(result, dict) and "passed" in result:
            results.append(result)
    if not results:
        return "No completed run_tests result recorded for this run"
    matched = [r for r in results if r.get("ref") == target_branch] if target_branch else []
    result = matched[-1] if matched else results[-1]
    prefix = "Target-branch result" if matched else "Latest recorded test result"
    return (f"{prefix}: ref={_show(result.get('ref'))}; "
            f"passed={_show(result.get('passed'))}; "
            f"test count={_show(result.get('tests'))}; "
            f"failed cases={_show(result.get('failed', []))}")


def _discussion(issue_number: int | None) -> list[str]:
    if issue_number is None:
        return ["No issue number available"]
    try:
        issue = Tracker().issue(issue_number)
    except (OSError, ValueError, KeyError):
        return [f"Issue #{issue_number} could not be loaded"]
    lines = [f"Issue #{issue_number}: {_show(issue.get('title'))}",
             "Opened by: " + _show(issue.get("author"))]
    posts = issue.get("discussion") or []
    if not posts:
        return lines + ["No human discussion recorded"]
    lines.append(f"Human discussion ({len(posts)} posts, oldest first; original text):")
    for post in posts:
        lines.append(f"--- {_show(post.get('author'))} "
                     f"[{_show(post.get('role'))}], {_show(post.get('date'))} ---")
        lines.append(str(post.get("body") or ""))
    return lines


def render(request: dict) -> str:
    """Render the reviewer's factual, non-persuasive approval screen."""
    if not isinstance(request, dict):
        raise ValueError("review request must be a dictionary")
    action = str(request.get("action") or "")
    args = request.get("args") or {}
    facts = request.get("facts") or {}
    if not isinstance(args, dict) or not isinstance(facts, dict):
        raise ValueError("request arguments and facts must be dictionaries")
    run_id = str(request.get("run_id") or "")
    issue_number = _issue_number(facts, args)

    lines = [
        "REVIEW REQUEST — FACTS, NOT A RECOMMENDATION",
        "Kind: " + _show(request.get("kind", "approval")),
        "Run ID: " + _show(run_id),
        "Action: " + _show(action),
        "Action class: " + _show(request.get("action_class")),
        "Issue: " + (f"#{issue_number}" if issue_number is not None else "Not available"),
        "",
        "EXACT PROPOSED CHANGE (DRY RUN; NOTHING APPLIED YET)",
        *_dry_run(action, args, facts),
        "",
        "HARNESS-COMPUTED FACTS",
        "Target created by this agent: " + _show(facts.get("target_created_by_agent")),
        "Issue opened by an agent: " + _show(facts.get("issue_opened_by_agent")),
        "Minutes since most recent human comment: " + _show(facts.get("minutes_since_human_comment")),
        "Target branch: " + _show(facts.get("branch")),
        "Base branch: " + _show(facts.get("base")),
        "Branch protected: " + _show(facts.get("branch_protected")),
        "Paths touched: " + _show(facts.get("paths", [])),
        "",
        "VERIFIED TEST RESULT (FROM RUN TRACE)",
        _latest_test_result(run_id, facts.get("branch")),
        "",
        "ISSUE THREAD (ORIGINAL HUMAN WORDS)",
        *_discussion(issue_number),
    ]
    if request.get("kind") == "escalation":
        lines.extend(["", "ESCALATION PACKET", _show(request.get("packet"))])
    if action not in WRITES and request.get("kind") != "escalation":
        lines.append("Note: this action is not normally a remote write.")
    lines.extend(["", "Review the exact change and external facts before choosing approve or deny."])
    return "\n".join(lines)
