#!/usr/bin/env python3
"""Deploy BizAtlas backend + frontend to the production host via SSH/SFTP.

Password must come from env BIZATLAS_SSH_PASSWORD (never hardcoded).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "139.224.163.203"
USER = "root"
REMOTE_APP = "/opt/bizatlas"
REMOTE_WEB = "/www/wwwroot/sy-realm.ltd/bizatlas"
HEALTH_CMD = "curl -s http://127.0.0.1:8000/v1/health/ready"

# Local paths relative to repo root -> remote under REMOTE_APP (same relative path)
BACKEND_GLOBS = [
    "packages/bizatlas",
    "apps/api",
]
BACKEND_FILES = [
    "content/rules/seed_financial.yaml",
    "content/fixtures/risky/company.json",
    "content/validation/backtest_report.json",
    "scripts/backtest_run.py",
]
OPTIONAL_DIRS = [
    "content/compliance",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def require_password() -> str:
    pw = os.environ.get("BIZATLAS_SSH_PASSWORD", "").strip()
    if not pw:
        print("ERROR: BIZATLAS_SSH_PASSWORD is not set", file=sys.stderr)
        sys.exit(1)
    return pw


def iter_local_files(root: Path, rel: str) -> list[Path]:
    p = root / rel
    if not p.exists():
        return []
    if p.is_file():
        return [p]
    files: list[Path] = []
    for f in p.rglob("*"):
        if f.is_file():
            # skip caches / bytecode
            parts = set(f.parts)
            if "__pycache__" in parts or ".pyc" in f.suffixes:
                continue
            files.append(f)
    return files


def sftp_mkdirs(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    cur = ""
    for part in parts:
        cur = f"{cur}/{part}"
        try:
            sftp.stat(cur)
        except OSError:
            sftp.mkdir(cur)


def upload_file(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    sftp_mkdirs(sftp, str(Path(remote).parent).replace("\\", "/"))
    sftp.put(str(local), remote)


def upload_tree(
    sftp: paramiko.SFTPClient,
    root: Path,
    local_rel: str,
    remote_base: str,
    *,
    strip_prefix: str | None = None,
) -> int:
    """Upload local_rel under root to remote_base preserving structure.

    If strip_prefix is set (e.g. 'apps/web/dist'), remote paths are relative
    to that prefix under remote_base.
    """
    count = 0
    for local in iter_local_files(root, local_rel):
        rel = local.relative_to(root).as_posix()
        if strip_prefix:
            if not rel.startswith(strip_prefix.rstrip("/") + "/") and rel != strip_prefix.rstrip("/"):
                continue
            suffix = rel[len(strip_prefix.rstrip("/")) :].lstrip("/")
            remote = f"{remote_base.rstrip('/')}/{suffix}" if suffix else remote_base.rstrip("/")
        else:
            remote = f"{remote_base.rstrip('/')}/{rel}"
        upload_file(sftp, local, remote)
        count += 1
        print(f"  PUT {rel} -> {remote}")
    return count


def run_remote(ssh: paramiko.SSHClient, cmd: str) -> tuple[int, str, str]:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def main() -> int:
    root = repo_root()
    password = require_password()

    dist = root / "apps" / "web" / "dist"
    if not (dist / "index.html").is_file():
        print(f"ERROR: missing frontend build at {dist / 'index.html'}", file=sys.stderr)
        return 1

    print(f"Connecting {USER}@{HOST} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=password, timeout=30)
    sftp = ssh.open_sftp()

    results: dict[str, object] = {}
    try:
        for d in (REMOTE_APP, REMOTE_WEB, f"{REMOTE_APP}/packages", f"{REMOTE_APP}/apps", f"{REMOTE_APP}/content", f"{REMOTE_APP}/scripts"):
            print(f"mkdir -p {d}")
            code, out, err = run_remote(ssh, f"mkdir -p {d}")
            if code != 0:
                print(f"  warn mkdir {d}: {err or out}")

        uploaded = 0
        print("Uploading backend packages/files ...")
        for rel in BACKEND_GLOBS:
            n = upload_tree(sftp, root, rel, REMOTE_APP)
            uploaded += n
            if n == 0:
                print(f"  SKIP missing {rel}")
        for rel in BACKEND_FILES:
            local = root / rel
            if not local.is_file():
                print(f"  SKIP missing {rel}")
                continue
            remote = f"{REMOTE_APP}/{rel}"
            upload_file(sftp, local, remote)
            print(f"  PUT {rel} -> {remote}")
            uploaded += 1
        for rel in OPTIONAL_DIRS:
            if (root / rel).exists():
                uploaded += upload_tree(sftp, root, rel, REMOTE_APP)
            else:
                print(f"  SKIP optional {rel}")
        results["backend_files"] = uploaded

        print(f"Uploading frontend dist -> {REMOTE_WEB} ...")
        web_n = upload_tree(
            sftp,
            root,
            "apps/web/dist",
            REMOTE_WEB,
            strip_prefix="apps/web/dist",
        )
        results["web_files"] = web_n

        print("Restarting bizatlas ...")
        code, out, err = run_remote(ssh, "systemctl restart bizatlas")
        results["restart_code"] = code
        results["restart_out"] = (out or err).strip()
        print(f"  exit={code} {(out or err).strip()}")

        print("Waiting 3s for uvicorn ...")
        run_remote(ssh, "sleep 3")

        print("Health check ...")
        code, out, err = run_remote(ssh, HEALTH_CMD)
        health_body = (out or err).strip()
        # 就绪探针可能短暂失败，再试一次
        if code != 0 or "db_ok" not in health_body:
            run_remote(ssh, "sleep 2")
            code, out, err = run_remote(ssh, HEALTH_CMD)
            health_body = (out or err).strip()
        results["health_code"] = code
        results["health_body"] = health_body
        print(f"  exit={code} body={health_body!r}")

        # 额外冒烟：贷前快路径
        smoke = (
            "curl -s -m 20 -X POST http://127.0.0.1:8000/v1/credit/decision "
            "-H 'Content-Type: application/json' "
            "-d '{\"company_id\":\"healthy\",\"applied_amount\":500,\"tenor_months\":12,\"skip_polish\":true}'"
        )
        print("Credit decision smoke ...")
        code, out, err = run_remote(ssh, smoke)
        smoke_body = (out or err).strip()
        results["credit_smoke_code"] = code
        results["credit_smoke_body"] = smoke_body[:500]
        print(f"  exit={code} body={smoke_body[:300]!r}")
    finally:
        sftp.close()
        ssh.close()

    print("---")
    print("DEPLOY SUMMARY")
    for k, v in results.items():
        print(f"  {k}: {v}")
    health_ok = int(results.get("health_code") or 1) == 0 and "db_ok" in str(
        results.get("health_body") or ""
    )
    ok = (
        int(results.get("backend_files") or 0) > 0
        and int(results.get("web_files") or 0) > 0
        and int(results.get("restart_code") or 1) == 0
        and health_ok
    )
    print("STATUS:", "OK" if ok else "CHECK_LOGS")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
