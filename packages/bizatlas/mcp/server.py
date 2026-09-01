"""BizAtlas MCP 服务骨架（P2 开放 API/MCP）。

最小可用的 MCP(JSON-RPC 2.0 over stdio) 服务端，暴露 ``bizatlas_analyze``
工具，让 Agent/IDE 直接调用 BizAtlas 研判能力。

- 零外部依赖：纯 JSON-RPC，不依赖 mcp SDK（可按需替换为官方 SDK）。
- 仅暴露**只读研判**工具，写操作（导出/复核）不在 MCP 面暴露，符合最小权限。
- 运行：``python -m bizatlas.mcp.server``（需先配置 LLM/数据源 .env）。

这是骨架：接入官方 MCP Python SDK 时，把 tools 列表与 handle() 逻辑平移即可。
"""
from __future__ import annotations

import json
import sys
from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "bizatlas_analyze",
        "description": "对一家企业做风险研判，返回五维评级、得分、命中规则与溯源。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "企业 ID 或 fixture 名（healthy/risky/defaulted）"},
                "intent": {"type": "string", "enum": ["analyze_risk", "gen_report"], "default": "analyze_risk"},
            },
            "required": ["company_id"],
        },
    }
]


def _analyze(company_id: str, intent: str = "analyze_risk") -> dict[str, Any]:
    from bizatlas.orchestrator.analyze import run_analyze
    from bizatlas.contracts.models import AnalyzeRequest

    result = run_analyze(AnalyzeRequest(company_id=company_id, intent=intent))
    risk = result.get("risk") or {}
    return {
        "grade": risk.get("grade"),
        "score": risk.get("score"),
        "headline": risk.get("headline"),
        "rules_hit": result.get("rules_hit"),
        "citations": len(result.get("citations") or []),
    }


def handle(req: dict[str, Any]) -> dict[str, Any]:
    """处理单条 JSON-RPC 请求，返回 JSON-RPC 响应。"""
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "bizatlas", "version": "0.1.0"}},
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = (req.get("params") or {}).get("name")
        args = (req.get("params") or {}).get("arguments") or {}
        if name != "bizatlas_analyze":
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown tool: {name}"}}
        try:
            data = _analyze(args.get("company_id", ""), args.get("intent", "analyze_risk"))
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}}
        except Exception as exc:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> None:
    """stdio 循环：每行一条 JSON-RPC 请求，输出一行响应。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        sys.stdout.write(json.dumps(handle(req), ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
