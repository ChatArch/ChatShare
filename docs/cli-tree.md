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
│   ├── init [--root ROOT] [--bind BIND] [--port PORT] [--base-url BASE-URL] [--username USERNAME] [--password-env PASSWORD-ENV] [--force]  # Initialize secure Dufs config and state; writes managed files.
│   ├── install [--version VERSION] [--platform TARGET] [--force]  # Install a verified Dufs runtime; writes managed runtime files.
│   ├── logs [--lines LINES]  # Read a bounded Dufs access-log tail; no writes.
│   ├── restart  # Restart Dufs through systemd --user; changes service state.
│   ├── service  # Manage the Linux systemd user-service definition.
│   │   └── install [--enable]  # Write the systemd user unit; optionally enable login startup.
│   ├── start  # Start Dufs through systemd --user; changes service state.
│   ├── status  # Read runtime, config, unit, and active state; no writes.
│   └── stop  # Stop Dufs through systemd --user; changes service state.
├── put <SOURCE> [DESTINATION] [--overwrite]  # Publish a local file; writes or replaces managed share data.
└── url <PATH>  # Build a direct URL for an existing managed file; no writes.
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
│   ├── init  # Initialize secure Dufs config and state; writes managed files.
│   ├── install  # Install a verified Dufs runtime; writes managed runtime files.
│   ├── logs  # Read a bounded Dufs access-log tail; no writes.
│   ├── restart  # Restart Dufs through systemd --user; changes service state.
│   ├── service  # Manage the Linux systemd user-service definition.
│   │   └── install  # Write the systemd user unit; optionally enable login startup.
│   ├── start  # Start Dufs through systemd --user; changes service state.
│   ├── status  # Read runtime, config, unit, and active state; no writes.
│   └── stop  # Stop Dufs through systemd --user; changes service state.
├── put  # Publish a local file; writes or replaces managed share data.
└── url  # Build a direct URL for an existing managed file; no writes.
```

## 接口约定

- `--home` 表示 ChatArch home，默认来自 ChatEnv，通常为 `~/.chatarch`。`--json` 对当前调用启用结构化输出。
- CLI 只负责参数解析和输出；安装、配置、服务与文件操作均有可导入 Python API。
- 破坏性覆盖必须显式使用 `--force` 或 `--overwrite`。
- 密码只通过环境变量名传入；不提供 `--password VALUE`。
- 当前只有一个 `default` 实例，不提供多实例或远程主机注册表。
- 旧版 `hello` 命令仅保留为隐藏兼容入口，不属于产品命令树。
