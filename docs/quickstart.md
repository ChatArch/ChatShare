# 快速开始

## 选择入口

<div class="grid cards" markdown>

-   **安装工具与运行时**

    使用现有 ChatArch Python 工具环境安装 ChatShare，再由 ChatShare 安装固定版本 Dufs。

-   **初始化安全配置**

    通过 ChatEnv 管理写入凭据，生成 loopback-only、匿名可读、鉴权可写、禁止删除的 Dufs 配置。

-   **启动服务**

    Linux 使用 `systemd --user`；不创建系统级 unit，也不启动裸后台进程。

-   **从分享，到获取**

    `chatshare put` 发布本机文件，`chatshare url` 重新取回已发布文件的公网链接，匿名 `curl` 或浏览器即可下载。

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
- HTTP/WebDAV 上传或 `PUT` 需要 Dufs HTTP Digest Auth；网页端会显示 ChatShare 登录弹窗，不再直接依赖浏览器默认认证弹窗
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

## 完整示例：从分享，到获取

下面的示例演示一个完整闭环：准备文件、发布、重新取链接、匿名下载验证。

```bash
# 1. 准备一个本机文件。
printf 'hello from ChatShare\n' > hello-share.txt

# 2. 发布到托管分享根目录下的相对路径。
#    这一步是本机 operator 动作：把文件原子复制到 ~/.chatarch/chatshare/.../data/。
chatshare --json put ./hello-share.txt examples/hello-share.txt

# 3. 之后如果只知道分享内路径，可以重新取回公网链接。
chatshare --json url examples/hello-share.txt

# 4. 匿名访问这个公网链接，不需要账号密码。
curl -fsSL https://share.public.wzhecnu.cn/examples/hello-share.txt
```

`chatshare put` 和 `chatshare url` 的区别：

| 命令 | 做什么 | 是否上传文件 |
| --- | --- | --- |
| `chatshare put SOURCE [DEST]` | 把本机文件复制到托管分享根目录，并返回 `DEST` 的链接 | 是 |
| `chatshare url DEST` | 检查 `DEST` 已经在托管分享根目录中存在，然后按 `CHATSHARE_DUFS_BASE_URL` 生成链接 | 否 |

因此，`chatshare url` 适合这些场景：

- 文件已经由 `chatshare put` 发布过，想重新打印链接；
- 文件是由别的受控流程直接放进托管 `data/` 目录的，想为它生成链接；
- 脚本需要用稳定的相对路径换成公网链接。

它不会复制、上传或创建文件；如果目标文件不存在，会直接报错。

## 完整示例：HTTP PUT 需要鉴权

网页浏览和下载是匿名的，但网络侧 HTTP/WebDAV `PUT` 必须带 Dufs HTTP Digest Auth。下面示例只把 secret 放在 ChatEnv 和临时 curl config 中，不放在命令行参数、URL 或日志里：

```bash
base_url="$(chatenv get CHATSHARE_DUFS_BASE_URL)"
writer_user="$(chatenv get CHATSHARE_DUFS_USERNAME)"
writer_password="$(chatenv get CHATSHARE_DUFS_PASSWORD)"

printf 'hello through authenticated HTTP PUT\n' > hello-http-put.txt

# 匿名 PUT 应返回 401。
curl -sS -o /dev/null -w '%{http_code}\n' \
  -T ./hello-http-put.txt \
  "${base_url%/}/hello-http-put.txt"

# 鉴权 PUT 使用 Digest Auth；secret 不进入 argv。
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

如果你只是在服务所在机器上发布文件，优先用 `chatshare put`；如果外部客户端需要通过网络写入，才使用 HTTP/WebDAV `PUT` + Digest Auth。

## 自动化输出

把全局 `--json` 放在子命令前：

```bash
chatshare --json dufs status
chatshare --json put ./report.pdf reports/report.pdf
chatshare --json url reports/report.pdf
```
