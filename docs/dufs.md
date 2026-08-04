# Dufs 运行时

## 责任边界

ChatShare 不修改 Dufs 源码。它把官方 release asset、配置和 Linux 用户服务组合成一个 ChatArch 可管理的运行时。

| 层 | 责任 |
|---|---|
| Dufs | HTTP/WebDAV、目录展示、Basic Auth、上传与读取 |
| ChatShare | release 选择和校验、ChatArch 路径、配置、systemd 用户生命周期、文件发布 |
| 反向代理 | TLS、可信 Host、外部入口与请求限制；不在当前 CLI 中 |

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

默认配置只监听 loopback，并使用共享 Basic Auth：

```yaml
serve-path: '<managed-data-root>'
bind: 127.0.0.1
port: 5000
auth:
  - '<username>:<password>@/:rw'
allow-upload: true
allow-delete: false
allow-search: true
allow-symlink: false
allow-archive: true
allow-hash: true
enable-cors: false
log-file: '<managed-access-log>'
```

这里的占位符不是可复制凭据。真实密码只从 `--password-env` 指定的环境变量读取；生成的 `config.yaml` 和 `instance.json` 权限为 `0600`，目录为 `0700`。`status` 和 JSON 输出不读取或显示密码。

## 生命周期

`service install` 生成 user unit 并运行 `systemctl --user daemon-reload`。只有显式 `--enable` 才启用登录后自动启动。

`start`、`stop`、`restart` 不直接发送进程信号，只操作 `chatshare-dufs.service`。`status` 将 inactive 作为正常状态返回，而不是把它误报为 CLI 崩溃。

## 升级与回滚

- 升级需要显式 `--version vX.Y.Z`。
- 新版本通过完整安装事务后才更新 `current`。
- 配置和数据不随二进制升级迁移或删除。
- 回滚使用已安装的旧版本重新执行 `install --version <old>`, 更新 `current` 后再 `restart`。
- ChatShare 不自动删除旧 runtime；清理策略需要单独设计。
