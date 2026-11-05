#!/usr/bin/env python3
"""Oracle Stop-hook entry point.

Wired as a Claude Code `Stop` hook (see README). At every would-be stop it:

  1. drains the Stop event JSON from stdin,
  2. asks `agents whoami` what this session is,
  3. gates by role: not an oracle ada/lead => allow the stop (exit 0),
  4. routes to this role's checklist (ada.yml / lead.yml),
  5. evaluates it with the `oracle` engine against the live repo + GitHub,
  6. translates the verdict into the Stop-hook contract:
        force-continue  -> exit 2, instruction on stderr
        allow stop      -> exit 0

THE ONE INVARIANT: **fail open.** An unbound session, an unknown role, a missing
`oracle` binary, a parse failure, ANY exception => exit 0. A hook that can wedge
a session is strictly worse than one that under-enforces. Nothing below is
allowed to exit non-zero except the single deliberate `sys.exit(2)`.

State is never stored here beyond a runaway-loop counter (kept in the temp dir,
never in the repo): the position is re-derived live every call by the engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import NoReturn

HERE = os.path.dirname(os.path.abspath(__file__))
ORACLE_ROLES = {"ada": "ada.yml", "lead": "lead.yml"}
ATTEMPT_CAP = 30  # consultations stuck on ONE item before we give up and allow stop


def _allow_stop() -> NoReturn:
    sys.exit(0)


def _read_stop_event() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _whoami(session_id: str | None) -> dict:
    cmd = ["agents", "whoami", "--json"]
    if session_id:
        cmd += ["--session-id", session_id]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True).stdout
    return json.loads(out)


def _attempts_path(role_yaml: str) -> str:
    # Key the counter by repo root + branch so worktrees/branches don't collide,
    # and keep it OUT of the repo (artifact-native state rule).
    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except Exception:
        root, branch = os.getcwd(), "?"
    key = hashlib.sha1(f"{root}\n{branch}\n{role_yaml}".encode()).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"oracle-attempts-{key}.json")


def _bump_attempt(role_yaml: str, state_id: str) -> int:
    path = _attempts_path(role_yaml)
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data[state_id] = int(data.get(state_id, 0)) + 1
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass
    return data[state_id]


def _evaluate(role_yaml: str, env: dict) -> tuple[str, int]:
    oracle_bin = shutil.which("oracle")
    if not oracle_bin:
        raise RuntimeError("oracle binary not on PATH")
    path = os.path.join(HERE, role_yaml)
    proc = subprocess.run(
        [oracle_bin, "next", "--yaml", path],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    return proc.stdout, proc.returncode


def _force_continue(prompt: str) -> NoReturn:
    print(prompt, file=sys.stderr)
    sys.exit(2)  # the one deliberate non-zero exit: Claude Code continues with stderr


def main() -> None:
    event = _read_stop_event()
    session_id = event.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID")

    try:
        me = _whoami(session_id)
    except Exception:
        _allow_stop()  # unbound / agents unavailable => fail open

    role = (me.get("type") or "").strip().lower()
    role_yaml = ORACLE_ROLES.get(role)
    if not role_yaml:
        _allow_stop()  # not an oracle ada/lead

    # Build the env the checklist runs under.
    env = os.environ.copy()
    env["ORACLE_DIR"] = HERE
    if role == "lead" and not env.get("ORACLE_DIVISION"):
        # Best-effort division for the lead NOW; now.py fails open without it.
        div = me.get("team") or me.get("role") or ""
        if div:
            env["ORACLE_DIVISION"] = div

    try:
        stdout, rc = _evaluate(role_yaml, env)
    except Exception:
        _allow_stop()  # any evaluation failure => fail open

    if rc == 1:
        _allow_stop()  # engine reported an error state => fail open

    if stdout.startswith("POSITION: "):
        first_nl = stdout.find("\n")
        state_id = stdout[len("POSITION: ") : first_nl].strip() if first_nl != -1 else "?"
        sep = stdout.find("\n---\n")
        prompt = stdout[sep + len("\n---\n") :] if sep != -1 else stdout
        count = _bump_attempt(role_yaml, state_id)
        if count > ATTEMPT_CAP:
            # Runaway: this item has not moved in ATTEMPT_CAP tries. Stop forcing;
            # it needs a human, not another identical attempt.
            print(
                f"oracle: `{state_id}` unmet {count} times in a row — allowing stop. This needs a human, not another attempt.",
                file=sys.stderr,
            )
            _allow_stop()
        _force_continue(prompt.rstrip("\n"))

    # DONE / WAIT / anything unrecognized => allow stop.
    _allow_stop()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        # Absolute last-resort fail-open: never let this hook wedge a session.
        sys.exit(0)
