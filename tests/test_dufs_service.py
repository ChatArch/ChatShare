from __future__ import annotations

import json
import stat
import subprocess

import pytest

from chatshare.dufs.config import DEFAULT_PASSWORD_ENV, init_instance
from chatshare.dufs.service import (
    UNIT_NAME,
    control_service,
    get_service_status,
    install_service,
    read_access_logs,
    render_service_unit,
)
from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def ready_paths(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    runtime = paths.dufs_runtime("v0.46.0")
    runtime.mkdir(parents=True)
    (runtime / "dufs").write_bytes(b"binary")
    (runtime / "dufs").chmod(0o755)
    (runtime / "install.json").write_text(
        json.dumps(
            {
                "asset": "dufs-v0.46.0-x86_64-unknown-linux-musl.tar.gz",
                "repo": "sigoden/dufs",
                "sha256": "a" * 64,
                "target": "x86_64-unknown-linux-musl",
                "version": "v0.46.0",
            }
        )
    )
    paths.dufs_current.symlink_to("v0.46.0", target_is_directory=True)
    init_instance(paths, environ={DEFAULT_PASSWORD_ENV: "unit-test-secret"})
    return paths


def completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def test_render_service_unit_uses_managed_paths_without_secret(tmp_path):
    paths = ready_paths(tmp_path)

    text = render_service_unit(paths)

    assert "Description=ChatShare Dufs file service" in text
    assert (
        f'ExecStart="{paths.dufs_current_binary}" --config "{paths.config_file}"'
        in text
    )
    assert f'WorkingDirectory="{paths.data_dir.resolve()}"' in text
    assert "Restart=on-failure" in text
    assert "NoNewPrivileges=true" in text
    assert "PrivateTmp=true" in text
    assert "UMask=0077" in text
    assert "WantedBy=default.target" in text
    assert "unit-test-secret" not in text
    assert "kill" not in text.lower()
    assert "pkill" not in text.lower()


def test_install_service_writes_canonical_and_user_units_without_enabling_by_default(
    tmp_path,
):
    paths = ready_paths(tmp_path)
    unit_dir = tmp_path / "systemd" / "user"
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return completed(argv)

    result = install_service(
        paths,
        unit_dir=unit_dir,
        enable=False,
        system="Linux",
        runner=runner,
    )

    live_unit = unit_dir / UNIT_NAME
    assert result == {
        "canonical_unit": str(paths.canonical_unit),
        "enabled": False,
        "unit": str(live_unit),
    }
    assert live_unit.read_text() == paths.canonical_unit.read_text()
    assert mode(live_unit) == 0o644
    assert mode(paths.canonical_unit) == 0o644
    assert [call[0] for call in calls] == [["systemctl", "--user", "daemon-reload"]]


def test_install_service_enables_only_when_explicit(tmp_path):
    paths = ready_paths(tmp_path)
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return completed(argv)

    result = install_service(
        paths,
        unit_dir=tmp_path / "units",
        enable=True,
        system="linux",
        runner=runner,
    )

    assert result["enabled"] is True
    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", UNIT_NAME],
    ]
    assert all("--now" not in call for call in calls)


def test_install_service_requires_linux_and_initialized_runtime(tmp_path):
    paths = ready_paths(tmp_path)
    with pytest.raises(ChatShareError, match="Linux systemd user service"):
        install_service(paths, unit_dir=tmp_path / "units", system="Darwin")

    empty = ChatSharePaths.from_home(tmp_path / "empty")
    with pytest.raises(ChatShareError, match="not installed"):
        install_service(empty, unit_dir=tmp_path / "units2", system="Linux")


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_control_service_uses_only_systemctl_user(action, tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return completed(argv, stdout="ok\n")

    result = control_service(action, system="Linux", runner=runner)

    assert result == {"action": action, "service": UNIT_NAME}
    assert calls[0][0] == ["systemctl", "--user", action, UNIT_NAME]
    flat = " ".join(calls[0][0]).lower()
    assert "kill" not in flat
    assert "pkill" not in flat


def test_control_service_rejects_unknown_action():
    with pytest.raises(ChatShareError, match="Unsupported service action"):
        control_service("remove", system="Linux", runner=lambda *a, **k: None)


def test_service_status_reports_active_and_inactive_as_data(tmp_path):
    paths = ready_paths(tmp_path)
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / UNIT_NAME).write_text("unit")

    active = get_service_status(
        paths,
        unit_dir=unit_dir,
        system="Linux",
        runner=lambda argv, **kwargs: completed(argv, 0, stdout="active\n"),
    )
    assert active["installed"] is True
    assert active["configured"] is True
    assert active["unit_installed"] is True
    assert active["service_supported"] is True
    assert active["active"] is True
    assert active["service_state"] == "active"
    assert active["version"] == "v0.46.0"
    assert active["base_url"] == "http://127.0.0.1:5000"
    assert "unit-test-secret" not in json.dumps(active)

    inactive = get_service_status(
        paths,
        unit_dir=unit_dir,
        system="Linux",
        runner=lambda argv, **kwargs: completed(argv, 3, stdout="inactive\n"),
    )
    assert inactive["active"] is False
    assert inactive["service_state"] == "inactive"


def test_service_status_on_macos_skips_systemctl(tmp_path):
    paths = ready_paths(tmp_path)

    status = get_service_status(
        paths,
        unit_dir=tmp_path / "units",
        system="Darwin",
        runner=lambda *args, **kwargs: pytest.fail("systemctl must not be called"),
    )

    assert status["service_supported"] is False
    assert status["active"] is False
    assert status["service_state"] == "unsupported"


def test_read_access_logs_is_bounded_and_missing_log_is_empty(tmp_path):
    paths = ready_paths(tmp_path)
    assert read_access_logs(paths, lines=2) == {
        "log": str(paths.access_log),
        "lines": [],
    }

    paths.access_log.write_text("one\ntwo\nthree\n")
    assert read_access_logs(paths, lines=2) == {
        "log": str(paths.access_log),
        "lines": ["two", "three"],
    }

    with pytest.raises(ChatShareError, match="between 1 and 10000"):
        read_access_logs(paths, lines=0)
