"""结构化日志（零依赖 JSON 输出 + request_id 透传）。

目标：企业环境下日志可被 Loki/ELK 直接采集——每行一条 JSON，带 ts/level/
request_id 与任意业务字段。避免在业务代码里拼字符串日志。
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

_request_id_ctx: ContextVar[str] = ContextVar("bizatlas_request_id", default="-")


def set_request_id(rid: str) -> Any:
    return _request_id_ctx.set(rid)


def get_request_id() -> str:
    return _request_id_ctx.get()


def new_request_id() -> str:
    import uuid

    return uuid.uuid4().hex[:16]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": _request_id_ctx.get(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for k, v in fields.items():
                log[k] = v
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False, default=str)


class StructuredLogger:
    """轻量结构化日志封装：bind(**fields) 产生带固定字段的子 logger。"""

    def __init__(self, logger: logging.Logger, **base: Any) -> None:
        self._logger = logger
        self._base = base

    def _emit(self, level: int, msg: str, **fields: Any) -> None:
        extra = {"fields": {**self._base, **fields}}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, msg, **fields)

    def info(self, msg: str, **fields: Any) -> None:
        self._emit(logging.INFO, msg, **fields)

    def warning(self, msg: str, **fields: Any) -> None:
        self._emit(logging.WARNING, msg, **fields)

    def error(self, msg: str, **fields: Any) -> None:
        self._emit(logging.ERROR, msg, **fields)

    def bind(self, **fields: Any) -> "StructuredLogger":
        return StructuredLogger(self._logger, **{**self._base, **fields})


def get_logger(name: str = "bizatlas") -> StructuredLogger:
    raw = logging.getLogger(name)
    if not raw.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        raw.addHandler(handler)
        raw.setLevel(logging.INFO)
        raw.propagate = False
    return StructuredLogger(raw)


# 默认根 logger
log = get_logger("bizatlas")
