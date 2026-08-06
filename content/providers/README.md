# 数据源占位

1. 密钥写在仓库根目录 `.env`（模板见 `../../.env.example`）
2. 在本目录 `registry.yaml` 把对应项 `enabled: true`、`status: ready`
3. 实现 `packages/data/providers/<id>.py`（当前多为 Stub，不中断流水线）

默认 `BIZATLAS_MODE=snapshot`：只靠上传 + fixtures，**不依赖任何外部 API**。

详见 `doc/11-data-apis.md` · `doc/13-features-and-differentiators.md`。
