import asyncio
import ipaddress
import json
import os
from pathlib import Path

import pytest

from chatshare.downloads import (
    DownloadError,
    DownloadLimits,
    DownloadService,
    PinnedHTTPSource,
    ResolvedTarget,
    atomic_publish,
    resolve_public_target,
    validate_target_path,
)


def run(awaitable):
    return asyncio.run(awaitable)


def test_url_policy_rejects_secrets_unsafe_ports_fragments_and_private_answers():
    async def resolver(host, port):
        assert host == "files.example"
        return ["203.0.113.10"]

    for url in (
        "ftp://files.example/a",
        "http://user:secret@files.example/a",
        "http://files.example:8080/a",
        "https://files.example/a#secret",
        "http://files.example/a\nInjected: yes",
        "http://127.0.0.1/a",
        "http://[::1]/a",
        "http://[::ffff:127.0.0.1]/a",
        "http://[2002:7f00:1::]/a",
        "http://[64:ff9b::7f00:1]/a",
        "http://[64:ff9b:1::1]/a",
        "http://[fe80::1]/a",
        "http://169.254.169.254/latest/meta-data/",
    ):
        with pytest.raises(DownloadError):
            run(resolve_public_target(url, resolver=resolver))


def test_url_policy_requires_every_dns_answer_to_be_public_and_returns_safe_label():
    async def mixed(host, port):
        return ["93.184.216.34", "10.0.0.1"]

    with pytest.raises(DownloadError, match="public"):
        run(resolve_public_target("https://files.example/path?signature=secret", resolver=mixed))

    async def public(host, port):
        return ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]

    target = run(resolve_public_target("https://files.example/path?signature=secret", resolver=public))
    assert target.host_label == "files.example"
    assert target.port == 443
    assert target.ips == (ipaddress.ip_address("93.184.216.34"), ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946"))
    assert "secret" not in repr(target)


def test_httpx_source_pins_numeric_peer_but_preserves_host_and_tls_identity():
    seen = []

    class Stream(__import__("httpx").AsyncByteStream):
        async def __aiter__(self):
            yield b"abc"

    async def handler(request):
        seen.append(request)
        return __import__("httpx").Response(200, headers={"content-length": "3"}, stream=Stream())

    target = ResolvedTarget(
        "https://files.example/path?secret=x", "https", "files.example", 443,
        "/path?secret=x", "files.example", (ipaddress.ip_address("93.184.216.34"),),
    )

    async def scenario():
        source = PinnedHTTPSource(lambda: __import__("httpx").MockTransport(handler))
        return [item async for item in source.stream(target, DownloadLimits(), asyncio.Event())]

    assert run(scenario()) == [{"status": 200, "length": 3, "location": None}, b"abc"]
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "files.example"
    assert seen[0].extensions["sni_hostname"] == "files.example"


def test_target_path_rejects_ambiguous_and_unsafe_names():
    for value in ("", "/abs", "../x", "a/../x", "a//x", "a\\x", "a/%2e/x", "a\x00x", ".", "a/."):
        with pytest.raises(DownloadError):
            validate_target_path(value)
    assert validate_target_path("folder/文件.bin") == ("folder", "文件.bin")


def test_atomic_publish_is_no_overwrite_and_rejects_symlink_parent(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.write_bytes(b"complete")
    atomic_publish(stage, root, ("folder", "file.bin"))
    assert (root / "folder/file.bin").read_bytes() == b"complete"
    assert not stage.exists()

    second = tmp_path / "second"
    second.write_bytes(b"replacement")
    with pytest.raises(DownloadError, match="exists"):
        atomic_publish(second, root, ("folder", "file.bin"))
    assert (root / "folder/file.bin").read_bytes() == b"complete"

    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    third = tmp_path / "third"
    third.write_bytes(b"escape")
    with pytest.raises(DownloadError):
        atomic_publish(third, root, ("link", "file.bin"))
    assert not (outside / "file.bin").exists()


def test_atomic_publish_rolls_back_a_link_when_directory_sync_fails(tmp_path, monkeypatch):
    root = tmp_path / "root"; root.mkdir()
    stage = tmp_path / "stage"; stage.write_bytes(b"complete")
    monkeypatch.setattr(os, "fsync", lambda descriptor: (_ for _ in ()).throw(OSError("test sync failure")))
    with pytest.raises(DownloadError, match="publish"):
        atomic_publish(stage, root, ("file.bin",))
    assert stage.read_bytes() == b"complete"
    assert not (root / "file.bin").exists()


class FakeSource:
    def __init__(self, chunks, *, length=None, status=200, redirect=None, pause=None):
        self.chunks = chunks
        self.length = length
        self.status = status
        self.redirect = redirect
        self.pause = pause
        self.calls = []

    async def stream(self, target, limits, cancel):
        self.calls.append(target)
        if self.redirect:
            yield {"status": 302, "location": self.redirect, "length": 0}
            return
        yield {"status": self.status, "length": self.length}
        for chunk in self.chunks:
            if self.pause:
                await self.pause.wait()
            if cancel.is_set():
                raise asyncio.CancelledError
            yield chunk


async def allow(*args):
    return True


async def public_resolver(host, port):
    return ["93.184.216.34"]


def make_service(tmp_path, source, **limit_overrides):
    limits = DownloadLimits(**limit_overrides)
    return DownloadService(
        base=tmp_path / "private",
        share_root=tmp_path / "share",
        source=source,
        resolver=public_resolver,
        limits=limits,
    )


def test_service_streams_counts_hashes_and_persists_only_safe_source(tmp_path):
    source = FakeSource([b"abc", b"def"], length=6)
    service = make_service(tmp_path, source)

    async def scenario():
        await service.start()
        job = await service.create("alice", "https://files.example/file?token=secret", "x.bin", allow)
        await service.join()
        result = service.get("alice", job["id"])
        await service.close()
        return result

    result = run(scenario())
    assert result["state"] == "completed"
    assert result["transferred"] == 6
    assert result["total"] == 6
    assert result["sha256"] == "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"
    assert result["source_host"] == "files.example"
    assert "token" not in json.dumps(result)
    assert (tmp_path / "share/x.bin").read_bytes() == b"abcdef"
    assert "secret" not in (tmp_path / "private/jobs.json").read_text()


@pytest.mark.parametrize(
    "source,limit,error",
    [
        (FakeSource([b"short"], length=8), {}, "truncated"),
        (FakeSource([b"too-large"], length=9), {"max_file_size": 8}, "large"),
        (FakeSource([], status=404), {}, "HTTP 404"),
    ],
)
def test_stream_failures_clean_private_partial_and_publish_nothing(tmp_path, source, limit, error):
    service = make_service(tmp_path, source, **limit)

    async def scenario():
        await service.start()
        job = await service.create("alice", "https://files.example/file", "x.bin", allow)
        await service.join()
        result = service.get("alice", job["id"])
        await service.close()
        return result

    result = run(scenario())
    assert result["state"] == "failed"
    assert error.lower() in result["error"].lower()
    assert not (tmp_path / "share/x.bin").exists()
    assert list((tmp_path / "private/staging").iterdir()) == []


def test_total_deadline_stops_non_idle_trickle_and_releases_worker(tmp_path):
    class TrickleSource:
        async def stream(self, target, limits, cancel):
            yield {"status": 200, "length": None}
            while True:
                await asyncio.sleep(0.01)
                yield b"x"

    service = make_service(tmp_path, TrickleSource(), concurrency=1, total_timeout=0.2, idle_timeout=2)

    async def scenario():
        await service.start()
        try:
            first = await service.create("alice", "https://files.example/trickle", "slow.bin", allow)
            await asyncio.wait_for(service.join(), timeout=1)
            failed = service.get("alice", first["id"])
            assert failed["state"] == "failed"
            assert "total" in failed["error"].lower()
            assert failed["transferred"] > 0
            assert not (tmp_path / "share/slow.bin").exists()
            assert list((tmp_path / "private/staging").iterdir()) == []
            service.source = FakeSource([b"ok"], length=2)
            second = await service.create("alice", "https://files.example/next", "next.bin", allow)
            await asyncio.wait_for(service.join(), timeout=1)
            assert service.get("alice", second["id"])["state"] == "completed"
        finally:
            await service.close()

    run(scenario())


def test_owner_visibility_namespace_conflicts_queue_bound_and_commit_revalidation(tmp_path):
    gate_calls = []

    async def gate(user, target):
        gate_calls.append((user, target))
        return len(gate_calls) == 1

    blocker = asyncio.Event()
    service = make_service(tmp_path, FakeSource([b"abc"], length=3, pause=blocker), concurrency=1, max_pending=2)

    async def scenario():
        await service.start()
        first = await service.create("alice", "https://files.example/a", "folder/a", gate)
        with pytest.raises(DownloadError, match="conflict"):
            await service.create("alice", "https://files.example/b", "folder", allow)
        with pytest.raises(DownloadError, match="owner"):
            service.get("bob", first["id"])
        blocker.set()
        await service.join()
        result = service.get("alice", first["id"])
        await service.close()
        return first, result

    first, result = run(scenario())
    assert first["state"] == "queued"
    assert result["state"] == "failed"
    assert "permission" in result["error"].lower()
    assert len(gate_calls) == 2
    assert not (tmp_path / "share/folder/a").exists()


def test_cancel_and_restart_recovery_have_terminal_truthful_states(tmp_path):
    blocker = asyncio.Event()
    service = make_service(tmp_path, FakeSource([b"abc"], length=3, pause=blocker))

    async def cancel_scenario():
        await service.start()
        job = await service.create("alice", "https://files.example/a", "a.bin", allow)
        await asyncio.sleep(0)
        cancelled = await service.cancel("alice", job["id"])
        await service.join()
        result = service.get("alice", job["id"])
        await service.close()
        return cancelled, result

    cancelled, result = run(cancel_scenario())
    assert cancelled["state"] in {"downloading", "cancelled"}
    assert result["state"] == "cancelled"
    assert not (tmp_path / "share/a.bin").exists()

    private = tmp_path / "recover"
    private.mkdir(mode=0o700)
    (private / "staging").mkdir(mode=0o700)
    (private / "staging/orphan.part").write_bytes(b"partial")
    (private / "jobs.json").write_text(json.dumps({"schema": 1, "jobs": [{"id": "j1", "owner": "alice", "state": "downloading", "target": "x", "source_host": "example.com", "transferred": 1, "total": None, "sha256": None, "error": None, "created_at": 1, "updated_at": 1, "started_at": 1}]}))
    recovered = DownloadService(base=private, share_root=tmp_path / "other-share", source=FakeSource([]), resolver=public_resolver)
    run(recovered.start())
    assert recovered.get("alice", "j1")["state"] == "interrupted"
    assert list((private / "staging").iterdir()) == []
    assert oct(private.stat().st_mode & 0o777) == "0o700"
    assert oct((private / "jobs.json").stat().st_mode & 0o777) == "0o600"


def test_real_pinned_http_source_rejects_negative_chunk_framing():
    async def scenario():
        async def handle(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n-1\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        try:
            server = await asyncio.start_server(handle, "127.0.0.1", 0)
        except OSError as exc:
            pytest.skip(f"loopback bind unavailable in test sandbox: {exc}")
        try:
            port = server.sockets[0].getsockname()[1]
            # Explicit low-level fixture target; production resolves and rejects
            # loopback before constructing a PinnedHTTPSource request.
            target = ResolvedTarget("http://files.example/a", "http", "files.example", port,
                                    "/a", "files.example", (ipaddress.ip_address("127.0.0.1"),))
            source = PinnedHTTPSource()
            with pytest.raises(DownloadError, match="invalid chunk framing"):
                async for _ in source.stream(target, DownloadLimits(), asyncio.Event()):
                    pass
        finally:
            server.close()
            await server.wait_closed()

    run(scenario())


def test_runtime_root_symlink_is_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "private"
    link.symlink_to(actual, target_is_directory=True)
    service = DownloadService(base=link, share_root=tmp_path / "share", source=FakeSource([]), resolver=public_resolver)
    with pytest.raises(DownloadError, match="symlink"):
        run(service.start())

    nested = DownloadService(base=link / "nested", share_root=tmp_path / "share2", source=FakeSource([]), resolver=public_resolver)
    with pytest.raises(DownloadError, match="symlink"):
        run(nested.start())
