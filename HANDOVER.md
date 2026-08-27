# BizAtlas（商舆）交接文档 · HANDOVER

> **结论先行**：BizAtlas 是一个工程化程度成熟的「企业风险研判 Agent」——FastAPI 后端（17 子模块 / 40+ 路由 / 4 数据源）、React 19 前端、30 个测试文件（当前 **154 passed, 0 failed**）。已建立 git 版本控制并完成 8 个失败测试的修复。**当前唯一阻断安全迭代的短板已解除**；剩余事项均为配置/运维类（见第 9 节）。

> **安全红线**：本文件**只标注密钥的存放位置，不写入任何真实密钥值**。阿里云 AccessKey、服务器 root 密码、各数据源 Token 均不在本文出现，请从对应密钥管理器/控制台获取。

---

## 1. 项目定位

| 项 | 值 |
|---|---|
| 名称 | BizAtlas（商舆） |
| 定位 | 面向 to-B 金融的「企业风险研判 Agent」：上传财务/工商资料 → 规则+计算+LLM 多 Agent → 风险评级与报告 |
| 对比 RedTrip | 比 RedTrip 工程化更成熟（模块化更彻底、测试更全、数据源更丰富），但 RedTrip 先有了 git |
| 演示模式 | `BIZATLAS_AUTH_DISABLED=true`（登录门控已移除，等价于 ADMIN 放行） |

---

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI 0.141 + uvicorn，Python 3.11（venv 隔离 `/opt/bizatlas/venv`） |
| 数据 | SQLite（`data/bizatlas.sqlite`）+ 4 外部数据源（TuShare / 企查查 / 天眼查 / AkShare） |
| 前端 | React 19 + TypeScript + Vite 6 + Tailwind 4 + Radix + ECharts + AntV G6 |
| 部署 | 宝塔 Linux 面板 + nginx 反代 + systemd + Cloudflare 隧道 |
| LLM | 微信 Token 网关（`LLM_API_BASE`=chatapi.weixin.qq.com），`LLM_MODEL=GLM-5.2` |

---

## 3. 服务器与部署

| 项 | 值 |
|---|---|
| 主机 | 阿里云轻量应用服务器 SWAS，地域 `cn-shanghai` |
| 实例 ID | `c713ed8539c948e28df4100b45db5647` |
| 公网 IP | `139.224.163.203`（内网 `172.24.47.242`） |
| 配置 | 2 核 1G / 30G ESSD / 峰值 200M，镜像「宝塔 Linux 面板 11.1.0」 |
| 计费 | 包年，**创建 2026-09-22，到期需续费** ⚠️ |
| 进程 | `bizatlas.service`（systemd），内存 ~45MB，零错误日志 |
| 端口 | 后端 8000（FastAPI）/ nginx 对外 8080，前端 build 在 `/www/wwwroot/sy-realm.ltd/bizatlas/` |
| 流量 | 用户 → nginx `:8080/bizatlas/` → 静态 SPA；`:8080/bizatlas/v1/*` → `127.0.0.1:8000/v1/`（3600s 超时）；公网经 Cloudflare 隧道回源 |

**常用运维命令**
```bash
systemctl status bizatlas          # 看进程状态
journalctl -u bizatlas -p err      # 看错误日志（正常应为空）
systemctl restart bizatlas         # 重启
/opt/bizatlas/venv/bin/python -m pytest tests/ -q   # 跑全量测试（约 3 分钟）
```

---

## 4. 域名与账号归属

| 项 | 值 | 说明 |
|---|---|---|
| 域名 | `sy-realm.ltd` | 注册 + DNS 均在**阿里云个人账号**（非 abc-ai.cn 公司账号） |
| 账号性质 | 个人账号，与 `abc-ai.cn` 相互独立 | 两套账单/权限，勿混淆 |
| DNS 记录 | `@/www` A + `_dnsauth` TXT | 已加 |
| 备案 | 未备案 | 直连被运营商拦截，当前走 Cloudflare 隧道绕过 |
| 同机部署 | RedTrip（端口 8799）与本服务共用一台 SWAS | 续费/迁移需一并考虑 |

---

## 5. 环境变量与密钥（位置，非值）

`.env` 位于 `/opt/bizatlas/.env`，已被 git 忽略（绝不入库）。关键项：

| 变量 | 状态 | 说明 |
|---|---|---|
| `LLM_API_BASE` / `LLM_MODEL` / `LLM_API_KEY` | ✅ 已配 | 微信 Token 网关 |
| `TUSHARE_TOKEN` / `TIANYANCHA_TOKEN` / `QICHACHA_TOKEN` | ✅ 已配 | 3 个数据源 Token |
| **`QICHACHA_SECRET`** | ❌ **缺失** | 企查查签名需要成对的 appkey+appsecret；当前仅有 `QICHACHA_TOKEN`，企查查调用可能失败，需补 |
| `SMTP_*` / `EMAIL_VERIFICATION_ENABLED` | ✅ 已配 | QQ 邮箱发信 |
| **`BIZATLAS_INTEGRITY_SECRET`** | ⚠️ 未配 | 测试告警「使用开发密钥签名，生产环境必须配置」 |
| 阿里云 AccessKey | 控制台管理 | **本文件不存放**；如曾明文暴露，立即禁用/重生成 |
| 服务器 root 密码 | 密码管理器 | **本文件不存放** |

---

## 6. 运行时状态

| 项 | 位置 |
|---|---|
| 主目录 | `/opt/bizatlas` |
| 数据库 | `data/bizatlas.sqlite`（有 `.bak-preclean` 备份） |
| 上传目录 | `uploads/`（运行产物，已 gitignore） |
| 演示 fixtures | `content/fixtures/{defaulted,healthy,risky}`；API 直接用 `company_id="healthy"` 等 fixture 键即可触发 |
| 规则/契约 | `content/rules/`、`packages/bizatlas/contracts/` |
| 前端产物 | `apps/web/dist-nginx/`（线上实际部署版本，已入库以便回滚对齐） |

---

## 7. 版本控制与回滚

仓库已 `git init` 并有两个提交：

| 提交 | 说明 |
|---|---|
| `0f723bc` | baseline：首次快照（372 文件，密钥已忽略） |
| `f620c3a` | fix：修复 8 个失败测试（sandbox 缺 import time / nl 编译器 LLM 失败降级 / 离线测试隔离 conftest） |

> 注：测试运行会写 `content/rules/custom_pilot.yaml`（pilot 规则保存产物），属测试副作用，未纳入提交，保持工作区干净即可。

**回滚**
```bash
git log --oneline          # 查看历史
git diff                   # 查看未提交改动
git checkout -- <file>    # 丢弃单文件改动
```

---

## 8. 测试与质量门禁

- 全量：`/opt/bizatlas/venv/bin/python -m pytest tests/ -q` → **154 passed**
- 测试套件按「离线优先」设计；`tests/conftest.py` 强制离线环境（关邮箱验证/SMTP、清空 TIANYANCHA_TOKEN），避免生产 `.env` 泄漏进测试
- 前端：`apps/web` 下 `pnpm typecheck`（如适用）

---

## 9. 已知风险与待办（按优先级）

| 优先级 | 事项 | 说明 / 动作 |
|---|---|---|
| 🔴 P0 | **轮换已泄露密钥** | 阿里云 AccessKey、服务器 root 密码若曾明文出现，立即在控制台禁用/重生成 + 改 root 密码 |
| 🟡 P1 | **补 `QICHACHA_SECRET`** | 企查查开放平台 appsecret，与 `QICHACHA_TOKEN` 成对；缺失会导致企查查数据源不可用 |
| 🟡 P1 | **SWAS 续费（2026-09-22）** | 与 RedTrip 共用，到期前两台服务全停 |
| 🟡 P1 | **配 `BIZATLAS_INTEGRITY_SECRET`** | 生产环境签名密钥，消除测试告警 |
| 🟡 P1 | **ICP 备案 / 域名合规** | `sy-realm.ltd` 未备案，当前依赖 Cloudflare 隧道，建议推进备案 |
| 🟢 P2 | **演示数据清理** | companies 列表有测试产生的企业，演示前可只保留 fixture 案例 |
| 🟢 P2 | **CI/CD** | 有 git 后配 GitHub Actions 跑测试 + 自动部署 |

---

## 10. 交接检查清单

- [ ] 阿里云个人账号 AccessKey 已确认归属（独立于 abc-ai.cn）
- [ ] `sy-realm.ltd` DNS 记录核对（@/www A + _dnsauth TXT）
- [ ] SWAS 续费提醒已设置（2026-09-22）
- [ ] `QICHACHA_SECRET` 已补配并验证企查查数据源
- [ ] `BIZATLAS_INTEGRITY_SECRET` 已配（生产）
- [ ] 泄露密钥已轮换
- [ ] `git log` 两个提交已知晓，回滚流程已验证
- [ ] `POST /v1/analyze` fixture 链路已实跑通过（healthy/risky/defaulted）
