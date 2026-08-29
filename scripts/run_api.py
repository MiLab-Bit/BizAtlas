"""Launch API with repo-local PYTHONPATH."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "apps"))


def main() -> None:
    import uvicorn

    from bizatlas.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "api.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        app_dir=str(ROOT / "apps"),
    )


if __name__ == "__main__":
    main()
