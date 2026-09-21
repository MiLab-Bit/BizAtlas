# skills/

本目录收录本项目的可复用操作手册（Skill），供团队与自动化助手共用。

| Skill | 用途 | 触发场景 |
|---|---|---|
| [`bizatlas-deploy`](bizatlas-deploy/SKILL.md) | 构建发布包、部署到生产服务器、推送 GitHub、验证与回滚 | 部署 / 发布 / 上线 / 查线上状态 / 打开开关 |
| [`constrained-network-install`](constrained-network-install/SKILL.md) | 在出网受限（响应约 48KB 处被掐断）的环境里装依赖、下大文件 | `pip` 报 `IncompleteRead` / `SSLEOFError`、`git clone` 中途失败 |

## 为什么放在仓库里

这两个流程都不是"读代码就能懂"的：它们依赖具体的服务器路径、systemd 服务名、
以及一批踩过的坑（相对导入、Activity 同步化、前端构建产物不可混用等）。
写在仓库里可以随代码一起演进，也便于新同事交接。

## 与线上环境的一致性

`bizatlas-deploy` 里记录的服务器事实（`/opt/bizatlas`、venv Python 3.11、
`bizatlas-temporal.service` / `bizatlas-worker.service`、前端 web root 等）
与 `deploy/systemd/` 下的 unit 文件、`doc/TEMPORAL.md` 的「生产启用记录」保持一致。
改动其中任一处的运行形态时，请同步更新这四处。
