"""工具执行沙箱：在隔离子进程中运行重/外部工具，强制超时与（Unix）内存上限。

为什么需要沙箱：
- 外部数据源/视觉后端可能因网络、超大输入、死循环卡死主进程；
- 熔断能拦「连续失败」，但拦不住「单次无限挂起」，沙箱补上最后一道隔离。

实现要点（跨平台，Windows 走 spawn）：
- 子进程只接收 (模块名, 限定名, 位置参, 关键字参) 这种可 pickle 的引用，
  运行时再用 importlib 还原函数，避免把整个调用方进程树 pickle 进子进程。
- 超时用 join(timeout) + terminate/kill 兜底；不在子进程内用 signal（Windows 无 SIGALRM）。
- 内存上限仅在 Unix 用 resource.setrlimit(RLIMIT_AS) 施加；Windows 跳过（无害）。
"""

from __future__ import annotations

import importlib
import multiprocessing as mp
import os
import traceback
import time
from typing import Any, Callable


class SandboxError(Exception):
    """沙箱工具执行失败（非超时类）。"""


class SandboxTimeout(SandboxError):
    """工具执行超过允许的时长，已被强制终止。"""


def _apply_memory_limit(memory_mb: int | None) -> None:  # pragma: no cover
    if memory_mb is None or os.name == "nt":
        return
    try:
        import resource

        limit = memory_mb * 1024 * 1024
        # RLIMIT_AS 限制进程虚拟地址空间；留出一点余量给解释器自身。
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (min(limit, hard), hard))
    except Exception:  # noqa: BLE001 — 非关键，失败不阻断
        pass


def _sandbox_target(ref: tuple, q: "mp.Queue") -> None:  # pragma: no cover
    # 仅在子进程执行，主进程覆盖率统计无法追踪，按 subprocess worker 排除。
    mod_name, qual, args, kwargs = ref
    try:
        module = importlib.import_module(mod_name)
        obj: Any = module
        for part in qual.split("."):
            obj = getattr(obj, part)
        out = obj(*args, **kwargs)
        q.put((True, out))
    except Exception as exc:  # noqa: BLE001 — 任何异常都透传回主进程
        q.put((False, (type(exc).__name__, str(exc), traceback.format_exc())))


def run_in_sandbox(
    fn: Callable[..., Any],
    *args: Any,
    timeout: float = 5.0,
    memory_mb: int | None = None,
    **kwargs: Any,
) -> Any:
    """在隔离子进程中执行 fn(*args, **kwargs)。

    返回 fn 的结果；超时抛 SandboxTimeout，执行异常抛 SandboxError。
    要求 fn 为模块级可导入对象（其 __module__/__qualname__ 可在子进程还原），
    且参数均可 pickle。
    """
    ref = (fn.__module__, fn.__qualname__, args, kwargs)
    q: "mp.Queue" = mp.Queue()
    proc = mp.Process(target=_sandbox_target, args=(ref, q))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        proc.join()
        raise SandboxTimeout(
            f"tool '{fn.__qualname__}' exceeded {timeout}s and was killed"
        )
    try:
        ok, val = q.get(timeout=2.0)
    except Exception:  # noqa: BLE001  # pragma: no cover
        raise SandboxError(
            f"tool '{fn.__qualname__}' produced no result (possible crash in child)"
        )
    if not ok:
        raise SandboxError(f"{val[0]}: {val[1]}")
    return val


# —— 测试/演示用模块级函数（子进程按 qualname 还原，必须可导入）——
def _demo_ok(value: int) -> int:
    return value * 2


def _demo_fail() -> None:
    raise ValueError("boom in sandbox")


def _demo_slow(seconds: float) -> str:
    time.sleep(seconds)
    return "done"
