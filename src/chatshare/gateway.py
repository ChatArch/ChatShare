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
from chatlogin import (
    AccessDenied,
    AsyncCallbackBackend,
    MemorySessionStore,
    Principal,
    SessionManager,
    StoreFull,
    require_csrf as require_chatlogin_csrf,
)
from chatlogin.ui import LoginUI
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
class DufsRelayContext:
    username: str
    authorization: str
    expires_at: float


@dataclass(repr=False)
class CsrfBootstrap:
    csrf_token: str
    expires_at: float
    created_at: float


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
    session_manager = SessionManager(
        MemorySessionStore(max_sessions=max_sessions),
        instance="chatshare-gateway",
        ttl=session_ttl,
        clock=clock,
    )
    login_ui = LoginUI(
        title="ChatShare",
        subtitle="浏览目录和管理文件需要登录。已有的具体文件链接仍可直接访问。",
        palette="forest",
        layout="card",
    )
    relay_contexts: dict[str, DufsRelayContext] = {}
    csrf_bootstraps: dict[str, CsrfBootstrap] = {}
    state_lock = anyio.Lock()
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

    def csrf_origin(request):
        fetch_site = request.headers.get("sec-fetch-site")
        return (
            request.headers.get("origin") == origin
            and fetch_site in (None, "same-origin")
        )

    def expire_private():
        now = clock()
        session_manager.purge_expired()
        for digest, context in list(relay_contexts.items()):
            if context.expires_at <= now:
                relay_contexts.pop(digest, None)
        for digest, bootstrap in list(csrf_bootstraps.items()):
            if bootstrap.expires_at <= now:
                csrf_bootstraps.pop(digest, None)

    def bound_csrf_bootstraps():
        expire_private()
        overflow = len(csrf_bootstraps) - max_sessions
        if overflow <= 0:
            return
        oldest = sorted(
            csrf_bootstraps,
            key=lambda digest: csrf_bootstraps[digest].created_at,
        )
        for digest in oldest[:overflow]:
            csrf_bootstraps.pop(digest, None)

    async def check(authorization=None):
        headers = {"authorization": authorization} if authorization else {}
        async with client() as connection:
            async with connection.stream(
                "CHECKAUTH", upstream + "/", headers=headers
            ) as response:
                return response.status_code == 200, response.headers.get(
                    "www-authenticate"
                )

    async def authenticate(username, password):
        authorization = (
            "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )
        valid, _ = await check(authorization)
        if not valid:
            return None
        return Principal(username, username)

    backend = AsyncCallbackBackend(authenticate)

    def session_digest(token):
        return session_manager.digest(token)

    def revoke_token(token):
        digest = session_digest(token)
        if digest is not None:
            relay_contexts.pop(digest, None)
            csrf_bootstraps.pop(digest, None)
        session_manager.revoke(token)

    async def resolved_session(request):
        async with state_lock:
            expire_private()
            token = request.cookies.get(COOKIE)
            current = session_manager.resolve(token)
            digest = session_digest(token)
            context = relay_contexts.get(digest) if digest else None
            if current and context:
                return token, digest, current, context
            if current or context:
                revoke_token(token)
            return token, digest, None, None

    async def session(request):
        token, digest, current, context = await resolved_session(request)
        if not current or not context:
            return None, None
        valid, _ = await check(context.authorization)
        if not valid:
            async with state_lock:
                latest = session_manager.resolve(token)
                if latest is current and relay_contexts.get(digest) is context:
                    revoke_token(token)
            return None, None
        async with state_lock:
            if session_manager.resolve(token) is not current or relay_contexts.get(digest) is not context:
                return None, None
        return current, context

    async def csrf_context(request):
        token, digest, current, _ = await resolved_session(request)
        if current:
            return current
        async with state_lock:
            expire_private()
            token = request.cookies.get(COOKIE)
            digest = session_digest(token)
            if digest is not None:
                bootstrap = csrf_bootstraps.get(digest)
                if bootstrap and bootstrap.expires_at > clock():
                    return bootstrap
            return None

    async def ensure_csrf(request):
        if not csrf_origin(request):
            return False
        context = await csrf_context(request)
        if context is None:
            return False
        try:
            require_chatlogin_csrf(context, request.headers.get("x-csrf-token"))
        except AccessDenied:
            return False
        return True

    async def session_payload(request):
        current, _ = await session(request)
        if current:
            return {
                "authenticated": True,
                "username": current.principal.display_name or current.principal.user_id,
                "csrf_token": current.csrf_token,
            }, None
        token = request.cookies.get(COOKIE)
        async with state_lock:
            expire_private()
            digest = session_digest(token)
            bootstrap = csrf_bootstraps.get(digest) if digest else None
            if bootstrap is None or bootstrap.expires_at <= clock():
                token = secrets.token_urlsafe(32)
                digest = session_digest(token)
                now = clock()
                bootstrap = CsrfBootstrap(
                    secrets.token_urlsafe(32), now + session_ttl, now
                )
                csrf_bootstraps[digest] = bootstrap
                bound_csrf_bootstraps()
        return {"authenticated": False, "csrf_token": bootstrap.csrf_token}, token

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
        if request.headers.get("x-csrf-token") is None and request.headers.get(
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
                "chatlogin.web.assets"
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
            next_url = _safe_next(request.query_params.get("next", "/"))
            content = login_ui.render(
                {
                    "assets_path": "/_chatshare/assets",
                    "login_url": "/_chatshare/login",
                    "session_url": "/_chatshare/session",
                    "next": next_url,
                }
            )
            return HTMLResponse(
                content if request.method == "GET" else "",
                headers={
                    **PRIVATE_HEADERS,
                    "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
                },
            )
        if path == "/_chatshare/session" and request.method == "GET":
            payload, token = await session_payload(request)
            response = JSONResponse(payload, headers=PRIVATE_HEADERS)
            if token:
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
        if (
            path not in {"/_chatshare/login", "/_chatshare/logout"}
            or request.method != "POST"
        ):
            return error(404)
        if not await ensure_csrf(request):
            return error(403)
        if path == "/_chatshare/logout":
            async with state_lock:
                revoke_token(request.cookies.get(COOKIE))
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
        principal = await backend.authenticate(username, password)
        if principal is None:
            return error(401)
        async with state_lock:
            expire_private()
            previous_token = request.cookies.get(COOKIE)
            previous_digest = session_digest(previous_token)
            try:
                issued = session_manager.issue(principal, previous_token=previous_token)
            except StoreFull:
                return error(429)
            digest = session_digest(issued.token)
            if digest is None:
                session_manager.revoke(issued.token)
                return error(503)
            if previous_digest is not None:
                relay_contexts.pop(previous_digest, None)
                csrf_bootstraps.pop(previous_digest, None)
            relay_contexts[digest] = DufsRelayContext(
                username=username,
                authorization=authorization,
                expires_at=issued.session.expires_at,
            )
            csrf_token = issued.session.csrf_token
            token = issued.token
        response = JSONResponse(
            {
                "authenticated": True,
                "username": username,
                "csrf_token": csrf_token,
                "next": _safe_next(
                    payload.get("next", request.query_params.get("next", "/"))
                    if isinstance(payload, dict)
                    else "/"
                ),
            },
            headers=PRIVATE_HEADERS,
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

    async def proxy(request, raw_target, current, context, concrete):
        explicit = request.headers.get("authorization")
        authenticated = bool(explicit or current)
        session_authorized = bool(current and not explicit and not concrete)
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
                "x-csrf-token",
            },
        )
        headers["accept-encoding"] = "identity"
        if explicit:
            headers["authorization"] = explicit
        elif session_authorized:
            headers["authorization"] = context.authorization
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
                if response.status_code == 401 and session_authorized:
                    async with state_lock:
                        revoke_token(request.cookies.get(COOKIE))
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
            if (
                explicit is None
                and request.method in {"GET", "HEAD"}
                and not decoded.endswith("/")
                and all(name in {"raw", "download", "cache"} for name, _ in flags)
                and not candidate.exists()
            ):
                return error(404)
            current, context = (None, None) if explicit else await session(request)
            if (
                current
                and not explicit
                and request.method not in SAFE_METHODS
                and not await ensure_csrf(request)
            ):
                return error(403)
            if not concrete and not explicit and not current:
                return await denied(request)
            return await proxy(
                request,
                raw_path + ("?" + query if query else ""),
                current,
                context,
                concrete,
            )
        except (ValueError, UnicodeError, OSError):
            return error(400)
        except httpx.HTTPError:
            return error(502)
        except TimeoutError:
            return error(408)

    return app
