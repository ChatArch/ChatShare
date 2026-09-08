<div align="center">
    <a href="https://pypi.org/project/ChatShare/"><img src="https://img.shields.io/pypi/v/ChatShare.svg" alt="PyPI 版本" /></a>
    <a href="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml"><img src="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml/badge.svg" alt="测试状态" /></a>
    <a href="https://arch.gh.wzhecnu.cn/ChatShare/"><img src="https://img.shields.io/badge/docs-MkDocs-blue.svg" alt="文档" /></a>
</div>

<div align="center">[中文版](README.md) | [英文版](README.en.md)</div>

# ChatShare

ChatShare 是 ChatArch 管理的文件分享 CLI。当前后端固定为 [Dufs](https://github.com/sigoden/dufs)，提供可审计的二进制安装、配置、用户级服务生命周期，以及本机文件/目录导入、分享目录树查看与直达 URL 生成。

## 安全默认值

从 `0.2.5` 起，安装 `server` 可选依赖即可使用应用内目录登录系统。登录页、会话和目录权限由 `chatshare serve` 负责；反向代理只转发，不承担鉴权。

```bash
python -m pip install "ChatShare[server]==0.2.5"
chatshare serve --allowed-host proxy.internal
```

网关默认监听 `127.0.0.1:5001`，读取现有实例的 root、Dufs loopback 地址和公网 base URL，不修改 Dufs。仅已知具体文件可匿名 GET/HEAD/Range；根目录、目录、搜索、JSON、归档和写入需要登录/原生鉴权。完整边界见 [安全与边界](docs/security.md)。公网代理切换、TLS 与现场验证由运维单独完成，绕过网关直连 Dufs 不受此门禁保护。

- Dufs 固定安装到 `~/.chatarch/chatshare/runtimes/dufs/`，不写系统目录。
- 服务只绑定 `127.0.0.1`；公网入口应由独立反向代理任务配置。
- 原生 Dufs 仍为匿名可读、鉴权可写；通过网关访问时，匿名只允许已知具体文件，浏览器目录访问使用服务端 cookie 会话。
- 删除和符号链接访问默认关闭。
- Linux 生命周期使用 `systemd --user`，不使用 `kill`、`pkill` 或不受控后台进程。

## 最短流程

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

运行 `chatshare --tree` 可读取 ChatStyle 从 Click 注册表生成的完整实时命令树；`chatshare tree <prefix>` 查看已发布分享目录的实际文件树；`chatshare --tree-brief` 显示省略参数签名的同一命令面。隐藏兼容入口不会出现在产品树中。

## 文档

- [快速开始](https://arch.gh.wzhecnu.cn/ChatShare/quickstart/)
- [CLI 树](https://arch.gh.wzhecnu.cn/ChatShare/cli-tree/)
- [Dufs 运行时](https://arch.gh.wzhecnu.cn/ChatShare/dufs/)
- [安全与边界](https://arch.gh.wzhecnu.cn/ChatShare/security/)

开发约定见 [`DEVELOP.md`](DEVELOP.md) 与 [`AGENTS.md`](AGENTS.md)。
