"""Smoke tests for the user-facing offline CLI."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    # Matplotlib is optional, but if installed it must not try to write into a
    # read-only home directory during a headless export.
    env["MPLCONFIGDIR"] = str((cwd or PROJECT_ROOT) / ".mplconfig")
    return subprocess.run(
        [sys.executable, "-m", "lifesim", *args],
        cwd=cwd or PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_module_entrypoint_runs_offline_headless(tmp_path) -> None:
    output = tmp_path / "demo"
    result = _cli("headless", "--days", "1", "--agents", "2", "--seed", "123", "--output", str(output))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["population"] == 2
    assert payload["summary"]["minute"] == 1440
    assert (output / "lifesim.sqlite3").exists()
    assert (output / "simulation_report.md").exists()
    assert (output / "simulation_report.html").exists()
    assert (output / "observatory_dashboard.svg").exists()
    with sqlite3.connect(output / "lifesim.sqlite3") as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_inspect_reads_saved_experiment_and_agent(tmp_path) -> None:
    output = tmp_path / "demo"
    run = _cli("run", "--days", "1", "--agents", "2", "--seed", "321", "--output", str(output))
    assert run.returncode == 0, run.stderr
    db = output / "lifesim.sqlite3"
    result = _cli("inspect", "--db", str(db), "--agent", "agent_001")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["id"] == "agent_001"
    assert "needs" in payload
    assert "relationships" in payload


@pytest.mark.benchmark
def test_100_agent_365_day_headless_benchmark(tmp_path) -> None:
    output = tmp_path / "benchmark"
    result = _cli(
        "headless",
        "--benchmark",
        "--days",
        "365",
        "--agents",
        "100",
        "--seed",
        "42",
        "--output",
        str(output),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["benchmark"] is True
    assert payload["database"] is None
    assert payload["summary"]["population"] == 100
    assert payload["summary"]["minute"] == 365 * 1440
    assert payload["summary"]["events"] == 365
    assert not (output / "lifesim.sqlite3").exists()
