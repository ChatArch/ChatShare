# Dufs Runtime

## Responsibility boundary

ChatShare does not modify Dufs source. It combines official release assets, configuration, and a Linux user service into a ChatArch-managed runtime.

| Layer | Responsibility |
|---|---|
| Dufs | HTTP/WebDAV, directory UI, Basic Auth, uploads, and reads |
| ChatShare | Release selection and integrity, ChatArch paths, configuration, systemd user lifecycle, and file publication |
| Reverse proxy | TLS, trusted Host enforcement, external ingress, and request limits; outside this CLI |

## Layout

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

The active Linux unit is `~/.config/systemd/user/chatshare-dufs.service`. It is the user-supervisor entry; the binary, configuration, data, logs, and canonical unit source remain ChatArch-owned.

## Installation transaction

`chatshare dufs install`:

1. Requests release metadata for a pinned `sigoden/dufs` tag.
2. Selects the unique `.tar.gz` asset for the OS and architecture.
3. Requires a valid `sha256:` digest in GitHub asset metadata.
4. Downloads inside the target runtime directory while streaming SHA-256.
5. Extracts only the regular `dufs` member and rejects links or path traversal.
6. Runs the non-listening `dufs --version` check.
7. Atomically replaces the versioned binary and `current` pointer.

A download, digest, extraction, or version failure never replaces the currently usable binary.

## Configuration

The default config is loopback-only with shared Basic Auth:

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

The placeholders are not copyable credentials. The real password is read only from the environment variable named by `--password-env`. Generated `config.yaml` and `instance.json` files use mode `0600`; directories use `0700`. `status` and JSON output never read or display the password.

## Lifecycle

`service install` generates the user unit and runs `systemctl --user daemon-reload`. Login-time startup is enabled only with explicit `--enable`.

`start`, `stop`, and `restart` do not signal processes directly; they operate on `chatshare-dufs.service`. `status` returns inactive as a normal service state instead of treating it as a CLI crash.

## Upgrade and rollback

- Upgrades require explicit `--version vX.Y.Z`.
- `current` changes only after the new version completes the installation transaction.
- Binary upgrades do not migrate or delete configuration and data.
- Roll back by installing an already trusted old version with `install --version <old>`, then `restart`.
- ChatShare does not automatically delete old runtimes; garbage collection requires a separate design.
