# Quick Start

ChatShare has two roles. **Most new machines only connect to an existing share**: configure ChatEnv once, then upload, list a directory, and retrieve links. Do **not** run `chatshare dufs init` on those clients. Only the host that stores the files installs Dufs, initializes an instance, and manages its systemd service.

Concrete file links are anonymously readable. Directory listings and writes require the existing Dufs writer account. The browser directory page uses a ChatShare login session; CLI and HTTP/WebDAV clients use the same account through HTTP Basic/Digest authentication. See [security boundaries](security.en.md).

## Choose a role

| What you need | Use | Do not use |
| --- | --- | --- |
| Upload or list files from a new laptop, workstation, or server | Configure the remote client, then use `put`, `tree`, and `url` | Do not install Dufs or run `dufs init` |
| Run the share service and store the real files | Deploy the server instance | Do not copy the server data root onto a client |
| Upload a large file in a browser | Log into the directory page, then drag a file or choose it | Do not treat 100% sent as completed |

## A. Connect to an existing share (new machine)

### 1. Install the CLI

```bash
uv tool install ChatShare
chatshare --version
```

The base package includes the HTTP client used for remote uploads and directory queries. It does not require `ChatShare[server]` or a local Dufs runtime.

### 2. Configure the writer account

Never put the password in shell history, command-line arguments, URLs, or scripts. Store these three values in the active ChatEnv `chatshare` profile. The service administrator provides `<share-url>`; it is normally an HTTPS address. Use an internal HTTPS address only on a trusted network when the administrator explicitly provides it.

```bash
chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://<share-url> -I
chatenv set CHATSHARE_DUFS_USERNAME=<writer-name> -I
read -rsp "ChatShare writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD
```

| Field | Purpose |
| --- | --- |
| `CHATSHARE_DUFS_BASE_URL` | Base URL of the existing share, with no credentials, query, or fragment |
| `CHATSHARE_DUFS_USERNAME` | Dufs account allowed to write and list directories |
| `CHATSHARE_DUFS_PASSWORD` | Password for that account; stored through protected ChatEnv configuration |

### 3. List, upload, and retrieve a link

```bash
# List the root. Remote mode reads the configured service; it does not need instance.json.
chatshare tree

# List a directory.
chatshare tree videos

# Upload a file. An interactive terminal shows progress automatically;
# --progress forces it on.
chatshare put --progress ./clip.mov videos/2026/clip.mov

# Check that the file exists and print its public direct link.
chatshare url videos/2026/clip.mov

# Put machine-readable output before the subcommand; progress remains on stderr.
chatshare --json put --progress ./clip.mov videos/2026/clip.mov
```

Remote `tree` lists the current contents of the selected directory. `put` checks the destination, creates missing parent directories one at a time, then streams a PUT request in 1 MiB chunks. Existing files are rejected by default; pass `--overwrite` explicitly to replace one. `url` uses authenticated HEAD to confirm that the target exists before returning its URL.

If a new machine previously showed this error, it was missing remote-client configuration, not a request to initialize another Dufs service:

```text
ChatShare Dufs instance is not initialized: .../instance.json
```

Configure ChatEnv as above. Afterwards `chatshare tree` contacts the configured service directly. When remote configuration is absent, the CLI explains which `CHATSHARE_DUFS_*` fields and setup command are missing.

### 4. Large files and progress

- The browser upload area immediately shows the file name, progress bar, transferred/total bytes, and speed. At 100% it says that the client is waiting for server confirmation; it shows success only after a 2xx response.
- On failure the page shows a reason and a Retry action. Retry first checks the remote byte count and resumes only when the offset is safe.
- CLI `--progress` streams the source instead of loading it all into memory; `--no-progress` suppresses terminal progress lines.
- The ChatShare gateway leaves `PUT`/`PATCH` read and write timeouts open while data is actively streaming, so a large active upload is not cut off by a 30-second metadata deadline. Reverse proxies, network equipment, disk capacity, and browsers can still impose their own limits; only a real upload and integrity readback prove a specific environment's limit.

## B. Deploy the share service (server host only)

This creates a managed local Dufs instance and belongs only on the host that stores shared files. Do not run these commands on a client machine.

```bash
uv tool install "ChatShare[server]"
chatshare dufs install

chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://<share-url> -I
chatenv set CHATSHARE_DUFS_USERNAME=<writer-name> -I
read -rsp "Dufs writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD

chatshare dufs init
chatshare dufs service install
chatshare dufs start
chatshare dufs status
```

The default instance lives under `~/.chatarch/chatshare/instances/default/`, and Dufs binds only to loopback. On the server, `chatshare put` atomically copies into the managed data root; `tree` and `url` inspect that local instance. Run the directory-login gateway with `chatshare serve`, then make a separate trusted HTTPS reverse-proxy change. Do not expose Dufs directly to the public network.

After upgrading ChatShare on the server, run `chatshare dufs assets sync` to copy the bundled UI assets. This command only replaces managed static files; it does not reset accounts, server configuration, or shared data. **Wait for all active uploads to finish** before an operator restarts Dufs (which caches its index HTML at startup) and the deployed ChatShare gateway (which loads JS/CSS at startup). Read back the real directory page's asset version and choose a file in a browser to confirm that progress appears. Installing a new Python package or synchronizing static files alone does not prove that the live page changed. Client-only machines must not run this command.

## HTTP/WebDAV clients

External programs can also upload through Dufs HTTP Basic/Digest authentication. The CLI is preferable for routine uploads and visible progress. When WebDAV compatibility is required, use Digest and put the password only in a temporary permission-restricted curl config:

```bash
base_url="$(chatenv get CHATSHARE_DUFS_BASE_URL)"
writer_user="$(chatenv get CHATSHARE_DUFS_USERNAME)"
read -rsp "ChatShare writer password: " writer_password && echo

umask 077
curl_config="$(mktemp)"
trap 'rm -f "$curl_config"' EXIT
printf 'user = "%s:%s"\n' "$writer_user" "$writer_password" > "$curl_config"
curl --digest --config "$curl_config" \
  -T ./clip.mov \
  "${base_url%/}/videos/clip.mov"
unset writer_password
```

Anonymous GET of a concrete file URL needs no password, but a link is not a private capability token. Directories, JSON listings, uploads, and other management operations still require authentication.

## Operator commands

```bash
# Generated from the live Click registry
chatshare --tree
chatshare --tree-brief

# Server-instance state and bounded access log
chatshare --json dufs status
chatshare dufs logs --lines 100
```

`dufs install`, `dufs init`, `dufs service install`, and `dufs start|stop|restart` are server-only. `put`, `tree`, and `url` use local mode when a local instance exists; without one they automatically use the configured remote service.
