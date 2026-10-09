from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from chatshare.errors import ChatShareError


def test_remote_client_lists_authenticated_directory_without_local_instance():
    from chatshare.remote import RemoteClient, RemoteSettings

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == "GET"
        assert request.url.path == "/videos"
        assert request.url.query == b"json"
        return httpx.Response(
            200,
            json={
                "path": "/videos/",
                "paths": [
                    {"name": "clip.mov", "path_type": "File", "size": 12},
                    {"name": "raw", "path_type": "Dir", "size": 0},
                ],
            },
        )

    client = RemoteClient(
        RemoteSettings("https://share.example.test", "writer", "not-a-real-secret"),
        transport=httpx.MockTransport(handler),
    )

    result = client.list_directory("videos")

    assert result["path"] == "videos"
    assert result["entries"] == 2
    assert result["lines"] == ["videos/", "+-- raw/", "`-- clip.mov"]
    assert seen[0].headers["authorization"].startswith("Basic ")


def test_remote_client_streams_file_after_preflight_and_emits_progress(tmp_path):
    from chatshare.remote import RemoteClient, RemoteSettings

    source = tmp_path / "video.mov"
    source.write_bytes(b"x" * (2 * 1024 * 1024 + 23))
    received = bytearray()
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "HEAD":
            return httpx.Response(404)
        if request.method == "MKCOL":
            return httpx.Response(201)
        if request.method == "PUT":
            assert request.extensions["timeout"]["read"] == 120
            assert request.extensions["timeout"]["write"] is None
            assert request.headers["content-length"] == str(source.stat().st_size)
            for chunk in request.stream:
                received.extend(chunk)
            return httpx.Response(201)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    updates = []
    client = RemoteClient(
        RemoteSettings("https://share.example.test", "writer", "not-a-real-secret"),
        transport=httpx.MockTransport(handler),
    )

    result = client.publish_file(source, "videos/2026/video.mov", progress=updates.append)

    assert calls == [
        ("HEAD", "/videos/2026/video.mov"),
        ("MKCOL", "/videos"),
        ("MKCOL", "/videos/2026"),
        ("PUT", "/videos/2026/video.mov"),
    ]
    assert bytes(received) == source.read_bytes()
    assert [update.transferred for update in updates] == sorted(
        update.transferred for update in updates
    )
    assert updates[0].transferred == 0
    assert updates[-1].transferred == source.stat().st_size
    assert result["path"] == "videos/2026/video.mov"
    assert result["size"] == source.stat().st_size
    assert result["source"] == str(source.resolve())
    assert result["url"] == "https://share.example.test/videos/2026/video.mov"
    assert result["sha256"] == __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    assert "not-a-real-secret" not in str(result)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://share.example.test",
        "https://writer:password@share.example.test",
        "https://share.example.test/?unexpected=query",
        "https://share.example.test/#unexpected-fragment",
    ],
)
def test_remote_settings_rejects_unsafe_or_ambiguous_base_url(base_url):
    from chatshare.remote import RemoteSettings

    with pytest.raises(ChatShareError):
        RemoteSettings(base_url, "writer", "not-a-real-secret")


def test_remote_settings_allows_http_only_for_loopback():
    from chatshare.remote import RemoteSettings

    assert RemoteSettings("http://127.0.0.1:5000", "writer", "not-a-real-secret").base_url == (
        "http://127.0.0.1:5000"
    )
