#!/usr/bin/env python3
"""CLI and usage adapters. Never read credentials or invoke a model to poll quota."""

import argparse
import json
import math
import os
from pathlib import Path
import selectors
import shlex
import subprocess
import sys
import tempfile
import time


RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["complete", "continue", "blocked", "quota"]},
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "completed_steps": {"type": "array", "items": {"type": "string"}},
        "retry_at": {"type": ["number", "null"]},
    },
    "required": ["status", "summary", "evidence", "completed_steps", "retry_at"],
    "additionalProperties": False,
}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".usage-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def observation(windows, source):
    valid = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        used = window.get("usedPercent", window.get("used_percentage"))
        reset = window.get("resetsAt", window.get("resets_at"))
        if not number(used) or used < 0 or (reset is not None and (not number(reset) or reset < 0)):
            continue
        valid.append({"used_percent": used, "resets_at": reset})
    return {"observed_at": time.time(), "windows": valid, "source": source}


def probe_codex(executable, timeout=15):
    """Initialize app-server and read ChatGPT limit buckets; no thread/turn starts."""
    process = subprocess.Popen(
        [str(executable), "app-server", "--stdio"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    pending = bytearray()
    deadline = time.monotonic() + timeout

    def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()

    def receive(identifier):
        while True:
            while b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending[:] = rest
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(message, dict) and message.get("id") == identifier:
                    if "error" in message:
                        # Do not copy potentially sensitive server diagnostics into a usage cache.
                        raise RuntimeError("Codex usage query was rejected")
                    return message.get("result", {})
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError("Codex usage query timed out")
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("Codex usage server closed before replying")
            pending.extend(chunk)
            if len(pending) > 1024 * 1024:
                raise RuntimeError("Codex usage response exceeded size limit")

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "agent_team_follow_through", "version": "1.0.0"}}})
        receive(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read"})
        result = receive(2)
        by_id = result.get("rateLimitsByLimitId") or {}
        bucket = by_id.get("codex") or result.get("rateLimits") or {}
        return observation([bucket.get("primary"), bucket.get("secondary")], "codex-app-server")
    finally:
        selector.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def read_claude_usage(cache_path):
    if not cache_path:
        return None
    try:
        value = json.loads(Path(cache_path).read_text())
        if not isinstance(value, dict) or not number(value.get("observed_at")):
            return None
        windows = value.get("windows")
        if not isinstance(windows, list):
            return None
        for window in windows:
            if not isinstance(window, dict) or not number(window.get("used_percent")) or window["used_percent"] < 0:
                return None
            reset = window.get("resets_at")
            if reset is not None and (not number(reset) or reset < 0):
                return None
        return value
    except (OSError, ValueError):
        return None


def build_command(provider, executable, prompt, schema_path, output_path, session_id=None):
    if provider == "codex":
        # A resumed command inherits exec's global config even though resume has no -s flag.
        command = [str(executable), "exec", "-c", 'sandbox_mode="workspace-write"']
        if session_id:
            command += ["resume"]
        command += ["--json", "--output-schema", str(schema_path), "--output-last-message", str(output_path)]
        if session_id:
            command += [session_id]
        return command + ["--", prompt]
    if provider == "claude":
        # Existing allow rules still apply; denied tools are surfaced, never bypassed.
        command = [str(executable), "-p", "--permission-mode", "acceptEdits",
                   "--output-format", "json", "--json-schema", json.dumps(RESULT_SCHEMA)]
        if session_id:
            command += ["--resume", session_id]
        return command + ["--", prompt]
    raise ValueError("Unsupported provider: " + str(provider))


def blocked(message, session_id=None):
    result = {"status": "blocked", "summary": message, "evidence": [],
              "completed_steps": [], "retry_at": None}
    if session_id:
        result["session_id"] = session_id
    return result


def _quota_error(value):
    """Recognize provider errors only, never arbitrary task output mentioning limits."""
    if not isinstance(value, dict):
        return None
    code = value.get("code", value.get("type", ""))
    message = value.get("message", "")
    known = code in {"usage_limit_reached", "rate_limit_error", "rate_limit_exceeded", "rate_limit"}
    if not known and not (isinstance(message, str) and any(
        marker in message.lower() for marker in ("usage limit", "rate limit", "rate_limit", "hit your limit")
    )):
        return None
    reset = value.get("resetsAt", value.get("resets_at", value.get("retry_at")))
    return {"status": "quota", "summary": "Provider reported a usage limit",
            "evidence": [], "completed_steps": [],
            "retry_at": reset if number(reset) and reset > time.time() else None}


def parse_result(provider, stdout, output_path):
    events = []
    try:
        full = json.loads(stdout)
        events = full if isinstance(full, list) else [full]
    except (ValueError, TypeError):
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
    session_id, candidate, quota, failed = None, None, None, False
    for event in events:
        if not isinstance(event, dict):
            continue
        session_id = event.get("session_id", event.get("thread_id", session_id))
        if event.get("permission_denials"):
            return blocked("Required tool permission was denied", session_id)
        kind = event.get("type")
        if event.get("is_error") or kind in {"error", "turn.failed"}:
            failed = True
            error = event.get("error")
            quota = quota or _quota_error(error if isinstance(error, dict) else event)
            for message in event.get("errors", []):
                if isinstance(message, str):
                    quota = quota or _quota_error({"message": message})
            if event.get("is_error") and isinstance(event.get("result"), str):
                quota = quota or _quota_error({"message": event["result"]})
        if kind == "rate_limit_event":
            info = event.get("rate_limit_info", {})
            if isinstance(info, dict) and info.get("status") in {"rejected", "rate_limited"}:
                quota = _quota_error({"code": "rate_limit", "resetsAt": info.get("resetsAt")})
        if provider == "claude" and kind == "result":
            candidate = event.get("structured_output")
    if quota:
        if session_id:
            quota["session_id"] = session_id
        return quota
    if failed:
        return blocked("Provider returned an execution error", session_id)
    if provider == "codex":
        try:
            candidate = json.loads(Path(output_path).read_text())
        except (OSError, ValueError):
            return blocked("Codex did not produce a valid structured result", session_id)
    if not isinstance(candidate, dict) or set(candidate) != set(RESULT_SCHEMA["required"]):
        return blocked("Provider did not produce the required structured result", session_id)
    if candidate.get("status") not in RESULT_SCHEMA["properties"]["status"]["enum"]:
        return blocked("Invalid result status", session_id)
    if not isinstance(candidate.get("summary"), str):
        return blocked("Invalid result summary", session_id)
    for key in ("evidence", "completed_steps"):
        if not isinstance(candidate.get(key), list) or any(not isinstance(x, str) or not x.strip() for x in candidate[key]):
            return blocked("Invalid result " + key, session_id)
    retry = candidate.get("retry_at")
    if retry is not None and (not number(retry) or retry < 0):
        return blocked("Invalid retry time", session_id)
    result = dict(candidate)
    if session_id:
        result["session_id"] = session_id
    return result


def capture_claude_status(raw, cache_path):
    data = json.loads(raw)
    limits = data.get("rate_limits") if isinstance(data, dict) else None
    # Explicitly missing data invalidates old observations instead of refreshing their age.
    windows = list(limits.values()) if isinstance(limits, dict) else []
    value = observation(windows, "claude-statusline")
    atomic_json(cache_path, value)
    return value


def statusline(cache_path, previous_path):
    raw = sys.stdin.buffer.read()
    try:
        capture_claude_status(raw, cache_path)
    except (OSError, ValueError, TypeError):
        pass  # Observability must never break the user's existing status line.
    if previous_path:
        try:
            previous = json.loads(Path(previous_path).read_text())
            command = previous.get("command")
            if isinstance(command, str) and command:
                # This is the user's pre-existing shell command, not generated input.
                return subprocess.run(command, shell=True, input=raw, check=False).returncode
        except (OSError, ValueError):
            pass
    return 0


def install_statusline(settings_path, cache_path, previous_path):
    """Opt-in wrapper; retain original command and settings backup, update idempotently."""
    import fcntl
    settings_path, previous_path = Path(settings_path), Path(previous_path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(settings_path) + ".follow-through.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original_bytes = settings_path.read_bytes() if settings_path.exists() else b"{}\n"
        settings = json.loads(original_bytes)
        original = settings.get("statusLine")
        marker = " claude-statusline "
        if original is not None and (not isinstance(original, dict) or original.get("type") != "command"):
            raise ValueError("Unsupported existing statusLine; left unchanged")
        already = bool(original and marker in original.get("command", "") and "providers.py" in original["command"])
        if already and not previous_path.exists():
            raise ValueError("Existing wrapper has no original-command record; left unchanged")
        if not already:
            if previous_path.exists():
                raise ValueError("Original-command record already exists but wrapper changed; inspect it before reinstalling")
            backup = settings_path.with_name(settings_path.name + ".follow-through-backup-" + str(time.time_ns()))
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(original_bytes)
            atomic_json(previous_path, original or {})
        command = shlex.join([sys.executable, str(Path(__file__).resolve()), "claude-statusline",
                              "--cache", str(Path(cache_path).resolve()), "--previous", str(previous_path.resolve())])
        settings["statusLine"] = dict(original or {}, type="command", command=command)
        # Preserve all unrelated settings semantically, and a byte-exact backup for rollback.
        atomic_json(settings_path, settings)
        return {"settings": str(settings_path), "previous": str(previous_path), "cache": str(cache_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("codex-usage", help="Read live limits without a model request")
    probe.add_argument("--executable", default="codex")
    capture = sub.add_parser("claude-statusline", help="Cache quota fields and preserve the existing status line")
    capture.add_argument("--cache", required=True)
    capture.add_argument("--previous")
    install = sub.add_parser("install-claude-statusline", help="Wrap statusLine, preserving the existing command and backup")
    install.add_argument("--settings", required=True)
    install.add_argument("--cache", required=True)
    install.add_argument("--previous", required=True)
    args = parser.parse_args()
    if args.command == "codex-usage":
        print(json.dumps(probe_codex(args.executable)))
    elif args.command == "claude-statusline":
        return statusline(args.cache, args.previous)
    else:
        print(json.dumps(install_statusline(args.settings, args.cache, args.previous)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
