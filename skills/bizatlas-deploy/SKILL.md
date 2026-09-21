---
name: bizatlas-deploy
description: 把 BizAtlas 新版本构建成发布包、部署到生产服务器（139.224.163.203）、推送 GitHub 并验证/回滚的完整流程。当用户要求「部署 / 发布 / 上线 / 推送到服务器或 GitHub / 打开某个开关 / 查线上状态」时使用。内含服务器关键路径、systemd 服务清单、以及踩过的坑（相对导入、沙箱 passthrough、不要用仓库 web-dist 覆盖线上等）。
agent_created: true
---

# BizAtlas 部署与发布

## 何时使用

- 「部署 / 发布 / 上线新版本」「推送到服务器」「推送到 GitHub」
- 「查线上状态 / 健康检查 / 看服务日志」
- 「打开/关闭某个开关（如 Temporal）」
- 需要把本地改动同步到生产

## 服务器关键事实（先读，能省一次探查）

| 项 | 值 |
|---|---|
| 主机 | `139.224.163.203`（阿里云 SWAS，cn-shanghai，Alibaba Cloud Linux 3，x86_64）|
| 登录 | `root` + 密码（凭据在密码管理器，**绝不入库/入日志**）|
| 网络 | 本机可**直连**服务器 22/80/443，**不需要走代理** |
| 应用目录 | `/opt/bizatlas`，**是 git 仓库**，分支 `master` |
| 远程 | `git@github.com:MiLab-Bit/BizAtlas.git`（SSH deploy key，`git push origin HEAD:main` 可用）|
| 运行 Python | `/opt/bizatlas/venv/bin/python` = **3.11.13**（系统 `python3` 是 3.6.8，**别用**）|
| venv pip | `pip` 的 shebang 已损坏 → **必须**用 `/opt/bizatlas/venv/bin/python -m pip` |
| API 服务 | `bizatlas.service` → `python -m apps.api.launcher`，cwd `/opt/bizatlas` |
| Temporal | `bizatlas-temporal.service`（`temporal server start-dev`，7233 gRPC / 8233 UI，db 在 `/var/lib/temporal/`）|
| Worker | `bizatlas-worker.service` → `scripts/run_worker.py`，队列 `bizatlas-task-queue` |
| 健康检查 | `curl http://127.0.0.1:8000/v1/health/ready`（看 `db_ok:true`）|
| 前端 web root | `/www/wwwroot/sy-realm.ltd/bizatlas/` |
| 服务器 Node | v20.20.2 + npm 10.8.2 **已装**（前端可直接在服务器构建）|
| 服务器出网 | pypi / 阿里云镜像**可达**；**github.com:443 不可达**（发布包下载会被挡）|

## 认证

密码从环境变量读，**永不写文件**：

```bash
export BIZATLAS_SSH_PASSWORD='<从密码管理器取>'
```

## 工具（位于工作区根目录）

| 脚本 | 用途 |
|---|---|
| `ssh_exec.py "cmd1" "cmd2"` | 远程执行任意命令（输出 `errors="replace"` 解码，避免多字节截断报错）|
| `remote_upload.py <本地文件...> <远端目录>` | SFTP 上传（带远端大小校验）|
| `push_to_server.py preflight` | **只读**探查线上状态（主机/服务/git/健康/磁盘）|
| `push_to_server.py deploy [--web]` | 上传发布包并执行 `apply_release.sh` |
| `build_release.py` | 生成 `_release/*.tar.gz` + `apply_release.sh` + `RELEASE_NOTES.md` |
| `get_deps.py` | **受限网络下的 pip 替代**：分片下载元数据+wheel，离线安装 |
| `pardl.py` / `rdl.py` | 并行分片下载器（把文件切 ~40KB、多线程 Range 拉取）|

## 标准流程

### 1) 本地改完 → 构建发布包

编辑 `build_release.py` 里的 `NEW_FILES` / `MODIFIED_FILES`（repo 相对路径），然后：

```bash
C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe build_release.py
```

产出 `_release/bizatlas-release-<ts>.tar.gz`（tarball 内是 repo 相对路径，解到 `/opt/bizatlas` 即覆盖到位）。

### 2) 部署

```bash
export BIZATLAS_SSH_PASSWORD='...'
C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe push_to_server.py preflight   # 先看状态
C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe push_to_server.py deploy      # 再执行
```

`apply_release.sh` 的安全顺序（**刻意设计，别打乱**）：

```
备份 → 解包 → 语法校验(用 venv python) → 重启+健康检查 → 前端(可选) → 提交并推送 GitHub
```

语法校验或健康检查失败 → **自动回滚且不推送**。

### 3) 验证

```bash
"$VENV_PY" -u ssh_exec.py "bash /tmp/verify_temporal.sh 2>&1 | tail -60"
```

## 回滚

```bash
# 代码
cp -a /root/bizatlas-backup-<ts>/. /opt/bizatlas/ && systemctl restart bizatlas
# 环境变量
cp -a /root/env-backup-<ts> /opt/bizatlas/.env && systemctl restart bizatlas
# 前端
cp -a /root/web-backup-<ts>/. /www/wwwroot/sy-realm.ltd/bizatlas/
```

## 踩过的坑（务必遵守）

1. **包内导入用相对导入**。线上模块路径是 `apps.api.app.main`（`python -m apps.api.launcher`），
   **没有顶层 `app` 包** → `from app.xxx import yyy` 会在运行时 `ModuleNotFoundError`。
   写 `from .xxx import yyy`。这类 bug 只在对应代码分支首次执行时才暴露。
2. **不要用仓库里的 `web-dist` 覆盖线上前端**。仓库 `web-dist` 只有 32 个 assets 而
   `index.html` 引用 94 个（残缺旧构建）；线上是 103 个 assets、引用零缺失的**更新**构建。
   覆盖 = 白屏。要更新前端就从源码在服务器上 `npm install && npm run build`。
3. **Workflow 代码有确定性约束**：不能 `datetime.now()` / `random` / `Path.resolve()` / 直接 IO，
   全部下沉到 Activity；否则 Worker 启动即 `Failed validating workflow`，需为域模块配沙箱 passthrough。
4. **Activity 超时必须传 `timedelta`**，传 int 会 `TypeError: Fail to convert to Duration`。
5. **同一 task queue 只跑一个 Worker**，多个会抢任务导致行为不一致；用
   `temporal task-queue describe --task-queue <q>` 查 pollers，必要时 `taskkill /F /PID`。
6. **Temporal payload 默认上限 ~2MB**；大结果（含 trace/agents/citations）要评估是否改为「落库 + 传引用」。
7. **`execute_update` 不支持关键字参数**，要写 `args=[...]`；`submit` 是终态时用 `handle.result()` 取快照。
8. **Update 可能早于 workflow 初始化** → 在 Update 里加 `workflow.wait_condition(lambda: self._ready)`。
9. 校验下载完整性要**按内容**，不能只看大小（分片下载可能留下全 NUL 但大小正确的文件）。
10. Windows Git Bash 下 `curl -o /dev/null` 会 write error(23) 且 size 显示 0，验证大小要写到真实临时文件。

## 相关文档

- `doc/TEMPORAL.md` — Temporal 架构、本地运行、接口变化
- `deploy/systemd/` — Temporal 与 Worker 的 systemd unit
- `deploy/docker-compose.temporal.yml` — 自托管形态
