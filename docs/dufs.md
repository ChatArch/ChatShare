# Dufs 运行时

目录登录网关是可选的 `chatshare serve` 前置服务，不是 Dufs fork。它读取现有实例状态，不需要重复 init 或改 Dufs binary/config/accounts/files，也不修改已安装的 assets。以下配置继续描述原生 Dufs；通过网关时目录和管理请求受到额外服务端门禁，详见[安全与边界](security.md)。

## 责任边界

ChatShare 不修改 Dufs 源码。它把官方 release asset、配置、定制 UI assets 和 Linux 用户服务组合成一个 ChatArch 可管理的运行时。

| 层 | 责任 |
|---|---|
| Dufs | HTTP/WebDAV、目录展示、HTTP Digest Auth、上传与读取 |
| ChatShare | release 选择和校验、ChatArch 路径、配置、页面 assets、systemd 用户生命周期、本地或已配置远端的文件发布与目录查询 |
| 反向代理 | TLS、可信 Host、外部入口与请求限制；不在当前 CLI 中 |

## 客户端模式

没有 `~/.chatarch/chatshare/instances/default/instance.json` 的新机器不是服务端故障。只要 active ChatEnv `chatshare` profile 配置了 `CHATSHARE_DUFS_BASE_URL`、`CHATSHARE_DUFS_USERNAME` 与 `CHATSHARE_DUFS_PASSWORD`，`chatshare put`、`tree` 和 `url` 自动改用远端 Dufs HTTP 客户端：

- `put` 先认证检查目标，逐级 `MKCOL` 建立缺失父目录，再用带 `Content-Length` 的 1 MiB 流式 PUT 上传；不在内存聚合整个文件，也不会承诺未验证的原子跨客户端 create-only 语义。
- `tree` 对选定目录发起带 Basic Auth 的 `?json` 请求；远端目录列表本身受现有网关/Dufs 鉴权保护。
- `url` 认证 `HEAD` 目标后才返回基于配置 base URL 的具体文件链接。
- HTTP 默认要求 HTTPS；仅 loopback `localhost`/`127.0.0.1`/`::1` 可使用 HTTP。base URL 不接受 URL 内凭据、查询串或片段。

客户端模式不安装 Dufs、不创建本机 data root、不注册远程主机，也不改变远端服务。服务端实例存在时，同一命令保留本地受管模式。完整配置见[快速开始](quickstart.md)。

## 目录布局

```text
~/.chatarch/chatshare/
├── runtimes/dufs/
│   ├── v0.46.0/
│   │   ├── dufs
│   │   └── install.json
│   └── current -> v0.46.0
├── instances/default/
│   ├── config.yaml
│   ├── instance.json
│   ├── assets/dufs/
│   │   ├── index.html
│   │   ├── index.css
│   │   └── index.js
│   ├── data/
│   └── logs/access.log
└── services/chatshare-dufs.service
```

Linux 的激活 unit 位于 `~/.config/systemd/user/chatshare-dufs.service`。它是用户级 supervisor 入口；二进制、配置、数据、日志和 unit 源文件仍由 ChatArch home 管理。

## 安装事务

`chatshare dufs install`：

1. 请求 `sigoden/dufs` 的固定 tag release 元数据。
2. 按操作系统和架构选择唯一 `.tar.gz` asset。
3. 要求 GitHub asset metadata 含合法 `sha256:` digest。
4. 在目标 runtime 目录内下载并流式计算 SHA-256。
5. 只提取 archive 中的普通文件 `dufs`；拒绝链接与路径穿越。
6. 执行无监听的 `dufs --version` 验证。
7. 原子替换版本二进制和 `current` 指针。

任何下载、digest、解包或版本检查失败都不会覆盖当前可用二进制。

## 配置

默认配置只监听 loopback，并使用“匿名只读 + 鉴权可写”的 Dufs HTTP Digest Auth 规则：

```yaml
serve-path: '<managed-data-root>'
bind: 127.0.0.1
port: 5000
auth:
  - '<username>:<password>@/:rw'
  - '@/'
allow-upload: true
allow-delete: false
allow-search: true
allow-symlink: false
allow-archive: true
allow-hash: true
enable-cors: false
assets: '<managed-assets-root>'
log-file: '<managed-access-log>'
```

这里的占位符不是可复制凭据。真实密码优先从 ChatEnv active `chatshare` profile 读取，也可由 `--password-env` 指定的进程环境变量覆盖；生成的 `config.yaml` 和 `instance.json` 权限为 `0600`，目录为 `0700`。`status` 和 JSON 输出不读取或显示密码。`assets` 指向 ChatShare 同步到 `~/.chatarch/chatshare/instances/default/assets/dufs/` 的自定义 Dufs 页面资源，用于提供页面内登录弹窗。

## 生命周期

`service install` 生成 user unit 并运行 `systemctl --user daemon-reload`。只有显式 `--enable` 才启用登录后自动启动。

`start`、`stop`、`restart` 不直接发送进程信号，只操作 `chatshare-dufs.service`。`status` 将 inactive 作为正常状态返回，而不是把它误报为 CLI 崩溃。

## 升级与回滚

- 升级需要显式 `--version vX.Y.Z`。
- 新版本通过完整安装事务后才更新 `current`。
- 配置和数据不随二进制升级迁移或删除。
- 回滚使用已安装的旧版本重新执行 `install --version <old>`, 更新 `current` 后再 `restart`。
- ChatShare 不自动删除旧 runtime；清理策略需要单独设计。
