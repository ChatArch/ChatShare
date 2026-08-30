# CLI Tree

ChatStyle renders `chatshare --tree` from the current Click registry. This page should stay aligned with runtime readback.

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
├── put <SOURCE> [DESTINATION] [--overwrite]  # Publish a local file or directory; writes managed share data.
├── tree [PREFIX]  # Print the managed share tree under an optional prefix; no writes.
└── url <PATH>  # Build a direct URL for an existing managed file; no writes.
```

`chatshare --tree-brief` preserves the same nodes and descriptions without parameter signatures:

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
├── put  # Publish a local file or directory; writes managed share data.
├── tree  # Print the managed share tree under an optional prefix; no writes.
└── url  # Build a direct URL for an existing managed file; no writes.
```

## Interface contract

- `--home` is the ChatArch home, derived from ChatEnv and normally `~/.chatarch`. `--json` enables structured output for the invocation.
- CLI callbacks only resolve arguments and render output; install, config, service, file publishing, and tree inspection expose importable Python APIs.
- Destructive replacement requires `--force` or `--overwrite`.
- Passwords are supplied by environment-variable name; there is no `--password VALUE` option.
- This version owns one `default` instance and has no multi-instance or remote-host registry.
- The old `hello` command remains as a hidden compatibility entry and is not part of the product tree.
