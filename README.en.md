<div align="center">
    <a href="https://pypi.org/project/ChatShare/"><img src="https://img.shields.io/pypi/v/ChatShare.svg" alt="PyPI version" /></a>
    <a href="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml"><img src="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml/badge.svg" alt="Test status" /></a>
    <a href="https://arch.gh.wzhecnu.cn/ChatShare/en/"><img src="https://img.shields.io/badge/docs-MkDocs-blue.svg" alt="Documentation" /></a>
</div>

<div align="center">[Chinese](README.md) | [English](README.en.md)</div>

# ChatShare

ChatShare is the ChatArch-managed file-sharing CLI. Its current backend is [Dufs](https://github.com/sigoden/dufs), with auditable binary installation, configuration, user-service lifecycle, local file/directory import, share-tree inspection, and direct URL generation.

## Secure defaults

Version `0.2.6` adds application-owned directory login through the `server` extra. `chatshare serve` owns the login page, sessions and directory authorization; the reverse proxy only forwards traffic.

```bash
python -m pip install "ChatShare[server]==0.2.6"
chatshare serve --allowed-host proxy.internal
```

The gateway defaults to `127.0.0.1:5001`, reads the existing instance root, loopback upstream and public base URL, and does not modify Dufs. Anonymous clients may only GET/HEAD/Range known concrete files; directories, JSON/search, archives and writes require login/native authentication. See [security boundaries](docs/security.en.md). Proxy cutover, TLS and live acceptance are separate operator tasks. Direct Dufs access bypasses this gate.

- Dufs is installed under `~/.chatarch/chatshare/runtimes/dufs/`, never a system prefix.
- The service binds only to `127.0.0.1`; public ingress belongs to a separate reverse-proxy task.
- Native Dufs remains anonymously readable with authenticated writes; gateway access limits anonymous reads to known concrete files and uses server-side cookie sessions for browser directory access.
- Delete and external-symlink access are disabled by default.
- Linux lifecycle uses `systemd --user`; ChatShare does not use `kill`, `pkill`, or an unmanaged background process.

## Shortest workflow

```bash
uv tool install ChatShare
chatshare dufs install
chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://share.example -I
chatenv set CHATSHARE_DUFS_USERNAME=chatshare -I
read -rsp "Dufs writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD
chatshare dufs init
chatshare dufs service install
chatshare dufs start
printf 'hello from ChatShare\n' > hello-share.txt
chatshare put ./hello-share.txt examples/hello-share.txt
chatshare tree examples
chatshare url examples/hello-share.txt
```

Run `chatshare --tree` for the full live command tree that ChatStyle generates from the Click registry. `chatshare tree <prefix>` inspects the actual published share tree, and `chatshare --tree-brief` shows the command surface without parameter signatures. Hidden compatibility entries are excluded from the product tree.

## Documentation

- [Quick Start](https://arch.gh.wzhecnu.cn/ChatShare/en/quickstart/)
- [CLI Tree](https://arch.gh.wzhecnu.cn/ChatShare/en/cli-tree/)
- [Dufs Runtime](https://arch.gh.wzhecnu.cn/ChatShare/en/dufs/)
- [Security and Boundaries](https://arch.gh.wzhecnu.cn/ChatShare/en/security/)

See [`DEVELOP.md`](DEVELOP.md) and [`AGENTS.md`](AGENTS.md) for development conventions.
