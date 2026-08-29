"""Linux systemd user-service lifecycle for the managed Dufs runtime."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from chatshare.dufs.config import load_instance_state, sync_dufs_assets
from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths

UNIT_NAME = "chatshare-dufs.service"
_ALLOWED_ACTIONS = {"start", "stop", "restart"}
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _system_name(system: str | None) -> str:
    return (system or platform.system()).lower()


def _require_linux(system: str | None) -> None:
    if _system_name(system) != "linux":
        raise ChatShareError(
            "ChatShare currently supports the Linux systemd user service only"
        )


def default_user_unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _systemd_quote(value: Path | str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ChatShareError("systemd unit paths must not contain newlines")
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "$$")
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def _systemd_path(value: Path | str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ChatShareError("systemd unit paths must not contain newlines")
    return text.replace("%", "%%")


def _atomic_write(path: Path, content: str, *, mode: int = 0o644) -> None:
    existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not existed:
        path.parent.chmod(0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.chmod(mode)
        os.replace(temporary, path)
        path.chmod(mode)
    except Exception as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ChatShareError(f"Unable to write systemd unit {path}: {exc}") from exc


def render_service_unit(paths: ChatSharePaths) -> str:
    state = load_instance_state(paths)
    return "\n".join(
        [
            "[Unit]",
            "Description=ChatShare Dufs file service",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"ExecStart={_systemd_quote(paths.dufs_current_binary)} --config {_systemd_quote(state.config)}",
            f"WorkingDirectory={_systemd_path(state.root)}",
            "Restart=on-failure",
            "RestartSec=3",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "StandardOutput=journal",
            "StandardError=journal",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def _run_systemctl(
    args: list[str],
    *,
    runner: Runner | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    execute = runner or subprocess.run
    argv = ["systemctl", "--user", *args]
    try:
        result = execute(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        raise ChatShareError(f"Unable to run {' '.join(argv)}: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "no output").strip()
        raise ChatShareError(f"{' '.join(argv)} failed: {detail}")
    return result


def install_service(
    paths: ChatSharePaths,
    *,
    unit_dir: Path | str | None = None,
    enable: bool = False,
    system: str | None = None,
    runner: Runner | None = None,
) -> dict[str, object]:
    _require_linux(system)
    if not paths.dufs_current_binary.is_file():
        raise ChatShareError(
            f"Dufs runtime is not installed: {paths.dufs_current_binary}"
        )
    if not paths.config_file.is_file() or not paths.state_file.is_file():
        raise ChatShareError(
            f"ChatShare Dufs instance is not initialized: {paths.instance_dir}"
        )
    sync_dufs_assets(paths)
    text = render_service_unit(paths)
    live_dir = (
        Path(unit_dir).expanduser() if unit_dir is not None else default_user_unit_dir()
    )
    live_unit = live_dir / UNIT_NAME
    _atomic_write(paths.canonical_unit, text)
    _atomic_write(live_unit, text)
    _run_systemctl(["daemon-reload"], runner=runner)
    if enable:
        _run_systemctl(["enable", UNIT_NAME], runner=runner)
    return {
        "canonical_unit": str(paths.canonical_unit),
        "enabled": enable,
        "unit": str(live_unit),
    }


def control_service(
    action: str,
    *,
    system: str | None = None,
    runner: Runner | None = None,
) -> dict[str, str]:
    if action not in _ALLOWED_ACTIONS:
        raise ChatShareError(f"Unsupported service action: {action!r}")
    _require_linux(system)
    _run_systemctl([action, UNIT_NAME], runner=runner)
    return {"action": action, "service": UNIT_NAME}


def _manifest_version(paths: ChatSharePaths) -> str | None:
    current = paths.dufs_current
    try:
        version = os.readlink(current) if current.is_symlink() else None
    except OSError:
        return None
    if not version:
        return None
    manifest = paths.dufs_manifest(version)
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return version
    return (
        str(payload.get("version") or version) if isinstance(payload, dict) else version
    )


def get_service_status(
    paths: ChatSharePaths,
    *,
    unit_dir: Path | str | None = None,
    system: str | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    linux = _system_name(system) == "linux"
    live_dir = (
        Path(unit_dir).expanduser() if unit_dir is not None else default_user_unit_dir()
    )
    live_unit = live_dir / UNIT_NAME
    installed = paths.dufs_current_binary.is_file()
    state = None
    state_error = None
    try:
        state = load_instance_state(paths)
    except ChatShareError as exc:
        state_error = str(exc)
    configured = state is not None and paths.config_file.is_file()

    active = False
    if not linux:
        service_state = "unsupported"
    elif not live_unit.is_file():
        service_state = "not-installed"
    else:
        try:
            process_result = _run_systemctl(
                ["is-active", UNIT_NAME], runner=runner, check=False
            )
            output = (process_result.stdout or process_result.stderr or "").strip()
            service_state = output.splitlines()[0] if output else "inactive"
            active = process_result.returncode == 0 and service_state == "active"
        except ChatShareError:
            service_state = "systemctl-unavailable"

    result: dict[str, Any] = {
        "active": active,
        "binary": str(paths.dufs_current_binary),
        "configured": configured,
        "installed": installed,
        "service_state": service_state,
        "service_supported": linux,
        "unit": str(live_unit),
        "unit_installed": live_unit.is_file(),
        "version": _manifest_version(paths),
    }
    if state is not None:
        result.update(
            {
                "base_url": state.base_url,
                "bind": state.bind,
                "config": str(state.config),
                "port": state.port,
                "root": str(state.root),
                "username": state.username,
            }
        )
    elif state_error:
        result["state_error"] = state_error
    return result


def read_access_logs(paths: ChatSharePaths, *, lines: int = 100) -> dict[str, object]:
    if not isinstance(lines, int) or not (1 <= lines <= 10000):
        raise ChatShareError("Log line count must be between 1 and 10000")
    if not paths.access_log.is_file():
        return {"log": str(paths.access_log), "lines": []}
    try:
        with paths.access_log.open("r", encoding="utf-8", errors="replace") as handle:
            selected = [line.rstrip("\r\n") for line in deque(handle, maxlen=lines)]
    except OSError as exc:
        raise ChatShareError(
            f"Unable to read Dufs access log {paths.access_log}: {exc}"
        ) from exc
    return {"log": str(paths.access_log), "lines": selected}
