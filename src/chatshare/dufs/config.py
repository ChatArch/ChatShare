"""Secure Dufs instance configuration and non-secret state."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_USERNAME = "chatshare"
DEFAULT_PASSWORD_ENV = "CHATSHARE_DUFS_PASSWORD"
_LOOPBACK_BINDS = {"127.0.0.1", "localhost", "::1"}
_AUTH_SEPARATORS = {":", "@", ",", "\n", "\r"}
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class InstanceState:
    schema_version: int
    backend: str
    instance: str
    root: Path
    bind: str
    port: int
    base_url: str
    username: str
    config: Path
    access_log: Path

    def to_json_dict(self) -> dict[str, object]:
        value = asdict(self)
        for key in ("root", "config", "access_log"):
            value[key] = str(value[key])
        return value

    def public_result(self, state_file: Path) -> dict[str, object]:
        return {
            "backend": self.backend,
            "base_url": self.base_url,
            "bind": self.bind,
            "config": str(self.config),
            "instance": self.instance,
            "port": self.port,
            "root": str(self.root),
            "state": str(state_file),
            "username": self.username,
        }


def _ensure_managed_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _ensure_data_root(path: Path) -> None:
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not existed:
        path.chmod(0o700)
    if not path.is_dir():
        raise ChatShareError(f"Dufs serve root is not a directory: {path}")


def _atomic_write(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        if isinstance(exc, ChatShareError):
            raise
        raise ChatShareError(f"Unable to write {path}: {exc}") from exc


def _yaml_quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ChatShareError("Dufs config values must not contain newlines")
    return "'" + value.replace("'", "''") + "'"


def _validate_auth_value(label: str, value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(separator in value for separator in _AUTH_SEPARATORS)
    ):
        raise ChatShareError(
            f"Dufs {label} contains an auth-rule delimiter, newline, or surrounding whitespace"
        )
    return value


def _normalize_base_url(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ChatShareError("Dufs base URL must not contain newlines")
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise ChatShareError(f"Invalid Dufs base URL: {value!r}") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ChatShareError(
            "Dufs base URL must be an http(s) URL without credentials, query, or fragment"
        )
    if parsed_port is not None and not (1 <= parsed_port <= 65535):
        raise ChatShareError("Dufs base URL contains an invalid port")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _default_base_url(bind: str, port: int) -> str:
    host = f"[{bind}]" if ":" in bind else bind
    return f"http://{host}:{port}"


def _render_config(state: InstanceState, password: str) -> str:
    auth_rule = f"{state.username}:{password}@/:rw"
    return "\n".join(
        [
            f"serve-path: {_yaml_quote(str(state.root))}",
            f"bind: {_yaml_quote(state.bind)}",
            f"port: {state.port}",
            "auth:",
            f"  - {_yaml_quote(auth_rule)}",
            "allow-upload: true",
            "allow-delete: false",
            "allow-search: true",
            "allow-symlink: false",
            "allow-archive: true",
            "allow-hash: true",
            "enable-cors: false",
            f"log-file: {_yaml_quote(str(state.access_log))}",
            "",
        ]
    )


def init_instance(
    paths: ChatSharePaths,
    *,
    root: Path | str | None = None,
    bind: str = DEFAULT_BIND,
    port: int = DEFAULT_PORT,
    base_url: str | None = None,
    username: str = DEFAULT_USERNAME,
    password_env: str = DEFAULT_PASSWORD_ENV,
    force: bool = False,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    if (paths.config_file.exists() or paths.state_file.exists()) and not force:
        raise ChatShareError(
            f"ChatShare Dufs instance already exists at {paths.instance_dir}; pass --force to replace it"
        )
    if not isinstance(bind, str) or bind not in _LOOPBACK_BINDS:
        raise ChatShareError(f"Dufs bind must be loopback-only, got {bind!r}")
    if type(port) is not int or not (1 <= port <= 65535):
        raise ChatShareError(f"Dufs port must be between 1 and 65535, got {port!r}")
    username = _validate_auth_value("username", username)
    if not isinstance(password_env, str) or not _ENV_NAME_RE.fullmatch(password_env):
        raise ChatShareError("Dufs password environment variable name is invalid")
    source = os.environ if environ is None else environ
    password = source.get(password_env, "")
    if not password:
        raise ChatShareError(
            f"Environment variable {password_env} is not set or is empty"
        )
    password = _validate_auth_value("password", password)

    root_path = (
        Path(root).expanduser().resolve()
        if root is not None
        else paths.data_dir.resolve()
    )
    if "\n" in str(root_path) or "\r" in str(root_path):
        raise ChatShareError("Dufs serve root must not contain newlines")
    normalized_base = (
        _normalize_base_url(base_url) if base_url else _default_base_url(bind, port)
    )
    state = InstanceState(
        schema_version=1,
        backend="dufs",
        instance="default",
        root=root_path,
        bind=bind,
        port=port,
        base_url=normalized_base,
        username=username,
        config=paths.config_file,
        access_log=paths.access_log,
    )

    _ensure_managed_directory(paths.instance_dir)
    _ensure_data_root(root_path)
    _ensure_managed_directory(paths.logs_dir)
    _atomic_write(paths.config_file, _render_config(state, password), mode=0o600)
    state_text = json.dumps(state.to_json_dict(), indent=2, sort_keys=True) + "\n"
    _atomic_write(paths.state_file, state_text, mode=0o600)
    return state.public_result(paths.state_file)


def load_instance_state(paths: ChatSharePaths) -> InstanceState:
    try:
        payload = json.loads(paths.state_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ChatShareError(
            f"ChatShare Dufs instance is not initialized: {paths.state_file}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ChatShareError(
            f"Unable to read ChatShare instance state {paths.state_file}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ChatShareError(
            f"Unsupported ChatShare instance state: {paths.state_file}"
        )
    try:
        if (
            type(payload.get("schema_version")) is not int
            or payload["schema_version"] != 1
        ):
            raise ValueError("schema_version")
        if payload.get("backend") != "dufs" or payload.get("instance") != "default":
            raise ValueError("backend/instance")
        root_value = payload["root"]
        bind_value = payload["bind"]
        port_value = payload["port"]
        base_url_value = payload["base_url"]
        username_value = payload["username"]
        config_value = payload["config"]
        access_log_value = payload["access_log"]
        if not all(
            isinstance(value, str) and value
            for value in (
                root_value,
                bind_value,
                base_url_value,
                username_value,
                config_value,
                access_log_value,
            )
        ):
            raise ValueError("string field")
        root_path = Path(root_value)
        if not root_path.is_absolute() or "\n" in root_value or "\r" in root_value:
            raise ValueError("root")
        if bind_value not in _LOOPBACK_BINDS:
            raise ValueError("bind")
        if type(port_value) is not int or not (1 <= port_value <= 65535):
            raise ValueError("port")
        normalized_base_url = _normalize_base_url(base_url_value)
        if normalized_base_url != base_url_value:
            raise ValueError("base_url")
        username = _validate_auth_value("username", username_value)
        config_path = Path(config_value)
        access_log_path = Path(access_log_value)
        if config_path != paths.config_file or access_log_path != paths.access_log:
            raise ValueError("managed path")
        return InstanceState(
            schema_version=1,
            backend="dufs",
            instance="default",
            root=root_path,
            bind=bind_value,
            port=port_value,
            base_url=normalized_base_url,
            username=username,
            config=config_path,
            access_log=access_log_path,
        )
    except (ChatShareError, KeyError, TypeError, ValueError) as exc:
        raise ChatShareError(
            f"Invalid or incomplete ChatShare instance state: {paths.state_file}"
        ) from exc
