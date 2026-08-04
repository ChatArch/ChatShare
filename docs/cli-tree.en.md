# CLI Tree

## Top-level commands

```text
chatshare [--home PATH] [--json] [--version]
├── dufs                 # Dufs runtime, configuration, and user service
├── put SOURCE [DEST]    # Publish a local file into the share root
└── url PATH             # Build a direct URL for an existing relative path
```

`--home` is the ChatArch home, derived from ChatEnv and normally `~/.chatarch`. `--json` enables structured output for the invocation.

## Dufs runtime

```text
chatshare dufs
├── install
│   ├── --version VERSION    # defaults to v0.46.0; no implicit latest
│   ├── --platform TARGET    # explicit test/cross-install override
│   └── --force              # atomically replace the same-version binary
├── init
│   ├── --root PATH          # defaults to the ChatArch-owned data directory
│   ├── --bind HOST          # loopback only
│   ├── --port PORT          # defaults to 5000
│   ├── --base-url URL       # public base used for generated share URLs
│   ├── --username NAME      # defaults to chatshare
│   ├── --password-env NAME  # defaults to CHATSHARE_DUFS_PASSWORD
│   └── --force              # replace existing configuration
├── service
│   └── install [--enable]   # install the Linux systemd user unit
├── start                    # systemctl --user start
├── stop                     # systemctl --user stop
├── restart                  # systemctl --user restart
├── status                   # summarize runtime, config, unit, and active state
└── logs [--lines N]         # read the tail of the managed access log
```

## File publication

```text
chatshare put SOURCE [DESTINATION]
└── --overwrite          # explicitly allow atomic replacement

chatshare url PATH
```

`DESTINATION` and `PATH` are POSIX-style relative paths. The CLI rejects absolute paths, empty components, `.`, `..`, and any resolved target outside the managed root.

## Interface contract

- CLI callbacks only resolve arguments and render output; install, config, service, and file operations expose importable Python APIs.
- Destructive replacement requires `--force` or `--overwrite`.
- Passwords are supplied by environment-variable name; there is no `--password VALUE` option.
- This version owns one `default` instance and has no multi-instance or remote-host registry.
- The old `hello` command remains as a hidden compatibility entry and is not part of the product tree.
