"""Exercise the documented CLI outside pytest's configured source path."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("python_flags", [[], ["-S"]])
def test_geographic_summary_help_without_pythonpath(tmp_path, python_flags):
    script = Path(__file__).resolve().parents[1] / "scripts/summarise_geographic_validation.py"
    env = {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}
    # -S additionally prevents an editable installation from masking a missing
    # source-path bootstrap. This help command needs only the standard library.
    result = subprocess.run(
        [sys.executable, *python_flags, str(script), "--help"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "--json" in result.stdout
