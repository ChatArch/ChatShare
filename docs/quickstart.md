# 快速开始

## 选择入口

<div class="grid cards" markdown>

-   **安装工具与运行时**

    使用现有 ChatArch Python 工具环境安装 ChatShare，再由 ChatShare 安装固定版本 Dufs。

-   **初始化安全配置**

    通过 ChatEnv 管理写入凭据，生成 loopback-only、匿名可读、鉴权可写、禁止删除的 Dufs 配置。

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

不要把密码放进 CLI 参数。服务部署时优先把写入凭据放进 ChatEnv active `chatshare` profile；ChatShare 会从 ChatEnv 读取 `CHATSHARE_DUFS_USERNAME`、`CHATSHARE_DUFS_PASSWORD` 和 `CHATSHARE_DUFS_BASE_URL`：

```bash
chatenv init -t chatshare -I
chatenv set CHATSHARE_DUFS_BASE_URL=https://share.public.wzhecnu.cn -I
chatenv set CHATSHARE_DUFS_USERNAME=chatshare -I
read -rsp "Dufs writer password: " CHATSHARE_DUFS_PASSWORD && echo
printf 'CHATSHARE_DUFS_PASSWORD=%s\n' "$CHATSHARE_DUFS_PASSWORD" | chatenv paste --stdin -y -I
unset CHATSHARE_DUFS_PASSWORD
chatshare dufs init
```

默认结果：

- 根目录：`~/.chatarch/chatshare/instances/default/data/`
- 配置：`~/.chatarch/chatshare/instances/default/config.yaml`
- 监听：`127.0.0.1:5000`
- 写入账号：ChatEnv 中的 `CHATSHARE_DUFS_USERNAME`，默认 `chatshare`
- 匿名浏览、下载、内联查看、搜索、归档和哈希可用
- HTTP/WebDAV 上传/PUT 需要 Dufs HTTP Digest Auth
- 删除、CORS 和外部符号链接关闭

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

目标必须是根目录内的相对路径；绝对路径和 `..` 会被拒绝。返回 URL 不包含账号或密码；数据读取是匿名的，HTTP/WebDAV `PUT` 使用 Dufs HTTP Digest Auth。

## 自动化输出

把全局 `--json` 放在子命令前：

```bash
chatshare --json dufs status
chatshare --json put ./report.pdf reports/report.pdf
```
