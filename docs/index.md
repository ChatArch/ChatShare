# ChatShare

ChatShare 把 Dufs 收进 ChatArch 的用户级目录和操作边界中：CLI 负责可信安装、配置、服务生命周期和本机文件发布，Dufs 负责 HTTP/WebDAV 文件服务。

<div class="grid cards" markdown>

-   :material-rocket-launch: **开始使用**

    ---

    从安装 ChatShare、获取 Dufs 到发布第一个文件。

    [进入快速开始](quickstart.md)

-   :material-console: **查看 CLI**

    ---

    按责任查看安装、配置、服务和分享命令。

    [查看 CLI 树](cli-tree.md)

-   :material-package-variant-closed: **理解运行时**

    ---

    查看版本固定、目录布局、systemd 用户服务和升级回滚。

    [查看 Dufs 运行时](dufs.md)

-   :material-shield-lock: **确认安全边界**

    ---

    查看鉴权、loopback 默认、权限和明确不支持的能力。

    [查看安全边界](security.md)

</div>

## 当前能力

| 责任 | ChatShare | Dufs |
|---|---|---|
| 二进制选择与校验 | 根据平台选择 release asset，验证 GitHub `sha256` digest | 提供官方 release asset |
| 配置与状态 | 管理 `~/.chatarch/chatshare/` 下的状态 | 读取生成的 YAML 配置 |
| 服务生命周期 | Linux `systemd --user` | 前台文件服务进程 |
| 文件发布 | 原子复制到受控根目录并生成 URL | 通过 HTTP/WebDAV 提供读取与上传 |
| 鉴权 | 安全采集和保存共享凭据 | HTTP Digest Auth 路径权限 |

## 不在当前范围

ChatShare 当前不提供账号系统、匿名能力链接、过期时间、下载次数、逐文件撤销、对象存储或多主机编排。这些能力不能由 Dufs 的直接路径模型自动推导。
