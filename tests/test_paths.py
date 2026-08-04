from types import SimpleNamespace


def test_explicit_home_builds_chatarch_owned_layout(tmp_path):
    from chatshare.paths import ChatSharePaths

    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    assert paths.chatarch_home == (tmp_path / "chatarch").resolve()
    assert paths.base == paths.chatarch_home / "chatshare"
    assert paths.dufs_runtimes == paths.base / "runtimes" / "dufs"
    assert paths.dufs_runtime("v0.46.0") == paths.dufs_runtimes / "v0.46.0"
    assert paths.dufs_binary("v0.46.0") == paths.dufs_runtime("v0.46.0") / "dufs"
    assert (
        paths.dufs_manifest("v0.46.0") == paths.dufs_runtime("v0.46.0") / "install.json"
    )
    assert paths.dufs_current == paths.dufs_runtimes / "current"
    assert paths.dufs_current_binary == paths.dufs_current / "dufs"
    assert paths.instance_dir == paths.base / "instances" / "default"
    assert paths.config_file == paths.instance_dir / "config.yaml"
    assert paths.state_file == paths.instance_dir / "instance.json"
    assert paths.data_dir == paths.instance_dir / "data"
    assert paths.logs_dir == paths.instance_dir / "logs"
    assert paths.access_log == paths.logs_dir / "access.log"
    assert paths.canonical_unit == paths.base / "services" / "chatshare-dufs.service"


def test_default_home_comes_from_chatenv(monkeypatch, tmp_path):
    import chatshare.paths as paths_module

    expected = tmp_path / "managed-chatarch"
    monkeypatch.setattr(
        paths_module, "get_paths", lambda: SimpleNamespace(home_dir=expected)
    )

    paths = paths_module.ChatSharePaths.from_home()

    assert paths.chatarch_home == expected.resolve()


def test_home_expands_user(monkeypatch, tmp_path):
    from chatshare.paths import ChatSharePaths

    monkeypatch.setenv("HOME", str(tmp_path))

    paths = ChatSharePaths.from_home("~/managed")

    assert paths.chatarch_home == (tmp_path / "managed").resolve()
