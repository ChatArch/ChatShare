<div align="center">
    <a href="https://pypi.org/project/ChatShare/"><img src="https://img.shields.io/pypi/v/ChatShare.svg" alt="PyPI version" /></a>
    <a href="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml"><img src="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml/badge.svg" alt="Test status" /></a>
    <a href="https://arch.gh.wzhecnu.cn/ChatShare/en/"><img src="https://img.shields.io/badge/docs-MkDocs-blue.svg" alt="Documentation" /></a>
</div>

<div align="center">[Chinese](README.md) | [English](README.en.md)</div>

# ChatShare

ChatShare is the ChatArch-managed file-sharing CLI. Its current backend is [Dufs](https://github.com/sigoden/dufs), with auditable server-runtime installation, configuration, user-service lifecycle, and **streaming upload, directory listing, and direct URL generation from a new machine connected to an existing share**.

> Version `0.2.8` adds the remote CLI, visible browser upload progress, and independent web-asset synchronization. Upgrade older `0.2.7` clients first; a server upgrade also requires synchronizing web assets.

## Secure defaults

Version `0.2.6` adds application-owned directory login through the `server` extra. `chatshare serve` owns the login page, sessions and directory authorization; the reverse proxy only forwards traffic.

```bash
python -m pip install "ChatShare[server]==0.2.8"
chatshare serve --allowed-host proxy.internal
```

The gateway defaults to `127.0.0.1:5001`, reads the existing instance root, loopback upstream and public base URL, and does not modify Dufs. Anonymous clients may only GET/HEAD/Range known concrete files; directories, JSON/search, archives and writes require login/native authentication. See [security boundaries](docs/security.en.md). Proxy cutover, TLS and live acceptance are separate operator tasks. Direct Dufs access bypasses this gate.

- Dufs is installed under `~/.chatarch/chatshare/runtimes/dufs/`, never a system prefix.
- The service binds only to `127.0.0.1`; public ingress belongs to a separate reverse-proxy task.
- Native Dufs remains anonymously readable with authenticated writes; gateway access limits anonymous reads to known concrete files and uses server-side cookie sessions for browser directory access.
- Delete and external-symlink access are disabled by default.
- Linux lifecycle uses `systemd --user`; ChatShare does not use `kill`, `pkill`, or an unmanaged background process.

## Shortest workflow: connect a new machine to an existing share

Do not run `chatshare dufs install` or `chatshare dufs init` on a new client. After configuring a writer account, `put`, `tree`, and `url` automatically use remote mode:

```bash
uv tool install ChatShare
chatenv init -t chatshare -I
chatenv set 'CHATSHARE_DUFS_BASE_URL=https://<share-url>' -I
chatenv set 'CHATSHARE_DUFS_USERNAME=<writer-name>' -I
read -rsp "ChatShare writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD

chatshare tree
chatshare put --progress ./video.mov videos/video.mov
chatshare url videos/video.mov
```

Browser uploads show a file name, byte progress, speed, and a server-confirmation phase; CLI `--progress` does the same with streaming reads. A host with an existing local instance retains local publication mode. See [Quick Start](docs/quickstart.en.md) for client configuration, HTTP/WebDAV authentication, large-file boundaries, and service deployment.

The signed-in directory page also provides [download jobs and directory shares](docs/downloads.en.md): the server can safely import a public HTTP/HTTPS direct file, and owners can issue revocable high-entropy read-only directory links. A directory share URL is itself a bearer capability; files retain their original public URIs.

Run `chatshare --tree` for the full live command tree that ChatStyle generates from the Click registry. `chatshare tree <prefix>` lists a directory from the local managed instance or configured remote server, and `chatshare --tree-brief` shows the command surface without parameter signatures. Hidden compatibility entries are excluded from the product tree.

## Documentation

- [Quick Start](https://arch.gh.wzhecnu.cn/ChatShare/en/quickstart/)
- [CLI Tree](https://arch.gh.wzhecnu.cn/ChatShare/en/cli-tree/)
- [Dufs Runtime](https://arch.gh.wzhecnu.cn/ChatShare/en/dufs/)
- [Download Jobs and Directory Shares](https://arch.gh.wzhecnu.cn/ChatShare/en/downloads/)
- [Security and Boundaries](https://arch.gh.wzhecnu.cn/ChatShare/en/security/)

See [`DEVELOP.md`](DEVELOP.md) and [`AGENTS.md`](AGENTS.md) for development conventions.
