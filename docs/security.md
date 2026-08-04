# 安全与边界

## 访问矩阵

| 操作 | 当前主体与凭据 |
|---|---|
| 安装、初始化、服务管理 | 登录到主机的 ChatArch 用户 |
| 本机 `put` 与 `url` | 同一 ChatArch 用户；不经过 HTTP |
| 浏览、下载、内联查看 | 持有共享 Dufs Basic Auth 的客户端 |
| HTTP/WebDAV 上传 | 持有共享 Dufs Basic Auth 的客户端 |
| HTTP 删除 | 默认不可用 |
| 清理、过期、逐文件撤销 | 当前未实现 |

第一版选择“读写共用一个凭据”，而不是匿名能力链接。URL 本身不是授权凭据；泄露 URL 不足以访问文件，但共享密码泄露会授予整个部署的读写权。

## 凭据

- 默认密码变量名：`CHATSHARE_DUFS_PASSWORD`。
- CLI 接收变量名，不接收密码值参数。
- Dufs 需要在启动时读取账号规则，因此密码会存在于 `config.yaml`；该文件以 `0600` 写入。
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

- 匿名链接或 URL bearer token
- 分享到期、下载次数和逐文件撤销
- 多用户/账号所有权和审计
- 浏览器会话、OAuth/OIDC
- S3/object key、CDN 或多节点复制
- 远程主机注册表和集中式编排

需要上述任一能力时，应先扩展产品和状态模型，而不是把它伪装成 Dufs 配置选项。
