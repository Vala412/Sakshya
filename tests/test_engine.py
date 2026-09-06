"""End-to-end regression gate: generate a labelled synthetic dataset, run it
through the full engine, and check every reason code hits perfect
precision/recall with zero false positives on clean cases.

Run as subprocesses (not imported directly) so this exercises the actual
scripts a user runs -- `python scripts/generate_synthetic.py` and
`python scripts/evaluate.py` -- rather than only the library code they call
into, catching regressions in the scripts' own CLI wiring too.

Read this the way the project docs insist on: a pass here means the
classifier still agrees with the generator's own assumptions about what
each code means. It is not evidence the codes are correct against a real
GSTR-2B export, which this project has never had access to.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_synthetic_eval_harness_passes_with_perfect_scores(tmp_path: Path) -> None:
    data_dir = tmp_path / "synthetic"

    generate = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_synthetic.py"),
            "--out-dir",
            str(data_dir),
            "--total",
            "60",
            "--clean",
            "12",
            "--seed",
            "1",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert generate.returncode == 0, generate.stdout + generate.stderr

    evaluate = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "evaluate.py"), "--data-dir", str(data_dir)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert evaluate.returncode == 0, evaluate.stdout + evaluate.stderr
    assert "RESULT: PASS" in evaluate.stdout
    assert "Clean cases: 12, false positives: 0" in evaluate.stdout
