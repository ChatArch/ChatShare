# 安全与边界

## 访问矩阵

| 操作 | 当前主体与凭据 |
|---|---|
| 安装、初始化、服务管理 | 登录到主机的 ChatArch 用户 |
| 本机 `put` 与 `url` | 同一 ChatArch 用户；不经过 HTTP |
| 浏览、下载、内联查看 | 匿名客户端；持有 URL 即可读取公开数据 |
| HTTP/WebDAV 上传/PUT | 持有共享 Dufs HTTP Auth 凭据的客户端 |
| HTTP 删除 | 默认不可用 |
| 清理、过期、逐文件撤销 | 当前未实现 |

第一版选择“匿名读 + 共享写入凭据”，而不是逐文件能力链接。URL 本身不是密钥；放到分享根的数据按设计可被匿名下载，写入密码泄露会授予整个部署的上传/覆盖能力。

## 凭据

- 默认 ChatEnv type：`chatshare`，关键字段：`CHATSHARE_DUFS_USERNAME`、`CHATSHARE_DUFS_PASSWORD`、`CHATSHARE_DUFS_BASE_URL`。
- 默认密码变量名：`CHATSHARE_DUFS_PASSWORD`；CLI 接收变量名，不接收密码值参数。
- Dufs 需要在启动时读取账号规则，因此密码会存在于 `config.yaml`；该文件以 `0600` 写入。
- 网页端登录弹窗只把用户输入交给浏览器/XHR 的 HTTP Auth header；不会新增后端会话、cookie 或 token，也不会调用 Dufs `LOGOUT` 挑战接口。
- 密码不得出现在 argv、URL、stdout、JSON、access log、unit 文件、README 或测试 fixture。
- 用户名和密码拒绝 Dufs auth 语法分隔符以及换行，防止规则注入。

## 网络

- `init` 只接受 `127.0.0.1`、`localhost` 或 `::1`。
- `0.0.0.0`、`::` 和 LAN 地址会被拒绝。
- 当前 CLI 不配置 TLS、Nginx、DNS 或公网入口。
- 对外发布应由独立部署任务提供可信 Host、TLS、请求大小/速率限制和回滚；不能把直接监听公网当成完成。

## 文件系统

- ChatArch 管理目录默认 `0700`，凭据与状态文件默认 `0600`。
- `put` 拒绝绝对目标、`.`、`..`、空组件和根目录逃逸。
- 发布使用同文件系统临时文件和原子替换；未指定 `--overwrite` 时拒绝覆盖。
- Dufs 的 `allow-symlink` 与 `allow-delete` 默认关闭。

## 明确不提供

- 分享到期、下载次数和逐文件撤销
- 多用户/账号所有权和审计
- 浏览器会话、OAuth/OIDC 或服务端账号所有权
- S3/object key、CDN 或多节点复制
- 远程主机注册表和集中式编排

需要上述任一能力时，应先扩展产品和状态模型，而不是把它伪装成 Dufs 配置选项。
