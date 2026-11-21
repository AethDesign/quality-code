#!/usr/bin/env python3
"""Run frozen ServiceFlow tests with a deterministic replacement for one timing check."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVICEFLOW = ROOT / "benchmarks" / "serviceflow-mvp-2026-10"
# The frozen original can time out before the child emits its start event.
# The replacement exercises execute_phase with an emitted event and a mocked process timeout.
REPLACED_TEST = "test_completion_runner.CompletionTests.test_native_phase_global_timeout_is_observable"
NATIVE_ROOT = "44444444-4444-4444-4444-444444444444"

sys.path.insert(0, str(SERVICEFLOW))
import run as serviceflow_run  # noqa: E402


def flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def select_cases(cases):
    matches = [case for case in cases if case.id() == REPLACED_TEST]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one frozen test to replace: {REPLACED_TEST!r}, found {len(matches)}")
    return [case for case in cases if case is not matches[0]]


class TimeoutReplacementTests(unittest.TestCase):
    def test_execute_phase_timeout_is_observable_with_native_event_and_snapshot(self):
        class FakePopen:
            def __init__(self, args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                self.returncode = None
                self.pid = 4242
                self.timeout = None
                kwargs["stdout"].write(
                    (json.dumps({"type": "thread.started", "thread_id": NATIVE_ROOT}) + "\n").encode()
                )

            def communicate(self, *, input=None, timeout=None):
                self.timeout = timeout
                raise subprocess.TimeoutExpired(self.args, timeout)

        def terminate(process, grace=2):
            process.returncode = -15

        with tempfile.TemporaryDirectory(prefix="serviceflow-timeout-contract-") as tmp:
            root = Path(tmp).resolve()
            site = root / "site"
            site.mkdir()
            sessions = root / "sessions"
            sessions.mkdir()
            (sessions / "native-root.jsonl").write_text(
                json.dumps({"type": "session_meta", "payload": {"id": NATIVE_ROOT, "cwd": str(site)}})
                + "\n"
                + json.dumps({"type": "turn_context", "payload": {"model": "fixture-model"}})
                + "\n"
            )
            protocol = {"sessions_dir": str(sessions), "cleanup_reserve_seconds": 0.01}
            metadata = {"phases": []}
            deadline = serviceflow_run.time.monotonic() + 5
            with patch.object(serviceflow_run, "command", return_value=["fake-native-cli"]), \
                 patch.object(serviceflow_run.subprocess, "Popen", FakePopen), \
                 patch.object(serviceflow_run, "terminate_group", side_effect=terminate) as cleanup:
                phase, phase_dir = serviceflow_run.execute_phase(
                    "single", site, root, protocol, metadata, deadline, b"brief",
                    role="builder", number=2, resume=NATIVE_ROOT, env={},
                )

            self.assertEqual(phase["state"], "timed_out")
            self.assertEqual(phase["root_id"], NATIVE_ROOT)
            self.assertEqual(phase["exit_code"], -15)
            self.assertIsNone(phase["cli_usage"])
            self.assertEqual(phase["native_before"]["id"], NATIVE_ROOT)
            self.assertEqual(phase["native_after"]["id"], NATIVE_ROOT)
            self.assertEqual(phase["native_after"]["actual_models"], ["fixture-model"])
            self.assertEqual(cleanup.call_count, 1)
            process = cleanup.call_args.args[0]
            self.assertIsNotNone(process.timeout)
            self.assertGreater(process.timeout, 0)
            self.assertLessEqual(process.timeout, 5)
            persisted = json.loads((phase_dir / "metadata.json").read_text())
            self.assertEqual(persisted["state"], "timed_out")
            self.assertIsNone(persisted["cli_usage"])
            self.assertEqual(serviceflow_run.parse_events(phase_dir / "events.jsonl")[0], NATIVE_ROOT)


def main() -> int:
    loader = unittest.defaultTestLoader
    discovered = loader.discover(str(SERVICEFLOW), pattern="test_*.py", top_level_dir=str(SERVICEFLOW))
    global DISCOVERED_CASES
    DISCOVERED_CASES = list(flatten(discovered))
    if loader.errors:
        print("ERROR: ServiceFlow test discovery failed:\n" + "\n".join(loader.errors), file=sys.stderr)
        return 2
    try:
        selected = select_cases(DISCOVERED_CASES)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Using deterministic timeout replacement for {REPLACED_TEST}", flush=True)
    replacement = loader.loadTestsFromTestCase(TimeoutReplacementTests)
    suite = unittest.TestSuite([*selected, replacement])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
