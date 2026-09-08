import base64
import asyncio

import httpx
import pytest

from chatshare.gateway import create_app


CSRF = {"Origin": "https://share.example", "X-ChatShare-CSRF": "1"}
GOOD = "Basic " + base64.b64encode(b"alice:correct-secret").decode()
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
)


class LocalClient:
    def __init__(self, app):
        self.loop = asyncio.new_event_loop()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://share.example",
            follow_redirects=True,
        )
        self.cookies = self.client.cookies

    def request(self, method, path, **kwargs):
        return self.loop.run_until_complete(self.client.request(method, path, **kwargs))

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def close(self):
        self.loop.run_until_complete(self.client.aclose())
        self.loop.close()


@pytest.fixture
def gateway(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "image.png").write_bytes(PNG)
    (root / "active.html").write_text('<!doctype html><script>fetch("/?json")</script>')
    (root / "space name.txt").write_bytes(b"file-bytes")
    (root / "dotted.dir").mkdir()
    outside = tmp_path / "outside"
    outside.write_text("private")
    (root / "escape").symlink_to(outside)
    calls = []
    control = {"valid": True, "marker": True, "status": 200, "now": 0}

    def upstream(request):
        calls.append(request)
        authorization = request.headers.get("authorization")
        valid = control["valid"] and authorization in (
            GOOD,
            "Digest real-client-header",
        )
        if request.method == "CHECKAUTH" or authorization and not valid:
            return httpx.Response(
                200 if valid else 401,
                content=b"alice" if valid else b"PRIVATE ERROR",
                headers={"www-authenticate": 'Digest realm="DUFS", nonce="nonce"'},
            )
        if request.url.path in ("/image.png", "/active.html", "/space name.txt"):
            headers = {
                "content-type": "image/png"
                if request.url.path == "/image.png"
                else "text/html",
                "etag": '"tag"',
                "accept-ranges": "bytes",
            }
            if control["marker"]:
                headers["content-disposition"] = 'inline; filename="image.png"'
            status = control["status"]
            body = (root / request.url.path.lstrip("/")).read_bytes()
            if "range" in request.headers:
                status = 206
                headers["content-range"] = f"bytes 0-3/{len(body)}"
                body = body[:4]
            return httpx.Response(
                status,
                headers=headers,
                content=body if control["marker"] else b"SECRET LISTING",
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b'<html><head></head><body><template id="index-data">{"user":"alice","paths":["SECRET LISTING"]}</template><script src="/__dufs_v0.46.0__/index.js"></script></body></html>',
        )

    app = create_app(
        root=root,
        upstream="http://127.0.0.1:5000",
        public_url="https://share.example",
        transport=httpx.MockTransport(upstream),
        clock=lambda: control["now"],
        session_ttl=60,
        max_sessions=2,
        login_limit=5,
    )
    client = LocalClient(app)
    try:
        yield client, calls, control, root
    finally:
        client.close()


def login(client):
    return client.post(
        "/_chatshare/login",
        headers=CSRF,
        json={"username": "alice", "password": "correct-secret"},
    )


@pytest.mark.parametrize("status", [401, 403])
def test_session_write_rejection_revokes_only_rejected_credentials(gateway, status):
    client, calls, control, _ = gateway
    assert login(client).status_code == 200
    control["status"] = status
    response = client.request("DELETE", "/image.png", headers=CSRF)
    assert response.status_code == status
    assert not response.content
    assert calls[-1].headers["authorization"] == GOOD
    expected = (
        {"authenticated": True, "username": "alice"}
        if status == 403
        else {"authenticated": False}
    )
    assert client.get("/_chatshare/session").json() == expected
    assert client.get("/").status_code == (200 if status == 403 else 401)


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_anonymous_file_rejection_does_not_revoke_browser_session(
    gateway, status, method
):
    client, calls, control, _ = gateway
    assert login(client).status_code == 200
    control["status"] = status
    response = client.request(method, "/image.png?token=invalid")
    assert response.status_code == status
    assert not response.content
    assert "authorization" not in calls[-1].headers
    assert client.get("/_chatshare/session").json() == {
        "authenticated": True,
        "username": "alice",
    }


def test_native_auth_rejection_does_not_revoke_browser_session(gateway):
    client, calls, _, _ = gateway
    assert login(client).status_code == 200
    response = client.request(
        "DELETE", "/image.png", headers={"Authorization": "Basic invalid"}
    )
    assert response.status_code == 401
    assert calls[-1].headers["authorization"] == "Basic invalid"
    assert client.get("/_chatshare/session").json() == {
        "authenticated": True,
        "username": "alice",
    }


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/dotted.dir",
        "/dotted.dir/",
        "/virtual/",
        "/?json",
        "/?q=x",
        "/?zip",
        "/image.png?json",
        "/image.png?%6ason",
        "/image.png?view",
        "/image.png?hash",
        "/image.png?tokengen",
        "/image.png?unknown",
        "/?token=secret",
        "/openapi.json",
        "/docs",
    ],
)
def test_anonymous_enumeration_denied(gateway, path):
    client, calls, _, _ = gateway
    response = client.get(path)
    assert response.status_code in (401, 403)
    assert "SECRET" not in response.text
    assert all(request.method == "CHECKAUTH" for request in calls)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "method", ["PROPFIND", "PUT", "DELETE", "MKCOL", "MOVE", "COPY", "PATCH", "OPTIONS"]
)
def test_anonymous_methods_denied(gateway, method):
    response = gateway[0].request(method, "/image.png")
    assert response.status_code in (401, 403)
    assert "SECRET" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/escape",
        "/%2e%2e/outside",
        "/%252e%252e/outside",
        "/bad%zz",
        "/bad%00",
        "/bad%5cname",
        "/image.png?%zz",
        "/%ff",
    ],
)
def test_invalid_paths(gateway, path):
    assert gateway[0].get(path).status_code == 400


@pytest.mark.parametrize(
    "method,headers,status",
    [("GET", {}, 200), ("HEAD", {}, 200), ("GET", {"Range": "bytes=0-3"}, 206)],
)
def test_raw_files(gateway, method, headers, status):
    client, calls, _, _ = gateway
    response = client.request(method, "/image.png?raw", headers=headers)
    assert response.status_code == status
    assert response.headers["etag"] == '"tag"'
    assert "sandbox" in response.headers["content-security-policy"]
    assert "allow-same-origin" not in response.headers["content-security-policy"]
    assert "authorization" not in calls[-1].headers
    assert "cookie" not in calls[-1].headers
    expected = PNG[:4] if status == 206 else PNG
    assert response.content == (b"" if method == "HEAD" else expected)
    assert response.headers["content-type"] == "image/png"


def test_race_and_safe_statuses(gateway):
    client, _, control, _ = gateway
    control["marker"] = False
    assert client.get("/image.png").status_code == 403
    for status in (304, 404, 416):
        control["status"] = status
        response = client.get("/image.png")
        assert response.status_code == status
        assert not response.content


def test_browser_login_redirect_and_next(gateway):
    client = gateway[0]
    response = client.get(
        "/dotted.dir", headers={"Accept": "text/html"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/_chatshare/login?next=")
    page = client.get(response.headers["location"])
    assert "登录" in page.text and "SECRET" not in page.text
    for target in ("//evil.example", "https://evil.example", "/%5cevil", "/%2f%2fevil"):
        assert (
            client.get("/_chatshare/login", params={"next": target}).status_code == 400
        )


def test_login_logout_rotation_and_expiry(gateway):
    client, calls, control, root = gateway
    assert client.get("/_chatshare/session").json() == {"authenticated": False}
    assert login(client).status_code == 200
    cookie = client.cookies.get("chatshare_session")
    assert cookie and len(cookie) >= 40
    assert client.get("/_chatshare/session").json() == {
        "authenticated": True,
        "username": "alice",
    }
    response = client.get("/")
    assert 'name="chatshare-gateway"' in response.text
    assert "/_chatshare/assets/index.js" in response.text
    assert "correct-secret" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "Cookie" in response.headers["vary"]
    assert client.post("/_chatshare/logout", headers=CSRF).status_code == 200
    client.cookies.set("chatshare_session", cookie)
    assert client.get("/").status_code == 401
    client.cookies.clear()
    assert login(client).status_code == 200
    control["valid"] = False
    assert client.get("/_chatshare/session").json() == {"authenticated": False}
    control["valid"] = True
    assert login(client).status_code == 200
    control["now"] = 61
    assert client.get("/").status_code == 401
    assert sorted(path.name for path in root.iterdir()) == [
        "active.html",
        "dotted.dir",
        "escape",
        "image.png",
        "space name.txt",
    ]


def test_login_failures_cookie_flags_limits(gateway):
    client = gateway[0]
    response = login(client)
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=60"):
        assert flag in response.headers["set-cookie"]
    assert (
        client.post(
            "/_chatshare/login",
            headers=CSRF,
            json={"username": "alice", "password": "wrong"},
        ).status_code
        == 401
    )
    assert (
        client.post("/_chatshare/login", headers=CSRF, content=b"x" * 4097).status_code
        == 413
    )
    for _ in range(5):
        response = login(client)
    assert response.status_code == 429


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "null", "X-ChatShare-CSRF": "1"},
        {"Origin": "https://evil.example", "X-ChatShare-CSRF": "1"},
        {**CSRF, "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_csrf(gateway, headers):
    client = gateway[0]
    assert client.post("/_chatshare/login", headers=headers, json={}).status_code == 403
    assert login(client).status_code == 200
    assert client.put("/new", headers=headers, content=b"data").status_code == 403
    assert client.post("/_chatshare/logout", headers=headers).status_code == 403


def test_native_auth_no_fallback_and_digest_retained(gateway):
    client, calls, _, _ = gateway
    assert client.get("/image.png", headers={"Authorization": ""}).status_code == 401
    assert (
        client.get("/image.png", headers={"Authorization": "Basic invalid"}).status_code
        == 401
    )
    assert calls[-1].headers["authorization"] == "Basic invalid"
    response = client.request(
        "PUT",
        "/new",
        headers={"Authorization": "Digest real-client-header"},
        content=b"upload",
    )
    assert response.status_code == 200
    assert calls[-1].method == "PUT"
    assert calls[-1].headers["authorization"] == "Digest real-client-header"


def test_hosts_assets_and_no_cors(gateway):
    client = gateway[0]
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/_chatshare/assets/index.js").status_code == 200
    assert client.get("/fake/index.js").status_code == 401
    response = client.get("/image.png", headers={"Origin": "https://blog.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert (
        client.get("/_chatshare/health", headers={"Host": "[::1]:5001"}).status_code
        == 200
    )
    assert (
        client.get(
            "/_chatshare/health",
            headers=[("Host", "share.example"), ("Host", "evil.example")],
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/_chatshare/health", headers={"Host": "share.example:invalid"}
        ).status_code
        == 400
    )


def test_reject_non_loopback_upstream(tmp_path):
    with pytest.raises(ValueError):
        create_app(
            root=tmp_path,
            upstream="http://example.com",
            public_url="https://share.example",
        )


def test_encoded_files_and_private_error_headers(gateway):
    client, _, control, _ = gateway
    assert client.get("/space%20name.txt?download").content == b"file-bytes"
    assert (
        client.get("/active.html")
        .headers["content-security-policy"]
        .startswith("sandbox ")
    )
    control["status"] = 500
    response = client.get("/image.png")
    assert response.status_code == 500 and not response.content
    for method in ("TRACE", "REPORT"):
        response = client.request(method, "/")
        assert response.headers["cache-control"] == "no-store"


def test_session_count_bound_and_unknown_cookie(gateway):
    client = gateway[0]
    client.cookies.set("chatshare_session", "unknown")
    assert client.get("/_chatshare/session").json() == {"authenticated": False}
    client.cookies.clear()
    assert login(client).status_code == 200
    client.cookies.clear()
    assert login(client).status_code == 200
    client.cookies.clear()
    assert login(client).status_code == 429


def test_native_challenge_and_ajax_suppression(gateway):
    client = gateway[0]
    response = client.request("PROPFIND", "/")
    assert response.headers["www-authenticate"].startswith("Digest ")
    response = client.get("/?json", headers={"X-ChatShare-CSRF": "1"})
    assert response.status_code == 401 and "www-authenticate" not in response.headers
    assert login(client).status_code == 200
    assert client.put("/new", headers=CSRF, content=b"data").status_code == 200
    assert client.get("/?token=secret").status_code == 403


def test_streaming_close_on_disconnect_and_marker_mismatch(tmp_path):
    (tmp_path / "file").write_bytes(b"content")

    class Feed(httpx.AsyncByteStream):
        def __init__(self):
            self.reads = 0
            self.closed = False

        async def __aiter__(self):
            for _ in range(1000):
                self.reads += 1
                yield b"x" * 65536

        async def aclose(self):
            self.closed = True

    async def exercise(marker, method="GET"):
        feed = Feed()
        headers = {"content-disposition": 'inline; filename="file"'} if marker else {}

        def upstream(request):
            return httpx.Response(200, headers=headers, stream=feed)

        app = create_app(
            root=tmp_path,
            upstream="http://127.0.0.1:5000",
            public_url="https://share.example",
            transport=httpx.MockTransport(upstream),
        )
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/file",
            "raw_path": b"/file",
            "query_string": b"",
            "headers": [(b"host", b"share.example")],
            "server": ("share.example", 443),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }
        starts = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                starts.append(message["status"])
            elif message.get("body") and marker:
                raise OSError("offline simulated disconnect")

        from starlette.requests import ClientDisconnect

        try:
            await app(scope, receive, send)
        except ClientDisconnect:
            pass
        assert feed.closed
        assert feed.reads == (1 if marker and method == "GET" else 0)
        assert starts == ([200] if marker else [403])

    asyncio.run(exercise(True))
    asyncio.run(exercise(False))
    asyncio.run(exercise(True, "HEAD"))


def test_inflight_bound_and_upstream_header_filtering(tmp_path):
    (tmp_path / "file").write_bytes(b"content")

    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()
        seen = []

        async def upstream(request):
            seen.append(request)
            entered.set()
            await release.wait()
            return httpx.Response(
                200,
                content=b"data",
                headers={
                    "content-disposition": 'inline; filename="file"',
                    "connection": "x-private",
                    "x-private": "remove",
                    "set-cookie": "upstream=secret",
                    "access-control-allow-origin": "*",
                },
            )

        app = create_app(
            root=tmp_path,
            upstream="http://127.0.0.1:5000",
            public_url="https://share.example",
            transport=httpx.MockTransport(upstream),
            max_inflight=1,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://share.example"
        ) as client:
            pending = asyncio.create_task(
                client.get(
                    "/file",
                    headers={
                        "Connection": "x-secret",
                        "X-Secret": "remove",
                        "Cookie": "unrelated=private",
                        "Forwarded": "host=evil.example",
                    },
                )
            )
            await entered.wait()
            assert (await client.get("/file")).status_code == 503
            release.set()
            response = await pending
            assert response.content == b"data"
            for name in (
                "x-private",
                "set-cookie",
                "access-control-allow-origin",
                "connection",
            ):
                assert name not in response.headers
            for name in ("x-secret", "cookie", "forwarded", "connection"):
                assert name not in seen[0].headers
            assert (await client.get("/file")).status_code == 200

    asyncio.run(exercise())


def test_upstream_failures_are_safe(tmp_path):
    def upstream(request):
        raise httpx.ConnectError("private upstream details")

    app = create_app(
        root=tmp_path,
        upstream="http://127.0.0.1:5000",
        public_url="https://share.example",
        transport=httpx.MockTransport(upstream),
    )
    client = LocalClient(app)
    try:
        response = login(client)
        assert response.status_code == 502 and not response.content
    finally:
        client.close()


def test_managed_state_factory_and_extra_host(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import chatshare.gateway as gateway_module
    from chatshare.paths import ChatSharePaths

    paths = ChatSharePaths.from_home(tmp_path / "home")
    seen = []

    def load(selected):
        assert selected == paths
        return SimpleNamespace(
            root=tmp_path,
            bind="localhost",
            port=5010,
            base_url="https://share.example:443",
        )

    def upstream(request):
        seen.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(gateway_module, "load_instance_state", load)
    app = create_app(
        paths,
        transport=httpx.MockTransport(upstream),
        allowed_hosts=("proxy.internal",),
    )
    client = LocalClient(app)
    try:
        response = client.get(
            "/_chatshare/health",
            headers={"Host": "proxy.internal", "X-Forwarded-Host": "evil.example"},
        )
        assert response.status_code == 200
        assert login(client).status_code == 200
        assert seen[-1].method == "CHECKAUTH"
        assert str(seen[-1].url) == "http://127.0.0.1:5010/"
        assert (
            client.post(
                "/_chatshare/logout",
                headers={"Origin": "https://proxy.internal", "X-ChatShare-CSRF": "1"},
            ).status_code
            == 403
        )
    finally:
        client.close()
