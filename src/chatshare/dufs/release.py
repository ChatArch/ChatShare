"""Trusted installation of official Dufs release assets."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import tarfile
import tempfile
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from chatshare.errors import ChatShareError
from chatshare.paths import ChatSharePaths

DEFAULT_DUFS_REPO = "sigoden/dufs"
DEFAULT_DUFS_VERSION = "v0.46.0"
_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_TARGETS = {
    "aarch64-apple-darwin",
    "aarch64-unknown-linux-musl",
    "arm-unknown-linux-musleabihf",
    "armv7-unknown-linux-musleabihf",
    "x86_64-apple-darwin",
    "x86_64-unknown-linux-musl",
}


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    sha256: str
    size: int


def normalize_version(version: str) -> str:
    value = version.strip()
    if value.lower() == "latest":
        raise ChatShareError(
            "Dufs installation requires an explicit release version; 'latest' is not accepted"
        )
    if not value.startswith("v"):
        value = f"v{value}"
    if not _VERSION_RE.fullmatch(value):
        raise ChatShareError(f"Invalid Dufs release version: {version!r}")
    return value


def detect_target(*, system: str | None = None, machine: str | None = None) -> str:
    os_name = (system or platform.system()).lower()
    arch = (machine or platform.machine()).lower()
    if arch in {"x86_64", "amd64"}:
        canonical_arch = "x86_64"
    elif arch in {"aarch64", "arm64"}:
        canonical_arch = "aarch64"
    elif arch in {"armv7", "armv7l"}:
        canonical_arch = "armv7"
    elif arch in {"arm", "armv6", "armv6l"}:
        canonical_arch = "arm"
    else:
        raise ChatShareError(f"Unsupported Dufs platform: {os_name}/{arch}")

    if os_name == "darwin" and canonical_arch in {"x86_64", "aarch64"}:
        return f"{canonical_arch}-apple-darwin"
    if os_name == "linux":
        if canonical_arch == "armv7":
            return "armv7-unknown-linux-musleabihf"
        if canonical_arch == "arm":
            return "arm-unknown-linux-musleabihf"
        return f"{canonical_arch}-unknown-linux-musl"
    raise ChatShareError(f"Unsupported Dufs platform: {os_name}/{arch}")


def fetch_release_metadata(repo: str, version: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/tags/{version}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ChatShare/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if getattr(response, "status", 200) != 200:
                raise ChatShareError(
                    f"GitHub release metadata request failed: HTTP {response.status}"
                )
            payload = json.loads(response.read().decode("utf-8"))
    except ChatShareError:
        raise
    except Exception as exc:
        raise ChatShareError(
            f"Unable to fetch Dufs release metadata for {version}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ChatShareError("GitHub release metadata is not a JSON object")
    return payload


def resolve_release_asset(
    payload: dict[str, Any], version: str, target: str
) -> ReleaseAsset:
    version = normalize_version(version)
    tag = payload.get("tag_name")
    if tag != version:
        raise ChatShareError(
            f"Dufs release tag mismatch: expected {version}, got {tag!r}"
        )
    expected_name = f"dufs-{version}-{target}.tar.gz"
    assets = payload.get("assets")
    matches = (
        [
            asset
            for asset in assets
            if isinstance(asset, dict) and asset.get("name") == expected_name
        ]
        if isinstance(assets, list)
        else []
    )
    if len(matches) != 1:
        raise ChatShareError(f"No Dufs release asset named {expected_name!r}")
    raw = matches[0]
    url = raw.get("browser_download_url")
    digest = raw.get("digest")
    size = raw.get("size")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ChatShareError(
            f"Dufs release asset {expected_name!r} has no HTTPS download URL"
        )
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ChatShareError(
            f"Dufs release asset {expected_name!r} has no sha256 digest"
        )
    sha256 = digest.removeprefix("sha256:").lower()
    if not _SHA256_RE.fullmatch(sha256):
        raise ChatShareError(
            f"Dufs release asset {expected_name!r} has an invalid sha256 digest"
        )
    if not isinstance(size, int) or size <= 0:
        raise ChatShareError(
            f"Dufs release asset {expected_name!r} has an invalid size"
        )
    return ReleaseAsset(name=expected_name, url=url, sha256=sha256, size=size)


def download_asset(
    asset: ReleaseAsset,
    destination: Path,
    *,
    opener: Callable[..., BinaryIO] = urllib.request.urlopen,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(asset.url, headers={"User-Agent": "ChatShare/0.1"})
    digest = hashlib.sha256()
    total = 0
    try:
        with opener(request, timeout=120) as response, destination.open("wb") as output:
            status = getattr(response, "status", 200)
            if status != 200:
                raise ChatShareError(f"Dufs asset download failed: HTTP {status}")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                total += len(chunk)
        actual = digest.hexdigest()
        if actual != asset.sha256:
            raise ChatShareError(
                f"Dufs asset SHA-256 mismatch for {asset.name}: expected {asset.sha256}, got {actual}"
            )
        if total != asset.size:
            raise ChatShareError(
                f"Dufs asset size mismatch for {asset.name}: expected {asset.size}, got {total}"
            )
    except ChatShareError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise ChatShareError(
            f"Unable to download Dufs asset {asset.name}: {exc}"
        ) from exc


def extract_dufs_archive(archive_path: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = [
                member
                for member in archive.getmembers()
                if member.name == "dufs" and member.isreg()
            ]
            if len(members) != 1:
                raise ChatShareError(
                    "Dufs archive must contain exactly one regular 'dufs' file"
                )
            source = archive.extractfile(members[0])
            if source is None:
                raise ChatShareError(
                    "Unable to read the Dufs binary from the release archive"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source, destination.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            destination.chmod(0o755)
    except ChatShareError:
        destination.unlink(missing_ok=True)
        raise
    except (tarfile.TarError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise ChatShareError(f"Unable to extract Dufs release archive: {exc}") from exc


def verify_dufs_binary(
    binary: Path,
    version: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    version = normalize_version(version)
    try:
        result = runner(
            [str(binary), "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        raise ChatShareError(f"Unable to execute Dufs version check: {exc}") from exc
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        raise ChatShareError(
            f"Dufs binary version check failed: {output or 'no output'}"
        )
    expected = re.escape(version.removeprefix("v"))
    if re.search(rf"(?<![0-9.])v?{expected}(?![0-9.])", output) is None:
        raise ChatShareError(
            f"Dufs binary version mismatch: expected {version}, got {output!r}"
        )
    return output


def _activate_version(paths: ChatSharePaths, version: str) -> None:
    if paths.dufs_runtimes.is_symlink():
        raise ChatShareError(
            f"Dufs runtimes directory must not be a symlink: {paths.dufs_runtimes}"
        )
    paths.dufs_runtimes.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = paths.dufs_current
    if current.exists() and not current.is_symlink():
        raise ChatShareError(f"Dufs current pointer is not a symlink: {current}")
    temporary = current.parent / f".current-{uuid.uuid4().hex}"
    try:
        temporary.symlink_to(version, target_is_directory=True)
        os.replace(temporary, current)
    finally:
        temporary.unlink(missing_ok=True)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChatShareError(
            f"Unable to read Dufs install manifest {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ChatShareError(f"Dufs install manifest is not a JSON object: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise ChatShareError(f"Unable to hash Dufs binary {path}: {exc}") from exc
    return digest.hexdigest()


def _validate_reused_manifest(
    manifest: dict[str, Any], *, version: str, target: str, repo: str, path: Path
) -> str:
    expected = {
        "asset": f"dufs-{version}-{target}.tar.gz",
        "repo": repo,
        "target": target,
        "version": version,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ChatShareError(
            f"Dufs install manifest does not match this runtime: {path}"
        )
    sha256 = manifest.get("sha256")
    if not isinstance(sha256, str) or _SHA256_RE.fullmatch(sha256) is None:
        raise ChatShareError(f"Dufs install manifest has an invalid SHA-256: {path}")
    return sha256


def install_dufs(
    paths: ChatSharePaths,
    *,
    version: str = DEFAULT_DUFS_VERSION,
    target: str | None = None,
    repo: str = DEFAULT_DUFS_REPO,
    force: bool = False,
    metadata_fetcher: Callable[[str, str], dict[str, Any]] | None = None,
    downloader: Callable[[ReleaseAsset, Path], None] | None = None,
    verifier: Callable[[Path, str], str] | None = None,
) -> dict[str, Any]:
    version = normalize_version(version)
    target = target or detect_target()
    if target not in _SUPPORTED_TARGETS:
        raise ChatShareError(f"Unsupported Dufs target: {target!r}")
    binary = paths.dufs_binary(version)
    manifest_path = paths.dufs_manifest(version)
    verify = verifier or (lambda path, expected: verify_dufs_binary(path, expected))

    if binary.is_file() and manifest_path.is_file() and not force:
        if binary.is_symlink() or manifest_path.is_symlink():
            raise ChatShareError(
                "Managed Dufs binary and manifest must not be symlinks"
            )
        manifest = _read_manifest(manifest_path)
        expected_sha256 = _validate_reused_manifest(
            manifest, version=version, target=target, repo=repo, path=manifest_path
        )
        actual_sha256 = _file_sha256(binary)
        if actual_sha256 != expected_sha256:
            raise ChatShareError(
                f"Dufs binary SHA-256 mismatch at {binary}: expected {expected_sha256}, got {actual_sha256}"
            )
        verify(binary, version)
        _activate_version(paths, version)
        return {
            "asset": manifest.get("asset"),
            "binary": str(binary),
            "reused": True,
            "sha256": manifest.get("sha256"),
            "target": manifest.get("target"),
            "version": version,
        }

    fetch = metadata_fetcher or fetch_release_metadata
    download = downloader or download_asset
    payload = fetch(repo, version)
    asset = resolve_release_asset(payload, version, target)

    runtime = paths.dufs_runtime(version)
    if runtime.is_symlink():
        raise ChatShareError(f"Dufs runtime directory must not be a symlink: {runtime}")
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=runtime) as temp_name:
        staging = Path(temp_name)
        archive = staging / asset.name
        staged_binary = staging / "dufs"
        staged_manifest = staging / "install.json"
        download(asset, archive)
        extract_dufs_archive(archive, staged_binary)
        verify(staged_binary, version)
        manifest = {
            "asset": asset.name,
            "repo": repo,
            "sha256": asset.sha256,
            "target": target,
            "version": version,
        }
        staged_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staged_manifest.chmod(0o600)
        os.replace(staged_binary, binary)
        binary.chmod(0o755)
        os.replace(staged_manifest, manifest_path)
        manifest_path.chmod(0o600)

    _activate_version(paths, version)
    return {
        **manifest,
        "binary": str(binary),
        "reused": False,
    }
