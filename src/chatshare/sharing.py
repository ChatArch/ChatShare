"""Local file publication and direct URL generation."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote

from chatshare.dufs.config import InstanceState, load_instance_state
from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:/")


def _relative_parts(value: Path | str) -> tuple[str, ...]:
    raw = str(value)
    if (
        not raw
        or raw.startswith("/")
        or _WINDOWS_DRIVE.match(raw)
        or "\\" in raw
        or raw.endswith("/")
    ):
        raise ChatShareError(
            f"Share destination must be a safe POSIX relative path, got {raw!r}"
        )
    parts = tuple(raw.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ChatShareError(
            f"Share destination must be a safe POSIX relative path, got {raw!r}"
        )
    return parts


def _managed_target(state: InstanceState, parts: tuple[str, ...]) -> tuple[Path, Path]:
    try:
        root = state.root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ChatShareError(f"ChatShare root does not exist: {state.root}") from exc
    if not root.is_dir():
        raise ChatShareError(f"ChatShare root is not a directory: {root}")
    target = root.joinpath(*parts)
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ChatShareError(
            f"Share destination escapes the managed root: {'/'.join(parts)}"
        ) from exc
    return root, target


def _url_for(state: InstanceState, parts: tuple[str, ...]) -> str:
    encoded = "/".join(quote(part, safe="") for part in parts)
    return f"{state.base_url.rstrip('/')}/{encoded}"


def _create_missing_parents(root: Path, parent: Path) -> None:
    missing: list[Path] = []
    current = parent
    while current != root and not current.exists():
        missing.append(current)
        current = current.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in reversed(missing):
        path.chmod(0o700)


def publish_file(
    paths: ChatSharePaths,
    source: Path | str,
    destination: Path | str | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise ChatShareError(
            f"Share source must be an existing regular file: {source_path}"
        )
    source_resolved = source_path.resolve()
    relative = source_path.name if destination is None else destination
    parts = _relative_parts(relative)
    state = load_instance_state(paths)
    _, target = _managed_target(state, parts)
    if target.is_symlink():
        raise ChatShareError(f"Share destination must not be a symlink: {target}")
    existed = target.exists()
    if existed and not overwrite:
        raise ChatShareError(
            f"Share destination already exists: {target}; pass --overwrite to replace it"
        )

    root, _ = _managed_target(state, parts)
    _create_missing_parents(root, target.parent)
    # Resolve again after creating parents to catch a symlink introduced during setup.
    _, target = _managed_target(state, parts)
    if target.is_symlink():
        raise ChatShareError(f"Share destination must not be a symlink: {target}")
    if target.exists() and not overwrite:
        raise ChatShareError(
            f"Share destination already exists: {target}; pass --overwrite to replace it"
        )

    temporary: Path | None = None
    digest = hashlib.sha256()
    size = 0
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        temporary = Path(temp_name)
        with (
            os.fdopen(descriptor, "wb") as output,
            source_resolved.open("rb") as input_file,
        ):
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise ChatShareError(
                    f"Share destination already exists: {target}; pass --overwrite to replace it"
                ) from exc
            temporary.unlink()
    except ChatShareError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ChatShareError(
            f"Unable to publish {source_resolved} to {target}: {exc}"
        ) from exc

    relative_text = "/".join(parts)
    return {
        "destination": str(target),
        "overwritten": existed,
        "path": relative_text,
        "sha256": digest.hexdigest(),
        "size": size,
        "source": str(source_resolved),
        "url": _url_for(state, parts),
    }


def build_file_url(paths: ChatSharePaths, relative_path: Path | str) -> dict[str, str]:
    parts = _relative_parts(relative_path)
    state = load_instance_state(paths)
    _, target = _managed_target(state, parts)
    if target.is_symlink():
        raise ChatShareError(f"Managed share path must not be a symlink: {target}")
    if not target.is_file():
        raise ChatShareError(f"Managed share file does not exist: {target}")
    relative_text = "/".join(parts)
    return {"path": relative_text, "url": _url_for(state, parts)}
