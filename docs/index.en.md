# ChatShare

ChatShare places Dufs inside ChatArch-owned paths and operational boundaries. The CLI owns trusted installation, configuration, service lifecycle, and local file publication; Dufs owns HTTP/WebDAV file serving.

<div class="grid cards" markdown>

-   :material-rocket-launch: **Get started**

    ---

    Install ChatShare, acquire Dufs, and publish the first file.

    [Open Quick Start](quickstart.md)

-   :material-console: **Inspect the CLI**

    ---

    Browse commands by install, configuration, service, and sharing responsibilities.

    [Open the CLI Tree](cli-tree.md)

-   :material-package-variant-closed: **Understand the runtime**

    ---

    Review version pinning, storage layout, the systemd user service, and rollback.

    [Open Dufs Runtime](dufs.md)

-   :material-shield-lock: **Confirm the security boundary**

    ---

    Review authentication, loopback defaults, permissions, and explicit exclusions.

    [Open Security and Boundaries](security.md)

</div>

## Current capabilities

| Responsibility | ChatShare | Dufs |
|---|---|---|
| Binary selection and integrity | Selects the release asset and verifies its GitHub `sha256` digest | Publishes official release assets |
| Configuration and state | Owns state under `~/.chatarch/chatshare/` | Reads generated YAML configuration |
| Service lifecycle | Linux `systemd --user` | Foreground file-server process |
| File publication | Atomically copies into the managed root and builds a URL | Serves files and accepts HTTP/WebDAV uploads |
| Authentication | Collects and stores the shared credential safely | HTTP Digest Auth path permissions |

## Out of scope

ChatShare does not currently provide accounts, anonymous capability links, expiry, download counts, per-file revocation, object storage, or multi-host orchestration. Dufs's direct-path model does not imply those semantics.
