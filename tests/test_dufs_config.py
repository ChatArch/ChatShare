from __future__ import annotations

import json
import stat

import pytest

from chatshare.dufs.config import (
    DEFAULT_PASSWORD_ENV,
    init_instance,
    load_instance_state,
)
from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_init_instance_writes_secure_config_and_non_secret_state(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    auth_value = "[REDACTED]"

    result = init_instance(paths, environ={DEFAULT_PASSWORD_ENV: auth_value})

    assert result == {
        "backend": "dufs",
        "base_url": "http://127.0.0.1:5000",
        "bind": "127.0.0.1",
        "config": str(paths.config_file),
        "instance": "default",
        "port": 5000,
        "root": str(paths.data_dir.resolve()),
        "state": str(paths.state_file),
        "username": "chatshare",
    }
    config_text = paths.config_file.read_text()
    assert f"auth:\n  - 'chatshare:{auth_value}@/:rw'" in config_text
    assert "  - '@/'" in config_text
    assert config_text.index("'chatshare:") < config_text.index("'@/'")
    assert "bind: '127.0.0.1'" in config_text
    assert "allow-upload: true" in config_text
    assert "allow-delete: false" in config_text
    assert "allow-symlink: false" in config_text
    assert "enable-cors: false" in config_text
    assert f"assets: '{paths.dufs_assets_dir}'" in config_text
    assert str(paths.access_log) in config_text
    for name in ("favicon.ico", "index.css", "index.html", "index.js"):
        assert (paths.dufs_assets_dir / name).is_file()

    state_text = paths.state_file.read_text()
    assert auth_value not in state_text
    state_payload = json.loads(state_text)
    assert state_payload["schema_version"] == 1
    assert state_payload["backend"] == "dufs"
    assert state_payload["config"] == str(paths.config_file)
    assert state_payload["access_log"] == str(paths.access_log)

    assert mode(paths.instance_dir) == 0o700
    assert mode(paths.data_dir) == 0o700
    assert mode(paths.dufs_assets_dir) == 0o700
    assert mode(paths.logs_dir) == 0o700
    assert mode(paths.config_file) == 0o600
    assert mode(paths.state_file) == 0o600


def test_load_instance_state_round_trips_types(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    init_instance(paths, environ={DEFAULT_PASSWORD_ENV: "secret-value"})

    state = load_instance_state(paths)

    assert state.root == paths.data_dir.resolve()
    assert state.config == paths.config_file
    assert state.access_log == paths.access_log
    assert state.port == 5000
    assert state.base_url == "http://127.0.0.1:5000"
    assert "secret-value" not in repr(state)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("instance", "other"),
        ("root", ["not", "a", "path"]),
        ("bind", "0.0.0.0"),
        ("port", True),
        ("port", "5000"),
        ("port", 0),
        ("base_url", "https://user:pass@example.test"),
        ("username", ["not", "a", "string"]),
        ("config", "/unexpected/config.yaml"),
        ("access_log", "/unexpected/access.log"),
    ],
)
def test_load_instance_state_rejects_wrong_field_shapes(field, value, tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    init_instance(paths, environ={DEFAULT_PASSWORD_ENV: "safe-value"})
    payload = json.loads(paths.state_file.read_text())
    payload[field] = value
    paths.state_file.write_text(json.dumps(payload))

    with pytest.raises(ChatShareError):
        load_instance_state(paths)


@pytest.mark.parametrize("payload", [[], "value", 1, None])
def test_load_instance_state_rejects_non_object_json(payload, tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    paths.instance_dir.mkdir(parents=True)
    paths.state_file.write_text(json.dumps(payload))

    with pytest.raises(ChatShareError, match="Unsupported"):
        load_instance_state(paths)


def test_init_uses_custom_root_base_url_and_password_env(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    root = tmp_path / "large disk" / "shared"

    result = init_instance(
        paths,
        root=root,
        port=7443,
        base_url="https://share.example.test/files/",
        username="operator",
        password_env="CUSTOM_DUFS_SECRET",
        environ={"CUSTOM_DUFS_SECRET": "password-with-'quote"},
    )

    assert result["root"] == str(root.resolve())
    assert result["base_url"] == "https://share.example.test/files"
    config_text = paths.config_file.read_text()
    assert "'operator:password-with-''quote@/:rw'" in config_text
    assert mode(root) == 0o700


@pytest.mark.parametrize(
    "bind", ["0.0.0.0", "::", "192.168.1.2", "10.0.0.7", "example.test"]
)
def test_init_rejects_non_loopback_bind(bind, tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    with pytest.raises(ChatShareError, match="loopback"):
        init_instance(paths, bind=bind, environ={DEFAULT_PASSWORD_ENV: "safe-value"})


@pytest.mark.parametrize("bind", ["127.0.0.1", "localhost", "::1"])
def test_init_accepts_loopback_bind(bind, tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / bind.replace(":", "_"))

    result = init_instance(
        paths, bind=bind, environ={DEFAULT_PASSWORD_ENV: "safe-value"}
    )

    assert result["bind"] == bind
    if bind == "::1":
        assert result["base_url"] == "http://[::1]:5000"


@pytest.mark.parametrize("port", [True, 0, -1, 65536, 100000])
def test_init_rejects_invalid_port(port, tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    with pytest.raises(ChatShareError, match="port"):
        init_instance(paths, port=port, environ={DEFAULT_PASSWORD_ENV: "safe-value"})


def test_init_rejects_non_string_bind_with_clean_domain_error(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    with pytest.raises(ChatShareError, match="bind"):
        init_instance(
            paths,
            bind=["127.0.0.1"],  # type: ignore[arg-type]
            environ={DEFAULT_PASSWORD_ENV: "safe-value"},
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://share.example.test",
        "https://user:pass@share.example.test",
        "https://share.example.test/?token=secret",
        "https://share.example.test/#fragment",
        "not-a-url",
    ],
)
def test_init_rejects_unsafe_base_url(base_url, tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    with pytest.raises(ChatShareError, match="base URL"):
        init_instance(
            paths, base_url=base_url, environ={DEFAULT_PASSWORD_ENV: "safe-value"}
        )


def test_init_requires_nonempty_password_environment_variable(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    with pytest.raises(ChatShareError, match=DEFAULT_PASSWORD_ENV):
        init_instance(paths, environ={})
    with pytest.raises(ChatShareError, match=DEFAULT_PASSWORD_ENV):
        init_instance(paths, environ={DEFAULT_PASSWORD_ENV: ""})


def test_init_rejects_invalid_password_environment_variable_name(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    with pytest.raises(ChatShareError, match="environment variable name"):
        init_instance(
            paths,
            password_env="BAD\nNAME",
            environ={"BAD\nNAME": "safe-value"},
        )


def test_init_allows_email_style_writer_username(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    result = init_instance(
        paths,
        username="writer@example.test",
        environ={DEFAULT_PASSWORD_ENV: "safe-value"},
    )

    assert result["username"] == "writer@example.test"
    assert "'writer@example.test:safe-value@/:rw'" in paths.config_file.read_text()


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("bad:name", "safe-value"),
        ("bad@/name", "safe-value"),
        ("bad,name", "safe-value"),
        ("bad\nname", "safe-value"),
        ("chatshare", "bad:value"),
        ("chatshare", "bad@/value"),
        ("chatshare", "bad,value"),
        ("chatshare", "bad\nvalue"),
    ],
)
def test_init_rejects_auth_rule_injection(username, password, tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    with pytest.raises(ChatShareError, match="auth-rule"):
        init_instance(
            paths,
            username=username,
            environ={DEFAULT_PASSWORD_ENV: password},
        )


def test_init_refuses_existing_config_without_force_and_force_replaces_it(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    init_instance(paths, environ={DEFAULT_PASSWORD_ENV: "first-secret"})

    with pytest.raises(ChatShareError, match="already exists"):
        init_instance(paths, environ={DEFAULT_PASSWORD_ENV: "second-secret"})
    assert "first-secret" in paths.config_file.read_text()
    assert "second-secret" not in paths.config_file.read_text()

    init_instance(paths, force=True, environ={DEFAULT_PASSWORD_ENV: "second-secret"})
    assert "first-secret" not in paths.config_file.read_text()
    assert "second-secret" in paths.config_file.read_text()
