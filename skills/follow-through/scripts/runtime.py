#!/usr/bin/env python3
"""Optional POSIX follow-through runner; only managed processes share its lock."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

import providers

TERMINAL = {"complete", "cancelled", "blocked"}
STATUSES = TERMINAL | {"ready", "running", "waiting", "scheduled"}
LOCK_ROOT = Path.home() / ".local" / "state" / "agent-team" / "locks"


def canonical(value, kind=None):
    path = Path(value).expanduser().absolute()
    # Resolve directory aliases (including macOS /tmp) while refusing a redirected
    # controller file or executable. Stored paths are always fully canonical.
    if path.is_symlink():
        raise ValueError("path must not be a symlink: " + str(path))
    path = path.resolve()
    if kind == "file" and not path.is_file():
        raise ValueError("not a file: " + str(path))
    if kind == "dir" and not path.is_dir():
        raise ValueError("not a directory: " + str(path))
    return path


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(state, check_environment=False):
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("unsupported task state")
    for key in ("workspace", "task_file", "python"):
        if not isinstance(state.get(key), str) or not Path(state[key]).is_absolute():
            raise ValueError("invalid absolute path: " + key)
    if check_environment:
        canonical(state["workspace"], "dir")
        canonical(state["task_file"], "file")
    if not isinstance(state.get("generation"), int) or state["generation"] < 1:
        raise ValueError("invalid generation")
    if state.get("status") not in STATUSES:
        raise ValueError("invalid status")
    names = state.get("providers")
    if not isinstance(names, list) or not names or len(set(names)) != len(names) or any(p not in ("codex", "claude") for p in names):
        raise ValueError("invalid providers")
    if "provider_args" in state or "args" in state:
        raise ValueError("custom provider arguments are unsupported")
    for name in names:
        executable = state["binaries"][name]
        if not isinstance(executable, str) or not Path(executable).is_absolute():
            raise ValueError("invalid provider binary path")
        if check_environment and not os.access(canonical(executable, "file"), os.X_OK):
            raise ValueError("provider binary is not executable")
    if check_environment:
        canonical(state["python"], "file")
    if not isinstance(state.get("path"), str):
        raise ValueError("invalid PATH")
    for key in ("steps", "evidence"):
        if not isinstance(state.get(key), list) or not all(isinstance(x, str) for x in state[key]):
            raise ValueError("invalid " + key)
    if not isinstance(state.get("sessions"), dict) or any(k not in names or not isinstance(v, str) for k, v in state["sessions"].items()):
        raise ValueError("invalid sessions")
    for key in ("no_progress", "launch_failures"):
        if not isinstance(state.get(key), int) or state[key] < 0:
            raise ValueError("invalid recovery counter")
    if state.get("next_at") is not None and not number(state["next_at"]):
        raise ValueError("invalid wake-up time")
    if check_environment and state.get("claude_usage"):
        canonical(state["claude_usage"])
    for key in ("observations", "quota_blocks"):
        if not isinstance(state.get(key), dict) or any(k not in names for k in state[key]):
            raise ValueError("invalid " + key)
    if any(value is not None and not number(value) for value in state["quota_blocks"].values()):
        raise ValueError("invalid quota reset")
    return state


def lock_file(path):
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError("lock must be a regular file")
    return fd


def controller_lock(kind, path):
    # Keep inode-bearing locks outside repositories and generated task directories.
    # A git clean in a managed workspace must never replace a live lock inode.
    LOCK_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()
    return lock_file(LOCK_ROOT / (kind + "-" + digest + ".lock"))


@contextlib.contextmanager
def transaction(path):
    path = canonical(path)
    fd = controller_lock("state", path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        state = validate(json.loads(path.read_text()))
        yield state
        atomic_json(path, state)
    finally:
        os.close(fd)


def atomic_json(path, state):
    fd, tmp = tempfile.mkstemp(prefix=".follow-through-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(state, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_state(path):
    path = canonical(path, "file")
    fd = controller_lock("state", path)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        return validate(json.loads(path.read_text()))
    finally:
        os.close(fd)


def change(path, generation, **updates):
    with transaction(path) as state:
        if state["generation"] != generation or state["status"] in TERMINAL:
            return False
        state.update(updates)
    return True


def initialize(args):
    path = canonical(args.state)
    workspace = canonical(args.workspace, "dir")
    task = canonical(args.task_file, "file")
    if path == task or path == workspace / ".follow-through.lock" or task in (workspace / ".follow-through.lock", Path(str(path) + ".lock")):
        raise ValueError("task/state/lock paths must be distinct")
    names = args.providers
    if len(set(names)) != len(names):
        raise ValueError("duplicate provider")
    binaries = {}
    for name in names:
        binary = shutil.which(name)
        if not binary:
            raise ValueError(name + " executable not found on PATH")
        binaries[name] = str(Path(binary).resolve())
    state = dict(version=1, workspace=str(workspace), task_file=str(task), providers=names,
                 binaries=binaries, python=str(Path(sys.executable).resolve()), path=os.environ.get("PATH", ""),
                 claude_usage=str(canonical(args.claude_usage)) if args.claude_usage else None,
                 status="ready", generation=1, sessions={}, steps=[], evidence=[], observations={},
                 quota_blocks={}, no_progress=0, launch_failures=0, next_at=None, job=None,
                 summary="Initialized; no executor launched.", active=None, last_started=None)
    validate(state, check_environment=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = controller_lock("state", path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if path.exists():
            raise ValueError("state already exists")
        atomic_json(path, state)
    finally:
        os.close(fd)
    return state


def quota(observation, now):
    """Return (capacity or None, blocked_until or None, blocked)."""
    if not isinstance(observation, dict):
        return None, None, False
    windows = observation.get("windows")
    observed = observation.get("observed_at")
    if not isinstance(windows, list) or not windows or not number(observed):
        return None, None, False
    fresh = 0 <= now - observed <= 300
    resets, unknown_block, capacities = [], False, []
    for window in windows:
        if not isinstance(window, dict) or not number(window.get("used_percent")):
            return None, None, False
        used, reset = window["used_percent"], window.get("resets_at")
        if reset is not None and not number(reset):
            return None, None, False
        if used >= 100:
            if reset is not None and reset > now:
                resets.append(reset)
            elif reset is None and fresh:
                unknown_block = True
            else:
                fresh = False  # Passed resets are unknown, never proof of capacity.
        capacities.append(max(0, 100 - used))
    if unknown_block or resets:
        return None, None if unknown_block else max(resets), True
    return min(capacities) if fresh else None, None, False


def observe(state):
    observations = dict(state.get("observations", {}))
    for name in state["providers"]:
        try:
            result = (providers.probe_codex(state["binaries"][name]) if name == "codex"
                      else providers.read_claude_usage(state.get("claude_usage")))
            if result is None:
                old = observations.get(name)
                result = dict(old, observed_at=0) if isinstance(old, dict) else None
            observations[name] = result
        except Exception:
            # Retain still-applicable blocking windows, but do not assert capacity.
            old = observations.get(name)
            if isinstance(old, dict):
                old = dict(old, observed_at=0)
            observations[name] = old
    return observations


def choose(state, exhausted, now):
    candidates, waits = [], []
    for name in state["providers"]:
        cap, reset, blocked = quota(state.get("observations", {}).get(name), now)
        local_reset = state.get("quota_blocks", {}).get(name)
        if number(local_reset) and local_reset > now:
            unknown_block = blocked and reset is None
            blocked = True
            reset = None if unknown_block else max(reset or 0, local_reset)
        if blocked or name in exhausted:
            if number(reset) and reset > now:
                waits.append(reset)
            continue
        candidates.append((name, cap))
    known = [(name, cap) for name, cap in candidates if cap is not None and cap > 0]
    if known:
        best = max(known, key=lambda item: item[1])
        current = next((x for x in known if x[0] == state.get("current_provider")), None)
        return (current[0] if current and best[1] - current[1] <= 15 else best[0]), None
    if candidates:
        current = next((name for name, _ in candidates if name == state.get("current_provider")), None)
        return current or candidates[0][0], None  # One explicit unknown-capacity attempt.
    return None, min(waits) + 5 if waits else None


def job_identity(path, generation):
    task_id = hashlib.sha256(str(path).encode()).hexdigest()[:20]
    return "dev.agent-team.follow-through." + task_id + "." + str(generation)


def cleanup_job(path, job):
    if not isinstance(job, dict) or not isinstance(job.get("generation"), int):
        return
    label = job_identity(path, job["generation"])
    expected = Path.home() / "Library" / "LaunchAgents" / (label + ".plist")
    if job.get("label") != label or job.get("plist") != str(expected):
        return
    # Only remove the exact plist whose payload we own. Never unload our own job.
    try:
        payload = plistlib.loads(expected.read_bytes())
        if payload.get("Label") == label and payload.get("ProgramArguments", [])[3:] == ["--state", str(path), "--wait", "--generation", str(job["generation"])]:
            expected.unlink()
    except (OSError, ValueError, plistlib.InvalidFileException):
        pass


def schedule(path, at):
    if not number(at):
        raise ValueError("invalid schedule time")
    if sys.platform != "darwin":
        raise ValueError("automatic scheduling requires macOS launchd; use run --wait")
    launchctl = shutil.which("launchctl")
    if not launchctl:
        raise ValueError("launchctl not found")
    old_job = None
    # Short state lock covers registration, never a model turn. A bootstrapped child
    # waits for this lock before admission, so it cannot race persisted registration.
    with transaction(path) as state:
        if state["status"] in TERMINAL:
            raise ValueError("cannot schedule a terminal task")
        if state["status"] == "running" or state.get("active"):
            raise ValueError("cannot schedule over an active executor; stop it first")
        old_job = state.get("job")
        generation = state["generation"] + 1
        label = job_identity(path, generation)
        directory = Path.home() / "Library" / "LaunchAgents"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (label + ".plist")
        payload = dict(Label=label, ProgramArguments=[state["python"], str(Path(__file__).resolve()), "run", "--state", str(path), "--wait", "--generation", str(generation)],
                       RunAtLoad=True, LimitLoadToSessionType=["Aqua", "Background"],
                       EnvironmentVariables={"PATH": state["path"]}, WorkingDirectory=state["workspace"])
        with target.open("xb") as handle:
            os.chmod(target, 0o600)
            plistlib.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            domain = None
            for kind in ("gui", "user"):
                candidate = kind + "/" + str(os.getuid())
                available = subprocess.run([launchctl, "print", candidate], stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, timeout=5)
                if available.returncode == 0:
                    domain = candidate
                    break
            if domain is None:
                raise RuntimeError("no accessible per-user launchd domain")
            result = subprocess.run([launchctl, "bootstrap", domain, str(target)], capture_output=True, text=True, timeout=15)
            if result.returncode:
                raise RuntimeError("launchctl bootstrap failed: " + result.stderr.strip())
        except Exception as exc:
            target.unlink()
            state.update(status="waiting", next_at=at, job=None, generation=generation,
                         summary="Automatic resume not scheduled: " + str(exc))
        else:
            state.update(status="scheduled", next_at=at, generation=generation,
                         job=dict(label=label, plist=str(target), generation=generation, domain=domain),
                         summary="Wake-up registered; executor has not started.")
    cleanup_job(path, old_job)
    return read_state(path)


def finish(path, generation, status, summary):
    job = None
    with transaction(path) as state:
        if state["generation"] != generation or state["status"] in TERMINAL:
            return
        job = state.get("job")
        state.update(status=status, summary=summary, generation=generation + 1,
                     active=None, next_at=None, job=None)
    cleanup_job(path, job)


def cancel(path):
    with transaction(path) as state:
        if state["status"] in TERMINAL:
            return state
        job = state.get("job")
        state.update(status="cancelled", generation=state["generation"] + 1,
                     next_at=None, job=None, summary="Cancellation requested; owning runner reaps its child.")
    cleanup_job(path, job)
    return read_state(path)


def still_current(path, generation):
    state = read_state(path)
    return state["generation"] == generation and state["status"] not in TERMINAL


def stop_child(child):
    # This is the isolated group created by our live Popen, never a PID from disk.
    # The leader can exit while a helper still holds its inherited workspace fd.
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()


def invoke(path, state, name, workspace_fd):
    generation = state["generation"]
    skill = Path(__file__).resolve().parent.parent / "SKILL.md"
    prompt = ("Carry out the next authorized step of this task. Preserve existing user work. "
              "Read live files and reconcile them with the continuity record. Return structured output "
              "matching the supplied schema. Report only actually completed steps and verified evidence; "
              "complete requires all original completion criteria. Do not modify controller state, locks, "
              "runtime scripts, launch plists or this task file. Do not launch another executor.\n\n"
              + skill.read_text() + "\n\nORIGINAL TASK:\n" + Path(state["task_file"]).read_text()
              + "\n\nCONTINUITY RECORD (evidence is agent-reported):\n" + json.dumps(state))
    with tempfile.TemporaryDirectory(prefix="follow-through-turn-") as tmp:
        schema, output = Path(tmp) / "schema.json", Path(tmp) / "result.json"
        schema.write_text(json.dumps(providers.RESULT_SCHEMA))
        command = providers.build_command(name, state["binaries"][name], prompt, str(schema), str(output), state["sessions"].get(name))
        with tempfile.TemporaryFile(mode="w+b") as stdout:
            child = subprocess.Popen(command, cwd=state["workspace"], env=dict(os.environ, PATH=state["path"]),
                                     stdout=stdout, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     start_new_session=True, pass_fds=(workspace_fd,))
            try:
                started = dict(pid=child.pid, provider=name, session_id=state["sessions"].get(name), at=time.time())
                if not change(path, generation, active=started, last_started=started):
                    return None
                while child.poll() is None:
                    if not still_current(path, generation):
                        return None
                    time.sleep(0.1)
                stdout.seek(0)
                result = providers.parse_result(name, stdout.read().decode("utf-8", "replace"), str(output))
                if child.returncode and result.get("status") != "quota":
                    result = dict(status="blocked", summary="Executor exited unsuccessfully (" + str(child.returncode) + ").",
                                  evidence=[], completed_steps=[], retry_at=None,
                                  session_id=result.get("session_id"))
                return result
            finally:
                stop_child(child)
                # Clear only our own informational PID, including after cancellation.
                with transaction(path) as latest:
                    if isinstance(latest.get("active"), dict) and latest["active"].get("pid") == child.pid:
                        latest["active"] = None


def run(path, wait=False, generation=None, no_schedule=False, retry_blocked=False):
    path = canonical(path, "file")
    initial = read_state(path)
    if retry_blocked:
        if generation is not None:
            raise ValueError("scheduled invocations cannot retry blocked tasks")
        with transaction(path) as latest:
            if latest["status"] != "blocked":
                raise ValueError("--retry-blocked requires a blocked task")
            latest.update(status="ready", generation=latest["generation"] + 1,
                          summary="User requested recovery; counters and progress retained.")
        initial = read_state(path)
    scheduled_invocation = generation is not None
    generation = initial["generation"] if generation is None else generation
    while True:
        state = read_state(path)
        if state["generation"] != generation or state["status"] in TERMINAL:
            return state
        due = state.get("next_at")
        if due is None or due <= time.time():
            break
        if not wait:
            return state
        time.sleep(min(0.25, due - time.time()))
    try:
        validate(state, check_environment=True)
    except (OSError, ValueError) as exc:
        finish(path, generation, "blocked", "Execution environment changed: " + str(exc))
        return read_state(path)
    fd = controller_lock("workspace", state["workspace"])
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not wait:
                    raise RuntimeError("another managed executor owns this workspace")
                if not still_current(path, generation):
                    return read_state(path)
                time.sleep(0.25)
        # Admission consumes a generation. A queued same-generation invocation is
        # stale even if this run later enters an unknown-reset or manual wait.
        with transaction(path) as admitted:
            if admitted["generation"] != generation or admitted["status"] in TERMINAL:
                return dict(admitted)
            due = admitted.get("next_at")
            if due is not None and due > time.time():
                return dict(admitted)
            admission_job = admitted.get("job")
            if scheduled_invocation and (not isinstance(admission_job, dict) or admission_job.get("generation") != generation):
                return dict(admitted)
            generation += 1
            admitted.update(status="running", next_at=None, generation=generation, job=None)
        cleanup_job(path, admission_job)
        exhausted = set()
        while still_current(path, generation):
            state = read_state(path)
            observations = observe(state)
            if not change(path, generation, observations=observations):
                break
            state["observations"] = observations
            name, wake = choose(state, exhausted, time.time())
            if name is None:
                change(path, generation, status="waiting", next_at=wake, active=None,
                       summary="Quota wait; " + ("manual resume required (reset unknown)." if wake is None else "observed reset saved."))
                if wake is not None and not no_schedule and still_current(path, generation):
                    try:
                        schedule(path, wake)
                    except (OSError, ValueError, RuntimeError) as exc:
                        change(path, generation, summary="Automatic resume not scheduled: " + str(exc))
                break
            if not change(path, generation, current_provider=name):
                break
            state["current_provider"] = name
            try:
                result = invoke(path, state, name, fd)
            except (OSError, subprocess.SubprocessError) as exc:
                failures = state["launch_failures"] + 1
                change(path, generation, launch_failures=failures, summary="Launch failed: " + str(exc))
                finish(path, generation, "blocked", "Launch failed; diagnose before retrying (attempt "
                       + str(failures) + "): " + str(exc))
                break
            if result is None or not still_current(path, generation):
                break
            if not isinstance(result, dict) or result.get("status") not in {"complete", "continue", "blocked", "quota"} or not isinstance(result.get("summary"), str) or any(not isinstance(result.get(key), list) or any(not isinstance(x, str) for x in result[key]) for key in ("evidence", "completed_steps")):
                finish(path, generation, "blocked", "Invalid executor result; manual diagnosis required.")
                break
            with transaction(path) as latest:
                if latest["generation"] != generation or latest["status"] in TERMINAL:
                    break
                before = set(latest["steps"])
                latest["steps"] = list(dict.fromkeys(latest["steps"] + result["completed_steps"]))
                latest["evidence"] = list(dict.fromkeys(latest["evidence"] + result["evidence"]))
                progress = bool(set(latest["steps"]) - before) and bool(result["evidence"])
                # Passive quota checks never reach here. An actual execution
                # resumption without progress counts even if it hits quota again.
                latest["no_progress"] = 0 if progress else latest["no_progress"] + 1
                latest["launch_failures"] = 0
                latest["summary"] = result["summary"]
                session = result.get("session_id")
                if isinstance(session, str) and session:
                    latest["sessions"][name] = session
                    if isinstance(latest.get("last_started"), dict):
                        latest["last_started"]["session_id"] = session
                count = latest["no_progress"]
                if result["status"] == "quota":
                    retry = result.get("retry_at")
                    latest["quota_blocks"][name] = retry if number(retry) and retry > time.time() else None
            if result["status"] == "complete":
                if result["completed_steps"] and result["evidence"]:
                    finish(path, generation, "complete", "Agent-reported completion: " + result["summary"])
                else:
                    finish(path, generation, "blocked", "Completion lacks completed steps and verification evidence.")
                break
            if result["status"] == "blocked" or count >= 3:
                finish(path, generation, "blocked", result["summary"] if count < 3 else "Three executions without evidenced progress; manual diagnosis required.")
                break
            if result["status"] == "quota":
                exhausted.add(name)
        return read_state(path)
    finally:
        os.close(fd)


def parse_time(value):
    try:
        result = float(value)
    except ValueError:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != datetime.timedelta(0):
            raise ValueError("schedule timestamp must explicitly use UTC")
        result = parsed.timestamp()
    if not number(result):
        raise ValueError("invalid time")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="save an explicitly authorized task without executing it")
    init.add_argument("--state", required=True)
    init.add_argument("--workspace", required=True)
    init.add_argument("--task-file", required=True)
    init.add_argument("--providers", nargs="+", choices=("codex", "claude"), required=True)
    init.add_argument("--claude-usage")
    for name in ("run", "status", "schedule", "cancel"):
        command = sub.add_parser(name)
        command.add_argument("--state", required=True)
        if name == "run":
            command.add_argument("--wait", action="store_true", help="wait without model calls until the persisted wake-up time")
            command.add_argument("--generation", type=int)
            command.add_argument("--no-schedule", action="store_true", help="save quota waits for manual resume")
            command.add_argument("--retry-blocked", action="store_true", help="explicitly retry a diagnosed blocked task, retaining progress and counters")
        elif name == "schedule":
            command.add_argument("--at", required=True, help="UTC ISO timestamp or epoch seconds")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            state = initialize(args)
        else:
            path = canonical(args.state, "file")
            if args.command == "run":
                state = run(path, args.wait, args.generation, args.no_schedule, args.retry_blocked)
            elif args.command == "schedule":
                state = schedule(path, parse_time(args.at))
            elif args.command == "cancel":
                state = cancel(path)
            else:
                state = read_state(path)
                try:
                    validate(state, check_environment=True)
                except (OSError, ValueError) as exc:
                    state = dict(state, environment_warning=str(exc))
        print(json.dumps(state, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print("follow-through: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
