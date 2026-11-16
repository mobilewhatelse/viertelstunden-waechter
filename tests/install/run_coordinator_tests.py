"""Runs every coordinator test (tests/install/*_test.py) - found automatically, so a new one is never forgotten. They need Home
Assistant, so this runs in its Docker image (locally in the test chain and on GitHub):

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/run_coordinator_tests.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
tests = sorted(here.glob("*_test.py"))
failed = []
for f in tests:
    print(f"== {f.name}", flush=True)
    if subprocess.run([sys.executable, str(f)], check=False).returncode != 0:
        failed.append(f.name)
print(f"COORDINATOR: {len(tests) - len(failed)} of {len(tests)} test files passed" + (f", FAILED: {', '.join(failed)}" if failed else ""))
sys.exit(1 if failed or not tests else 0)
