"""Persistent, owner-scoped URL download jobs for the ChatShare gateway."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import ssl
import stat
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable
from urllib.parse import quote, urljoin, urlsplit


TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted"}
ACTIVE_STATES = {"queued", "downloading", "committing"}


class DownloadError(Exception):
    """A safe, user-displayable download failure."""


@dataclass(frozen=True)
class DownloadLimits:
    concurrency: int = 2
    max_pending: int = 20
    max_file_size: int = 20 * 1024**3
    connect_timeout: float = 5
    idle_timeout: float = 30
    redirect_limit: int = 5
    chunk_size: int = 64 * 1024
    max_jobs: int = 200

    def __post_init__(self):
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
            for value in asdict(self).values()
        ):
            raise ValueError("Download limits must be positive numbers")


@dataclass(frozen=True, repr=False)
class ResolvedTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    request_target: str
    host_label: str
    ips: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]

    def __repr__(self) -> str:
        return f"ResolvedTarget(scheme={self.scheme!r}, host={self.host_label!r}, port={self.port!r})"


async def _system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(record[4][0] for record in records))


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if not address.is_global:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None and not address.ipv4_mapped.is_global:
            return False
        if address.sixtofour is not None and not address.sixtofour.is_global:
            return False
        if address.teredo is not None and any(not item.is_global for item in address.teredo):
            return False
    return True


async def resolve_public_target(
    url: str,
    *,
    resolver: Callable[[str, int], Awaitable[list[str]]] = _system_resolver,
) -> ResolvedTarget:
    if not isinstance(url, str) or not url or len(url) > 8192:
        raise DownloadError("Source URL is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise DownloadError("Source URL contains control characters")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise DownloadError("Source URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DownloadError("Source must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise DownloadError("Source URL credentials are not allowed")
    if parsed.fragment:
        raise DownloadError("Source URL fragments are not allowed")
    expected_port = 80 if parsed.scheme == "http" else 443
    if port is not None and port != expected_port:
        raise DownloadError("Source URL must use the default HTTP(S) port")
    hostname = parsed.hostname.rstrip(".").lower()
    if not hostname or any(character.isspace() for character in hostname):
        raise DownloadError("Source hostname is invalid")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            answers = await resolver(hostname, expected_port)
        except (OSError, asyncio.TimeoutError) as exc:
            raise DownloadError("Source hostname could not be resolved") from exc
        if not answers:
            raise DownloadError("Source hostname has no addresses")
        try:
            addresses = tuple(dict.fromkeys(ipaddress.ip_address(value) for value in answers))
        except ValueError as exc:
            raise DownloadError("Source DNS response is invalid") from exc
    else:
        addresses = (literal,)
    if not all(_is_public(address) for address in addresses):
        raise DownloadError("Every source address must be public")
    path = parsed.path or "/"
    request_target = path + (("?" + parsed.query) if parsed.query else "")
    return ResolvedTarget(
        url=url,
        scheme=parsed.scheme,
        hostname=hostname,
        port=expected_port,
        request_target=request_target,
        host_label=hostname,
        ips=addresses,
    )


def validate_target_path(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4096:
        raise DownloadError("Target path is required")
    if value.startswith("/") or "\\" in value or "%" in value:
        raise DownloadError("Target path is ambiguous or absolute")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise DownloadError("Target path contains control characters")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} or len(part.encode("utf-8")) > 255 for part in parts):
        raise DownloadError("Target path contains an unsafe component")
    return parts


def atomic_publish(stage: Path, root: Path, parts: tuple[str, ...]) -> None:
    """Atomically hard-link a complete private file into a safely opened tree."""

    validate_target_path("/".join(parts))
    try:
        if root.is_symlink():
            raise DownloadError("Share root must not be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        source_stat = stage.stat(follow_symlinks=False)
        root_stat = root.stat(follow_symlinks=False)
        if not stat.S_ISREG(source_stat.st_mode):
            raise DownloadError("Private staging object is not a regular file")
        if source_stat.st_dev != root_stat.st_dev:
            raise DownloadError("Private staging and share root must use the same filesystem")
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(root, flags)
        try:
            for component in parts[:-1]:
                try:
                    os.mkdir(component, mode=0o755, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            try:
                os.link(
                    stage,
                    parts[-1],
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise DownloadError("Target already exists") from exc
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        stage.unlink()
    except DownloadError:
        raise
    except (OSError, ValueError) as exc:
        raise DownloadError(f"Unable to publish target safely: {exc}") from exc


class PinnedHTTPSource:
    """Small HTTP/1.1 streaming client whose socket uses an already validated IP."""

    async def _line(self, reader: asyncio.StreamReader, timeout: float) -> bytes:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout)
        except asyncio.TimeoutError as exc:
            raise DownloadError("Source download idle timeout") from exc
        if len(line) > 8192:
            raise DownloadError("Source response header is too large")
        return line

    async def stream(
        self, target: ResolvedTarget, limits: DownloadLimits, cancel: asyncio.Event
    ) -> AsyncIterator[dict | bytes]:
        context = ssl.create_default_context() if target.scheme == "https" else None
        reader = writer = None
        last_error: Exception | None = None
        for address in target.ips:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        str(address),
                        target.port,
                        ssl=context,
                        server_hostname=target.hostname if context else None,
                        limit=128 * 1024,
                    ),
                    limits.connect_timeout,
                )
                break
            except (OSError, asyncio.TimeoutError) as exc:
                last_error = exc
        if reader is None or writer is None:
            raise DownloadError("Unable to connect to source") from last_error
        try:
            host = target.hostname
            if ":" in host:
                host = f"[{host}]"
            request = (
                f"GET {target.request_target} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "User-Agent: ChatShare/URL-download\r\n"
                "Accept: */*\r\n"
                "Accept-Encoding: identity\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            writer.write(request)
            await asyncio.wait_for(writer.drain(), limits.idle_timeout)
            status_line = await self._line(reader, limits.idle_timeout)
            try:
                protocol, status_text, _ = status_line.decode("latin-1").split(" ", 2)
                status_code = int(status_text)
            except (ValueError, UnicodeError) as exc:
                raise DownloadError("Source returned an invalid HTTP status") from exc
            if protocol not in {"HTTP/1.0", "HTTP/1.1"}:
                raise DownloadError("Source returned an unsupported HTTP response")
            headers: dict[str, list[str]] = {}
            total_headers = 0
            while True:
                line = await self._line(reader, limits.idle_timeout)
                total_headers += len(line)
                if total_headers > 64 * 1024:
                    raise DownloadError("Source response headers are too large")
                if line in {b"\r\n", b"\n"}:
                    break
                if not line or b":" not in line or line[:1] in b" \t":
                    raise DownloadError("Source returned invalid HTTP headers")
                name, value = line.decode("latin-1").split(":", 1)
                headers.setdefault(name.strip().lower(), []).append(value.strip())
            lengths = headers.get("content-length", [])
            if len(set(lengths)) > 1:
                raise DownloadError("Source returned conflicting lengths")
            try:
                length = int(lengths[0]) if lengths else None
            except ValueError as exc:
                raise DownloadError("Source returned an invalid length") from exc
            if length is not None and length < 0:
                raise DownloadError("Source returned an invalid length")
            location = headers.get("location", [None])[-1]
            yield {"status": status_code, "length": length, "location": location}
            if status_code < 200 or status_code >= 300:
                return
            transfer = ",".join(headers.get("transfer-encoding", [])).lower()
            if transfer and transfer != "chunked":
                raise DownloadError("Source transfer encoding is unsupported")
            if transfer == "chunked":
                while True:
                    size_line = await self._line(reader, limits.idle_timeout)
                    try:
                        size = int(size_line.split(b";", 1)[0].strip(), 16)
                    except ValueError as exc:
                        raise DownloadError("Source returned invalid chunk framing") from exc
                    if size < 0:
                        raise DownloadError("Source returned invalid chunk framing")
                    if size == 0:
                        return
                    remaining = size
                    while remaining:
                        chunk = await asyncio.wait_for(
                            reader.read(min(remaining, limits.chunk_size)), limits.idle_timeout
                        )
                        if not chunk:
                            raise DownloadError("Source response was truncated")
                        remaining -= len(chunk)
                        yield chunk
                    if await asyncio.wait_for(reader.readexactly(2), limits.idle_timeout) != b"\r\n":
                        raise DownloadError("Source returned invalid chunk framing")
            else:
                remaining = length
                while remaining is None or remaining > 0:
                    chunk = await asyncio.wait_for(
                        reader.read(
                            limits.chunk_size if remaining is None else min(remaining, limits.chunk_size)
                        ),
                        limits.idle_timeout,
                    )
                    if not chunk:
                        break
                    if remaining is not None:
                        remaining -= len(chunk)
                    yield chunk
                if remaining:
                    raise DownloadError("Source response was truncated")
        except asyncio.IncompleteReadError as exc:
            raise DownloadError("Source response was truncated") from exc
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ssl.SSLError):
                pass


PermissionCheck = Callable[[str, str], Awaitable[bool]]


class DownloadService:
    """Bounded worker pool and durable, credential-free job metadata."""

    def __init__(
        self,
        *,
        base: Path,
        share_root: Path,
        source=None,
        resolver=_system_resolver,
        limits: DownloadLimits | None = None,
        clock=time.time,
    ):
        self.base = Path(base)
        self.share_root = Path(share_root)
        self.staging = self.base / "staging"
        self.metadata = self.base / "jobs.json"
        self.source = source or PinnedHTTPSource()
        self.resolver = resolver
        self.limits = limits or DownloadLimits()
        self.clock = clock
        self.jobs: dict[str, dict] = {}
        self._private: dict[str, tuple[str, PermissionCheck]] = {}
        self._cancel: dict[str, asyncio.Event] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.limits.max_pending)
        self._workers: list[asyncio.Task] = []
        self._executions: dict[str, asyncio.Task] = {}
        self._closing = False
        self._persist_lock = asyncio.Lock()

    def _safe_job(self, job: dict) -> dict:
        result = dict(job)
        if result.get("state") == "downloading" and result.get("started_at"):
            elapsed = max(self.clock() - result["started_at"], 0.001)
            result["speed"] = int(result["transferred"] / elapsed)
        else:
            result["speed"] = 0
        return result

    async def start(self) -> None:
        if self.base.is_symlink():
            raise DownloadError("Download runtime root must not be a symlink")
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.base.is_symlink() or not self.base.is_dir():
            raise DownloadError("Download runtime root is unsafe")
        self.base.chmod(0o700)
        if self.staging.is_symlink():
            raise DownloadError("Download staging root must not be a symlink")
        self.staging.mkdir(mode=0o700, exist_ok=True)
        self.staging.chmod(0o700)
        self.share_root.mkdir(parents=True, exist_ok=True)
        if self.metadata.exists():
            if self.metadata.is_symlink() or not self.metadata.is_file():
                raise DownloadError("Download metadata file is unsafe")
            try:
                payload = json.loads(self.metadata.read_text(encoding="utf-8"))
                loaded = payload["jobs"]
                if not isinstance(loaded, list) or len(loaded) > self.limits.max_jobs:
                    raise ValueError("jobs")
                for job in loaded:
                    if not isinstance(job, dict) or not isinstance(job.get("id"), str):
                        raise ValueError("job")
                    if job.get("state") in ACTIVE_STATES:
                        job["state"] = "interrupted"
                        job["error"] = "Gateway restarted before completion"
                        job["updated_at"] = self.clock()
                    self.jobs[job["id"]] = job
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise DownloadError("Download metadata is invalid") from exc
        for child in self.staging.iterdir():
            if child.is_symlink() or not child.is_file():
                raise DownloadError("Download staging contains an unsafe object")
            child.unlink()
        await self._persist()

    def _ensure_workers(self) -> None:
        if not self._workers:
            self._workers = [
                asyncio.create_task(self._worker(), name=f"chatshare-download-{index}")
                for index in range(self.limits.concurrency)
            ]

    async def close(self) -> None:
        self._closing = True
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def join(self) -> None:
        await self._queue.join()

    async def _persist(self) -> None:
        async with self._persist_lock:
            terminal = sorted(self.jobs.values(), key=lambda item: item["created_at"], reverse=True)
            keep = terminal[: self.limits.max_jobs]
            self.jobs = {job["id"]: job for job in keep}
            temporary = self.base / f".jobs.{secrets.token_hex(8)}.tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                content = json.dumps({"schema": 1, "jobs": keep}, ensure_ascii=False, separators=(",", ":")).encode()
                os.write(descriptor, content)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, self.metadata)
            self.metadata.chmod(0o600)

    def _conflicts(self, parts: tuple[str, ...]) -> bool:
        for job in self.jobs.values():
            if job["state"] not in ACTIVE_STATES:
                continue
            other = tuple(job["target"].split("/"))
            shared = min(len(parts), len(other))
            if parts[:shared] == other[:shared]:
                return True
        return False

    async def create(self, owner: str, url: str, target: str, permission: PermissionCheck) -> dict:
        parts = validate_target_path(target)
        resolved = await resolve_public_target(url, resolver=self.resolver)
        if sum(job["state"] in ACTIVE_STATES for job in self.jobs.values()) >= self.limits.max_pending:
            raise DownloadError("Download queue is full")
        if self._conflicts(parts):
            raise DownloadError("Target namespace conflicts with an active job")
        if not await permission(owner, target):
            raise DownloadError("Dufs denied upload permission for this target")
        now = self.clock()
        identifier = secrets.token_urlsafe(18)
        job = {
            "id": identifier,
            "owner": owner,
            "state": "queued",
            "target": target,
            "source_host": resolved.host_label,
            "transferred": 0,
            "total": None,
            "sha256": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
        }
        self.jobs[identifier] = job
        self._private[identifier] = (url, permission)
        self._cancel[identifier] = asyncio.Event()
        self._locks[identifier] = asyncio.Lock()
        await self._persist()
        self._ensure_workers()
        await self._queue.put(identifier)
        return self._safe_job(job)

    def list(self, owner: str) -> list[dict]:
        return [
            self._safe_job(job)
            for job in sorted(self.jobs.values(), key=lambda item: item["created_at"], reverse=True)
            if job["owner"] == owner
        ]

    def get(self, owner: str, identifier: str) -> dict:
        job = self.jobs.get(identifier)
        if not job or job["owner"] != owner:
            raise DownloadError("Job not found for owner")
        return self._safe_job(job)

    async def cancel(self, owner: str, identifier: str) -> dict:
        current = self.get(owner, identifier)
        if current["state"] in TERMINAL_STATES:
            return current
        async with self._locks[identifier]:
            job = self.jobs[identifier]
            if job["state"] in {"queued", "downloading"}:
                self._cancel[identifier].set()
                execution = self._executions.get(identifier)
                if execution is not None:
                    execution.cancel()
                if job["state"] == "queued":
                    job["state"] = "cancelled"
                    job["updated_at"] = self.clock()
                    await self._persist()
            return self._safe_job(job)

    async def _worker(self) -> None:
        while not self._closing:
            identifier = await self._queue.get()
            try:
                if self.jobs.get(identifier, {}).get("state") == "queued":
                    execution = asyncio.create_task(self._run(identifier))
                    self._executions[identifier] = execution
                    await execution
            finally:
                self._executions.pop(identifier, None)
                self._queue.task_done()

    async def _run(self, identifier: str) -> None:
        job = self.jobs[identifier]
        url, permission = self._private[identifier]
        cancel = self._cancel[identifier]
        stage = self.staging / f"{identifier}.part"
        try:
            if cancel.is_set():
                raise asyncio.CancelledError
            job.update(state="downloading", started_at=self.clock(), updated_at=self.clock())
            await self._persist()
            digest = hashlib.sha256()
            transferred = 0
            redirects = 0
            current_url = url
            with stage.open("xb") as handle:
                stage.chmod(0o600)
                while True:
                    target = await resolve_public_target(current_url, resolver=self.resolver)
                    header = None
                    redirected = False
                    async for item in self.source.stream(target, self.limits, cancel):
                        if isinstance(item, dict):
                            header = item
                            status = item.get("status")
                            if status in {301, 302, 303, 307, 308}:
                                location = item.get("location")
                                if not isinstance(location, str) or not location:
                                    raise DownloadError("Source redirect has no location")
                                redirects += 1
                                if redirects > self.limits.redirect_limit:
                                    raise DownloadError("Source redirect limit exceeded")
                                current_url = urljoin(current_url, location)
                                redirected = True
                                break
                            if status != 200:
                                raise DownloadError(f"Source returned HTTP {status}")
                            length = item.get("length")
                            if length is not None and length > self.limits.max_file_size:
                                raise DownloadError("Source file is too large")
                            job["total"] = length
                            continue
                        if header is None:
                            raise DownloadError("Source response metadata is missing")
                        if cancel.is_set():
                            raise asyncio.CancelledError
                        transferred += len(item)
                        if transferred > self.limits.max_file_size:
                            raise DownloadError("Source file is too large")
                        handle.write(item)
                        digest.update(item)
                        job.update(transferred=transferred, updated_at=self.clock())
                        await self._persist()
                    if redirected:
                        continue
                    if header is None:
                        raise DownloadError("Source returned no response")
                    expected = header.get("length")
                    if expected is not None and transferred != expected:
                        raise DownloadError("Source response was truncated")
                    break
                handle.flush()
                os.fsync(handle.fileno())
            async with self._locks[identifier]:
                if cancel.is_set():
                    raise asyncio.CancelledError
                job.update(state="committing", updated_at=self.clock())
                await self._persist()
                if not await permission(job["owner"], job["target"]):
                    raise DownloadError("Dufs upload permission changed before commit")
                atomic_publish(stage, self.share_root, validate_target_path(job["target"]))
                job.update(
                    state="completed",
                    sha256=digest.hexdigest(),
                    updated_at=self.clock(),
                    error=None,
                )
                await self._persist()
        except asyncio.CancelledError:
            if cancel.is_set():
                job.update(state="cancelled", error=None, updated_at=self.clock())
                await self._persist()
            else:
                job.update(state="interrupted", error="Worker stopped", updated_at=self.clock())
                await self._persist()
        except (DownloadError, OSError, asyncio.TimeoutError) as exc:
            job.update(state="failed", error=str(exc)[:512], updated_at=self.clock())
            await self._persist()
        finally:
            stage.unlink(missing_ok=True)
            self._private.pop(identifier, None)


__all__ = [
    "DownloadError",
    "DownloadLimits",
    "DownloadService",
    "PinnedHTTPSource",
    "ResolvedTarget",
    "atomic_publish",
    "resolve_public_target",
    "validate_target_path",
]
