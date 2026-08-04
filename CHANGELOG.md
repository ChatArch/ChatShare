# Changelog

## 2026-08-04

### Added

- 设计并实现由 ChatArch 管理的 Dufs CLI：可信 release 安装、安全配置、Linux `systemd --user` 生命周期、本机文件发布与直达 URL。
- 新增中英文快速开始、CLI 树、Dufs 运行时和安全边界文档。

### Changed

- 文档站切换到 ChatArch 公共文档域名、后缀式中英文站点和 PR Preview Docs。


## 2026-06-23

### Added

### Changed

- 准备 `0.1.0` 发版，用于验证 PyPI Trusted Publishing 免 token 发布流程。

- 发布 workflow 改为显式 `v*` tag / `workflow_dispatch` 触发，使用 PyPI Trusted Publishing（`id-token: write` + `environment: pypi`），不再依赖仓库级 PyPI token secret。

### Fixed
