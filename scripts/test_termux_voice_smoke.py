import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import termux_voice_smoke


HELPER = """import json
import struct
import sys
import time

scenario = {scenario!r}
if "--build-commit" in sys.argv:
    if scenario == "commit_timeout":
        time.sleep(60)
    print("dev")
    sys.exit(0)

for response in ("ready", "runtimeReady", "closed"):
    size = struct.unpack(">I", sys.stdin.buffer.read(4))[0]
    sys.stdin.buffer.read(size)
    payload = json.dumps(dict(type=response)).encode()
    frame = struct.pack(">I", len(payload)) + payload
    if scenario == "partial_header":
        frame = frame[:1]
    elif scenario == "partial_payload":
        frame = frame[:5]
    # Fragment even successful responses to exercise reads across pipe writes.
    for byte in frame:
        sys.stdout.buffer.write(bytes([byte]))
        sys.stdout.buffer.flush()
        time.sleep(0.001)
    if scenario.startswith("partial_"):
        time.sleep(60)
"""


class VoiceSmokeTests(unittest.TestCase):
    def run_smoke(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "codex-resources/voice/bin/codex-voice-host"
            helper.parent.mkdir(parents=True)
            helper.write_text(
                f"#!{sys.executable}\n" + HELPER.format(scenario=scenario)
            )
            helper.chmod(0o700)
            with (
                mock.patch.object(sys, "argv", ["voice-smoke", directory]),
                mock.patch.object(termux_voice_smoke, "RESPONSE_TIMEOUT", 1),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                termux_voice_smoke.main()
            return output.getvalue()

    def test_fragmented_responses_complete_the_handshake(self):
        self.assertIn("PASS: handshake", self.run_smoke("complete"))

    def test_partial_frames_time_out(self):
        for scenario in ("partial_header", "partial_payload"):
            with self.subTest(scenario=scenario):
                with self.assertRaisesRegex(RuntimeError, "helper response timed out"):
                    self.run_smoke(scenario)

    def test_build_commit_query_times_out(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_smoke("commit_timeout")


if __name__ == "__main__":
    unittest.main()
