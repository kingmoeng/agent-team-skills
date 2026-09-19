import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/follow-through/scripts/providers.py"
spec = importlib.util.spec_from_file_location("providers_under_test", SCRIPT)
providers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(providers)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="provider test ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.output = self.root / "result.json"

    def result(self, **kwargs):
        return dict(status="complete", summary="Done", evidence=["tests passed"],
                    completed_steps=["step 1"], retry_at=None, **kwargs)

    def test_codex_resume_is_exact_session_and_literal_prompt(self):
        prompt = "literal $(touch bad) `pwd` --dangerously-bypass-approvals-and-sandbox"
        argv = providers.build_command("codex", "/path with spaces/codex", prompt,
                                       self.root / "schema.json", self.output, "specific-session")
        self.assertIn("resume", argv)
        self.assertIn("specific-session", argv)
        self.assertEqual(argv[-2:], ["--", prompt])
        self.assertNotIn("--last", argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)

    def test_claude_schema_and_permission_mode(self):
        argv = providers.build_command("claude", "claude", "task", "schema", self.output)
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), providers.RESULT_SCHEMA)
        self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_structured_results_and_session(self):
        self.output.write_text(json.dumps(self.result()))
        result = providers.parse_result("codex", '{"type":"thread.started","thread_id":"id"}\n', self.output)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["session_id"], "id")
        result = providers.parse_result("claude", json.dumps({"type": "result", "session_id": "c",
                    "structured_output": self.result()}), self.output)
        self.assertEqual(result["session_id"], "c")

    def test_denied_tools_override_claimed_completion(self):
        data = {"type": "result", "permission_denials": [{"tool_name": "Bash"}],
                "structured_output": self.result()}
        self.assertEqual(providers.parse_result("claude", json.dumps(data), self.output)["status"], "blocked")

    def test_error_overrides_stale_output_and_distinguishes_quota(self):
        self.output.write_text(json.dumps(self.result()))
        error = {"type": "turn.failed", "error": {"message": "connection failed"}}
        self.assertEqual(providers.parse_result("codex", json.dumps(error), self.output)["status"], "blocked")
        reset = time.time() + 200
        error["error"] = {"code": "usage_limit_reached", "resets_at": reset}
        result = providers.parse_result("codex", json.dumps(error), self.output)
        self.assertEqual(result["status"], "quota")
        self.assertEqual(result["retry_at"], reset)

    def test_task_text_mentioning_quota_is_not_error(self):
        data = {"type": "result", "structured_output": self.result()}
        data["structured_output"]["summary"] = "Implemented rate limit support"
        self.assertEqual(providers.parse_result("claude", json.dumps(data), self.output)["status"], "complete")

    def test_malformed_results_fail_closed(self):
        for data in ({}, {"status": "complete"}, dict(self.result(), retry_at=float("nan")),
                     dict(self.result(), evidence="test"), dict(self.result(), completed_steps=[42])):
            with self.subTest(data=data):
                self.output.write_text(json.dumps(data))
                self.assertEqual(providers.parse_result("codex", "", self.output)["status"], "blocked")

    def test_statusline_caches_only_quota_not_private_payload(self):
        cache = self.root / "usage.json"
        providers.capture_claude_status(json.dumps({"secret": "DO NOT STORE", "rate_limits": {
            "five_hour": {"used_percentage": 20, "resets_at": 9999999999},
            "seven_day": {"used_percentage": 100, "resets_at": 99999999999}}}), cache)
        value = providers.read_claude_usage(cache)
        self.assertEqual(len(value["windows"]), 2)
        self.assertNotIn("secret", cache.read_text())
        providers.capture_claude_status("{}", cache)
        self.assertEqual(providers.read_claude_usage(cache)["windows"], [])

    def test_invalid_observations_are_unknown(self):
        cache = self.root / "usage.json"
        self.assertIsNone(providers.read_claude_usage(cache))
        for value in ({"observed_at": 123, "windows": [{"used_percent": -1}]},
                      {"observed_at": float("nan"), "windows": []}, []):
            cache.write_text(json.dumps(value))
            self.assertIsNone(providers.read_claude_usage(cache))

    def test_statusline_wrap_preserves_command_settings_and_input(self):
        settings = self.root / "settings.json"
        previous = self.root / "old.json"
        cache = self.root / "usage.json"
        before = {"statusLine": {"type": "command", "command": "cat", "padding": 2}, "unrelated": {"keep": True}}
        raw_before = json.dumps(before).encode()
        settings.write_bytes(raw_before)
        providers.install_statusline(settings, cache, previous)
        providers.install_statusline(settings, cache, previous)
        after = json.loads(settings.read_text())
        self.assertEqual(after["unrelated"], before["unrelated"])
        self.assertEqual(after["statusLine"]["padding"], 2)
        self.assertEqual(json.loads(previous.read_text()), before["statusLine"])
        self.assertEqual(next(self.root.glob("settings.json.follow-through-backup-*")).read_bytes(), raw_before)
        payload = b'{"rate_limits":{"five_hour":{"used_percentage":10,"resets_at":9999999999}}}\n'
        process = subprocess.run([sys.executable, str(SCRIPT), "claude-statusline", "--cache", str(cache),
                                  "--previous", str(previous)], input=payload, capture_output=True)
        self.assertEqual(process.stdout, payload)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(providers.read_claude_usage(cache)["windows"][0]["used_percent"], 10)

    def test_statusline_changed_by_user_is_not_overwritten(self):
        settings, previous = self.root / "settings.json", self.root / "previous.json"
        settings.write_text('{"statusLine":{"type":"command","command":"printf hello"}}')
        previous.write_text("{}")
        with self.assertRaises(ValueError):
            providers.install_statusline(settings, self.root / "cache", previous)
        self.assertEqual(json.loads(settings.read_text())["statusLine"]["command"], "printf hello")

    def test_probe_timeout_reaps_child(self):
        # Use the real stdin/stdout protocol with a local fake server, no network/model.
        fake = self.root / "server"
        fake.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(20)\n")
        fake.chmod(0o700)
        with self.assertRaises(TimeoutError):
            providers.probe_codex(str(fake), timeout=0.05)

    def test_probe_handshake_and_both_windows(self):
        fake = self.root / "server"
        fake.write_text('''#!/usr/bin/env python3
import json,sys
init=json.loads(sys.stdin.readline())
assert init["method"] == "initialize"
print(json.dumps({"id":1,"result":{}}),flush=True)
assert json.loads(sys.stdin.readline())["method"] == "initialized"
query=json.loads(sys.stdin.readline())
assert query["method"] == "account/rateLimits/read"
print(json.dumps({"id":2,"result":{"rateLimits":{"primary":{"usedPercent":25,"resetsAt":9999999999},"secondary":{"usedPercent":100,"resetsAt":99999999999}}}}),flush=True)
sys.stdin.read()
''')
        fake.chmod(0o700)
        result = providers.probe_codex(str(fake))
        self.assertEqual([w["used_percent"] for w in result["windows"]], [25, 100])


if __name__ == "__main__":
    unittest.main()
