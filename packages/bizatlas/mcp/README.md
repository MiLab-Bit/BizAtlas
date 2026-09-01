# BizAtlas MCP Server

只读 MCP（Model Context Protocol）服务，让 Agent / IDE（如 Claude Desktop、Cursor）直接调用 BizAtlas 企业风险研判能力。

- 协议：JSON-RPC 2.0 over stdio，零外部依赖（不依赖官方 MCP SDK）。
- 最小权限：仅暴露只读研判工具 `bizatlas_analyze`，写操作不在 MCP 面暴露。
- 启动：`python -m bizatlas.mcp.server`（需先配置 LLM/数据源 .env）。

## 工具
- `bizatlas_analyze(company_id, intent="analyze_risk")` → 五维评级、得分、命中规则与溯源条数。

## 客户端注册示例（Claude Desktop / 通用 MCP）
```json
{
  "mcpServers": {
    "bizatlas": {
      "command": "python",
      "args": ["-m", "bizatlas.mcp.server"],
      "env": {
        "LLM_API_BASE": "https://your-llm-base/openai/v1",
        "LLM_API_KEY": "sk-xxx",
        "LLM_MODEL": "your-model",
        "BIZATLAS_AUTH_DISABLED": "false"
      }
    }
  }
}
```

## 客户端示例（本仓库）
```bash
python -m bizatlas.mcp.client_example --company risky
```
