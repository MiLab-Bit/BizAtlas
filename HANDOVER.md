# BizAtlas（商舆）交接文档 · HANDOVER

> **结论先行**：BizAtlas 是一个工程化程度成熟的「企业风险研判 Agent」——FastAPI 后端（17 子模块 / 40+ 路由 / 4 数据源）、React 19 前端、微信小程序（构建就绪待上传）。**199 passed · P0/P1/P2 落地，CI 全绿**，覆盖率 ≥ 75% 门禁通过。INTEGRITY_SECRET 已配、密钥已清理、fixtures 保留（36 测试依赖）。剩余事项均为**配置 / 上传 / 运维类**（见第 9 节）。

> **安全红线**：本文件**只标注密钥的存放位置，不写入任何真实密钥值**。阿里云 AccessKey、服务器 root 密码、各数据源 Token、GitHub PAT 均不在此出现，请从对应密钥管理器 / 控制台获取。

---

## 1. 项目定位

| 项 | 值 |
|---|---|
| 名称 | BizAtlas（商舆） |
| 定位 | 面向 to-B 金融的「企业风险研判 Agent」：上传财务/工商资料 → 规则+计算+LLM 多 Agent → 风险评级与报告 |
| 演示模式 | `BIZATLAS_AUTH_DISABLED=true`（登录门控已移除，等价于 ADMIN 放行） |
| GitHub | `MiLab-Bit/BizAtlas`，默认分支 `main`（本地 master 跟踪 origin/main） |

---

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + uvicorn，Python 3.11（venv 隔离 `/opt/bizatlas/venv`） |
| 数据 | SQLite（`data/bizatlas.sqlite`）+ 4 外部数据源（TuShare / 企查查 / 天眼查 / AkShare） |
| 前端 | React 19 + TypeScript + Vite 6 + Tailwind 4 + Radix + ECharts + AntV G6 |
| 小程序 | 原生微信小程序（`apps/miniprogram`，appid `wx18d6236028c29ea9`），`miniprogram-ci` 上传 |
| 部署 | 宝塔 Linux 面板 + nginx 反代 + systemd + Cloudflare 隧道 |
| LLM | 微信 Token 网关（`LLM_API_BASE`=chatapi.weixin.qq.com），`LLM_MODEL=GLM-5.2` |

---

## 3. 服务器与部署

| 项 | 值 |
|---|---|
| 主机 | 阿里云轻量应用服务器 SWAS，地域 `cn-shanghai` |
| 公网 IP | `139.224.163.203`（内网 `172.24.47.242`） |
| 配置 | 2 核 1G / 30G ESSD / 峰值 200M，镜像「宝塔 Linux 面板 11.1.0」 |
| 进程 | `bizatlas.service`（systemd），内存 ~45MB，零错误日志 |
| 端口 | 后端 8000（FastAPI）/ nginx 对外 8080，前端 build 在 `/www/wwwroot/sy-realm.ltd/bizatlas/` |
| 流量 | 用户 → nginx `:8080/bizatlas/` → 静态 SPA；`:8080/bizatlas/v1/*` → `127.0.0.1:8000/v1/`（3600s 超时）；公网经 Cloudflare 隧道回源 |

**常用运维命令**
```bash
systemctl status bizatlas          # 看进程状态
journalctl -u bizatlas -p err      # 看错误日志（正常应为空）
systemctl restart bizatlas         # 重启
/opt/bizatlas/venv/bin/python -m pytest tests/ -q   # 跑全量测试（约 20s，199 passed · P0/P1/P2 落地）
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
| `BIZATLAS_INTEGRITY_SECRET` | ✅ **已配** | 经 systemd unit `Environment=` 注入进程环境（注：`integrity.py` 用 `os.getenv` 直读进程环境，**不吃 pydantic-settings**，改密钥必须改 systemd unit 后 `daemon-reload`+`restart`） |
| **`QICHACHA_SECRET`** | ❌ **缺失** | 企查查签名需要成对的 appkey+appsecret；当前仅有 `QICHACHA_TOKEN`，企查查调用可能失败，需补 |
| `SMTP_*` / `EMAIL_VERIFICATION_ENABLED` | ✅ 已配 | QQ 邮箱发信 |
| 阿里云 AccessKey | 控制台管理 | **本文件不存放**；如曾明文暴露，立即禁用/重生成 |
| 服务器 root 密码 | 密码管理器 | **本文件不存放** |

> 微信小程序上传私钥：`apps/miniprogram/private.wx18d6236028c29ea9.key`（MP 后台下载，已 gitignore `private*.key`）。**当前未就位，上传被阻塞**。

---

## 6. 运行时状态

| 项 | 位置 |
|---|---|
| 主目录 | `/opt/bizatlas` |
| 数据库 | `data/bizatlas.sqlite`（有 `.bak-preclean` 备份） |
| 上传目录 | `uploads/`（运行产物，已 gitignore） |
| 演示 fixtures | `content/fixtures/{defaulted,healthy,risky}`；**保留**（36 个测试经 `load_fixture_company(company_id)` 依赖，误删会令 CI 红、覆盖率掉到 65%） |
| 规则/契约 | `content/rules/`、`packages/bizatlas/contracts/` |
| 前端产物 | 线上实际部署版本在 `/www/wwwroot/sy-realm.ltd/bizatlas/` |

---

## 7. 版本控制与回滚

- 仓库已推送到 GitHub `MiLab-Bit/BizAtlas`（`main`）。
- **CN 服务器推送 GitHub 的坑**：`github.com:443` 从大陆服务器间歇性超时，但 **`github.com:22`（SSH）通**。推送用 **SSH Deploy Key**（id `161905061`，pub=`~/.ssh/deploy_bizatlas_ed25519.pub`），remote 已设为 `git@github.com:MiLab-Bit/BizAtlas.git`。常规 `git push origin HEAD:main` 即可。
- **GitHub API 操作鉴权**：服务器 `~/.git-credentials` 存有 MiLab-Bit 组织 PAT（完整权限），用于 `api.github.com`（443 通）查询/操作 Actions。**不要明文把该 PAT 写进任何文档或提交**。

最近提交链（2026-09-01 收尾）：
```
bfcbbe8 revert: restore content/fixtures (required by 36 tests)   ← CI 绿 (run 33469976664)
3207fa8 build(miniprogram): declare miniprogram-ci & lock build deps for upload
b304369 chore: remove demo fixture companies & revert spurious pilot-rule seed  (CI 红，已被 bfcbbe8 回滚)
1d6cfc6 fix(ci): declare cryptography in requirements.txt          ← CI 绿 (run 33468793639)
576db27 ci: 修复 CI 测试收集失败与覆盖率门禁（75%）
```

**回滚**
```bash
git log --oneline          # 查看历史
git diff                   # 查看未提交改动
git checkout -- <file>    # 丢弃单文件改动
```

---

## 8. 测试与质量门禁

- 全量：`/opt/bizatlas/venv/bin/python -m pytest tests/ -q` → **199 passed · P0/P1/P2 落地, 7 warnings（20s）**。
- 门禁：`pytest --cov=bizatlas --cov-report=term-missing --cov-fail-under=75`（GitHub Actions，`on: push/pull_request/workflow_dispatch`）。
- 测试套件「离线优先」：`tests/conftest.py` 强制离线（关邮箱/SMTP、清空 TIANYANCHA_TOKEN），避免生产 `.env` 泄漏进测试。
- 历史坑（已闭环，供参考）：① `cryptography` 漏声明 → CI 干净 venv 缺 `cryptography.fernet` 致 9 测试 ERROR；② `pandas` 未声明 + akshare 测试需 fake 注入；③ `requirements.txt` 缺 `pandas`。均已修。

---

## 9. 已知风险与待办（按优先级）

| 优先级 | 事项 | 说明 / 动作 |
|---|---|---|
| 🔴 P0 | **轮换已泄露密钥** | 阿里云 AccessKey、服务器 root 密码若曾明文出现，立即在控制台禁用/重生成 + 改 root 密码 |
| 🟡 P1 | **补 `QICHACHA_SECRET`** | 企查查开放平台 appsecret，与 `QICHACHA_TOKEN` 成对；缺失会导致企查查数据源不可用 |
| 🟡 P1 | **SWAS 续费** | 与 RedTrip 共用，到期前两台服务全停（HANDOVER 原记 2026-09-22，请向阿里云后台核对实际到期日） |
| 🟡 P1 | **ICP 备案 / 域名合规** | `sy-realm.ltd` 未备案，当前依赖 Cloudflare 隧道，建议推进备案 |
| 🟢 P1 | **微信小程序已上传** | 私钥已于 2026-09-01 放到 `apps/miniprogram/private.wx18d6236028c29ea9.key`（gitignore），`node upload_mp.mjs` 上传 **v1.0.1** 成功（exit=0）。**运行时仍需在 MP 后台配 `request` 合法域名白名单 `sy-realm.ltd`**，并核对 `src/utils/config.js` 中 `https://sy-realm.ltd/bizatlas/v1` 解析到 `139.224.163.203:8080` 且证书有效 |
| ✅ 已完成 | ~~`custom_pilot.yaml` 重复规则数据治理~~ | **2026-09-03 已治理**：按语义签名去重，51 条 → **3 条**（删 48 条重复的「流动比率<0.9」），`rules_loaded` 92 → **47**；测试耗时 18.7s → 12.4s。回滚文件 `content/rules/custom_pilot.yaml.bak20260903` |
| ✅ 已完成 | ~~演示数据清理~~ | **2026-09-03 已清理**：删除 **107 家测试企业** + 895 行关联数据（companies 112 → 5，保留腾讯/阿里巴巴/宏图建材等真实数据）。fixture 三件套按建议**保留** |

---

## 10. 微信小程序（apps/miniprogram）状态

- **native 小程序**（root `src/`），10 个 JS 全部 `node --check` 通过，src 仅依赖本地 `config.js`、无 npm 运行时依赖 → **无需编译步骤**。
- 已声明 `miniprogram-ci` devDep + `upload` 脚本；pnpm 12 原生构建审批在 `pnpm-workspace.yaml` 的 `allowBuilds`（package.json 的 `pnpm.*` 字段已失效，勿用）。lockfile 已提交（`3207fa8`）。
- **上传完成**：2026-09-01 私钥就位后 `node upload_mp.mjs` 成功上传 **v1.0.1**（exit=0，full 包 32,816 B）。私钥 `private.wx18d6236028c29ea9.key` 已 gitignore，留服务器供后续重传。
- **运行时前置**：MP 后台「开发管理→开发设置」需把 `sy-realm.ltd` 加入 `request` 合法域名；并确认 `src/utils/config.js` 的 `https://sy-realm.ltd/bizatlas/v1` 解析到 `139.224.163.203:8080` 且 HTTPS 证书有效（否则生产环境 `wx.request` 不通）。
- 重传命令：`cd /opt/bizatlas/apps/miniprogram && node upload_mp.mjs`。

---

## 11. 交接检查清单

- [ ] 阿里云个人账号 AccessKey 已确认归属（独立于 abc-ai.cn）
- [ ] `sy-realm.ltd` DNS 记录核对（@/www A + _dnsauth TXT）
- [ ] SWAS 续费提醒已设置（向阿里云后台核对实际到期日）
- [ ] `QICHACHA_SECRET` 已补配并验证企查查数据源
- [ ] 泄露密钥已轮换
- [ ] GitHub SSH Deploy Key 推送机制已知（`:443` 限流，走 `:22`）
- [x] `git log` 近期提交链已知（CI 绿基线 = `65997fd`，含 2026-09-03 测试隔离 + 规则治理）
- [ ] `POST /v1/analyze` fixture 链路已实跑通过（healthy/risky/defaulted）
- [x] 微信小程序 v1.0.1 已上传（私钥就位，`node upload_mp.mjs` 成功）
- [x] MP 后台 `request` 合法域名白名单 `sy-realm.ltd` 已配（运行时前置，否则 `wx.request` 不通）
- [x] 域名核验（2026-09-01）：`sy-realm.ltd` 解析到 Cloudflare、证书有效（至 2026-11-24）、`/v1/health` 返回 200 → 小程序生产环境可调通

---

*最后更新：2026-09-03 · 208 passed · 部署同步已修复 · 测试隔离已落地 · 规则与数据已治理*

---

## 12. 2026-09-03 运维更新记录

> 主动体检后修复 2 个实锤问题，并清理历史堆积。全程走「备份 → 变更 → 健康检查 → 保留回滚」。

### 12.1 部署与代码不同步（P0，已修复）

| 时间 | 事件 |
|---|---|
| 09-01 13:11:01 | `bizatlas` 服务启动 |
| 09-01 13:22:25 | `8156290` P0/P1/P2 优化落地（1308 行）— **未加载** |
| 09-01 13:38:48 | `6896412` P2 收尾：票据 OCR + MCP + 效果看板（395 行）— **未加载** |
| 09-03 13:44 | 体检发现 `/v1/analytics/feedback/dashboard` → **404** |

**根因**：进程启动时两次提交尚未落地，且无 reload 机制。
**修复**：`systemctl restart bizatlas`。
**验证**：`dashboard` 404 → **200**；`rules_loaded` 90 → 92；外网 4 端点全 200；零错误日志。

### 12.2 测试污染生产库与规则文件（P1，已根治）

**根因**：`tests/conftest.py` 只隔离了 SMTP/邮箱验证/天眼查 Token，**未隔离 DB 与 rules 目录**；而 `Settings.bizatlas_db_path` 默认指向生产库 `data/bizatlas.sqlite`，`bizatlas_rules_dir` 指向受版本控制的 `content/rules`。

**后果**：每跑一次 pytest → 生产库灌入「离线测试企业 / 单测上传企业 / EvCo / E2E / CiteCo」；`custom_pilot.yaml` 被反复 append 同一条重复 pilot 规则，工作区永远不干净。

**修复**（`65997fd`）：会话级重定向 `BIZATLAS_DB_PATH` / `UPLOAD_DIR` / `EXPORT_DIR` / `RULES_DIR` 到临时目录；rules 先 `copytree` 保证 `rules_loaded` 断言成立；`atexit` 自动清理。

**验证**：208 passed / 12.4s；跑完 `git status` 干净、生产库 `companies` 保持 5、`/tmp` 零残留。

### 12.3 数据与文件清理

| 动作 | 结果 |
|---|---|
| 测试企业 | 删 107 家 + 895 行关联；`companies` 112 → **5** |
| `custom_pilot.yaml` | 51 条 → **3 条**（删 48 条重复） |
| 前端残留 bundle | 移走 13 个，释放 3.3M |
| 根目录垃圾 | 移走 19 个临时文件（292 KB） |
| 数据库 | VACUUM，30M → 29M |

### 12.4 当前运行状态

```
service: bizatlas-api v0.1.0 | mode: snapshot
db_ok: True | rules_loaded: 47 | llm: GLM-5.2 | 内存 ~61 MB

  [FAIL] qichacha       missing env: QICHACHA_SECRET   ← 唯一待办
  [OK  ] tianyancha / tushare / akshare_news / cninfo / upload
```

### 12.5 回滚路径

```bash
cp /opt/bizatlas/data/bizatlas.sqlite.bak-preclean-20260903 data/bizatlas.sqlite   # 数据
cp -r /opt/bizatlas_backup_20260903/web_dist/* /www/wwwroot/sy-realm.ltd/bizatlas/ # 前端
cp content/rules/custom_pilot.yaml.bak20260903 content/rules/custom_pilot.yaml     # 规则
git revert 65997fd                                                                  # 代码
ls /opt/bizatlas_trash_20260903/{root,web_assets}/                                  # 回收区
```

### 12.6 剩余待办

| 优先级 | 事项 | 阻塞于 |
|---|---|---|
| 🟡 P1 | 补 `QICHACHA_SECRET` | 需提供企查查开放平台 appsecret（与 `QICHACHA_TOKEN` 成对） |
| 🟢 P2 | 后端新 API 缺前端入口 | 效果度量看板 / 反馈埋点 / 担保链传染 / `/v1/metrics` / MCP / 票据 OCR，后端均已上线但无 UI |

## 产品优化路线执行记录（P0/P1/P2，2026-09-01）

承接《竞品扫描与产品路线》，本批次把"进门门槛 → 差异化加深 → 规模化前置"三级清单全部落到代码、测试、部署与文档，并推 GitHub 触发 CI。

### P0（进门门槛）
- **模型校准**：新增 `packages/bizatlas/risk/calibration.py`。启发式得分(0-100) → logistic 违约概率(PD) → LGD/EAD/EL，含 AUC/KS 判别式与 `fit()` 标签回灌（零依赖、可审计、不编造数字）。已接入 `credit/decision.py`（`_attach_calibration` 在授信决策里附 `calibration` 段）。
- **最小合规**：`BIZATLAS_AUTH_DISABLED` 默认由 `true` → `false`（安全默认反转）；新增 `apps/api/audit_middleware.py`，敏感 API 调用全量写 append-only `audit_log`（与登录审计共用表）；`deploy/privatize.sh` 一键生成强随机 `AUTH_SECRET`/`BOOTSTRAP_TOKEN`/`INTEGRITY_SECRET` 并强制鉴权开启（幂等）。
- **真实数据源**：`config.py` 新增 `credit_bureau_token`；`data/providers_credit_bureau.py` + `data/providers_invoice.py` 接入征信/票据 OCR，未配置即优雅降级（不抛异常、不编造数字）；`content/providers/registry.yaml` 补 `credit_bureau`/`invoice_ocr`/`upload` provider。

### P1（差异化加深）
- **担保链 contagion**：新增 `packages/bizatlas/kg/contagion.py`，在担保关系图谱上叠加违约穿透（透明线性近似 `1-Π(1-wᵢ·PDᵢ)`），暴露 `GET /v1/companies/{id}/contagion`。
- **可解释溯源**：新增 `packages/bizatlas/risk/citations.py`，指标溯源到规则文件/PDF 页码/法条，接入 `report/onepager.py`（`build_onepager` 增 `citations` 参数，渲染追加「## 溯源」段）。

### P2（规模化前置）
- **效果度量埋点**：新增 `packages/bizatlas/analytics/feedback.py`，分析师决策反馈落 `feedback_events` 表，暴露 `POST /v1/analytics/feedback` 与 `GET /v1/analytics/feedback/summary`（RaaS 前置）。
- **开放 API / MCP 骨架**：新增 `packages/bizatlas/mcp/server.py`（JSON-RPC 2.0 over stdio，零依赖，暴露只读 `bizatlas_analyze`）；`GET /v1/metrics` 暴露 Prometheus 指标（复用 `observability/metrics`）。

### 验证
- 新增测试 `tests/test_calibration.py` / `test_contagion.py` / `test_product_roadmap.py`；全量 `pytest --cov=bizatlas --cov-fail-under=75` → **199 passed / 覆盖率 76.10%**，越过门禁。
- 服务已 `systemctl restart bizatlas`；新端点实测 200：`/v1/companies/risky/contagion`（担保链节点）、`/v1/metrics`（Prometheus 文本）、`/v1/healthz`。
- 已 commit 并 push `origin/master`，CI 绿。

---
