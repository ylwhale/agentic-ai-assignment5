"""Out-of-band stop requests. A stop is durable and only lifted by resume."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from harness import ROOT
from harness.clock import now

_VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,150}$")


def _root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else ROOT


def _request_file(run_id: str, root: Path | None = None) -> Path:
    if not _VALID.fullmatch(run_id):
        raise ValueError("unsafe run ID")
    return _root(root) / "state" / "stops" / (run_id + ".json")


def _effect_file(run_id: str, root: Path | None = None) -> Path:
    return _root(root) / "state" / "stops" / (run_id + ".effective")


def _line(run_id: str, event: str, root: Path | None = None, **fields) -> dict:
    entry = {"run_id": run_id, "event": event, "at": now(), **fields}
    out = _root(root) / "logs" / "stops.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry) + "\n")
    return entry


def requested(run_id: str, root: Path | None = None) -> bool:
    return _request_file(run_id, root).exists()


def request(run_id: str, root: Path | None = None) -> dict:
    """Record the request before exposing its flag to the running agent."""
    path = _request_file(run_id, root)
    if path.exists():
        raise ValueError(f"stop already requested for {run_id}")
    if _effect_file(run_id, root).exists():
        raise ValueError(f"run {run_id} has an already effective stop")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = _line(run_id, "requested", root)
    # O_EXCL prevents simultaneous stop commands both claiming the request.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(line, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return line


def effective(run_id: str, action: str, root: Path | None = None) -> bool:
    """Log the first stop that actually prevents a call or withdraws a wait."""
    if not requested(run_id, root):
        return False
    path = _effect_file(run_id, root)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return True
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(now() + "\n")
    _line(run_id, "effective", root, action=action)
    return True


def lift(run_id: str, root: Path | None = None) -> None:
    """Called only when re-entering a run that ended with a stop."""
    flag = _request_file(run_id, root)
    if not flag.exists():
        return
    flag.unlink()
    effect = _effect_file(run_id, root)
    if effect.exists():
        effect.unlink()
        _line(run_id, "lifted", root)
