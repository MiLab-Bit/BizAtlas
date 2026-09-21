"""Worker 启动脚本（命令行入口）。

用法：
    python scripts/run_worker.py
等价于 `bizatlas-worker`（pyproject 控制台脚本）。
需先启动 Temporal 集群（见 deploy/docker-compose.temporal.yml 或 `temporal server start-dev`）。
"""

from __future__ import annotations

from bizatlas.temporal.worker import run

if __name__ == "__main__":
    run()
