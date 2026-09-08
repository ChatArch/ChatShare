"""In-memory browser authentication gate in front of an unchanged loopback Dufs."""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import secrets
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit

import httpx
import anyio
from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

from chatshare.dufs.config import load_instance_state
from chatshare.paths import ChatSharePaths

COOKIE = "chatshare_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
RAW_FLAGS = {"raw", "download", "cache", "token"}
HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
PRIVATE_HEADERS = {
    "cache-control": "no-store",
    "vary": "Cookie, Authorization",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}
FILE_CSP = "sandbox allow-scripts allow-downloads; frame-ancestors *"
ASSET_PREFIX = re.compile(r"/__dufs_v\d+\.\d+\.\d+__/")


@dataclass(repr=False)
class Session:
    username: str
    authorization: str
    expires: float


def _decode(value: str) -> str:
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("encoding")
    decoded = unquote(value, encoding="utf-8", errors="strict")
    if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
        raise ValueError("control")
    if "\\" in decoded or "%" in decoded:
        raise ValueError("ambiguous encoding")
    return decoded


def _safe_next(value: str) -> str:
    decoded = _decode(value)
    if (
        not decoded.startswith("/")
        or decoded.startswith("//")
        or urlsplit(decoded).netloc
    ):
        raise ValueError("next")
    return value


def _headers(headers, excluded=()):
    connection = {
        part.strip().lower() for part in headers.get("connection", "").split(",")
    }
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in HOP_HEADERS | connection | set(excluded)
    }


class _OwnedStream(StreamingResponse):
    def __init__(self, upstream_response, client, **kwargs):
        self.upstream_response = upstream_response
        self.client = client
        super().__init__(upstream_response.aiter_raw(chunk_size=65536), **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.move_on_after(5, shield=True):
                await self.upstream_response.aclose()
                await self.client.aclose()


class _ExactTrustedHost(TrustedHostMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        hosts = [
            value.decode("latin-1")
            for name, value in scope["headers"]
            if name.lower() == b"host"
        ]
        valid = False
        if len(hosts) == 1:
            try:
                host = urlsplit("//" + hosts[0])
                valid = (
                    host.hostname in self.allowed_hosts
                    and not host.username
                    and not host.password
                    and not host.path
                    and not host.query
                    and not host.fragment
                    and (host.port is None or 1 <= host.port <= 65535)
                    and not any(character.isspace() for character in hosts[0])
                )
            except ValueError:
                pass
        if not valid:
            return await Response(status_code=400, headers=PRIVATE_HEADERS)(
                scope, receive, send
            )
        return await self.app(scope, receive, send)


class _InflightLimit:
    def __init__(self, app, limit):
        self.app = app
        self.limit = limit
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if self.active >= self.limit:
            return await Response(status_code=503, headers=PRIVATE_HEADERS)(
                scope, receive, send
            )
        self.active += 1

        async def private_send(message):
            if message["type"] == "http.response.start":
                replaced = {name.encode() for name in PRIVATE_HEADERS}
                message["headers"] = [
                    (name, value)
                    for name, value in message["headers"]
                    if name.lower() not in replaced
                ]
                message["headers"].extend(
                    (name.encode(), value.encode())
                    for name, value in PRIVATE_HEADERS.items()
                )
            await send(message)

        try:
            await self.app(scope, receive, private_send)
        finally:
            self.active -= 1


def create_app(
    paths: ChatSharePaths | None = None,
    *,
    root: Path | None = None,
    upstream: str | None = None,
    public_url: str | None = None,
    allowed_hosts=(),
    transport=None,
    clock=time.monotonic,
    session_ttl: int = 3600,
    max_sessions: int = 256,
    login_limit: int = 30,
    max_inflight: int = 64,
):
    """Create an ASGI app; explicit settings/transport provide an offline test seam."""
    if root is None or upstream is None or public_url is None:
        state = load_instance_state(paths or ChatSharePaths.from_home())
        root = state.root
        host = "[::1]" if state.bind == "::1" else "127.0.0.1"
        upstream = f"http://{host}:{state.port}"
        public_url = state.base_url
    target = urlsplit(upstream)
    public = urlsplit(public_url)
    if (
        target.scheme != "http"
        or not ipaddress.ip_address(target.hostname).is_loopback
        or target.username
        or target.password
        or target.path not in ("", "/")
        or target.query
        or target.fragment
    ):
        raise ValueError("Dufs upstream must be numeric HTTP loopback without a path")
    if (
        public.scheme not in ("http", "https")
        or not public.hostname
        or public.username
        or public.password
        or public.path not in ("", "/")
        or public.query
        or public.fragment
    ):
        raise ValueError("Public URL must be an HTTP(S) origin")
    if not all(
        type(value) is int and value > 0
        for value in (session_ttl, max_sessions, login_limit, max_inflight)
    ):
        raise ValueError("Gateway limits must be positive integers")
    if any(
        not host or any(character in host for character in "*/:@")
        for host in allowed_hosts
    ):
        raise ValueError("Allowed hosts must be exact hostnames")
    origin = str(httpx.URL(public_url)).rstrip("/")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("The managed root must be a directory")
    sessions: dict[str, Session] = {}
    attempts: list[float] = []
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        _ExactTrustedHost,
        allowed_hosts=[
            public.hostname,
            "localhost",
            "127.0.0.1",
            "::1",
            *allowed_hosts,
        ],
        www_redirect=False,
    )
    app.add_middleware(_InflightLimit, limit=max_inflight)

    def client():
        return httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(30, connect=5),
            follow_redirects=False,
            trust_env=False,
        )

    def csrf(request):
        fetch_site = request.headers.get("sec-fetch-site")
        return (
            request.headers.get("x-chatshare-csrf") == "1"
            and request.headers.get("origin") == origin
            and fetch_site in (None, "same-origin")
        )

    def expire():
        now = clock()
        for token in list(sessions):
            if sessions[token].expires <= now:
                del sessions[token]

    async def check(authorization=None):
        headers = {"authorization": authorization} if authorization else {}
        async with client() as connection:
            async with connection.stream(
                "CHECKAUTH", upstream + "/", headers=headers
            ) as response:
                return response.status_code == 200, response.headers.get(
                    "www-authenticate"
                )

    async def session(request):
        expire()
        token = request.cookies.get(COOKIE)
        current = sessions.get(token)
        if current:
            valid, _ = await check(current.authorization)
            if (
                not valid
                or current.expires <= clock()
                or sessions.get(token) is not current
            ):
                sessions.pop(token, None)
                return None
        return current

    def error(status):
        return Response(status_code=status, headers=PRIVATE_HEADERS)

    async def denied(request):
        if (
            request.method in {"GET", "HEAD"}
            and "text/html" in request.headers.get("accept", "")
            and request.headers.get("sec-fetch-mode", "navigate") == "navigate"
        ):
            next_url = quote(
                str(request.url.path)
                + ("?" + request.url.query if request.url.query else ""),
                safe="",
            )
            return RedirectResponse(
                "/_chatshare/login?next=" + next_url,
                status_code=303,
                headers=PRIVATE_HEADERS,
            )
        response = error(401)
        if request.headers.get("x-chatshare-csrf") != "1" and request.headers.get(
            "sec-fetch-mode"
        ) not in {"cors", "same-origin"}:
            _, challenge = await check()
            if challenge:
                response.headers["www-authenticate"] = challenge
        return response

    async def gateway_endpoint(request, path):
        if path == "/_chatshare/health" and request.method in {"GET", "HEAD"}:
            return JSONResponse({"ok": True}, headers=PRIVATE_HEADERS)
        if path.startswith("/_chatshare/assets/") and request.method in {"GET", "HEAD"}:
            name = path.removeprefix("/_chatshare/assets/")
            package = (
                "chatshare.assets.gateway"
                if name in {"login.js", "login.css"}
                else "chatshare.assets.dufs"
            )
            types = {
                "index.js": "text/javascript",
                "index.css": "text/css",
                "favicon.ico": "image/x-icon",
                "login.js": "text/javascript",
                "login.css": "text/css",
            }
            if name not in types:
                return error(404)
            content = resources.files(package).joinpath(name).read_bytes()
            return Response(
                content if request.method == "GET" else b"",
                media_type=types[name],
                headers=PRIVATE_HEADERS,
            )
        if path == "/_chatshare/login" and request.method in {"GET", "HEAD"}:
            _safe_next(request.query_params.get("next", "/"))
            content = (
                resources.files("chatshare.assets.gateway")
                .joinpath("login.html")
                .read_text(encoding="utf-8")
            )
            return HTMLResponse(
                content if request.method == "GET" else "",
                headers={
                    **PRIVATE_HEADERS,
                    "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
                },
            )
        if path == "/_chatshare/session" and request.method == "GET":
            current = await session(request)
            payload = {"authenticated": bool(current)}
            if current:
                payload["username"] = current.username
            return JSONResponse(payload, headers=PRIVATE_HEADERS)
        if (
            path not in {"/_chatshare/login", "/_chatshare/logout"}
            or request.method != "POST"
        ):
            return error(404)
        if not csrf(request):
            return error(403)
        if path == "/_chatshare/logout":
            sessions.pop(request.cookies.get(COOKIE), None)
            response = JSONResponse({"authenticated": False}, headers=PRIVATE_HEADERS)
            response.delete_cookie(
                COOKIE,
                path="/",
                secure=public.scheme == "https",
                httponly=True,
                samesite="strict",
            )
            return response
        now = clock()
        attempts[:] = [stamp for stamp in attempts if stamp > now - 60]
        if len(attempts) >= login_limit:
            return error(429)
        attempts.append(now)
        body = bytearray()
        with anyio.fail_after(10):
            async for chunk in request.stream():
                if len(body) + len(chunk) > 4096:
                    return error(413)
                body.extend(chunk)
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return error(415)
        try:
            payload = json.loads(body)
            username, password = payload["username"], payload["password"]
            if (
                not isinstance(username, str)
                or not isinstance(password, str)
                or not 1 <= len(username) <= 128
                or not 1 <= len(password) <= 1024
                or ":" in username
                or any(ord(character) < 32 for character in username + password)
            ):
                return error(400)
        except (ValueError, KeyError, TypeError):
            return error(400)
        authorization = (
            "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )
        valid, _ = await check(authorization)
        if not valid:
            return error(401)
        expire()
        sessions.pop(request.cookies.get(COOKIE), None)
        if len(sessions) >= max_sessions:
            return error(429)
        token = secrets.token_urlsafe(32)
        sessions[token] = Session(username, authorization, clock() + session_ttl)
        response = JSONResponse(
            {"authenticated": True, "username": username}, headers=PRIVATE_HEADERS
        )
        response.set_cookie(
            COOKIE,
            token,
            max_age=session_ttl,
            secure=public.scheme == "https",
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    async def proxy(request, raw_target, current, concrete):
        explicit = request.headers.get("authorization")
        authenticated = bool(explicit or current)
        headers = _headers(
            request.headers,
            {
                "host",
                "cookie",
                "authorization",
                "accept-encoding",
                "forwarded",
                "x-forwarded-host",
                "x-forwarded-proto",
                "x-forwarded-for",
                "x-chatshare-csrf",
            },
        )
        headers["accept-encoding"] = "identity"
        if explicit:
            headers["authorization"] = explicit
        elif current and not concrete:
            headers["authorization"] = current.authorization
        connection = client()
        response = None
        transferred = False
        try:
            outgoing = connection.build_request(
                request.method,
                upstream + raw_target,
                headers=headers,
                content=request.stream(),
            )
            outgoing.headers.pop("connection", None)
            response = await connection.send(outgoing, stream=True)
            selected = _headers(
                response.headers,
                {
                    "set-cookie",
                    "access-control-allow-origin",
                    "access-control-allow-credentials",
                },
            )
            selected.update(PRIVATE_HEADERS)
            marker = bool(
                re.fullmatch(
                    r'(?:inline|attachment); filename="[^\r\n]*"(?:; filename\*=UTF-8\'\'[^\r\n]*)?',
                    response.headers.get("content-disposition", ""),
                    re.IGNORECASE,
                )
            )
            if response.status_code in {401, 403}:
                if current:
                    sessions.pop(request.cookies.get(COOKIE), None)
                result = error(response.status_code)
                if explicit and response.headers.get("www-authenticate"):
                    result.headers["www-authenticate"] = response.headers[
                        "www-authenticate"
                    ]
                return result
            if 300 <= response.status_code < 400 and response.status_code != 304:
                location = response.headers.get("location", "")
                if not authenticated:
                    return error(403)
                try:
                    _safe_next(location)
                except ValueError:
                    return error(502)
                return Response(
                    status_code=response.status_code,
                    headers={**PRIVATE_HEADERS, "location": location},
                )
            if response.status_code in {304, 404, 416}:
                selected = {
                    name: value
                    for name, value in selected.items()
                    if name
                    in {"etag", "last-modified", "content-range", "accept-ranges"}
                }
                selected.update(PRIVATE_HEADERS)
                if concrete:
                    selected["content-security-policy"] = FILE_CSP
                return Response(status_code=response.status_code, headers=selected)
            if response.status_code >= 400:
                return error(response.status_code)
            if not authenticated and (
                response.status_code not in {200, 206} or not marker
            ):
                return error(403)
            if concrete and response.status_code in {200, 206} and not marker:
                return error(403)
            if marker:
                selected["content-security-policy"] = FILE_CSP
            elif (
                authenticated
                and request.method == "GET"
                and response.status_code == 200
                and response.headers.get("content-type", "").startswith("text/html")
            ):
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > 2 * 1024 * 1024:
                        return error(502)
                    body.extend(chunk)
                html = body.decode("utf-8")
                if '<template id="index-data">' not in html or not ASSET_PREFIX.search(
                    html
                ):
                    return error(502)
                html = ASSET_PREFIX.sub("/_chatshare/assets/", html)
                html = html.replace(
                    "<head>", '<head><meta name="chatshare-gateway" content="1">', 1
                )
                selected.pop("content-length", None)
                selected.pop("content-encoding", None)
                selected.pop("etag", None)
                selected["content-security-policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
                )
                return HTMLResponse(html, headers=selected)
            if request.method == "HEAD":
                return Response(status_code=response.status_code, headers=selected)
            if response.is_stream_consumed:
                return Response(
                    response.content, status_code=response.status_code, headers=selected
                )
            transferred = True
            return _OwnedStream(
                response, connection, status_code=response.status_code, headers=selected
            )
        finally:
            if not transferred:
                with anyio.move_on_after(5, shield=True):
                    if response is not None:
                        await response.aclose()
                    await connection.aclose()

    @app.api_route(
        "/{path:path}",
        methods=[
            "GET",
            "HEAD",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
            "PROPFIND",
            "PROPPATCH",
            "MKCOL",
            "MOVE",
            "COPY",
            "LOCK",
            "UNLOCK",
            "CHECKAUTH",
        ],
    )
    async def dispatch(request: Request, path: str):
        try:
            raw_path = request.scope["raw_path"].decode("ascii")
            decoded = _decode(raw_path)
            query = request.scope["query_string"].decode("ascii")
            _decode(query)
            if (
                not decoded.startswith("/")
                or "//" in decoded
                or any(part in {".", ".."} for part in decoded.split("/"))
            ):
                return error(400)
            if decoded.startswith("/_chatshare/"):
                return await gateway_endpoint(request, decoded)
            candidate = (root / decoded.lstrip("/")).resolve()
            if not candidate.is_relative_to(root):
                return error(400)
            flags = parse_qsl(
                query, keep_blank_values=True, strict_parsing=False, max_num_fields=32
            )
            concrete = (
                request.method in {"GET", "HEAD"}
                and candidate.is_file()
                and not decoded.endswith("/")
                and all(name in RAW_FLAGS for name, _ in flags)
            )
            if any(name == "token" for name, _ in flags) and not concrete:
                return error(403)
            explicit = request.headers.get("authorization")
            if explicit is not None and not explicit.lower().startswith(
                ("basic ", "digest ")
            ):
                return error(401)
            current = None if explicit else await session(request)
            if (
                current
                and not explicit
                and request.method not in SAFE_METHODS
                and not csrf(request)
            ):
                return error(403)
            if not concrete and not explicit and not current:
                return await denied(request)
            return await proxy(
                request, raw_path + ("?" + query if query else ""), current, concrete
            )
        except (ValueError, UnicodeError, OSError):
            return error(400)
        except httpx.HTTPError:
            return error(502)
        except TimeoutError:
            return error(408)

    return app
