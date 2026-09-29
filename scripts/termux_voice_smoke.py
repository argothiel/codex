#!/usr/bin/env python3
"""Verify the packaged helper protocol and runtime without opening audio devices."""

import argparse
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import time

RESPONSE_TIMEOUT = 30


def read_exact(stream, size, deadline):
    data = bytearray()
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([stream], [], [], remaining)[0]:
            raise RuntimeError("helper response timed out")
        chunk = os.read(stream.fileno(), size - len(data))
        if not chunk:
            raise RuntimeError("helper closed output before completing its response")
        data.extend(chunk)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve() / "codex-resources/voice"
    helper = root / "bin/codex-voice-host"
    env = {key: os.environ[key] for key in ("HOME", "TMPDIR") if key in os.environ}
    env.update(
        LD_LIBRARY_PATH=str(root / "lib"),
        LD_PRELOAD=str(root / "lib/libtermux-exec.so"),
    )
    for key in (
        "GST_PLUGIN_PATH",
        "GST_PLUGIN_PATH_1_0",
        "GST_PLUGIN_SYSTEM_PATH",
        "GST_PLUGIN_SYSTEM_PATH_1_0",
    ):
        env[key] = ""
    env.update(
        GST_REGISTRY="/dev/null", GST_REGISTRY_UPDATE="no", GST_REGISTRY_FORK="no"
    )
    commit = subprocess.check_output(
        [str(helper), "--build-commit"], env=env, text=True, timeout=RESPONSE_TIMEOUT
    ).strip()
    with subprocess.Popen(
        [str(helper)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
    ) as process:
        try:
            requests = (
                (dict(type="hello", protocol=1, buildCommit=commit), "ready"),
                (dict(type="initializeRuntime"), "runtimeReady"),
                (dict(type="close"), "closed"),
            )
            for message, expected in requests:
                payload = json.dumps(message).encode()
                process.stdin.write(struct.pack(">I", len(payload)) + payload)
                process.stdin.flush()
                deadline = time.monotonic() + RESPONSE_TIMEOUT
                header = read_exact(process.stdout, 4, deadline)
                size = struct.unpack(">I", header)[0]
                if size > 128 * 1024:
                    raise RuntimeError("oversized helper response")
                response = json.loads(read_exact(process.stdout, size, deadline))
                if response != {"type": expected}:
                    raise RuntimeError(f"unexpected response to {message['type']}")
                print(expected, flush=True)
            if process.wait(timeout=5) != 0:
                raise RuntimeError("helper shutdown failed")
            print("PASS: handshake, runtime initialization, shutdown")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
