"""Run each integration test file in its own Python process.

libobs has a known limitation: state from previous obs_startup/obs_shutdown
cycles can accumulate and cause heap corruption late in long test runs
(OBS Studio itself never restarts libobs in a single process). Running each
test file in a fresh subprocess fully isolates them.

Usage:  python scripts/run_tests.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
INT_TESTS = sorted((ROOT / "tests" / "integration").glob("test_*.py"))
UNIT_TESTS = ROOT / "tests" / "unit"
py = sys.executable

failed: list[str] = []

print("\n--- unit tests (single process) ---")
rc = subprocess.call([py, "-m", "pytest", str(UNIT_TESTS), "-q", "--tb=short"], cwd=ROOT)
if rc != 0:
    failed.append("unit")

for test_file in INT_TESTS:
    rel = test_file.relative_to(ROOT)
    print(f"\n--- {rel} ---")
    rc = subprocess.call([py, "-m", "pytest", str(rel), "-q", "--tb=short"], cwd=ROOT)
    if rc != 0:
        failed.append(str(rel))

print("\n=========================================")
print(f"  Failed:  {len(failed)}")
for f in failed: print(f"    - {f}")
sys.exit(1 if failed else 0)
