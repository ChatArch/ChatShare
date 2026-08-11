# CLI 树

`chatshare --tree` 会从当前 Click 注册表生成以下命令树。这个页面应与 runtime readback 保持一致。

```text
chatshare # Manage Dufs-backed file sharing inside ChatArch
├── --help # Show this message and exit
├── --version # Show the version and exit
├── --tree # Print the registered command tree
├── --home HOME # ChatArch home (default: ChatEnv home, normally ~/.chatarch).
├── --json # Emit structured JSON output.
├── dufs # Manage the Dufs runtime, configuration, and user service
│   ├── install [--version VERSION] [--platform TARGET] [--force] # Install and verify an official Dufs release asset
│   ├── init [--root ROOT] [--bind BIND] [--port PORT] [--base-url BASE-URL] [--username USERNAME] [--password-env PASSWORD-ENV] [--force] # Initialize the secure default Dufs instance
│   ├── service # Install the Linux systemd user-service definition
│   │   └── install [--enable] # Install the generated systemd user unit
│   ├── start # Start Dufs through systemd --user
│   ├── stop # Stop Dufs through systemd --user
│   ├── restart # Restart Dufs through systemd --user
│   ├── status # Show runtime, config, unit, and active state
│   └── logs [--lines LINES] # Read the bounded tail of the Dufs access log
├── put SOURCE [DESTINATION] [--overwrite] # Publish a local file into the managed share root
└── url PATH # Build a direct URL for an existing managed file
```

## 接口约定

- `--home` 表示 ChatArch home，默认来自 ChatEnv，通常为 `~/.chatarch`。`--json` 对当前调用启用结构化输出。
- CLI 只负责参数解析和输出；安装、配置、服务与文件操作均有可导入 Python API。
- 破坏性覆盖必须显式使用 `--force` 或 `--overwrite`。
- 密码只通过环境变量名传入；不提供 `--password VALUE`。
- 当前只有一个 `default` 实例，不提供多实例或远程主机注册表。
- 旧版 `hello` 命令仅保留为隐藏兼容入口，不属于产品命令树。
