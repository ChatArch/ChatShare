# Quick Start

## Choose an entry point

<div class="grid cards" markdown>

-   **Install the tool and runtime**

    Install ChatShare through the existing ChatArch Python tool environment, then let ChatShare install a pinned Dufs release.

-   **Initialize a safe config**

    Store writer credentials in ChatEnv and generate a loopback-only Dufs config with anonymous reads, authenticated writes, and delete disabled.

-   **Start the service**

    Linux uses `systemd --user`; ChatShare does not create a system unit or unmanaged background process.

-   **Share, then retrieve**

    `chatshare put` publishes a local file or directory, `chatshare tree` inspects the published directory structure, `chatshare url` retrieves the public URL for an already-published path, and anonymous `curl` or a browser can download it.

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
- HTTP/WebDAV upload or `PUT` requires Dufs HTTP Auth; the web UI shows the ChatShare login dialog and sends an explicit auth header instead of relying on the browser's default auth prompt
- The directory page provides a drag-and-drop upload zone and a "Choose files" button; dropped files enter the upload queue directly, opening the ChatShare login dialog first when needed
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

## Complete example: share, then retrieve

This example shows the full loop: prepare a file, publish it, inspect the share tree, retrieve the URL again, and download it anonymously.

```bash
# 1. Prepare a local file.
printf 'hello from ChatShare\n' > hello-share.txt

# 2. Publish it to a relative path below the managed share root.
#    This is a local operator action: it atomically copies the file into
#    ~/.chatarch/chatshare/.../data/.
chatshare --json put ./hello-share.txt examples/hello-share.txt

# 3. Inspect the actual server-side tree for the published directory.
chatshare tree examples

# 4. If you later only know the in-share path, retrieve the public URL again.
chatshare --json url examples/hello-share.txt

# 5. Read the public URL anonymously; no username or password is needed.
curl -fsSL https://share.public.wzhecnu.cn/examples/hello-share.txt
```

`chatshare put`, `chatshare tree`, and `chatshare url` are different commands:

| Command | What it does | Writes share data |
| --- | --- | --- |
| `chatshare put SOURCE [DEST]` | Copies a local file or directory into the managed share root and returns the URL for `DEST`; directory uploads preserve relative paths recursively | Yes |
| `chatshare tree [DEST]` | Reads the actual tree under the managed share root or a subdirectory | No |
| `chatshare url DEST` | Checks that `DEST` already exists under the managed share root, then builds the URL from `CHATSHARE_DUFS_BASE_URL` | No |

Use `chatshare url` when:

- a file was already published with `chatshare put` and you want to print the link again;
- another controlled process placed a file directly under the managed `data/` directory and you want a link for it;
- automation needs to convert a stable relative path into a public URL.

It does not copy, upload, or create files. If the target file does not exist, it fails.

## Complete example: HTTP PUT requires authentication

Web browsing and downloads are anonymous, but network-side HTTP/WebDAV `PUT` requires Dufs HTTP Digest Auth. The example below keeps the secret in ChatEnv and a temporary curl config, not in argv, URLs, or logs:

```bash
base_url="$(chatenv get CHATSHARE_DUFS_BASE_URL)"
writer_user="$(chatenv get CHATSHARE_DUFS_USERNAME)"
writer_password="$(chatenv get CHATSHARE_DUFS_PASSWORD)"

printf 'hello through authenticated HTTP PUT\n' > hello-http-put.txt

# Anonymous PUT should return 401.
curl -sS -o /dev/null -w '%{http_code}\n' \
  -T ./hello-http-put.txt \
  "${base_url%/}/hello-http-put.txt"

# Authenticated PUT uses Digest Auth; the secret does not enter argv.
umask 077
curl_config="$(mktemp)"
trap 'rm -f "$curl_config"' EXIT
printf 'user = "%s:%s"\n' "$writer_user" "$writer_password" > "$curl_config"
curl --digest --config "$curl_config" \
  -T ./hello-http-put.txt \
  "${base_url%/}/hello-http-put.txt"

unset writer_password
curl -fsSL "${base_url%/}/hello-http-put.txt"
```

If you are publishing from the service host, prefer `chatshare put`. Use HTTP/WebDAV `PUT` + Digest Auth only for network clients that need write access.

## Automation output

Place global `--json` before the subcommand:

```bash
chatshare --json dufs status
chatshare --json put ./report.pdf reports/report.pdf
chatshare --json tree reports
chatshare --json url reports/report.pdf
```
