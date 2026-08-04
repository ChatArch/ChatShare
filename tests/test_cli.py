from __future__ import annotations

import json

from click.testing import CliRunner

from chatshare.cli import main
from chatshare.errors import ChatShareError


def invoke(args, **kwargs):
    return CliRunner().invoke(main, args, **kwargs)


def test_help_exposes_real_product_tree_and_hides_legacy_hello():
    result = invoke(["--help"])

    assert result.exit_code == 0, result.output
    assert "dufs" in result.output
    assert "put" in result.output
    assert "url" in result.output
    assert "--home" in result.output
    assert "--json" in result.output
    assert "hello" not in result.output


def test_dufs_help_exposes_documented_command_tree():
    result = invoke(["dufs", "--help"])

    assert result.exit_code == 0, result.output
    for command in [
        "install",
        "init",
        "service",
        "start",
        "stop",
        "restart",
        "status",
        "logs",
    ]:
        assert command in result.output

    service = invoke(["dufs", "service", "--help"])
    assert service.exit_code == 0, service.output
    assert "install" in service.output


def test_version_and_hidden_hello_compatibility():
    version = invoke(["--version"])
    assert version.exit_code == 0
    assert "0.2.0" in version.output

    hello = invoke(["hello", "Alice", "-I"])
    assert hello.exit_code == 0
    assert "Hello, Alice!" in hello.output


def test_install_command_passes_explicit_contract_and_renders_json(
    monkeypatch, tmp_path
):
    from chatshare.dufs import release

    calls = []

    def fake_install(paths, **kwargs):
        calls.append((paths, kwargs))
        return {"binary": "/managed/dufs", "reused": False, "version": "v0.46.0"}

    monkeypatch.setattr(release, "install_dufs", fake_install)

    result = invoke(
        [
            "--home",
            str(tmp_path / "chatarch"),
            "--json",
            "dufs",
            "install",
            "--version",
            "0.46.0",
            "--platform",
            "x86_64-unknown-linux-musl",
            "--force",
        ]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "binary": "/managed/dufs",
        "reused": False,
        "version": "v0.46.0",
    }
    paths, kwargs = calls[0]
    assert paths.chatarch_home == (tmp_path / "chatarch").resolve()
    assert kwargs == {
        "force": True,
        "target": "x86_64-unknown-linux-musl",
        "version": "0.46.0",
    }


def test_init_command_maps_options_without_password_value(monkeypatch, tmp_path):
    from chatshare.dufs import config

    calls = []

    def fake_init(paths, **kwargs):
        calls.append((paths, kwargs))
        return {"config": "/managed/config.yaml", "username": kwargs["username"]}

    monkeypatch.setattr(config, "init_instance", fake_init)
    result = invoke(
        [
            "--home",
            str(tmp_path / "chatarch"),
            "--json",
            "dufs",
            "init",
            "--root",
            str(tmp_path / "data"),
            "--bind",
            "localhost",
            "--port",
            "7443",
            "--base-url",
            "https://share.example.test",
            "--username",
            "operator",
            "--password-env",
            "CUSTOM_SECRET",
            "--force",
        ]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["username"] == "operator"
    _, kwargs = calls[0]
    assert kwargs == {
        "base_url": "https://share.example.test",
        "bind": "localhost",
        "force": True,
        "password_env": "CUSTOM_SECRET",
        "port": 7443,
        "root": tmp_path / "data",
        "username": "operator",
    }
    assert "password" not in result.output.lower()


def test_actual_init_does_not_emit_secret(monkeypatch, tmp_path):
    auth_value = "[REDACTED]"
    result = invoke(
        ["--home", str(tmp_path / "chatarch"), "--json", "dufs", "init"],
        env={"CHATSHARE_DUFS_PASSWORD": auth_value},
    )

    assert result.exit_code == 0, result.output
    assert auth_value not in result.output
    payload = json.loads(result.output)
    assert payload["config"].endswith("config.yaml")


def test_service_install_and_control_commands_delegate(monkeypatch, tmp_path):
    from chatshare.dufs import service

    install_calls = []
    control_calls = []
    monkeypatch.setattr(
        service,
        "install_service",
        lambda paths, **kwargs: (
            install_calls.append((paths, kwargs))
            or {"unit": "/managed/service", "enabled": kwargs["enable"]}
        ),
    )
    monkeypatch.setattr(
        service,
        "control_service",
        lambda action: (
            control_calls.append(action)
            or {"action": action, "service": service.UNIT_NAME}
        ),
    )

    installed = invoke(
        [
            "--home",
            str(tmp_path / "chatarch"),
            "--json",
            "dufs",
            "service",
            "install",
            "--enable",
        ]
    )
    assert installed.exit_code == 0, installed.output
    assert json.loads(installed.output)["enabled"] is True
    assert install_calls[0][1] == {"enable": True}

    for action in ["start", "stop", "restart"]:
        result = invoke(["--json", "dufs", action])
        assert result.exit_code == 0, result.output
    assert control_calls == ["start", "stop", "restart"]


def test_status_and_logs_commands_delegate(monkeypatch, tmp_path):
    from chatshare.dufs import service

    monkeypatch.setattr(
        service,
        "get_service_status",
        lambda paths: {"active": False, "service_state": "inactive"},
    )
    monkeypatch.setattr(
        service,
        "read_access_logs",
        lambda paths, **kwargs: {"log": "/managed/access.log", "lines": ["one", "two"]},
    )

    status = invoke(["--home", str(tmp_path / "home"), "--json", "dufs", "status"])
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["service_state"] == "inactive"

    logs = invoke(["--home", str(tmp_path / "home"), "dufs", "logs", "--lines", "2"])
    assert logs.exit_code == 0, logs.output
    assert logs.output.splitlines() == ["one", "two"]


def test_put_and_url_commands_delegate(monkeypatch, tmp_path):
    from chatshare import sharing

    put_calls = []
    url_calls = []
    source = tmp_path / "source.txt"
    source.write_text("data")
    monkeypatch.setattr(
        sharing,
        "publish_file",
        lambda paths, source, destination, **kwargs: (
            put_calls.append((paths, source, destination, kwargs))
            or {"path": destination, "url": "https://share.test/item"}
        ),
    )
    monkeypatch.setattr(
        sharing,
        "build_file_url",
        lambda paths, relative: (
            url_calls.append((paths, relative))
            or {"path": relative, "url": "https://share.test/item"}
        ),
    )

    put = invoke(
        [
            "--home",
            str(tmp_path / "home"),
            "--json",
            "put",
            str(source),
            "nested/item.txt",
            "--overwrite",
        ]
    )
    assert put.exit_code == 0, put.output
    assert json.loads(put.output)["path"] == "nested/item.txt"
    assert put_calls[0][1:] == (source, "nested/item.txt", {"overwrite": True})

    url = invoke(["--home", str(tmp_path / "home"), "--json", "url", "nested/item.txt"])
    assert url.exit_code == 0, url.output
    assert json.loads(url.output)["url"] == "https://share.test/item"
    assert url_calls[0][1] == "nested/item.txt"


def test_domain_error_becomes_click_error_without_traceback(monkeypatch):
    from chatshare.dufs import release

    monkeypatch.setattr(
        release,
        "install_dufs",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ChatShareError("trusted failure")
        ),
    )

    result = invoke(["dufs", "install"])

    assert result.exit_code == 1
    assert "Error: trusted failure" in result.output
    assert "Traceback" not in result.output
