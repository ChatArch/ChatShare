# Security and Boundaries

## Access matrix

| Operation | Current actor and credential |
|---|---|
| Install, initialize, and manage service | The ChatArch user logged into the host |
| Local `put` and `url` | The same ChatArch user; no HTTP request |
| Browse, download, and inline view | A client holding the shared Dufs Basic Auth credential |
| HTTP/WebDAV upload | A client holding the shared Dufs Basic Auth credential |
| HTTP delete | Disabled by default |
| Cleanup, expiry, and per-file revocation | Not implemented |

The first version uses one shared credential for reads and writes rather than anonymous capability links. A URL is not an authorization credential. Leaking a URL is insufficient for access, while leaking the shared password grants deployment-wide read/write access.

## Credentials

- Default password variable: `CHATSHARE_DUFS_PASSWORD`.
- The CLI accepts an environment-variable name, never a password-value option.
- Dufs must read the account rule at startup, so the password exists in `config.yaml`; the file is written with mode `0600`.
- The password must never appear in argv, URLs, stdout, JSON, access logs, unit files, README examples, or test fixtures.
- Usernames and passwords reject Dufs auth-rule delimiters and newlines to prevent rule injection.

## Network

- `init` accepts only `127.0.0.1`, `localhost`, or `::1`.
- `0.0.0.0`, `::`, and LAN addresses are rejected.
- This CLI does not configure TLS, Nginx, DNS, or public ingress.
- External publication belongs to a separate deployment task with trusted Hosts, TLS, request size/rate limits, and rollback. Direct public binding is not acceptance.

## Filesystem

- ChatArch-managed directories default to mode `0700`; credential and state files default to `0600`.
- `put` rejects absolute destinations, `.`, `..`, empty components, and root escapes.
- Publication uses a same-filesystem temporary file and atomic replacement. Existing files require explicit `--overwrite`.
- Dufs `allow-symlink` and `allow-delete` are disabled by default.

## Explicitly unsupported

- Anonymous links or URL bearer tokens
- Share expiry, download limits, or per-file revocation
- Multi-user ownership and audit
- Browser sessions or OAuth/OIDC
- S3/object keys, CDN, or multi-node replication
- Remote-host registry or centralized orchestration

Any of these capabilities requires a product and state-model extension; it must not be disguised as a Dufs configuration toggle.
