# Security and Boundaries

## Access matrix

| Operation | Current actor and credential |
|---|---|
| Install, initialize, and manage service | The ChatArch user logged into the host |
| Local `put` and `url` | The same ChatArch user; no HTTP request |
| Browse, download, and inline view | Anonymous client; anyone with the URL can read public data |
| HTTP/WebDAV upload | A client holding the shared Dufs HTTP Digest Auth credential |
| HTTP delete | Disabled by default |
| Cleanup, expiry, and per-file revocation | Not implemented |

The first version uses anonymous reads plus one shared credential for writes rather than per-file capability links. A URL is not a secret; anything placed under the share root is intentionally readable by anonymous clients, while leaking the shared password grants deployment-wide upload/overwrite access.

## Credentials

- Default password variable: `CHATSHARE_DUFS_PASSWORD`.
- The CLI accepts an environment-variable name, never a password-value option.
- Dufs must read the account rule at startup, so the password exists in `config.yaml`; the file is written with mode `0600`.
- The web login dialog only passes user input into the browser/XHR HTTP Digest Auth flow; it does not add server-side sessions, cookies, or tokens.
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

- Share expiry, download limits, or per-file revocation
- Multi-user ownership and audit
- Browser sessions, OAuth/OIDC, or server-side account ownership
- S3/object keys, CDN, or multi-node replication
- Remote-host registry or centralized orchestration

Any of these capabilities requires a product and state-model extension; it must not be disguised as a Dufs configuration toggle.
