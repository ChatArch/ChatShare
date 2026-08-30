"""CLI entrypoint for ChatShare."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import click
from chatstyle import (
    CommandField,
    CommandSchema,
    add_interactive_option,
    add_tree_option,
    render_success,
    resolve_command_inputs,
)

from chatshare import __version__
from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths

T = TypeVar("T")


@dataclass(frozen=True)
class CliContext:
    paths: ChatSharePaths
    json_output: bool


HELLO_SCHEMA = CommandSchema(
    name="hello",
    fields=(CommandField("name", prompt="name", required=True),),
)


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ChatShareError as exc:
        raise click.ClickException(str(exc)) from exc


def _emit(context: CliContext, value: dict[str, Any]) -> None:
    if context.json_output:
        click.echo(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return
    lines = value.get("lines")
    if isinstance(lines, list):
        for line in lines:
            click.echo(str(line))
        return
    for key in sorted(value):
        rendered = value[key]
        if isinstance(rendered, bool):
            rendered = str(rendered).lower()
        elif rendered is None:
            rendered = "-"
        click.echo(f"{key}: {rendered}")


@click.group(name="chatshare", context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--home",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    envvar="CHATARCH_HOME",
    help="ChatArch home (default: ChatEnv home, normally ~/.chatarch).",
)
@click.option(
    "--json", "json_output", is_flag=True, help="Emit structured JSON output."
)
@click.version_option(version=__version__, prog_name="chatshare")
@add_tree_option(renderer_options={"root_name": "chatshare"})
@click.pass_context
def main(context: click.Context, home: Path | None, json_output: bool) -> None:
    """Manage Dufs-backed file sharing inside ChatArch."""

    context.obj = CliContext(
        paths=ChatSharePaths.from_home(home), json_output=json_output
    )


@main.group()
def dufs() -> None:
    """Manage the local Dufs runtime, configuration, and user service."""


@dufs.command("install")
@click.option(
    "--version", default="v0.46.0", show_default=True, help="Explicit Dufs release tag."
)
@click.option("--platform", "target", help="Override the Dufs target triple.")
@click.option(
    "--force", is_flag=True, help="Atomically replace the same-version runtime."
)
@click.pass_obj
def install_command(
    context: CliContext, version: str, target: str | None, force: bool
) -> None:
    """Install a verified Dufs runtime; writes managed runtime files."""

    from chatshare.dufs.release import install_dufs

    result = _execute(
        lambda: install_dufs(
            context.paths,
            version=version,
            target=target,
            force=force,
        )
    )
    _emit(context, result)


@dufs.command("init")
@click.option(
    "--root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    help="Directory served by Dufs (default: managed instance data).",
)
@click.option(
    "--bind", default="127.0.0.1", show_default=True, help="Loopback bind host."
)
@click.option("--port", type=click.IntRange(1, 65535), default=5000, show_default=True)
@click.option(
    "--base-url",
    help="Base URL used for generated file URLs (default: ChatEnv profile or loopback).",
)
@click.option(
    "--username",
    help="Dufs writer username (default: ChatEnv profile or chatshare).",
)
@click.option(
    "--password-env",
    default="CHATSHARE_DUFS_PASSWORD",
    show_default=True,
    help="Environment variable containing the shared Dufs password.",
)
@click.option(
    "--force", is_flag=True, help="Replace the existing instance config and state."
)
@click.pass_obj
def init_command(
    context: CliContext,
    root: Path | None,
    bind: str,
    port: int,
    base_url: str | None,
    username: str | None,
    password_env: str,
    force: bool,
) -> None:
    """Initialize secure Dufs config and state; writes managed files."""

    from chatshare.config import merged_chatshare_environ
    from chatshare.dufs.config import DEFAULT_USERNAME, init_instance

    environ = merged_chatshare_environ(context.paths.chatarch_home)
    resolved_username = (
        username or environ.get("CHATSHARE_DUFS_USERNAME") or DEFAULT_USERNAME
    )
    resolved_base_url = base_url or environ.get("CHATSHARE_DUFS_BASE_URL") or None
    result = _execute(
        lambda: init_instance(
            context.paths,
            root=root,
            bind=bind,
            port=port,
            base_url=resolved_base_url,
            username=resolved_username,
            password_env=password_env,
            force=force,
            environ=environ,
        )
    )
    _emit(context, result)


@dufs.group("service")
def service_group() -> None:
    """Manage the Linux systemd user-service definition."""


@service_group.command("install")
@click.option(
    "--enable", is_flag=True, help="Enable login-time startup without starting now."
)
@click.pass_obj
def install_service_command(context: CliContext, enable: bool) -> None:
    """Write the systemd user unit; optionally enable login startup."""

    from chatshare.dufs.service import install_service

    result = _execute(lambda: install_service(context.paths, enable=enable))
    _emit(context, result)


def _control_and_emit(context: CliContext, action: str) -> None:
    from chatshare.dufs.service import control_service

    result = _execute(lambda: control_service(action))
    _emit(context, result)


@dufs.command("start")
@click.pass_obj
def start_command(context: CliContext) -> None:
    """Start Dufs through systemd --user; changes service state."""

    _control_and_emit(context, "start")


@dufs.command("stop")
@click.pass_obj
def stop_command(context: CliContext) -> None:
    """Stop Dufs through systemd --user; changes service state."""

    _control_and_emit(context, "stop")


@dufs.command("restart")
@click.pass_obj
def restart_command(context: CliContext) -> None:
    """Restart Dufs through systemd --user; changes service state."""

    _control_and_emit(context, "restart")


@dufs.command("status")
@click.pass_obj
def status_command(context: CliContext) -> None:
    """Read runtime, config, unit, and active state; no writes."""

    from chatshare.dufs.service import get_service_status

    result = _execute(lambda: get_service_status(context.paths))
    _emit(context, result)


@dufs.command("logs")
@click.option("--lines", type=click.IntRange(1, 10000), default=100, show_default=True)
@click.pass_obj
def logs_command(context: CliContext, lines: int) -> None:
    """Read a bounded Dufs access-log tail; no writes."""

    from chatshare.dufs.service import read_access_logs

    result = _execute(lambda: read_access_logs(context.paths, lines=lines))
    _emit(context, result)


@main.command("put")
@click.argument("source", type=click.Path(path_type=Path))
@click.argument("destination", required=False)
@click.option(
    "--overwrite", is_flag=True, help="Atomically replace an existing destination."
)
@click.pass_obj
def put_command(
    context: CliContext,
    source: Path,
    destination: str | None,
    overwrite: bool,
) -> None:
    """Publish a local file or directory; writes managed share data."""

    from chatshare.sharing import publish_path

    result = _execute(
        lambda: publish_path(
            context.paths,
            source,
            destination,
            overwrite=overwrite,
        )
    )
    _emit(context, result)


@main.command("tree")
@click.argument("prefix", required=False)
@click.pass_obj
def tree_command(context: CliContext, prefix: str | None) -> None:
    """Print the managed share tree under an optional prefix; no writes."""

    from chatshare.sharing import build_share_tree

    result = _execute(lambda: build_share_tree(context.paths, prefix))
    _emit(context, result)


@main.command("url")
@click.argument("path")
@click.pass_obj
def url_command(context: CliContext, path: str) -> None:
    """Build a direct URL for an existing managed file; no writes."""

    from chatshare.sharing import build_file_url

    result = _execute(lambda: build_file_url(context.paths, path))
    _emit(context, result)


@main.command("hello", hidden=True)
@click.argument("name", required=False)
@add_interactive_option
def hello(name: str | None, interactive: bool | None) -> None:
    """Print the legacy greeting for 0.1.0 compatibility."""

    values = resolve_command_inputs(
        schema=HELLO_SCHEMA,
        provided={"name": name},
        interactive=interactive,
        usage="Usage: chatshare hello [NAME]",
    )
    render_success(f"Hello, {values['name']}!")


if __name__ == "__main__":
    main()
