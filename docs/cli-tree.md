# CLI 树

`chatshare --tree` 会由 ChatStyle 从当前 Click 注册表生成以下完整命令树。这个页面应与 runtime readback 保持一致。

```text
chatshare
├── --help  # Show this message and exit.
├── --home HOME  # ChatArch home (default: ChatEnv home, normally ~/.chatarch).
├── --json  # Emit structured JSON output.
├── --version  # Show the version and exit.
├── --tree  # Print the registered CLI tree and exit.
├── --tree-brief  # Print the registered CLI tree without parameter signatures and exit.
├── dufs  # Manage the local Dufs runtime, configuration, and user service.
│   ├── assets  # Manage the existing instance's web UI assets without reinitializing it.
│   │   └── sync  # Copy bundled web UI assets; restart Dufs later to refresh cached HTML.
│   ├── init [--root ROOT] [--bind BIND] [--port PORT] [--base-url BASE-URL] [--username USERNAME] [--password-env PASSWORD-ENV] [--force]  # Initialize secure Dufs config and state; writes managed files.
│   ├── install [--version VERSION] [--platform TARGET] [--force]  # Install a verified Dufs runtime; writes managed runtime files.
│   ├── logs [--lines LINES]  # Read a bounded Dufs access-log tail; no writes.
│   ├── restart  # Restart Dufs through systemd --user; changes service state.
│   ├── service  # Manage the Linux systemd user-service definition.
│   │   └── install [--enable]  # Write the systemd user unit; optionally enable login startup.
│   ├── start  # Start Dufs through systemd --user; changes service state.
│   ├── status  # Read runtime, config, unit, and active state; no writes.
│   └── stop  # Stop Dufs through systemd --user; changes service state.
├── put <SOURCE> [DESTINATION] [--overwrite] [--progress]  # Publish locally when initialized, otherwise to configured ChatShare.
├── serve [--bind BIND] [--port PORT] [--allowed-host ALLOWED-HOSTS]  # Run the directory-login gateway in the foreground; no Dufs changes.
├── tree [PREFIX]  # List a local managed tree or the configured remote directory.
└── url <PATH>  # Get a local managed or configured remote file URL.
```

`chatshare --tree-brief` 保留相同节点和说明，但省略参数签名：

```text
chatshare
├── --help  # Show this message and exit.
├── --home  # ChatArch home (default: ChatEnv home, normally ~/.chatarch).
├── --json  # Emit structured JSON output.
├── --version  # Show the version and exit.
├── --tree  # Print the registered CLI tree and exit.
├── --tree-brief  # Print the registered CLI tree without parameter signatures and exit.
├── dufs  # Manage the local Dufs runtime, configuration, and user service.
│   ├── assets  # Manage the existing instance's web UI assets without reinitializing it.
│   │   └── sync  # Copy bundled web UI assets; restart Dufs later to refresh cached HTML.
│   ├── init  # Initialize secure Dufs config and state; writes managed files.
│   ├── install  # Install a verified Dufs runtime; writes managed runtime files.
│   ├── logs  # Read a bounded Dufs access-log tail; no writes.
│   ├── restart  # Restart Dufs through systemd --user; changes service state.
│   ├── service  # Manage the Linux systemd user-service definition.
│   │   └── install  # Write the systemd user unit; optionally enable login startup.
│   ├── start  # Start Dufs through systemd --user; changes service state.
│   ├── status  # Read runtime, config, unit, and active state; no writes.
│   └── stop  # Stop Dufs through systemd --user; changes service state.
├── put  # Publish locally when initialized, otherwise to configured ChatShare.
├── serve  # Run the directory-login gateway in the foreground; no Dufs changes.
├── tree  # List a local managed tree or the configured remote directory.
└── url  # Get a local managed or configured remote file URL.
```

## 接口约定

- `--home` 表示 ChatArch home，默认来自 ChatEnv，通常为 `~/.chatarch`。它同时定位本机实例与 active `chatshare` 配置；`--json` 对当前调用启用结构化输出。
- `put`、`tree`、`url` 优先使用已存在的本机 `default` 实例；没有 `instance.json` 时改用 active ChatEnv 中的单个已配置远端 URL，不要求运行 `dufs init`。
- `put --progress` 在 stderr 显示流式字节进度；`--no-progress` 关闭它。JSON 结果保持 stdout 可解析。
- CLI 只负责参数解析和输出；安装、配置、服务、文件发布与目录查询均有可导入 Python API。
- 破坏性覆盖必须显式使用 `--force` 或 `--overwrite`。
- 密码只通过 ChatEnv 或受控环境变量读取，不提供 `--password VALUE`。
- 当前只有一个本机 `default` 实例，不提供多实例或远程主机注册表。
- 旧版 `hello` 命令仅保留为隐藏兼容入口，不属于产品命令树。
