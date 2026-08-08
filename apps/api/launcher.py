"""BizAtlas API 启动入口（对应 pyproject 的 bizatlas-api 控制台脚本）。

容器/生产用：python -m apps.api.launcher  （WORKDIR 指向仓库根）。
开发用：uvicorn apps.api.app.main:app --reload
"""

from __future__ import annotations

import uvicorn

from bizatlas.config import get_settings


def main() -> None:
    settings = get_settings()
    # 启动前填充受治理工具注册表（权限+熔断+沙箱）。
    from bizatlas.tools.builtins import register_default_tools

    register_default_tools()

    uvicorn.run(
        "apps.api.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
