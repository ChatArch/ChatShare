# Changelog

## Unreleased

- 网关转发上游响应头时保留原始字节，修复中文文件名触发响应头编码异常而返回 400 的问题；文件名、目录结构及现有鉴权规则不变。

- 网关目录页新增“从链接下载”：持久任务支持排队、下载、原子提交、完成、失败、取消与重启中断状态，按用户隔离，并显示真实字节、已知/未知总量、速度和安全来源主机。
- 新增可撤销的 256-bit 目录 bearer capability。访客只能只读浏览明确分享的目录及子目录；文件链接继续使用原始 URI，搜索、归档、写入、任务和父目录不可用。
- URL 下载逐跳执行公共 HTTP/HTTPS、DNS 全答案和固定连接地址校验；私有暂存完成后才在同文件系统无覆盖发布。默认并发 2、待处理 20、单文件 20 GiB、连接 5 秒、空闲 30 秒、重定向 5 次。

## 0.2.8

- 新机器的 `put`、`tree`、`url` 在没有本机 Dufs `instance.json` 时自动使用 active ChatEnv `chatshare` profile 中已配置的远端分享服务；远端上传以 1 MiB 分块流式读取，不把文件聚合进内存。
- `chatshare put --progress` 提供终端流式进度；浏览器上传区显示文件名、原生进度条、已传/总量、速度、服务端确认和失败重试状态；网络中断/超时会显示明确原因，窄屏页面将进度条完整保留在视口内。
- 网关保留认证 `PUT`/`PATCH` 的流式写入，不施加上传总时限；上游响应的 I/O 空闲超时为 120 秒，普通元数据和读取请求为 30 秒。
- 新增 `chatshare dufs assets sync`，升级服务端时只同步网页资源；页面在旧版 HTML 下也可创建上传进度表，完整更新需待上传结束后重启 Dufs 和网关。
- 重写中英文 Quick Start，明确区分新机器连接已有服务与服务端部署，涵盖 ChatEnv 鉴权配置、目录查询、大文件行为及 HTTP/WebDAV 边界。

## 0.2.7

- 网关保留无请求体 GET/HEAD 的原始传输语义，不再额外附加空分块请求体，修复并发下载大文件时 Dufs 响应被截断的问题。
- 补充无请求体、显式长度及分块请求体的回归测试；继续支持流式上传，文件权限和浏览器会话鉴权不变。

## 0.2.6

- 网关浏览器登录改用 ChatLogin `AsyncCallbackBackend`、`SessionManager`、`MemorySessionStore`、`require_csrf` 与共享 `LoginUI`，Dufs 仍通过 CHECKAUTH 和原请求 ACL 作为凭据及权限权威。
- `/_chatshare/session` 保持匿名 200，并返回每次会话独有的 `csrf_token`；cookie 写入改用 `X-CSRF-Token`，旧 `X-ChatShare-CSRF: 1` 不再作为替代。
- Dufs Authorization 只保存在服务端私有 relay context 中，并按 ChatLogin session digest 索引；登录替换、登出、过期与上游 401 撤销会同步清理该 context。

## 0.2.5

- 新增 `ChatShare[server]` 可选依赖和 `chatshare serve`，在应用内提供中文登录页、登录/退出接口、限时 HttpOnly 会话与目录权限检查，复用既有 Dufs 账号和实例，不修改 Dufs。
- 匿名访问首页和目录进入登录页；目录 JSON、搜索、WebDAV 枚举、归档及写入需鉴权，已知文件的 GET/HEAD/Range 直链保持公开。
- 保留原生 Basic/Digest 上传客户端及缺失文件空 404 语义；原有 403 权限拒绝不会误撤销有效会话，不放宽删除权限。
- 增加同源 CSRF、Host 与路径校验、登录容量限制、流式资源清理、禁止缓存和主动文件内容沙箱。退出后返回或刷新仍需登录。
- 登录表单显式使用 POST，即使脚本未加载也不会通过 URL 提交凭据；会话模式不再把密码存入浏览器存储。
- 补齐中英文使用说明、CLI 树、打包资源与回归测试；Tag 发布检查只获取默认分支，避免覆盖已检出的注解 Tag。

## 2026-08-29

### Added

- `chatshare put` 支持递归发布本机目录并保留相对路径；新增 `chatshare tree [PREFIX]` 读取已发布分享目录树。
- 准备 `0.2.4`：新增 ChatShare 管理的 Dufs 自定义页面 assets，并在 Dufs config 中写入 `assets:`，让目录页显示右上角文字登录按钮和页面内登录弹窗。
- 网页端上传、新建、移动、保存等写操作改为先通过自定义登录弹窗收集凭据，再由 XHR 显式发送 HTTP Auth header，避免触发浏览器默认认证弹窗。
- 新增醒目的拖拽上传区和“选择文件”按钮，拖拽文件会直接进入上传队列；未登录时先弹 ChatShare 登录框，登录成功后继续上传。

### Fixed

- 修复点击 Home 或重新载入目录后仅显示未登录状态的问题：页面会从 `sessionStorage` 恢复凭据并静默重新校验。
- 退出登录不再调用 Dufs `LOGOUT` 挑战接口，避免点击账号按钮/退出时冒出浏览器默认认证弹窗；顶部登录态改成账号菜单，点击后再选择“退出登录”。

## 2026-08-22

### Changed

- 发布 `0.2.3` patch：移除 package-local Click tree renderer，改用 `chatstyle>=0.2.0,<0.3.0` 的 `add_tree_option()`，并新增真实注册命令面的 `--tree-brief`。
- 将 ChatEnv runtime 下限对齐到 `chatenv>=0.2.10,<0.3.0`，保留 typed `chatshare` profile registration 与 ChatEnv storage paths。
- CLI tree 说明补充读写/服务状态副作用，CI 增加 Python 3.10-3.12、installed console-script、build 与 Twine gates。

## 2026-08-11

### Fixed

- 发布 `0.2.2` hotfix：为 Material 图标卡片启用 `pymdownx.emoji` + Material emoji renderer，避免 MkDocs 生成页面残留 `:material-*:` literal token。
- 增加回归测试：docs 源码只要使用 `:material-*:`，`mkdocs.yml` 必须配置 Material emoji renderer。

## 2026-08-11

### Added

- 新增 runtime `chatshare --tree`，从真实 Click registry 输出 `dufs`、`put`、`url` 命令树，并明确排除隐藏兼容 `hello` 入口。
- 补充测试锁定 `--tree` 与隐藏兼容命令的验收边界。

### Changed

- 发布 `0.2.1` patch，并同步 CLI 树文档到 runtime readback 输出。

## 2026-08-04

### Added

- 设计并实现由 ChatArch 管理的 Dufs CLI：可信 release 安装、安全配置、Linux `systemd --user` 生命周期、本机文件发布与直达 URL。
- 新增 ChatEnv `chatshare` 配置 schema，用于管理 Dufs 写入账号、写入密码和 public base URL。
- 新增中英文快速开始、CLI 树、Dufs 运行时和安全边界文档。
- 快速开始补齐“从分享到获取”的完整示例，说明 `chatshare put` 与 `chatshare url` 的边界，并演示匿名读取与 Digest Auth `PUT`。

### Changed

- Dufs 默认访问模型调整为匿名可读、HTTP/WebDAV PUT 鉴权可写。
- 文档站切换到 ChatArch 公共文档域名、后缀式中英文站点和 PR Preview Docs。


## 2026-06-23

### Added

### Changed

- 准备 `0.1.0` 发版，用于验证 PyPI Trusted Publishing 免 token 发布流程。

- 发布 workflow 改为显式 `v*` tag / `workflow_dispatch` 触发，使用 PyPI Trusted Publishing（`id-token: write` + `environment: pypi`），不再依赖仓库级 PyPI token secret。

### Fixed
