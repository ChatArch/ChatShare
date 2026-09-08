# Security and Boundaries

## Access matrix

| Operation | Current actor and credential |
|---|---|
| Install, initialize, and manage service | The ChatArch user logged into the host |
| Local `put` and `url` | The same ChatArch user; no HTTP request |
| Known concrete file GET/HEAD/Range | Anonymous, including cross-site PNG embeds |
| Directory HTML/JSON, search, WebDAV enumeration, archives | Gateway browser session or native Dufs Basic/Digest |
| HTTP/WebDAV upload | A client holding the shared Dufs HTTP Auth credential |
| HTTP delete | Disabled by default |
| Cleanup, expiry, and per-file revocation | Not implemented |

This matrix applies only through `chatshare serve`. Direct Dufs still has its original anonymous read permissions; do not expose a bypass route. A known file URL is not a secret or per-file capability. The gate prevents enumeration, not guessing file names or revoking individual published URLs. Existing Dufs permissions, including `allow-delete: false`, remain authoritative.

## Credentials

- Default password variable: `CHATSHARE_DUFS_PASSWORD`.
- The CLI accepts an environment-variable name, never a password-value option.
- Dufs must read the account rule at startup, so the password exists in `config.yaml`; the file is written with mode `0600`.
- Gateway login validates credentials with native Dufs CHECKAUTH using Basic over numeric loopback. Only a random HttpOnly, SameSite=Strict, Path=/ session cookie reaches the browser; Secure follows the configured HTTPS public URL. Ephemeral server memory holds auth material, never a second account database or credentials on disk.
- Every cookie-authorized request rechecks Dufs; logout, expiry and password rejection revoke the session. A password change takes effect when the unchanged Dufs process itself recognizes it. Sessions do not survive a gateway restart. Native explicit Basic/Digest is passed to Dufs for real verification without replaying Digest against a different method or URI.
- Gateway JS clears only `chatshare.dufs.credentials` and never stores new passwords in DOM/storage. Original non-gateway Dufs mode remains compatible and retains its legacy browser storage behavior; it is not a substitute for the server gate.
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
- OAuth/OIDC, persistent sessions, or server-side account ownership
- S3/object keys, CDN, or multi-node replication
- Remote-host registry or centralized orchestration

Any of these capabilities requires a product and state-model extension; it must not be disguised as a Dufs configuration toggle.

## Gateway operation and limits

Use the tested local `0.2.4+directorylogin.1` wheel with the `server` extra. `chatshare serve` runs in the foreground on `127.0.0.1:5001`; `--bind ::1`, `--port` and repeated `--allowed-host proxy.internal` are available. `create_app(ChatSharePaths.from_home())` is the importable ASGI factory. Server dependencies are imported only by `serve`/the gateway module. Existing managed state supplies the root, port and public origin; no parallel endpoint/password environment variables are introduced. Public URLs must be HTTP(S) origins without a subpath.

- Run one process/worker. Defaults: 3,600-second absolute sessions, 256 sessions, 30 login attempts per rolling 60 seconds globally, 64 active HTTP requests, 4,096-byte login JSON, 128-character usernames and 1,024-character passwords. Login bodies time out after 10 seconds; upstream operations have 5-second connect/30-second I/O timeouts. Capacity failures are 429/503. Global rate limiting is deliberately bounded but can affect other users during abuse; the external proxy should add client-specific limits.
- Proxy TLS must preserve the configured public Origin. Allowed Host defaults to the public hostname and loopback, plus exact `--allowed-host` values. Forwarded headers never establish authority; wildcard hosts and CORS are not enabled. Login/logout and cookie writes require the configured Origin and `X-ChatShare-CSRF: 1`, rejecting null/foreign origins and cross-site Fetch Metadata. Native explicit auth clients need no CSRF header.
- Anonymous reads require a regular file inside the managed root and only `raw`, `download`, `cache` or `token` query keys. `token` cannot grant directory authority. Invalid/ambiguous percent encodings, control characters, backslashes, traversal, repeated path separators and symlink escapes are rejected conservatively, including double-encoded paths and literal percent filenames.
- Anonymous 200/206 requires Dufs's real-file Content-Disposition. Directory replacement without that marker fails closed before any body is sent. Safe 304/404/416 responses never forward upstream bodies. File/download/upload traffic streams in 64 KiB response chunks; only authenticated Dufs management HTML is buffered, with a 2 MiB cap. Unsupported HTML contracts fail closed with 502. No automatic upstream redirect following or retries.
- Management HTML must contain the packaged Dufs `index-data` template and versioned `/__dufs_v<version>__/` asset contract. The gateway injects an explicit marker and rewrites assets to its packaged JS/CSS/favicon; it never mutates installed Dufs runtime assets. Only gateway-owned assets/endpoints are public exceptions, not similarly named user files.
- All responses are no-store with Cookie/Authorization Vary. Raw file responses receive CSP `sandbox allow-scripts allow-downloads` without `allow-same-origin`, preventing uploaded active content from reading logged-in same-origin APIs. PNG embeds remain possible. This intentionally limits active-content previews. Trusted management assets are not sandboxed; management pages use a separate restrictive CSP. Gateway JS hides page snapshots on pagehide and reloads restored pages.
- No service installation, reverse-proxy changes, deployment, account mutation, secret logging or public publication is performed. The supervisor must validate the actual Dufs marker/template contract, authenticated UI/upload client behavior, proxy/TLS, range/hash correctness and rollback before cutover. This candidate's tests use only temporary roots and mocked upstreams.
