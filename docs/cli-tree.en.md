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

## Interface contract

- `--home` is the ChatArch home, derived from ChatEnv and normally `~/.chatarch`. It locates both the local instance and the active `chatshare` configuration; `--json` enables structured output for the invocation.
- `put`, `tree`, and `url` prefer an existing local `default` instance. Without `instance.json`, they use the single remote URL in active ChatEnv configuration; they do not require `dufs init`.
- `put --progress` renders streaming byte progress on stderr; `--no-progress` suppresses it. The JSON result remains parseable on stdout.
- CLI callbacks only resolve arguments and render output; install, config, service, file publication, and directory queries expose importable Python APIs.
- Destructive replacement requires `--force` or `--overwrite`.
- Passwords are read from ChatEnv or controlled process environment; there is no `--password VALUE` option.
- This version owns one local `default` instance and has no multi-instance or remote-host registry.
- The old `hello` command remains as a hidden compatibility entry and is not part of the product tree.
