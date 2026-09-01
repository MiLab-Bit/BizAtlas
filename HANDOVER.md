# BizAtlas（商舆）交接文档 · HANDOVER

> **结论先行**：BizAtlas 是一个工程化程度成熟的「企业风险研判 Agent」——FastAPI 后端（17 子模块 / 40+ 路由 / 4 数据源）、React 19 前端、微信小程序（构建就绪待上传）。**179 passed，CI 全绿**，覆盖率 ≥ 75% 门禁通过。INTEGRITY_SECRET 已配、密钥已清理、fixtures 保留（36 测试依赖）。剩余事项均为**配置 / 上传 / 运维类**（见第 9 节）。

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
/opt/bizatlas/venv/bin/python -m pytest tests/ -q   # 跑全量测试（约 20s，179 passed）
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

- 全量：`/opt/bizatlas/venv/bin/python -m pytest tests/ -q` → **179 passed, 7 warnings（20s）**。
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
| 🟢 P2 | **`custom_pilot.yaml` 重复规则数据治理** | HEAD 已含 89 条重复的「流动比率<0.9」pilot 规则（历史 seed 冗余），属数据卫生问题，可单独做去重，不阻塞功能 |
| 🟢 P2 | **演示数据清理（若坚持）** | 三 fixture 是测试基础设施，删除需同步改造 36 个依赖测试；建议保留，改清理服务器 `companies` 表里测试产生的企业 |

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
- [ ] `git log` 近期提交链已知（CI 绿基线 = `bfcbbe8`）
- [ ] `POST /v1/analyze` fixture 链路已实跑通过（healthy/risky/defaulted）
- [x] 微信小程序 v1.0.1 已上传（私钥就位，`node upload_mp.mjs` 成功）
- [ ] MP 后台 `request` 合法域名白名单 `sy-realm.ltd` 已配（运行时前置，否则 `wx.request` 不通）

---

*最后更新：2026-09-01 · 179 passed · CI 绿 · 小程序 v1.0.1 已上传*
