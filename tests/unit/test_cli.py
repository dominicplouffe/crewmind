"""The `crewmind` command starts with an empty catalog (phase 0 exit; IF-4.3)."""

from __future__ import annotations

import subprocess
import sys


def test_IF_4_3_crewmind_help_runs() -> None:
    """IF-4.3: `crewmind --help` exits 0 and describes the command."""
    result = subprocess.run(
        [sys.executable, "-c", "from crewmind.surfaces.cli.main import main; main()", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage" in result.stdout
