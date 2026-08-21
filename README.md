<div align="center">
    <a href="https://pypi.org/project/ChatShare/"><img src="https://img.shields.io/pypi/v/ChatShare.svg" alt="PyPI 版本" /></a>
    <a href="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml"><img src="https://github.com/ChatArch/ChatShare/actions/workflows/ci.yml/badge.svg" alt="测试状态" /></a>
    <a href="https://arch.gh.wzhecnu.cn/ChatShare/"><img src="https://img.shields.io/badge/docs-MkDocs-blue.svg" alt="文档" /></a>
</div>

<div align="center">[中文版](README.md) | [英文版](README.en.md)</div>

# ChatShare

ChatShare 是 ChatArch 管理的文件分享 CLI。当前后端固定为 [Dufs](https://github.com/sigoden/dufs)，提供可审计的二进制安装、配置、用户级服务生命周期，以及本机文件导入与直达 URL 生成。

## 安全默认值

- Dufs 固定安装到 `~/.chatarch/chatshare/runtimes/dufs/`，不写系统目录。
- 服务只绑定 `127.0.0.1`；公网入口应由独立反向代理任务配置。
- 浏览、下载和内联查看默认匿名可访问；HTTP/WebDAV `PUT` 等写入操作需要 Dufs HTTP Digest Auth。
- 删除和符号链接访问默认关闭。
- Linux 生命周期使用 `systemd --user`，不使用 `kill`、`pkill` 或不受控后台进程。

## 最短流程

```bash
uv tool install ChatShare
chatshare dufs install
chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://share.public.wzhecnu.cn -I
chatenv set CHATSHARE_DUFS_USERNAME=chatshare -I
read -rsp "Dufs writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD
chatshare dufs init
chatshare dufs service install
chatshare dufs start
printf 'hello from ChatShare\n' > hello-share.txt
chatshare put ./hello-share.txt examples/hello-share.txt
chatshare url examples/hello-share.txt
```

运行 `chatshare --tree` 可读取 ChatStyle 从 Click 注册表生成的完整实时命令树；`chatshare --tree-brief` 显示省略参数签名的同一命令面。隐藏兼容入口不会出现在产品树中。

## 文档

- [快速开始](https://arch.gh.wzhecnu.cn/ChatShare/quickstart/)
- [CLI 树](https://arch.gh.wzhecnu.cn/ChatShare/cli-tree/)
- [Dufs 运行时](https://arch.gh.wzhecnu.cn/ChatShare/dufs/)
- [安全与边界](https://arch.gh.wzhecnu.cn/ChatShare/security/)

开发约定见 [`DEVELOP.md`](DEVELOP.md) 与 [`AGENTS.md`](AGENTS.md)。
