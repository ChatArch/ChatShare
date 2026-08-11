# CLI Tree

`chatshare --tree` renders the command tree from the current Click registry. This page should stay aligned with runtime readback.

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

## Interface contract

- `--home` is the ChatArch home, derived from ChatEnv and normally `~/.chatarch`. `--json` enables structured output for the invocation.
- CLI callbacks only resolve arguments and render output; install, config, service, and file operations expose importable Python APIs.
- Destructive replacement requires `--force` or `--overwrite`.
- Passwords are supplied by environment-variable name; there is no `--password VALUE` option.
- This version owns one `default` instance and has no multi-instance or remote-host registry.
- The old `hello` command remains as a hidden compatibility entry and is not part of the product tree.
