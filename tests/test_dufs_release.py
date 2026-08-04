from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from chatshare.dufs.release import (
    DEFAULT_DUFS_VERSION,
    ReleaseAsset,
    detect_target,
    download_asset,
    extract_dufs_archive,
    install_dufs,
    normalize_version,
    resolve_release_asset,
    verify_dufs_binary,
)
from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths


def make_archive(
    path: Path, *, name: str = "dufs", data: bytes = b"dufs-binary", kind: str = "file"
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name)
        if kind == "symlink":
            info.type = tarfile.SYMTYPE
            info.linkname = "/outside"
            archive.addfile(info)
        else:
            info.mode = 0o755
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def release_payload(
    version: str = "v0.46.0", *, digest: str | None = None
) -> dict[str, object]:
    asset_name = f"dufs-{version}-x86_64-unknown-linux-musl.tar.gz"
    return {
        "tag_name": version,
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": f"https://example.invalid/{asset_name}",
                "digest": digest or "sha256:" + "a" * 64,
                "size": 123,
            }
        ],
    }


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", "x86_64-unknown-linux-musl"),
        ("linux", "amd64", "x86_64-unknown-linux-musl"),
        ("Linux", "aarch64", "aarch64-unknown-linux-musl"),
        ("Darwin", "arm64", "aarch64-apple-darwin"),
        ("darwin", "x86_64", "x86_64-apple-darwin"),
        ("Linux", "armv7l", "armv7-unknown-linux-musleabihf"),
    ],
)
def test_detect_target_maps_supported_platforms(system, machine, expected):
    assert detect_target(system=system, machine=machine) == expected


def test_detect_target_rejects_unknown_platform():
    with pytest.raises(ChatShareError, match="Unsupported Dufs platform"):
        detect_target(system="Plan9", machine="mips")


def test_install_rejects_unsupported_target_before_network(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")

    with pytest.raises(ChatShareError, match="Unsupported Dufs target"):
        install_dufs(
            paths,
            target="../../unexpected",
            metadata_fetcher=lambda repo, version: pytest.fail("network must not run"),
        )


def test_default_version_is_pinned_and_latest_is_rejected():
    assert DEFAULT_DUFS_VERSION == "v0.46.0"
    assert normalize_version("0.46.0") == "v0.46.0"
    assert normalize_version("v0.46.0") == "v0.46.0"
    with pytest.raises(ChatShareError, match="explicit release version"):
        normalize_version("latest")


def test_resolve_release_asset_requires_exact_asset_and_sha256_digest():
    payload = release_payload()

    asset = resolve_release_asset(payload, "v0.46.0", "x86_64-unknown-linux-musl")

    assert asset.name == "dufs-v0.46.0-x86_64-unknown-linux-musl.tar.gz"
    assert asset.sha256 == "a" * 64
    assert asset.size == 123

    payload["assets"][0]["digest"] = None
    with pytest.raises(ChatShareError, match="sha256 digest"):
        resolve_release_asset(payload, "v0.46.0", "x86_64-unknown-linux-musl")


def test_resolve_release_asset_rejects_tag_or_asset_mismatch():
    with pytest.raises(ChatShareError, match="tag mismatch"):
        resolve_release_asset(
            release_payload("v0.45.0"), "v0.46.0", "x86_64-unknown-linux-musl"
        )

    with pytest.raises(ChatShareError, match="No Dufs release asset"):
        resolve_release_asset(
            release_payload(), "v0.46.0", "aarch64-unknown-linux-musl"
        )


def test_download_asset_streams_and_verifies_sha256(tmp_path):
    data = b"trusted archive bytes"
    asset = ReleaseAsset(
        name="dufs.tar.gz",
        url="https://example.invalid/dufs.tar.gz",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )

    class Response(io.BytesIO):
        status = 200

    destination = tmp_path / "dufs.tar.gz"
    download_asset(asset, destination, opener=lambda request, timeout: Response(data))

    assert destination.read_bytes() == data

    bad = ReleaseAsset(asset.name, asset.url, "0" * 64, asset.size)
    with pytest.raises(ChatShareError, match="SHA-256 mismatch"):
        download_asset(
            bad, tmp_path / "bad.tar.gz", opener=lambda request, timeout: Response(data)
        )


def test_extract_dufs_archive_accepts_only_regular_dufs_member(tmp_path):
    archive = tmp_path / "dufs.tar.gz"
    output = tmp_path / "dufs"
    make_archive(archive, data=b"executable")

    extract_dufs_archive(archive, output)

    assert output.read_bytes() == b"executable"
    assert output.stat().st_mode & 0o777 == 0o755

    malicious = tmp_path / "malicious.tar.gz"
    make_archive(malicious, name="dufs", kind="symlink")
    with pytest.raises(ChatShareError, match="regular"):
        extract_dufs_archive(malicious, tmp_path / "never")

    traversal = tmp_path / "traversal.tar.gz"
    make_archive(traversal, name="../dufs")
    with pytest.raises(ChatShareError, match="exactly one regular 'dufs'"):
        extract_dufs_archive(traversal, tmp_path / "never2")


def test_verify_dufs_binary_requires_expected_version(tmp_path):
    binary = tmp_path / "dufs"
    binary.write_text("placeholder")

    def ok_runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0, stdout="dufs v0.46.0\n", stderr=""
        )

    assert verify_dufs_binary(binary, "v0.46.0", runner=ok_runner) == "dufs v0.46.0"

    def cargo_version_runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0, stdout="dufs 0.46.0\n", stderr=""
        )

    assert (
        verify_dufs_binary(binary, "v0.46.0", runner=cargo_version_runner)
        == "dufs 0.46.0"
    )

    def mismatch_runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0, stdout="dufs v0.45.0\n", stderr=""
        )

    with pytest.raises(ChatShareError, match="version mismatch"):
        verify_dufs_binary(binary, "v0.46.0", runner=mismatch_runner)

    def prefix_runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0, stdout="dufs v0.46.01\n", stderr=""
        )

    with pytest.raises(ChatShareError, match="version mismatch"):
        verify_dufs_binary(binary, "v0.46.0", runner=prefix_runner)

    for invalid_output in ["dufs v0.46.0-rc1\n", "dufs x0.46.0garbage\n"]:
        with pytest.raises(ChatShareError, match="version mismatch"):
            verify_dufs_binary(
                binary,
                "v0.46.0",
                runner=lambda *args, output=invalid_output, **kwargs: (
                    subprocess.CompletedProcess(args[0], 0, stdout=output, stderr="")
                ),
            )


def test_install_dufs_writes_manifest_and_atomically_activates_version(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    old_runtime = paths.dufs_runtime("v0.45.0")
    old_runtime.mkdir(parents=True)
    (old_runtime / "dufs").write_text("old")
    paths.dufs_current.symlink_to("v0.45.0", target_is_directory=True)

    payload = release_payload()

    def fake_fetch(repo, version):
        assert repo == "sigoden/dufs"
        assert version == "v0.46.0"
        return payload

    def fake_download(asset, destination):
        make_archive(destination, data=b"new-binary")

    verified = []

    def fake_verify(binary, version):
        verified.append((binary.read_bytes(), version))
        return "dufs v0.46.0"

    result = install_dufs(
        paths,
        target="x86_64-unknown-linux-musl",
        metadata_fetcher=fake_fetch,
        downloader=fake_download,
        verifier=fake_verify,
    )

    assert result["version"] == "v0.46.0"
    assert result["reused"] is False
    assert paths.dufs_binary("v0.46.0").read_bytes() == b"new-binary"
    assert paths.dufs_current.is_symlink()
    assert os.readlink(paths.dufs_current) == "v0.46.0"
    assert paths.dufs_current_binary.read_bytes() == b"new-binary"
    assert verified == [(b"new-binary", "v0.46.0")]
    manifest = json.loads(paths.dufs_manifest("v0.46.0").read_text())
    assert manifest == {
        "asset": "dufs-v0.46.0-x86_64-unknown-linux-musl.tar.gz",
        "binary_sha256": hashlib.sha256(b"new-binary").hexdigest(),
        "repo": "sigoden/dufs",
        "sha256": "a" * 64,
        "target": "x86_64-unknown-linux-musl",
        "version": "v0.46.0",
    }


def test_install_failure_preserves_existing_binary_and_current_pointer(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    runtime = paths.dufs_runtime("v0.46.0")
    runtime.mkdir(parents=True)
    binary = runtime / "dufs"
    binary.write_bytes(b"known-good")
    paths.dufs_current.symlink_to("v0.46.0", target_is_directory=True)

    def fail_download(asset, destination):
        raise ChatShareError("network failed")

    with pytest.raises(ChatShareError, match="network failed"):
        install_dufs(
            paths,
            target="x86_64-unknown-linux-musl",
            force=True,
            metadata_fetcher=lambda repo, version: release_payload(),
            downloader=fail_download,
            verifier=lambda binary, version: "never",
        )

    assert binary.read_bytes() == b"known-good"
    assert os.readlink(paths.dufs_current) == "v0.46.0"


def test_install_reuses_existing_version_without_network(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    runtime = paths.dufs_runtime("v0.46.0")
    runtime.mkdir(parents=True)
    binary = runtime / "dufs"
    binary.write_bytes(b"known-good")
    binary_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    archive_digest = "a" * 64
    (runtime / "install.json").write_text(
        json.dumps(
            {
                "asset": "dufs-v0.46.0-x86_64-unknown-linux-musl.tar.gz",
                "binary_sha256": binary_digest,
                "repo": "sigoden/dufs",
                "sha256": archive_digest,
                "target": "x86_64-unknown-linux-musl",
                "version": "v0.46.0",
            }
        )
    )
    verified = []

    result = install_dufs(
        paths,
        target="x86_64-unknown-linux-musl",
        metadata_fetcher=lambda repo, version: pytest.fail("network must not be used"),
        verifier=lambda binary, version: (
            verified.append((binary, version)) or "dufs v0.46.0"
        ),
    )

    assert result["reused"] is True
    assert result["sha256"] == archive_digest
    assert result["binary_sha256"] == binary_digest
    assert verified == [(binary, "v0.46.0")]
    assert os.readlink(paths.dufs_current) == "v0.46.0"


def test_install_refuses_to_reuse_tampered_binary(tmp_path):
    paths = ChatSharePaths.from_home(tmp_path / "chatarch")
    runtime = paths.dufs_runtime("v0.46.0")
    runtime.mkdir(parents=True)
    binary = runtime / "dufs"
    binary.write_bytes(b"tampered")
    actual_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    (runtime / "install.json").write_text(
        json.dumps(
            {
                "asset": "dufs-v0.46.0-x86_64-unknown-linux-musl.tar.gz",
                "binary_sha256": "a" * 64,
                "repo": "sigoden/dufs",
                "sha256": actual_digest,
                "target": "x86_64-unknown-linux-musl",
                "version": "v0.46.0",
            }
        )
    )

    with pytest.raises(ChatShareError, match="SHA-256 mismatch"):
        install_dufs(
            paths,
            target="x86_64-unknown-linux-musl",
            verifier=lambda binary, version: "dufs 0.46.0",
        )
