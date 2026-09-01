from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import patch

from bizatlas.mcp import server as mcp_server


def test_mcp_initialize_and_list():
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "bizatlas"
    lst = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in lst["result"]["tools"]]
    assert "bizatlas_analyze" in names


def test_mcp_call_analyze():
    fake = {"grade": "A", "score": 88, "headline": "稳定", "rules_hit": 3, "citations": 2}
    with patch.object(mcp_server, "_analyze", return_value=fake):
        resp = mcp_server.handle({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "bizatlas_analyze", "arguments": {"company_id": "risky"}},
        })
    assert resp.get("error") is None
    content = resp["result"]["content"][0]["text"]
    assert json.loads(content) == fake


def test_mcp_unknown_tool_errors():
    resp = mcp_server.handle({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"},
    })
    assert resp["error"]["code"] == -32601


def test_mcp_subprocess_smoke():
    """拉起真实 server 子进程，验证 initialize + tools/list（不调 analyze，避免依赖 LLM）。"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "bizatlas.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
        proc.stdin.flush()
        init = json.loads(proc.stdout.readline())
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
        proc.stdin.flush()
        tools = json.loads(proc.stdout.readline())
        assert init["result"]["serverInfo"]["name"] == "bizatlas"
        assert any(t["name"] == "bizatlas_analyze" for t in tools["result"]["tools"])
    finally:
        proc.terminate()
