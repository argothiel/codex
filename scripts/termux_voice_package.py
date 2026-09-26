#!/usr/bin/env python3
"""Assemble a separate local Termux development package with its voice libraries."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = (
    "app",
    "audioconvert",
    "audioresample",
    "coreelements",
    "opus",
    "rtp",
    "rtpmanager",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--helper-only", action="store_true")
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
    build = ROOT / "codex-rs/target/debug"
    voice = output / "codex-resources/voice"
    libraries = voice / "lib"
    libraries.mkdir(parents=True)
    pending = []

    def copy(source, destination):
        if not source.is_file():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        pending.append(destination)

    copy(build / "codex-voice-host", voice / "bin/codex-voice-host")
    copy(prefix / "lib/libtermux-exec.so", libraries / "libtermux-exec.so")
    copy(prefix / "lib/libgstreamer-1.0.so", libraries / "libgstreamer-1.0.so")
    for plugin in PLUGINS:
        name = f"libgst{plugin}.so"
        copy(prefix / "lib/gstreamer-1.0" / name, libraries / "gstreamer-1.0" / name)
    if not args.helper_only:
        copy(build / "codex", output / "bin/codex")
        copy(build / "codex-code-mode-host", output / "bin/codex-code-mode-host")
        cpp = prefix / "lib/node_modules/@mmmbuto/codex-cli-termux/bin/libc++_shared.so"
        copy(cpp, output / "bin/libc++_shared.so")
        launcher = output / "run-codex"
        launcher.write_text(
            f"#!{prefix}/bin/sh\n"
            'PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1\n'
            'export LD_LIBRARY_PATH="$PACKAGE_DIR/bin:$PACKAGE_DIR/codex-resources/voice/lib"\n'
            'exec "$PACKAGE_DIR/bin/codex" "$@"\n'
        )
        launcher.chmod(0o700)
    examined = set()
    while pending:
        binary = pending.pop()
        if binary in examined:
            continue
        examined.add(binary)
        dynamic = subprocess.check_output(
            ["llvm-readelf", "--dynamic", str(binary)], text=True
        )
        for name in re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic):
            source = prefix / "lib" / name
            if source.is_file() and not (libraries / name).exists():
                copy(source, libraries / name)
    metadata = {
        "version": "0.156.1",
        "layoutVersion": 1,
        "entrypoint": "bin/codex",
        "resourcesDir": "codex-resources",
        "development": True,
    }
    (output / "codex-package.json").write_text(json.dumps(metadata, indent=2) + "\n")
    hashes = {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    (output / "files.sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
