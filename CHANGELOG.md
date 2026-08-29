# Changelog

## 2026-08-29

### Added

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
