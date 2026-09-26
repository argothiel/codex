#!/usr/bin/env python3
"""Wait for an Actions build, download its CLI, and verify the artifact."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", type=int)
    parser.add_argument("--repo", default="argothiel/codex-termux")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run = str(args.run_id)
    subprocess.run(
        [
            "gh",
            "run",
            "watch",
            run,
            "--repo",
            args.repo,
            "--interval",
            "20",
            "--exit-status",
        ],
        check=True,
    )
    metadata = json.loads(
        subprocess.check_output(
            [
                "gh",
                "run",
                "view",
                run,
                "--repo",
                args.repo,
                "--json",
                "headSha,conclusion",
            ],
            text=True,
        )
    )
    if metadata["conclusion"] != "success":
        raise RuntimeError("the build did not succeed")
    commit = metadata["headSha"]
    output = (args.output or ROOT / ".artifacts/github-voice-cli" / run).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output.parent, prefix=".voice-download-"
    ) as temporary:
        artifact = output if output.exists() else Path(temporary) / "artifact"
        if not output.exists():
            subprocess.run(
                [
                    "gh",
                    "run",
                    "download",
                    run,
                    "--repo",
                    args.repo,
                    "--name",
                    f"android-voice-cli-{commit}",
                    "--dir",
                    str(artifact),
                ],
                check=True,
            )
        if (artifact / "SOURCE_COMMIT.txt").read_text().strip() != commit:
            raise RuntimeError("artifact revision does not match the build")
        verified = set()
        for line in (artifact / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split(maxsplit=1)
            path = (artifact / name).resolve()
            if not path.is_relative_to(artifact.resolve()):
                raise RuntimeError("checksum path escapes the artifact")
            with path.open("rb") as binary:
                actual = hashlib.file_digest(binary, "sha256").hexdigest()
            if actual != expected:
                raise RuntimeError(f"checksum mismatch: {name}")
            verified.add(name)
        if not {"bin/codex", "bin/libc++_shared.so"}.issubset(verified):
            raise RuntimeError("artifact lacks required checksums")
        if not output.exists():
            artifact.rename(output)
    print(f"PASS: downloaded and verified {commit}\n{output}")


if __name__ == "__main__":
    main()
