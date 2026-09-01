"""BizAtlas MCP 客户端示例（P2 开放 API/MCP）。

通过 stdio 子进程拉起 ``bizatlas.mcp.server``，完成 initialize → tools/list
→ tools/call(bizatlas_analyze) 一次往返，演示 Agent/IDE 如何调用 BizAtlas 研判。

用法：
    python -m bizatlas.mcp.client_example --company risky
前置：已配置 LLM/数据源 .env（analyze 需要 LLM）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def _rpc(proc, method: str, params=None, rid: int = 1) -> dict[str, Any]:
    req = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        req["params"] = params
    proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)


def main() -> None:
    argv = sys.argv[1:]
    company = argv[argv.index("--company") + 1] if "--company" in argv else "risky"
    proc = subprocess.Popen(
        [sys.executable, "-m", "bizatlas.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        init = _rpc(proc, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "example", "version": "0.1"}})
        tools = _rpc(proc, "tools/list")
        call = _rpc(proc, "tools/call", {"name": "bizatlas_analyze", "arguments": {"company_id": company}})
    finally:
        proc.terminate()
    print(json.dumps({"initialize": init, "tools": tools, "analyze": call}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
