<div align="center">
    <a href="https://pypi.org/project/ChatShare/"><img src="https://img.shields.io/pypi/v/ChatShare.svg" alt="PyPI version" /></a>
    <a href="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml"><img src="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml/badge.svg" alt="Test status" /></a>
    <a href="https://arch.gh.wzhecnu.cn/ChatShare/en/"><img src="https://img.shields.io/badge/docs-MkDocs-blue.svg" alt="Documentation" /></a>
</div>

<div align="center">[Chinese](README.md) | [English](README.en.md)</div>

# ChatShare

ChatShare is the ChatArch-managed file-sharing CLI. Its current backend is [Dufs](https://github.com/sigoden/dufs), with auditable binary installation, configuration, user-service lifecycle, local file import, and direct URL generation.

## Secure defaults

- Dufs is installed under `~/.chatarch/chatshare/runtimes/dufs/`, never a system prefix.
- The service binds only to `127.0.0.1`; public ingress belongs to a separate reverse-proxy task.
- Reads and writes require Dufs Basic Auth. The shared password is read from an environment variable and persisted only in a mode-`0600` config file.
- Delete and external-symlink access are disabled by default.
- Linux lifecycle uses `systemd --user`; ChatShare does not use `kill`, `pkill`, or an unmanaged background process.

## Shortest workflow

```bash
uv tool install ChatShare
chatshare dufs install
read -rsp "Dufs password: " CHATSHARE_DUFS_PASSWORD && echo
export CHATSHARE_DUFS_PASSWORD
chatshare dufs init
unset CHATSHARE_DUFS_PASSWORD
chatshare dufs service install
chatshare dufs start
chatshare put ./report.pdf reports/report.pdf
```

## Documentation

- [Quick Start](https://arch.gh.wzhecnu.cn/ChatShare/en/quickstart/)
- [CLI Tree](https://arch.gh.wzhecnu.cn/ChatShare/en/cli-tree/)
- [Dufs Runtime](https://arch.gh.wzhecnu.cn/ChatShare/en/dufs/)
- [Security and Boundaries](https://arch.gh.wzhecnu.cn/ChatShare/en/security/)

See [`DEVELOP.md`](DEVELOP.md) and [`AGENTS.md`](AGENTS.md) for development conventions.
