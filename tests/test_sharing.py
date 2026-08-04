from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import pytest

from chatshare.dufs.config import DEFAULT_PASSWORD_ENV, init_instance
from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths
from chatshare.sharing import build_file_url, publish_file


def ready_paths(tmp_path, *, base_url=None):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    init_instance(
        paths,
        base_url=base_url,
        environ={DEFAULT_PASSWORD_ENV: "sharing-test-secret"},
    )
    return paths


def test_publish_file_uses_source_name_and_returns_digest_and_url(tmp_path):
    paths = ready_paths(tmp_path)
    source = tmp_path / "report.pdf"
    data = b"report contents"
    source.write_bytes(data)

    result = publish_file(paths, source)

    target = paths.data_dir / "report.pdf"
    assert target.read_bytes() == data
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert result == {
        "destination": str(target),
        "overwritten": False,
        "path": "report.pdf",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "source": str(source.resolve()),
        "url": "http://127.0.0.1:5000/report.pdf",
    }
    assert "sharing-test-secret" not in str(result)


def test_publish_nested_destination_and_url_quotes_each_segment(tmp_path):
    paths = ready_paths(tmp_path, base_url="https://share.example.test/files/")
    source = tmp_path / "input.bin"
    source.write_bytes(b"data")

    result = publish_file(paths, source, "报告 2026/a #1.bin")

    assert result["path"] == "报告 2026/a #1.bin"
    assert result["url"] == (
        "https://share.example.test/files/%E6%8A%A5%E5%91%8A%202026/a%20%231.bin"
    )
    assert Path(result["destination"]).read_bytes() == b"data"


@pytest.mark.parametrize(
    "destination",
    [
        "",
        "/absolute/file",
        "C:/absolute/file",
        ".",
        "..",
        "a/../b",
        "a/./b",
        "a//b",
        "a/b/",
        r"a\b",
    ],
)
def test_publish_rejects_unsafe_destination(destination, tmp_path):
    paths = ready_paths(tmp_path)
    source = tmp_path / "source"
    source.write_bytes(b"data")

    with pytest.raises(ChatShareError, match="relative path"):
        publish_file(paths, source, destination)


def test_publish_rejects_symlink_parent_escape(tmp_path):
    paths = ready_paths(tmp_path)
    source = tmp_path / "source"
    source.write_bytes(b"data")
    outside = tmp_path / "outside"
    outside.mkdir()
    (paths.data_dir / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ChatShareError, match="escapes"):
        publish_file(paths, source, "escape/stolen.bin")

    assert not (outside / "stolen.bin").exists()


def test_publish_requires_existing_regular_source(tmp_path):
    paths = ready_paths(tmp_path)

    with pytest.raises(ChatShareError, match="regular file"):
        publish_file(paths, tmp_path / "missing")
    with pytest.raises(ChatShareError, match="regular file"):
        publish_file(paths, tmp_path)


def test_publish_refuses_overwrite_then_atomically_replaces_when_explicit(tmp_path):
    paths = ready_paths(tmp_path)
    source = tmp_path / "source"
    source.write_bytes(b"new")
    target = paths.data_dir / "item.bin"
    target.write_bytes(b"old")

    with pytest.raises(ChatShareError, match="already exists"):
        publish_file(paths, source, "item.bin")
    assert target.read_bytes() == b"old"

    result = publish_file(paths, source, "item.bin", overwrite=True)
    assert result["overwritten"] is True
    assert target.read_bytes() == b"new"


def test_publish_without_overwrite_cannot_replace_racing_destination(
    monkeypatch, tmp_path
):
    from chatshare import sharing

    paths = ready_paths(tmp_path)
    source = tmp_path / "source"
    source.write_bytes(b"new")
    target = paths.data_dir / "item.bin"

    def racing_link(source_path, destination_path, **kwargs):
        target.write_bytes(b"racer")
        raise FileExistsError(destination_path)

    monkeypatch.setattr(sharing.os, "link", racing_link)

    with pytest.raises(ChatShareError, match="already exists"):
        publish_file(paths, source, "item.bin")
    assert target.read_bytes() == b"racer"


def test_publish_preserves_permissions_of_existing_custom_root(tmp_path):
    root = tmp_path / "shared-root"
    root.mkdir(mode=0o755)
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    init_instance(
        paths,
        root=root,
        environ={DEFAULT_PASSWORD_ENV: "sharing-test-secret"},
    )
    root.chmod(0o755)
    source = tmp_path / "source"
    source.write_bytes(b"data")

    publish_file(paths, source, "item.bin")

    assert stat.S_IMODE(root.stat().st_mode) == 0o755


def test_build_file_url_requires_existing_managed_file(tmp_path):
    paths = ready_paths(tmp_path, base_url="https://share.example.test/base/")
    target = paths.data_dir / "nested" / "item.txt"
    target.parent.mkdir()
    target.write_text("hello")

    result = build_file_url(paths, "nested/item.txt")

    assert result == {
        "path": "nested/item.txt",
        "url": "https://share.example.test/base/nested/item.txt",
    }

    with pytest.raises(ChatShareError, match="does not exist"):
        build_file_url(paths, "missing.txt")


def test_build_file_url_rejects_target_symlink_even_inside_root(tmp_path):
    paths = ready_paths(tmp_path)
    real = paths.data_dir / "real.txt"
    real.write_text("hello")
    link = paths.data_dir / "link.txt"
    link.symlink_to(real)

    with pytest.raises(ChatShareError, match="symlink"):
        build_file_url(paths, "link.txt")
