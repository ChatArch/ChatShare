# Quick Start

## Choose an entry point

<div class="grid cards" markdown>

-   **Install the tool and runtime**

    Install ChatShare through the existing ChatArch Python tool environment, then let ChatShare install a pinned Dufs release.

-   **Initialize a safe config**

    Supply the shared password through an environment variable and generate a loopback-only Dufs config with delete disabled.

-   **Start the service**

    Linux uses `systemd --user`; ChatShare does not create a system unit or unmanaged background process.

-   **Publish a file**

    `chatshare put` atomically copies a local file into the share root and returns its direct URL.

</div>

## Install

Use the existing ChatArch Python package flow for a released version:

```bash
uv tool install ChatShare
chatshare --version
```

For an unreleased review build, pin the install to a reviewed Git ref:

```bash
uv tool install --from "git+https://github.com/ChatArch/ChatShare.git@<reviewed-ref>" ChatShare
```

Install Dufs. The default is the ChatShare-validated `v0.46.0`; the CLI does not silently follow `latest`:

```bash
chatshare dufs install
```

## Initialize

Do not pass the password as a CLI argument. Service deployments should store the writer credential in the active ChatEnv `chatshare` profile. ChatShare reads `CHATSHARE_DUFS_USERNAME`, `CHATSHARE_DUFS_PASSWORD`, and `CHATSHARE_DUFS_BASE_URL` from ChatEnv:

```bash
chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://share.public.wzhecnu.cn -I
chatenv set CHATSHARE_DUFS_USERNAME=chatshare -I
read -rsp "Dufs writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD
chatshare dufs init
```

Defaults:

- Root: `~/.chatarch/chatshare/instances/default/data/`
- Config: `~/.chatarch/chatshare/instances/default/config.yaml`
- Listener: `127.0.0.1:5000`
- Writer username: `CHATSHARE_DUFS_USERNAME` from ChatEnv, defaulting to `chatshare`
- Anonymous browse, download, inline view, search, archive, and hash enabled
- HTTP/WebDAV upload/PUT requires Dufs HTTP Digest Auth
- Delete, CORS, and external symlinks disabled

## Install and start the user service

```bash
chatshare dufs service install
chatshare dufs start
chatshare dufs status
```

Enable login-time startup explicitly:

```bash
chatshare dufs service install --enable
```

`start`, `stop`, and `restart` delegate to `systemctl --user`. macOS supports installation, initialization, and file publication, but this version does not provide launchd lifecycle commands.

## Publish and retrieve a URL

```bash
chatshare put ./report.pdf reports/2026/report.pdf
chatshare url reports/2026/report.pdf
```

The destination must be a relative path below the managed root. Absolute paths and `..` are rejected. Returned URLs contain no username or password. Data reads are anonymous; HTTP/WebDAV `PUT` uses Dufs HTTP Digest Auth.

## Automation output

Place global `--json` before the subcommand:

```bash
chatshare --json dufs status
chatshare --json put ./report.pdf reports/report.pdf
```
