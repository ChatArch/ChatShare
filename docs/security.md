# 安全与边界

## 访问矩阵

| 操作 | 当前主体与凭据 |
|---|---|
| 安装、初始化、服务管理 | 登录到主机的 ChatArch 用户 |
| 本机 `put` 与 `url` | 同一 ChatArch 用户；不经过 HTTP |
| 已知具体文件 GET/HEAD/Range | 匿名客户端；保留跨站 PNG 嵌入 |
| 目录 HTML/JSON、搜索、WebDAV 枚举、归档 | 网关浏览器会话或 Dufs 原生 Basic/Digest |
| HTTP/WebDAV 上传/PUT | 持有共享 Dufs HTTP Auth 凭据的客户端 |
| HTTP 删除 | 默认不可用 |
| 清理、过期、逐文件撤销 | 当前未实现 |

该矩阵只适用于 `chatshare serve`。直连 Dufs 仍保留原生匿名读权限，不能暴露绕过网关的入口。文件 URL 不是密钥；目录门禁不防止猜测文件名，也不提供逐文件撤销。Dufs 现有账号权限及 `allow-delete: false` 始终保留。

## 凭据

- 默认 ChatEnv type：`chatshare`，关键字段：`CHATSHARE_DUFS_USERNAME`、`CHATSHARE_DUFS_PASSWORD`、`CHATSHARE_DUFS_BASE_URL`。
- 默认密码变量名：`CHATSHARE_DUFS_PASSWORD`；CLI 接收变量名，不接收密码值参数。
- Dufs 需要在启动时读取账号规则，因此密码会存在于 `config.yaml`；该文件以 `0600` 写入。
- 网关登录通过 numeric loopback 上的 Dufs 原生 CHECKAUTH + Basic 验证凭据。浏览器只获得随机 HttpOnly、SameSite=Strict、Path=/ 会话 cookie；公网 base URL 为 HTTPS 时设置 Secure。鉴权材料仅短暂保留于服务端内存，不写入文件、不建立第二套账号数据库。
- 每次 cookie 授权请求重新验证 Dufs；登出、过期及密码拒绝都会撤销会话。密码轮换在原有 Dufs 进程识别新密码后生效；网关重启使全部会话失效。原生 Basic/Digest 按原请求转发验证，不把 Digest 重放成其他方法或 URI。
- 上游 403 表示权限不足，不代表退出登录；只有转发了该会话凭据的请求收到 401 时，代理才撤销会话。匿名具体文件/token 请求失败不影响独立的浏览器会话。既有禁止删除规则继续生效，UI 显示权限错误而不强制登出。
- 网关 JS 只清除旧 `chatshare.dufs.credentials`，不把新密码写入 DOM/storage。非网关 Dufs UI 保留旧兼容行为和旧浏览器凭据存储，不能替代服务端门禁。
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
- OAuth/OIDC、持久浏览器会话或服务端账号所有权
- S3/object key、CDN 或多节点复制
- 远程主机注册表和集中式编排

需要上述任一能力时，应先扩展产品和状态模型，而不是把它伪装成 Dufs 配置选项。

## 网关运行与限制

安装 `ChatShare[server]==0.2.5`。登录系统由应用自身实现，Nginx 等反向代理只转发，不需要 `auth_basic` 或 `auth_request`。`chatshare serve` 前台监听 `127.0.0.1:5001`，支持 `--bind ::1`、`--port` 和重复 `--allowed-host proxy.internal`。可导入 `create_app(ChatSharePaths.from_home())` 创建 ASGI 应用。非 server CLI 不导入 FastAPI/httpx/uvicorn。root、端口及公网 origin 来自已有实例状态；不添加平行 endpoint/password 环境变量，公网 URL 必须是无子路径的 HTTP(S) origin。

- 单进程/单 worker；默认会话绝对 TTL 3600 秒、最多 256 个会话、全局滚动 60 秒最多 30 次登录、最多 64 个在途请求。登录 JSON 上限 4096 字节、用户名 128 字符、密码 1024 字符，读取超时 10 秒；上游连接超时 5 秒、I/O 超时 30 秒。容量不足返回 429/503。全局限速可能影响其他用户，应由外部代理增加客户端限速。
- Host 只接受公网 hostname、loopback 与显式 allowed-host；不信任 forwarded headers，不启用 CORS。代理必须保留配置的公网 Origin；登录/登出和 cookie 写入必须带该 Origin 与 `X-ChatShare-CSRF: 1`，拒绝 null/foreign origin 和跨站 Fetch Metadata。原生显式鉴权客户端不需要此 header。
- 匿名仅允许 managed root 内普通文件及 `raw`、`download`、`cache`、`token` 查询键；token 不能获取目录权限。保守拒绝不合法/歧义百分号编码、控制字符、反斜杠、路径穿越、重复分隔符和 symlink 逃逸，包括双重编码和文件名中的字面百分号。
- 缺失文件例外：通过严格路径、编码及 root 校验后，无显式 Authorization 的 GET/HEAD 若路径不存在、无尾部斜杠，且没有查询或仅含 `raw`、`download`、`cache` 查询键，则在本地返回空正文、no-store 的 404，不请求 Dufs、不返回目录数据。这保留上传客户端匿名检查目标是否存在的行为。已有目录（包括带点且无尾部斜杠的目录）、根目录、元数据/搜索/归档、token 查询及写入仍受门禁保护；无效显式鉴权不能降级到该 404。
- 匿名 200/206 必须携带 Dufs 真实文件 Content-Disposition，分类后替换为目录时无 marker 则在发送任何正文前拒绝。304/404/416 不转发上游正文。文件/归档/上传不整体缓冲；响应以 64 KiB 块流式转发，只有已授权 Dufs 管理 HTML 可缓冲，最多 2 MiB，未知 HTML contract 返回 502。不自动重定向或重试。
- 管理 HTML 必须包含 Dufs `index-data` 模板和 `/__dufs_v<version>__/` 版本化 assets contract；网关注入明确 marker 并改用包内 JS/CSS/favicon，不修改安装中的 Dufs assets。公开资源例外只限网关自有端点和 assets，不按用户文件后缀放行。
- 所有响应 no-store，Vary 包含 Cookie/Authorization。原始文件响应加 CSP `sandbox allow-scripts allow-downloads`，不含 `allow-same-origin`，阻止上传的主动内容读取登录态目录 API，仍允许 PNG 嵌入；部分主动内容预览会受限。可信管理页使用独立限制性 CSP，不加文件 sandbox。页面退出隐藏快照，恢复时重新载入。
- `serve` 不安装后台服务、不改代理或账号，也不记录凭据。生产部署使用正常服务监督器，切换前验证目标 Dufs 模板、登录/退出、上传客户端、代理/TLS、Range/哈希与回滚。自动化单元测试采用临时目录和模拟上游，不能替代目标部署的真实验收。
