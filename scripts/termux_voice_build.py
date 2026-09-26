#!/usr/bin/env python3
"""Build the development voice helper or CLI natively on Termux, with a live log."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "component", choices=("helper", "cli", "code-mode-host", "test", "fix")
    )
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--jobs", default="3")
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    env = dict(os.environ)
    prefix = Path(env.get("PREFIX", "/data/data/com.termux/files/usr"))
    clang = shutil.which("clang")
    if clang is None:
        parser.error("Termux clang is required")
    builtins = subprocess.check_output(
        [clang, "-print-libgcc-file-name"], text=True
    ).strip()
    toolchain = ROOT / ".artifacts/termux-voice-toolchain"
    toolchain.mkdir(parents=True, exist_ok=True)
    linker = toolchain / "clang"
    # Rust disables the compiler driver's default runtime libraries. V8 needs
    # compiler-rt's cache-flush routine; native TLS needs Termux's OpenSSL before
    # Android's incompatible libssl in /system/lib64. C compilation is unchanged.
    linker.write_text(
        f"#!{sys.executable}\nimport os, sys\nargs = sys.argv[1:]\n"
        'if "-nodefaultlibs" in args:\n'
        f"    args = [{('-L' + str(prefix / 'lib'))!r}, *args, {builtins!r}]\n"
        f"os.execv({clang!r}, [{clang!r}, *args])\n"
    )
    linker.chmod(0o700)
    env.update(
        {
            "CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER": "clang",
            "CARGO_TARGET_AARCH64_LINUX_ANDROID_RUSTFLAGS": f"-L native=/system/lib64 -C link-arg=-Wl,-rpath,{prefix}/lib",
            "CC_aarch64_linux_android": "clang",
            "CXX_aarch64_linux_android": "clang++",
            "CARGO_PROFILE_DEV_DEBUG": "0",
            "CARGO_PROFILE_TEST_DEBUG": "0",
            "CARGO_BUILD_JOBS": args.jobs,
            "PROTOC": str(prefix / "bin/protoc"),
            "PATH": os.pathsep.join(
                [str(toolchain), str(Path.home() / ".local/bin"), env["PATH"]]
            ),
        }
    )
    if args.component in ("cli", "code-mode-host"):
        artifacts = ROOT / ".artifacts/rusty_v8/rusty-v8-v150.4.0"
        archive = (
            artifacts / "librusty_v8_ptrcomp_sandbox_release_aarch64-linux-android.a.gz"
        )
        bindings = (
            artifacts / "src_binding_ptrcomp_sandbox_release_aarch64-linux-android.rs"
        )
        if not archive.is_file() or not bindings.is_file():
            parser.error("run scripts/fetch_rusty_v8_android.py first")
        env.update(
            RUSTY_V8_ARCHIVE=str(archive), RUSTY_V8_SRC_BINDING_PATH=str(bindings)
        )
        cpp = prefix / "lib/node_modules/@mmmbuto/codex-cli-termux/bin/libc++_shared.so"
        if not cpp.is_file():
            parser.error(
                "matching libc++_shared.so from the Termux Codex package is required"
            )
        package, binary = (
            ("codex-cli", "codex")
            if args.component == "cli"
            else ("codex-code-mode-host", "codex-code-mode-host")
        )
        command = [
            "cargo",
            "rustc",
            "-p",
            package,
            "--bin",
            binary,
            "--",
            "-C",
            f"link-arg={cpp}",
            "-C",
            "link-arg=-Wl,-rpath,$ORIGIN",
        ]
    elif args.component == "helper":
        command = ["cargo", "build", "-p", "codex-voice-host"]
    else:
        command = ["just", args.component, *args.args]
    args.log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    state_path = args.log.with_suffix(".state.json")
    state = {
        "pid": os.getpid(),
        "started": datetime.now().astimezone().isoformat(),
        "status": "running",
        "command": command,
    }
    state_path.write_text(json.dumps(state) + "\n")
    with args.log.open("a") as log:
        log.write(f"\nStarted: {datetime.now().astimezone().isoformat()}\n")
        log.write(f"Command: {command!r}\n")
        log.flush()
        with subprocess.Popen(
            command,
            cwd=ROOT / "codex-rs",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        ) as process:
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end="", flush=True)
            result = process.wait()
            log.write(
                f"Exit status: {result}; elapsed: {time.monotonic() - started:.1f}s\n"
            )
    state.update(status="finished", exit_code=result)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state) + "\n")
    temporary.replace(state_path)
    return result


if __name__ == "__main__":
    sys.exit(main())
