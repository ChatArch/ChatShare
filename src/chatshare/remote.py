"""Authenticated streaming client for an existing ChatShare/Dufs server."""

from __future__ import annotations

import hashlib
import ipaddress
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from chatshare.config import merged_chatshare_environ
from chatshare.errors import ChatShareError
from chatshare.sharing import PublishProgress, ProgressCallback, _relative_directory_parts, _relative_parts

_UPLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, repr=False)
class RemoteSettings:
    """Validated non-local ChatShare connection settings."""

    base_url: str
    username: str
    password: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        hostname = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ChatShareError("CHATSHARE_DUFS_BASE_URL must be a plain http(s) origin or path prefix")
        if parsed.scheme == "http" and not _is_loopback(hostname):
            raise ChatShareError("CHATSHARE_DUFS_BASE_URL must use https outside loopback")
        if not self.username or not self.password:
            raise ChatShareError(
                "ChatShare remote writes require CHATSHARE_DUFS_USERNAME and CHATSHARE_DUFS_PASSWORD"
            )
        normalized_path = parsed.path.rstrip("/")
        object.__setattr__(
            self,
            "base_url",
            urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", "")),
        )


def _is_loopback(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def load_remote_settings(
    home: Path | str | None = None,
    *,
    process_environ: Mapping[str, str] | None = None,
) -> RemoteSettings:
    """Load client credentials from the active ChatEnv profile or process env."""

    values = merged_chatshare_environ(home, process_environ)
    base_url = values.get("CHATSHARE_DUFS_BASE_URL", "").strip()
    username = values.get("CHATSHARE_DUFS_USERNAME", "").strip()
    password = values.get("CHATSHARE_DUFS_PASSWORD", "")
    if not base_url:
        raise ChatShareError(
            "ChatShare is not configured for a remote server. Run `chatenv init -t chatshare -I`, "
            "then set CHATSHARE_DUFS_BASE_URL, CHATSHARE_DUFS_USERNAME, and CHATSHARE_DUFS_PASSWORD."
        )
    return RemoteSettings(base_url, username, password)


class _FileStream(httpx.SyncByteStream):
    """Read a source file one bounded chunk at a time and report copy progress."""

    def __init__(self, source: Path, progress: ProgressCallback | None) -> None:
        self.source = source
        self.total = source.stat().st_size
        self.progress = progress
        self.digest = hashlib.sha256()

    def __iter__(self) -> Iterator[bytes]:
        transferred = 0
        self._emit(transferred)
        with self.source.open("rb") as input_file:
            while chunk := input_file.read(_UPLOAD_CHUNK_SIZE):
                yield chunk
                transferred += len(chunk)
                self.digest.update(chunk)
                self._emit(transferred)

    def _emit(self, transferred: int) -> None:
        if self.progress is not None:
            self.progress(
                PublishProgress(
                    source=self.source,
                    transferred=transferred,
                    total=self.total,
                )
            )


class RemoteClient:
    """Small Dufs/WebDAV client for a configured, already-running share."""

    def __init__(
        self,
        settings: RemoteSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.auth = httpx.BasicAuth(settings.username, settings.password)

    def publish_file(
        self,
        source: Path | str,
        destination: Path | str | None = None,
        *,
        overwrite: bool = False,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        source_path = Path(source).expanduser()
        if source_path.is_symlink() or not source_path.is_file():
            raise ChatShareError(f"Share source must be an existing regular non-symlink file: {source_path}")
        source_resolved = source_path.resolve()
        relative = source_path.name if destination is None else destination
        parts = _relative_parts(relative)
        target_url = self._url_for(parts)

        existing = self._request("HEAD", target_url)
        if existing.status_code == 200 and not overwrite:
            raise ChatShareError(
                f"Remote share destination already exists: {'/'.join(parts)}; pass --overwrite to replace it"
            )
        if existing.status_code not in {200, 404}:
            self._raise_for_status(existing, "check remote destination")
        self._ensure_parents(parts[:-1])

        stream = _FileStream(source_resolved, progress)
        response = self._request(
            "PUT",
            target_url,
            content=stream,
            headers={"content-length": str(stream.total)},
            timeout=httpx.Timeout(120, connect=5, write=None, pool=30),
        )
        self._raise_for_status(response, "upload file")
        return {
            "path": "/".join(parts),
            "sha256": stream.digest.hexdigest(),
            "size": stream.total,
            "source": str(source_resolved),
            "url": target_url,
        }

    def list_directory(self, prefix: Path | str | None = None) -> dict[str, object]:
        parts = () if prefix is None else _relative_directory_parts(prefix)
        response = self._request("GET", self._url_for(parts) + "?json")
        self._raise_for_status(response, "list remote directory")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ChatShareError("Remote ChatShare returned an invalid directory listing") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("paths"), list):
            raise ChatShareError("Remote ChatShare returned an unsupported directory listing")
        entries = []
        for item in payload["paths"]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise ChatShareError("Remote ChatShare returned an invalid directory entry")
            name = item["name"]
            kind = item.get("path_type")
            if kind not in {"Dir", "File"}:
                raise ChatShareError("Remote ChatShare returned an unsupported directory entry")
            entries.append((name, kind == "Dir"))
        entries.sort(key=lambda item: (not item[1], item[0].casefold(), item[0]))
        label = "." if not parts else "/".join(parts) + "/"
        lines = [label]
        for index, (name, directory) in enumerate(entries):
            lines.append(("`-- " if index == len(entries) - 1 else "+-- ") + name + ("/" if directory else ""))
        return {
            "entries": len(entries),
            "lines": lines,
            "path": "/".join(parts),
            "url": self._url_for(parts),
        }

    def build_file_url(self, relative_path: Path | str) -> dict[str, str]:
        parts = _relative_parts(relative_path)
        response = self._request("HEAD", self._url_for(parts))
        if response.status_code == 404:
            raise ChatShareError(f"Remote share file does not exist: {'/'.join(parts)}")
        self._raise_for_status(response, "check remote file")
        return {"path": "/".join(parts), "url": self._url_for(parts)}

    def _ensure_parents(self, parts: tuple[str, ...]) -> None:
        for length in range(1, len(parts) + 1):
            response = self._request("MKCOL", self._url_for(parts[:length]))
            if response.status_code not in {201, 405}:
                self._raise_for_status(response, "create remote destination directory")

    def _url_for(self, parts: tuple[str, ...]) -> str:
        encoded = "/".join(quote(part, safe="") for part in parts)
        return self.settings.base_url.rstrip("/") + "/" + encoded

    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        try:
            with httpx.Client(
                auth=self.auth,
                follow_redirects=False,
                timeout=httpx.Timeout(30, connect=5, pool=30),
                transport=self.transport,
                trust_env=False,
            ) as client:
                return client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ChatShareError(f"Unable to contact the configured ChatShare server: {exc.__class__.__name__}") from exc
        except OSError as exc:
            raise ChatShareError(f"Unable to read upload source: {exc.__class__.__name__}") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        if response.status_code in {401, 403}:
            raise ChatShareError(
                "ChatShare authentication failed; check CHATSHARE_DUFS_USERNAME and CHATSHARE_DUFS_PASSWORD"
            )
        raise ChatShareError(f"Unable to {action}: remote server returned HTTP {response.status_code}")
