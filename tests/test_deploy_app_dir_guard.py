"""Fail-closed release selection: local subprocess tests, never deploy or restart."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "deploy.sh"


def test_deploy_requires_explicit_app_dir_before_touching_services(tmp_path: Path) -> None:
    """Missing/empty APP_DIR must exit before attempting a service operation."""
    marker = tmp_path / "called"
    for name in ("git", "systemctl", "curl"):
        fake = tmp_path / name
        fake.write_text(f"#!/bin/sh\nprintf '%s\n' {name} >> {marker}\nexit 99\n")
        fake.chmod(0o755)
    env = os.environ.copy()
    env.pop("APP_DIR", None)
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    for omitted in (True, False):
        if not omitted:
            env["APP_DIR"] = ""
        result = subprocess.run(
            ["bash", str(SCRIPT), "--detect"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2, (result.stdout, result.stderr)
        assert "必须显式指定 APP_DIR" in result.stderr
        assert not marker.exists(), "service/checkout command called before APP_DIR guard"


def test_deploy_rejects_invalid_explicit_directory_without_restart(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["APP_DIR"] = str(tmp_path / "does-not-exist")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--detect"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "APP_DIR 不存在" in result.stderr
