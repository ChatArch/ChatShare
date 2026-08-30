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


def _relative_directory_parts(value: Path | str) -> tuple[str, ...]:
    raw = str(value)
    if raw.endswith("/") and raw != "/":
        raw = raw[:-1]
    return _relative_parts(raw)


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


def _publish_regular_file(
    state: InstanceState,
    source_path: Path,
    parts: tuple[str, ...],
    *,
    overwrite: bool,
) -> dict[str, object]:
    if not source_path.is_file():
        raise ChatShareError(
            f"Share source must be an existing regular file: {source_path}"
        )
    source_resolved = source_path.resolve()
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
    relative = source_path.name if destination is None else destination
    parts = _relative_parts(relative)
    state = load_instance_state(paths)
    return _publish_regular_file(state, source_path, parts, overwrite=overwrite)


def _collect_directory_upload(
    source_root: Path, prefix_parts: tuple[str, ...]
) -> tuple[list[tuple[str, ...]], list[tuple[Path, tuple[str, ...]]]]:
    directories = [prefix_parts]
    files: list[tuple[Path, tuple[str, ...]]] = []
    for path in sorted(
        source_root.rglob("*"), key=lambda item: item.relative_to(source_root).parts
    ):
        relative_parts = path.relative_to(source_root).parts
        target_parts = prefix_parts + relative_parts
        _relative_parts("/".join(target_parts))
        if path.is_symlink():
            raise ChatShareError(
                f"Share directory source must not contain symlinks: {path}"
            )
        if path.is_dir():
            directories.append(target_parts)
        elif path.is_file():
            files.append((path, target_parts))
        else:
            raise ChatShareError(
                f"Share directory source contains an unsupported entry: {path}"
            )
    return directories, files


def _preflight_directory_upload(
    state: InstanceState,
    directories: list[tuple[str, ...]],
    files: list[tuple[Path, tuple[str, ...]]],
    *,
    overwrite: bool,
) -> None:
    for parts in directories:
        _, target = _managed_target(state, parts)
        if target.is_symlink():
            raise ChatShareError(f"Share destination must not be a symlink: {target}")
        if target.exists() and not target.is_dir():
            raise ChatShareError(
                f"Share destination already exists and is not a directory: {target}"
            )
    for _, parts in files:
        _, target = _managed_target(state, parts)
        if target.is_symlink():
            raise ChatShareError(f"Share destination must not be a symlink: {target}")
        if target.exists() and target.is_dir():
            raise ChatShareError(
                f"Share destination already exists and is a directory: {target}"
            )
        if target.exists() and not overwrite:
            raise ChatShareError(
                f"Share destination already exists: {target}; pass --overwrite to replace it"
            )


def _ensure_directory_targets(
    state: InstanceState, directories: list[tuple[str, ...]]
) -> None:
    root, _ = _managed_target(state, ())
    for parts in sorted(directories, key=len):
        _, target = _managed_target(state, parts)
        if target.is_symlink():
            raise ChatShareError(f"Share destination must not be a symlink: {target}")
        if target.exists() and not target.is_dir():
            raise ChatShareError(
                f"Share destination already exists and is not a directory: {target}"
            )
        _create_missing_parents(root, target)
        _, target = _managed_target(state, parts)
        if target.is_symlink() or not target.is_dir():
            raise ChatShareError(f"Share destination is not a directory: {target}")


def publish_directory(
    paths: ChatSharePaths,
    source: Path | str,
    destination: Path | str | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    source_path = Path(source).expanduser()
    if not source_path.is_dir():
        raise ChatShareError(
            f"Share source must be an existing directory: {source_path}"
        )
    source_resolved = source_path.resolve()
    if destination is None:
        relative = source_path.name or source_resolved.name
    else:
        relative = destination
    parts = _relative_directory_parts(relative)
    state = load_instance_state(paths)
    directories, files = _collect_directory_upload(source_resolved, parts)
    _preflight_directory_upload(state, directories, files, overwrite=overwrite)
    _ensure_directory_targets(state, directories)

    overwritten_files = 0
    for file_path, file_parts in files:
        result = _publish_regular_file(
            state, file_path, file_parts, overwrite=overwrite
        )
        if result["overwritten"]:
            overwritten_files += 1

    _, target = _managed_target(state, parts)
    relative_text = "/".join(parts)
    return {
        "destination": str(target),
        "directories": len(directories),
        "files": len(files),
        "overwritten": overwritten_files > 0,
        "overwritten_files": overwritten_files,
        "path": relative_text,
        "source": str(source_resolved),
        "url": _url_for(state, parts),
    }


def publish_path(
    paths: ChatSharePaths,
    source: Path | str,
    destination: Path | str | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    source_path = Path(source).expanduser()
    if source_path.is_dir():
        return publish_directory(
            paths, source_path, destination, overwrite=overwrite
        )
    return publish_file(paths, source_path, destination, overwrite=overwrite)


def _tree_entry_type(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


def _tree_sort_key(path: Path) -> tuple[int, str, str]:
    kind = _tree_entry_type(path)
    return (0 if kind == "directory" else 1, path.name.casefold(), path.name)


def _tree_display_name(path: Path) -> str:
    kind = _tree_entry_type(path)
    suffix = "/" if kind == "directory" else "@" if kind == "symlink" else ""
    return f"{path.name}{suffix}"


def _render_tree(path: Path, label: str) -> list[str]:
    lines = [label]

    def walk(directory: Path, prefix: str) -> None:
        children = sorted(directory.iterdir(), key=_tree_sort_key)
        for index, child in enumerate(children):
            last = index == len(children) - 1
            connector = "`-- " if last else "+-- "
            extension = "    " if last else "|   "
            lines.append(f"{prefix}{connector}{_tree_display_name(child)}")
            if _tree_entry_type(child) == "directory":
                walk(child, prefix + extension)

    if path.is_dir():
        walk(path, "")
    return lines


def build_share_tree(
    paths: ChatSharePaths, prefix: Path | str | None = None
) -> dict[str, object]:
    state = load_instance_state(paths)
    parts = () if prefix is None else _relative_directory_parts(prefix)
    _, target = _managed_target(state, parts)
    if target.is_symlink():
        raise ChatShareError(f"Managed share path must not be a symlink: {target}")
    if not target.exists():
        raise ChatShareError(f"Managed share path does not exist: {target}")
    if not target.is_dir() and not target.is_file():
        raise ChatShareError(f"Managed share path is not a file or directory: {target}")
    relative_text = "/".join(parts)
    label = "." if not parts else relative_text + ("/" if target.is_dir() else "")
    lines = _render_tree(target, label)
    return {
        "entries": max(0, len(lines) - 1),
        "kind": _tree_entry_type(target),
        "lines": lines,
        "path": relative_text,
        "root": str(state.root),
        "target": str(target),
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
