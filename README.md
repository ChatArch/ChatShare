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
- 读写均要求 Dufs Basic Auth，共享密码只从环境变量读取并写入 `0600` 配置文件。
- 删除和符号链接访问默认关闭。
- Linux 生命周期使用 `systemd --user`，不使用 `kill`、`pkill` 或不受控后台进程。

## 最短流程

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

## 文档

- [快速开始](https://arch.gh.wzhecnu.cn/ChatShare/quickstart/)
- [CLI 树](https://arch.gh.wzhecnu.cn/ChatShare/cli-tree/)
- [Dufs 运行时](https://arch.gh.wzhecnu.cn/ChatShare/dufs/)
- [安全与边界](https://arch.gh.wzhecnu.cn/ChatShare/security/)

开发约定见 [`DEVELOP.md`](DEVELOP.md) 与 [`AGENTS.md`](AGENTS.md)。
