# 快速开始

ChatShare 有两种使用方式。**绝大多数新电脑只需要连接已有分享服务**：配置一次 ChatEnv 后直接上传、查看目录和取回链接，**不要**运行 `chatshare dufs init`。只有部署分享服务的运维主机才安装 Dufs、初始化实例并管理 systemd 服务。

具体文件链接可匿名读取；目录列表和写入需要已有 Dufs 写入账号。浏览器目录页通过 ChatShare 登录会话工作；CLI 和 HTTP/WebDAV 客户端使用同一组账号的 HTTP Basic/Digest 鉴权。详见[安全与边界](security.md)。

## 选择入口

| 你要做什么 | 使用方式 | 不要做什么 |
| --- | --- | --- |
| 在新电脑、工作站或另一台服务器上传/列目录 | 配置远端客户端，然后用 `put`、`tree`、`url` | 不要安装 Dufs 或执行 `dufs init` |
| 运行分享服务、保存实际文件、管理 Dufs | 部署服务端实例 | 不要把服务端数据目录复制到客户端 |
| 在浏览器上传大文件 | 登录目录页，拖入文件或点“选择文件” | 不要把“已发送 100%”误认为已完成 |

## A. 连接已有分享服务（新机器）

### 1. 安装 CLI

```bash
uv tool install ChatShare
chatshare --version
```

基础包已包含远端上传和目录查询所需的 HTTP 客户端；不需要 `ChatShare[server]`，也不需要本机 Dufs。

### 2. 配置写入账号

不要把密码写进 shell 历史、命令行参数、URL 或脚本。通过 ChatEnv active `chatshare` profile 保存以下三个值；`<share-url>` 应由服务管理员提供，通常是 HTTPS 地址。仅可信内部网络且服务管理员明确提供时，才使用内部 HTTPS 地址。

```bash
chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://<share-url> -I
chatenv set CHATSHARE_DUFS_USERNAME=<writer-name> -I
read -rsp "ChatShare writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD
```

配置只包含：

| 字段 | 用途 |
| --- | --- |
| `CHATSHARE_DUFS_BASE_URL` | 已有分享服务的基础 URL，不带账号、查询串或片段 |
| `CHATSHARE_DUFS_USERNAME` | 允许写入/列目录的 Dufs 账号 |
| `CHATSHARE_DUFS_PASSWORD` | 该账号密码；ChatEnv 以受保护配置保存 |

### 3. 列目录、上传并取回链接

```bash
# 列出根目录；远端模式只读取服务端，不要求本机 instance.json。
chatshare tree

# 列出一个目录。
chatshare tree videos

# 上传一个文件。交互终端会自动显示进度；--progress 可强制显示。
chatshare put --progress ./clip.mov videos/2026/clip.mov

# 上传完成后，检查存在并打印公开直链。
chatshare url videos/2026/clip.mov

# 机器可读输出放在子命令前；进度仍写 stderr。
chatshare --json put --progress ./clip.mov videos/2026/clip.mov
```

远端 `tree` 会列出所选目录的当前内容；`put` 会先检查目标、依次建立缺失父目录，然后以 1 MiB 分块流式 PUT 上传。默认拒绝覆盖已存在文件；需要替换时显式传 `--overwrite`。`url` 会认证检查目标文件存在后返回链接。

如果新机器出现下面的错误，说明它还没有远端客户端配置，而不是要你初始化一个新 Dufs 服务：

```text
ChatShare Dufs instance is not initialized: .../instance.json
```

当前版本应改为按本节配置 ChatEnv；完成后 `chatshare tree` 会直接访问已配置的服务。没有可用的远端配置时，CLI 会提示缺少的 `CHATSHARE_DUFS_*` 字段和初始化命令。

### 4. 大文件与进度语义

- 浏览器上传区会立即显示文件名、进度条、已传/总大小和速度；到 100% 后显示“已发送，等待服务器确认”，只有收到 2xx 响应才显示“上传完成”。
- 失败时界面显示失败原因和“重试”；重试会先检查远端已接收长度，在安全范围内续传。
- CLI 的 `--progress` 使用流式读取，不把整个文件装入内存；`--no-progress` 可关闭终端进度行。
- ChatShare 网关对 `PUT`/`PATCH` 不设置固定读写总时限，因此持续有数据传输的大文件不会被 30 秒元数据超时中断。反向代理、网络设备、磁盘容量和浏览器仍可能各自设有限制；只有实传和完整性回读能证明具体环境的上限。

## B. 部署分享服务（仅服务端主机）

以下流程会创建本机受管 Dufs 实例，适用于真正保存分享文件的主机；客户端不要执行这些命令。

```bash
uv tool install "ChatShare[server]"
chatshare dufs install

chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://<share-url> -I
chatenv set CHATSHARE_DUFS_USERNAME=<writer-name> -I
read -rsp "Dufs writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD

chatshare dufs init
chatshare dufs service install
chatshare dufs start
chatshare dufs status
```

默认实例位于 `~/.chatarch/chatshare/instances/default/`，Dufs 只监听 loopback。服务端本地执行 `chatshare put` 时会原子复制到受管数据目录；`tree` 和 `url` 读取本地实例。目录登录网关以 `chatshare serve` 运行，并由独立反向代理任务将可信 HTTPS 入口指向它；不要把 Dufs 直接暴露到公网。

升级服务端 ChatShare 后执行 `chatshare dufs assets sync` 同步新页面资源；该命令只替换受管静态文件，不重置账号、服务配置或数据。**等所有在途上传结束后**，再由运维重启 Dufs（它在启动时缓存首页 HTML）与部署的 ChatShare 网关（它在启动时载入 JS/CSS）。回读实际目录页的资源版本，并用浏览器选择文件确认进度条出现；仅升级 Python 包或同步静态文件不足以证明页面已经更新。新机器客户端不执行这一步。

## HTTP/WebDAV 客户端

外部程序也可使用 Dufs HTTP Basic/Digest Auth 上传。CLI 更适合日常文件上传和可见进度；需要 WebDAV 兼容时使用 Digest，密码只写入临时、权限受限的 curl 配置文件：

```bash
base_url="$(chatenv get CHATSHARE_DUFS_BASE_URL)"
writer_user="$(chatenv get CHATSHARE_DUFS_USERNAME)"
read -rsp "ChatShare writer password: " writer_password && echo

umask 077
curl_config="$(mktemp)"
trap 'rm -f "$curl_config"' EXIT
printf 'user = "%s:%s"\n' "$writer_user" "$writer_password" > "$curl_config"
curl --digest --config "$curl_config" \
  -T ./clip.mov \
  "${base_url%/}/videos/clip.mov"
unset writer_password
```

匿名 `GET` 具体文件链接无需密码，但不要把链接当作私有能力令牌。目录、JSON 列表、上传和其他管理操作仍需鉴权。

## 运维命令

```bash
# 真实注册命令树
chatshare --tree
chatshare --tree-brief

# 服务端实例状态与受限 access log
chatshare --json dufs status
chatshare dufs logs --lines 100
```

`dufs install`、`dufs init`、`dufs service install`、`dufs start|stop|restart` 只属于服务端。`put`、`tree`、`url` 会在检测到本机实例时使用本机模式；没有本机实例时自动使用已配置的远端服务。
