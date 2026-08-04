# CLI 树

## 顶层命令

```text
chatshare [--home PATH] [--json] [--version]
├── dufs                 # Dufs 运行时、配置与用户服务
├── put SOURCE [DEST]    # 把本机文件发布到分享根目录
└── url PATH             # 为已有相对路径生成直达 URL
```

`--home` 表示 ChatArch home，默认来自 ChatEnv，通常为 `~/.chatarch`。`--json` 对当前调用启用结构化输出。

## Dufs 运行时

```text
chatshare dufs
├── install
│   ├── --version VERSION    # 默认 v0.46.0，不接受隐式 latest
│   ├── --platform TARGET    # 测试/交叉安装时显式覆盖
│   └── --force              # 原子替换同版本二进制
├── init
│   ├── --root PATH          # 默认 ChatArch 内部 data 目录
│   ├── --bind HOST          # 仅接受 loopback
│   ├── --port PORT          # 默认 5000
│   ├── --base-url URL       # 生成分享 URL 的公开基址
│   ├── --username NAME      # 写入账号；可来自 ChatEnv，默认 chatshare
│   ├── --password-env NAME  # 默认 CHATSHARE_DUFS_PASSWORD
│   └── --force              # 覆盖现有配置
├── service
│   └── install [--enable]   # 安装 Linux systemd 用户 unit
├── start                    # systemctl --user start
├── stop                     # systemctl --user stop
├── restart                  # systemctl --user restart
├── status                   # 汇总运行时、配置、unit 与 active 状态
└── logs [--lines N]         # 读取受控 access log 末尾
```

## 文件发布

```text
chatshare put SOURCE [DESTINATION]
└── --overwrite          # 显式允许原子替换已有文件

chatshare url PATH
```

`DESTINATION` 和 `PATH` 使用 POSIX 风格相对路径。命令拒绝绝对路径、空组件、`.`、`..` 以及解析后越出根目录的目标。

## 接口约定

- CLI 只负责参数解析和输出；安装、配置、服务与文件操作均有可导入 Python API。
- 破坏性覆盖必须显式使用 `--force` 或 `--overwrite`。
- 密码只通过环境变量名传入；不提供 `--password VALUE`。
- 当前只有一个 `default` 实例，不提供多实例或远程主机注册表。
- 旧版 `hello` 命令仅保留为隐藏兼容入口，不属于产品命令树。
