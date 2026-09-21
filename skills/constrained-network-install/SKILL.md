---
name: constrained-network-install
description: 在「出网受限」的环境里安装 Python 依赖或下载大文件。当 pip/npm/git clone 出现 IncompleteRead / SSLEOFError / 连接在大约 48KB 处被掐断，或需要下载 GitHub Release 大二进制时使用。提供并行 Range 分片下载器与必配的解析器，可绕开「响应传一半就被切断」的出口限制。
agent_created: true
---

# 受限网络下的装包与下载

## 症状识别（命中任意一条就用本技能）

- `pip install` 报 `IncompleteRead(N bytes read, M more expected)`
- `SSLEOFError` / `schannel: failed to receive handshake`
- `git clone` 卡住或中途失败，但 `git ls-remote` 正常
- 小请求（几 KB）能通，**大响应在约 32–98KB 处被掐断**
- 明明是 200 的下载，文件却总是差一截

## 根因

出口链路上有中间层会在传输约 48KB 后切断连接，并且**源站可能忽略 `Range` 头**（回 200 而非 206）。
所以「整包下载」和「普通断点续传」都不可靠 —— 但**只要源站支持 Range（回 206 + Content-Range）**，
就可以把文件切成 ~40KB 的小段、多线程并发拉取，每段都小于掐断阈值，从而绕过去。

## 先决条件：确认源站支持 Range

```bash
curl -s -D - -o /dev/null -H "Range: bytes=0-99" "<URL>" | grep -iE "^HTTP|content-range|accept-ranges"
```

必须看到 `HTTP ... 206` **且** `Content-Range: bytes 0-99/<total>`。若回 200，说明不支持，换源。

已验证支持 Range 的源：
- `files.pythonhosted.org`（PyPI wheel）
- `cdn.jsdelivr.net`（GitHub 文件的 CDN 镜像）
- `objects.githubusercontent.com`（GitHub Release 资产，经重定向后）

## 工具

| 文件 | 用途 |
|---|---|
| `pardl.py` | **并行分片下载器**。`download(url, dest, chunk=40000, workers=10, headers=None)`；自带 `total_size(url)`（带重试）。核心：分片读满所需字节即返回，**不等 EOF**（否则每次都要等到超时）|
| `rdl.py` | 单线程顺序续传下载器（小文件或并行不可用时用）|
| `get_deps.py` | **pip 替代解析器**：用 `pip._vendor.packaging` 做依赖闭包，元数据与 wheel 都走 `pardl`，最后 `pip install --no-index --find-links` 离线装 |

## 用法一：装 Python 包

```bash
# 1. 编辑 get_deps.py 顶部的 ROOTS 列表为目标包
#    注意：依赖必须从 PyPI JSON 的 info.requires_dist 读（不是 per-file 字段），
#    并过滤 marker 与 prerelease
# 2. 用 venv 的 python 跑（需要 pip 自带的 packaging）
C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe -u get_deps.py

# 3. 离线安装
C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/pip.exe \
  install --no-index --find-links _deps <包名>
```

## 用法二：下载单个大文件

```python
import sys; sys.path.insert(0, r"<工作区根>")
import pardl
pardl.download("https://.../file.tar.gz", "file.tar.gz", chunk=40000, workers=16)
```

拿到压缩包后再 SFTP 上传到目标机（若目标机自己下载不了，例如服务器访问不到 github.com:443）。

## 关键实现要点（改代码时别退化）

1. **分片读满即返回**：`fetch_range` 要按 `need = b - a + 1` 精确读满就 return，
   不要 `r.read()` 读完 —— 服务器发完分片不一定关连接，等 EOF 会白等到超时。
2. **失败分片要重试**：`tries` 给足（60–120），瞬时失败很常见。
3. **先落占位文件再填充**：多线程写不同 offset，最后统计「非零分片数 / 总片数」看进度。
4. **完整性必须按内容校验**：
   - PyPI：比对 JSON 里的 `digests.sha256`
   - GitHub：比对 release asset 的 `size`，并可用 `sha256sum` 复核
   - 切勿只看文件大小 —— 并行下载可能留下**全 NUL 但大小正确**的坏文件
5. **元数据也可能被掐断**：PyPI 的 `/pypi/<name>/json` 常 >100KB，也要走分片下载。

## 替代源（GitHub 相关）

- 文件清单（GitHub API 403 限流时）：`https://ungh.cc/repos/{owner}/{repo}/files/{branch}`
- 单文件：`https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}`
- Release 大二进制：**本机分片下载后 SFTP 上传**，比在受限机上硬下更可靠

## 其他环境注意

- 本机若走本地代理（如 Clash `127.0.0.1:7897`），代理的 DNS 可能坏：
  **纯 IP 能通、域名全失败**。可用 `curl --connect-to host:443:IP:443` 验证；
  代理节点不稳时 `pip`/`git` 会间歇 `SSLEOF`，重试 + 分片是最实用的对策。
- 国内镜像（清华/阿里）可能被代理规则判为「直连」而被挡；**官方源走代理反而更通**。
- 目标机（如国内服务器）可能**能直连官方源**、但访问不了 GitHub —— 按目标机分别选下载位置。
