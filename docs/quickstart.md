# 快速开始

## 选择入口

<div class="grid cards" markdown>

-   **安装工具与运行时**

    使用现有 ChatArch Python 工具环境安装 ChatShare，再由 ChatShare 安装固定版本 Dufs。

-   **初始化安全配置**

    通过环境变量输入共享密码，生成 loopback-only、禁止删除的 Dufs 配置。

-   **启动服务**

    Linux 使用 `systemd --user`；不创建系统级 unit，也不启动裸后台进程。

-   **发布文件**

    `chatshare put` 将本机文件原子复制到分享根目录并返回直达 URL。

</div>

## 安装

正式版本使用现有 ChatArch Python 包流程：

```bash
uv tool install ChatShare
chatshare --version
```

评审尚未发布的提交时，固定到已审查的 Git ref：

```bash
uv tool install --from "git+https://github.com/ChatArch/ChatShare.git@<reviewed-ref>" ChatShare
```

安装 Dufs。默认固定到 ChatShare 验证过的 `v0.46.0`，不会静默追随 `latest`：

```bash
chatshare dufs install
```

## 初始化

不要把密码放进 CLI 参数。默认从 `CHATSHARE_DUFS_PASSWORD` 读取：

```bash
read -rsp "Dufs password: " CHATSHARE_DUFS_PASSWORD && echo
export CHATSHARE_DUFS_PASSWORD
chatshare dufs init
unset CHATSHARE_DUFS_PASSWORD
```

默认结果：

- 根目录：`~/.chatarch/chatshare/instances/default/data/`
- 配置：`~/.chatarch/chatshare/instances/default/config.yaml`
- 监听：`127.0.0.1:5000`
- 账号：`chatshare`
- 读取、上传、搜索、归档和哈希可用
- 删除、CORS、外部符号链接和匿名读取关闭

## 安装用户服务并启动

```bash
chatshare dufs service install
chatshare dufs start
chatshare dufs status
```

如需登录后自动启动，显式启用：

```bash
chatshare dufs service install --enable
```

`start`、`stop`、`restart` 都委托给 `systemctl --user`。macOS 可以执行安装、初始化和文件发布，但当前不提供 launchd 生命周期命令。

## 发布与取回 URL

```bash
chatshare put ./report.pdf reports/2026/report.pdf
chatshare url reports/2026/report.pdf
```

目标必须是根目录内的相对路径；绝对路径和 `..` 会被拒绝。返回 URL 不包含账号或密码，访问时由 Dufs HTTP Digest Auth 完成鉴权。

## 自动化输出

把全局 `--json` 放在子命令前：

```bash
chatshare --json dufs status
chatshare --json put ./report.pdf reports/report.pdf
```
