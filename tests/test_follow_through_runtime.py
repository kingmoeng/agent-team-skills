import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/follow-through/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("follow_runtime", SCRIPTS / "runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def result(status="complete", steps=None, evidence=None, session="session"):
    return dict(status=status, summary="checked", completed_steps=steps if steps is not None else ["step"],
                evidence=evidence if evidence is not None else ["test passed"], session_id=session, retry_at=None)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="runtime tests ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.locks = self.root / "controller locks"
        lock_patch = mock.patch.object(runtime, "LOCK_ROOT", self.locks)
        lock_patch.start()
        self.addCleanup(lock_patch.stop)
        self.task = self.root / "task instructions.txt"
        self.task.write_text("Only run the fake test executor.")
        self.path = self.root / "state with spaces.json"
        self.binary = str(Path(sys.executable).resolve())
        args = argparse.Namespace(state=str(self.path), workspace=str(self.root), task_file=str(self.task),
                                  providers=["codex", "claude"], claude_usage=None)
        with mock.patch.object(runtime.shutil, "which", return_value=self.binary):
            runtime.initialize(args)
        self.observations = {p: dict(observed_at=time.time(), windows=[dict(used_percent=10, resets_at=None)]) for p in ("codex", "claude")}
        self.observe = mock.patch.object(runtime, "observe", side_effect=lambda s: self.observations)
        self.observe.start()
        self.addCleanup(self.observe.stop)

    def invoke_results(self, results):
        calls = []
        def invoke(path, state, provider, fd):
            calls.append((provider, dict(state["sessions"]), list(state["steps"])))
            return results.pop(0)
        return calls, mock.patch.object(runtime, "invoke", side_effect=invoke)

    def test_multistep_sessions_and_completion(self):
        calls, patch = self.invoke_results([result("continue", ["one"]), result("complete", ["two"])])
        with patch:
            state = runtime.run(self.path)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["steps"], ["one", "two"])
        self.assertEqual(calls[1][1], {"codex": "session"})
        self.assertIn("Agent-reported", state["summary"])

    def test_quota_handoff_and_returning_session(self):
        quota_result = result("quota", [], [], "codex-session")
        calls, patch = self.invoke_results([result("continue", ["one"], session="codex-session"), quota_result,
                                          result("continue", ["two"], session="claude-session"), result("complete", ["three"], session="claude-session")])
        with patch:
            state = runtime.run(self.path, no_schedule=True)
        self.assertEqual([x[0] for x in calls], ["codex", "codex", "claude", "claude"])
        self.assertEqual(state["sessions"], {"codex": "codex-session", "claude": "claude-session"})
        self.assertEqual(state["steps"], ["one", "two", "three"])

    def test_unknown_quota_not_retried(self):
        self.observations = {}
        calls, patch = self.invoke_results([result("quota", [], []), result("quota", [], [])])
        with patch:
            state = runtime.run(self.path, no_schedule=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(state["status"], "waiting")
        self.assertIsNone(state["next_at"])
        self.assertEqual(state["no_progress"], 2)

    def test_repeated_quota_execution_resumptions_are_bounded(self):
        self.observations = {}
        calls, patch = self.invoke_results([result("quota", [], []) for _ in range(3)])
        with patch:
            self.assertEqual(runtime.run(self.path, no_schedule=True)["status"], "waiting")
            state = runtime.run(self.path, no_schedule=True)
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(len(calls), 3)

    def test_passive_wait_does_not_increment_no_progress(self):
        now = time.time()
        self.observations = {name: dict(observed_at=now, windows=[dict(used_percent=100, resets_at=now + 300)]) for name in ("codex", "claude")}
        with mock.patch.object(runtime, "invoke") as invoke:
            state = runtime.run(self.path, no_schedule=True)
        invoke.assert_not_called()
        self.assertEqual(state["no_progress"], 0)
        self.assertEqual(state["next_at"], now + 305)

    def test_blocking_windows_and_stale_observations(self):
        now = time.time()
        observation = dict(observed_at=now - 1000, windows=[dict(used_percent=100, resets_at=now + 20), dict(used_percent=100, resets_at=now + 80)])
        self.assertEqual(runtime.quota(observation, now), (None, now + 80, True))
        self.assertEqual(runtime.quota(observation, now + 90), (None, None, False))
        observation["observed_at"] = now
        observation["windows"].append(dict(used_percent=100, resets_at=None))
        self.assertEqual(runtime.quota(observation, now), (None, None, True))

    def test_stickiness_and_known_capacity_preference(self):
        state = runtime.read_state(self.path)
        state.update(observations=self.observations, current_provider="claude")
        self.assertEqual(runtime.choose(state, set(), time.time())[0], "claude")
        state["observations"]["claude"] = None
        self.assertEqual(runtime.choose(state, set(), time.time())[0], "codex")

    def test_three_no_progress_blocks(self):
        calls, patch = self.invoke_results([result("continue", [], []) for _ in range(3)])
        with patch:
            state = runtime.run(self.path)
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(len(calls), 3)

    def test_launch_failure_bounded(self):
        with mock.patch.object(runtime, "invoke", side_effect=OSError("cannot exec")) as invoke:
            state = runtime.run(self.path)
            self.assertEqual(invoke.call_count, 1)
            state = runtime.run(self.path, retry_blocked=True)
            self.assertEqual(invoke.call_count, 2)
        self.assertEqual(state["launch_failures"], 2)
        self.assertEqual(state["status"], "blocked")

    def test_init_creates_state_directory(self):
        target = self.root / "new control directory" / "run.json"
        args = argparse.Namespace(state=str(target), workspace=str(self.root), task_file=str(self.task),
                                  providers=["codex"], claude_usage=None)
        with mock.patch.object(runtime.shutil, "which", return_value=self.binary):
            runtime.initialize(args)
        self.assertEqual(runtime.read_state(target)["status"], "ready")

    def test_retry_does_not_reset_progress_or_recovery(self):
        runtime.change(self.path, 1, steps=["existing"], no_progress=2)
        runtime.finish(self.path, 1, "blocked", "needs input")
        calls, patch = self.invoke_results([result("complete", ["final"])])
        with patch:
            state = runtime.run(self.path, retry_blocked=True)
        self.assertEqual(calls[0][2], ["existing"])
        self.assertEqual(state["steps"], ["existing", "final"])

    def test_active_task_cannot_be_rescheduled(self):
        runtime.change(self.path, 1, status="running")
        with mock.patch.object(runtime.sys, "platform", "darwin"), mock.patch.object(runtime.shutil, "which", return_value="/bin/launchctl"):
            with self.assertRaisesRegex(ValueError, "active executor"):
                runtime.schedule(self.path, time.time() + 10)

    def test_malformed_and_evidenceless_completion_block(self):
        with mock.patch.object(runtime, "invoke", return_value={"status": "complete"}):
            self.assertEqual(runtime.run(self.path)["status"], "blocked")

    def test_stale_generation_and_before_due_never_invoke(self):
        with mock.patch.object(runtime, "invoke") as invoke:
            runtime.run(self.path, generation=50)
            runtime.change(self.path, 1, next_at=time.time() + 300, status="waiting")
            runtime.run(self.path)
        invoke.assert_not_called()

    def test_workspace_lock_excludes_second_state(self):
        fd = runtime.controller_lock("workspace", self.root)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with mock.patch.object(runtime, "invoke") as invoke, self.assertRaisesRegex(RuntimeError, "owns this workspace"):
                runtime.run(self.path)
            invoke.assert_not_called()
        finally:
            os.close(fd)

    def test_real_child_start_checkpoint_and_cancel(self):
        marker = self.root / "started"
        script = "from pathlib import Path; import time; Path(" + repr(str(marker)) + ").write_text('yes'); time.sleep(30)"
        errors = []
        def runner():
            try:
                runtime.run(self.path)
            except Exception as exc:
                errors.append(exc)
        with mock.patch.object(runtime.providers, "build_command", return_value=[self.binary, "-c", script]):
            thread = threading.Thread(target=runner)
            thread.start()
            deadline = time.time() + 5
            while not marker.exists() and time.time() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            active = runtime.read_state(self.path)["active"]
            self.assertIsInstance(active["pid"], int)
            runtime.cancel(self.path)
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            with self.assertRaises(ProcessLookupError):
                os.kill(active["pid"], 0)
            self.assertIsNone(runtime.read_state(self.path)["active"])
            fd = runtime.controller_lock("workspace", self.root)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)

    def test_parent_death_child_inherits_workspace_lock(self):
        # Run the actual invoke path in a sacrificial parent, then kill only parent.
        marker = self.root / "child pid"
        child_script = "import os,time; from pathlib import Path; Path(" + repr(str(marker)) + ").write_text(str(os.getpid())); time.sleep(4)"
        parent_script = ("import sys; sys.path.insert(0," + repr(str(SCRIPTS)) + "); import runtime; "
                         "runtime.LOCK_ROOT=runtime.Path(" + repr(str(self.locks)) + "); "
                         "runtime.observe=lambda s:{}; runtime.providers.build_command=lambda *a:[sys.executable,'-c'," + repr(child_script) + "]; "
                         "runtime.run(" + repr(str(self.path)) + ")")
        parent = subprocess.Popen([self.binary, "-c", parent_script], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        child_pid = None
        try:
            deadline = time.time() + 5
            while not marker.exists() and time.time() < deadline and parent.poll() is None:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), parent.stderr.read().decode() if parent.poll() is not None else "no child")
            child_pid = int(marker.read_text())
            parent.kill()
            parent.wait()
            fd = runtime.controller_lock("workspace", self.root)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait()
            parent.stderr.close()
            if child_pid:
                try:
                    os.kill(child_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def test_schedule_payload_failure_cleanup_and_literal_spaces(self):
        home = self.root / "home with spaces"
        home.mkdir()
        with mock.patch.object(runtime.sys, "platform", "darwin"), mock.patch.object(runtime.Path, "home", return_value=home), mock.patch.object(runtime.shutil, "which", return_value="/bin/launchctl"), mock.patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as launch:
            state = runtime.schedule(self.path, time.time() + 120)
            target = Path(state["job"]["plist"])
            payload = plistlib.loads(target.read_bytes())
            self.assertEqual(payload["ProgramArguments"][4], str(self.path))
            self.assertTrue(payload["RunAtLoad"])
            self.assertNotIn("KeepAlive", payload)
            self.assertIsNone(state["last_started"])
            self.assertEqual(launch.call_args.args[0][-1], str(target))
            runtime.cancel(self.path)
            self.assertFalse(target.exists())

    def test_scheduler_failure_is_manual_wait(self):
        home = self.root / "home"
        home.mkdir()
        with mock.patch.object(runtime.sys, "platform", "darwin"), mock.patch.object(runtime.Path, "home", return_value=home), mock.patch.object(runtime.shutil, "which", return_value="/bin/launchctl"), mock.patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 5, "", "denied")):
            state = runtime.schedule(self.path, time.time() + 120)
            self.assertEqual(state["status"], "waiting")
            self.assertIsNone(state["job"])
            self.assertIn("not scheduled", state["summary"])
            self.assertEqual(list((home / "Library/LaunchAgents").glob("*.plist")), [])

    def test_scheduler_uses_background_user_domain_without_gui(self):
        home = self.root / "background home"
        home.mkdir()
        def launch(command, **kwargs):
            unavailable = command[1] == "print" and command[2].startswith("gui/")
            return subprocess.CompletedProcess(command, 125 if unavailable else 0, "", "")
        with mock.patch.object(runtime.sys, "platform", "darwin"), mock.patch.object(runtime.Path, "home", return_value=home), mock.patch.object(runtime.shutil, "which", return_value="/bin/launchctl"), mock.patch.object(runtime.subprocess, "run", side_effect=launch):
            state = runtime.schedule(self.path, time.time() + 120)
            self.assertEqual(state["job"]["domain"], "user/" + str(os.getuid()))
            runtime.cancel(self.path)

    def test_reject_custom_provider_arguments(self):
        state = runtime.read_state(self.path)
        state["binaries"]["codex"] = {"executable": self.binary, "args": ["--unsafe"]}
        with self.assertRaises(ValueError):
            runtime.validate(state)

    def test_late_cancel_preserves_completion(self):
        runtime.finish(self.path, 1, "complete", "verified")
        before = runtime.read_state(self.path)
        self.assertEqual(runtime.cancel(self.path), before)

    def test_cancel_and_status_survive_environment_drift(self):
        self.task.unlink()
        self.assertEqual(runtime.read_state(self.path)["status"], "ready")
        self.assertEqual(runtime.cancel(self.path)["status"], "cancelled")

    def test_unknown_capacity_keeps_current_provider(self):
        state = runtime.read_state(self.path)
        state.update(observations={}, current_provider="claude")
        self.assertEqual(runtime.choose(state, set(), time.time())[0], "claude")

    def test_queued_generation_cannot_execute_new_manual_wait(self):
        self.observations = {}
        calls, patch = self.invoke_results([result("quota", [], []), result("quota", [], [])])
        with patch:
            state = runtime.run(self.path, no_schedule=True)
            self.assertEqual(state["status"], "waiting")
            self.assertGreater(state["generation"], 1)
            runtime.run(self.path, wait=True, generation=1)
        self.assertEqual(len(calls), 2)

    def test_due_time_rechecked_after_lock(self):
        original = runtime.controller_lock
        def lock(kind, path):
            if kind == "workspace":
                with runtime.transaction(self.path) as state:
                    state.update(status="waiting", next_at=time.time() + 3600)
            return original(kind, path)
        with mock.patch.object(runtime, "controller_lock", side_effect=lock), mock.patch.object(runtime, "invoke") as invoke:
            state = runtime.run(self.path)
        invoke.assert_not_called()
        self.assertEqual(state["status"], "waiting")

    def test_scheduled_generation_requires_matching_job(self):
        with mock.patch.object(runtime, "invoke") as invoke:
            runtime.run(self.path, generation=1)
        invoke.assert_not_called()

    def test_real_child_result_and_nonzero_exit(self):
        payload = result()
        payload.pop("session_id")
        def command(provider, executable, prompt, schema, output, session):
            script = "from pathlib import Path; Path(" + repr(output) + ").write_text(" + repr(json.dumps(payload)) + "); print('{\"type\":\"thread.started\",\"thread_id\":\"real-session\"}')"
            return [self.binary, "-c", script]
        with mock.patch.object(runtime.providers, "build_command", side_effect=command):
            state = runtime.run(self.path)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["last_started"]["session_id"], "real-session")
        self.assertEqual(state["sessions"]["codex"], "real-session")

    def test_nonzero_exit_cannot_claim_completion(self):
        with mock.patch.object(runtime.providers, "build_command", return_value=[self.binary, "-c", "raise SystemExit(2)"]), mock.patch.object(runtime.providers, "parse_result", return_value=result()):
            state = runtime.run(self.path)
        self.assertEqual(state["status"], "blocked")
        self.assertIn("unsuccessfully", state["summary"])

    def test_exited_cli_helpers_do_not_retain_workspace_lock(self):
        payload = result()
        payload.pop("session_id")
        def command(provider, executable, prompt, schema, output, session):
            code = ("import subprocess,sys; from pathlib import Path; "
                    "subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],close_fds=False); "
                    "Path(" + repr(output) + ").write_text(" + repr(json.dumps(payload)) + ")")
            return [self.binary, "-c", code]
        with mock.patch.object(runtime.providers, "build_command", side_effect=command):
            state = runtime.run(self.path)
        self.assertEqual(state["status"], "complete")
        fd = runtime.controller_lock("workspace", self.root)
        try:
            # Signal delivery can lag the direct child's exit very briefly.
            deadline = time.monotonic() + 3
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        self.fail("Exited CLI helper retained workspace lock")
                    time.sleep(0.02)
        finally:
            os.close(fd)

    def test_return_to_provider_resumes_its_own_session(self):
        with runtime.transaction(self.path) as state:
            state["sessions"] = {"codex": "old-codex", "claude": "old-claude"}
            state["current_provider"] = "claude"
        self.observations["claude"] = dict(observed_at=time.time(), windows=[dict(used_percent=100, resets_at=time.time() + 600)])
        calls, patch = self.invoke_results([result()])
        with patch:
            runtime.run(self.path)
        self.assertEqual(calls[0][0], "codex")
        self.assertEqual(calls[0][1]["codex"], "old-codex")


if __name__ == "__main__":
    unittest.main()
