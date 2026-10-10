import asyncio
import base64

import httpx

from chatshare.downloads import DownloadError
from chatshare.gateway import create_app
from chatshare.shares import ShareStore


class Client:
    def __init__(self, app):
        self.loop = asyncio.new_event_loop()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://share.example", follow_redirects=False)

    def request(self, method, path, **kwargs):
        return self.loop.run_until_complete(self.client.request(method, path, **kwargs))

    def close(self):
        self.loop.run_until_complete(self.client.aclose())
        self.loop.close()


def auth(name):
    return "Basic " + base64.b64encode(f"{name}:secret".encode()).decode()


def login(client, name):
    session = client.request("GET", "/_chatshare/session").json()
    response = client.request(
        "POST", "/_chatshare/login", headers={"Origin": "https://share.example", "X-CSRF-Token": session["csrf_token"]},
        json={"username": name, "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


class Downloads:
    def __init__(self):
        self.jobs = {}

    async def start(self): pass
    async def close(self): pass

    async def create(self, owner, url, target, permission):
        assert "signed-secret" in url
        if not await permission(owner, target):
            raise DownloadError("permission")
        job = {"id": "job1", "owner": owner, "state": "queued", "target": target, "source_host": "files.example", "transferred": 0, "total": None, "speed": 0, "sha256": None, "error": None}
        self.jobs[job["id"]] = job
        return dict(job)

    def list(self, owner):
        return [dict(job) for job in self.jobs.values() if job["owner"] == owner]

    def get(self, owner, identifier):
        job = self.jobs.get(identifier)
        if not job or job["owner"] != owner:
            raise DownloadError("Job not found for owner")
        return dict(job)

    async def cancel(self, owner, identifier):
        job = self.get(owner, identifier)
        self.jobs[identifier]["state"] = "cancelled"
        return {**job, "state": "cancelled"}


def test_download_and_share_apis_are_session_csrf_owner_scoped_and_capability_is_confined(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "public.txt").write_text("public")
    calls = []

    def upstream(request):
        calls.append(request)
        authorization = request.headers.get("authorization")
        username = "alice" if authorization == auth("alice") else "bob" if authorization == auth("bob") else None
        if request.method == "CHECKAUTH":
            return httpx.Response(200 if username else 401, content=(username or "").encode())
        if request.url.query == b"json":
            if authorization:
                return httpx.Response(200, json={"user": username, "allow_upload": True, "dir_exists": request.url.path == "/docs/", "paths": []})
            if request.url.path == "/docs/":
                return httpx.Response(200, json={"dir_exists": True, "paths": [{"name": "manual.pdf", "path_type": "File", "size": 10}, {"name": "sub", "path_type": "Dir", "size": 0}]})
            if request.url.path == "/docs/sub/":
                return httpx.Response(200, json={"dir_exists": True, "paths": []})
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b'<html><head></head><body><template id="index-data">e30=</template><script src="/__dufs_v0.46.0__/index.js"></script></body></html>')

    shares = ShareStore(tmp_path / "private-shares")
    asyncio.run(shares.start())
    downloads = Downloads()
    app = create_app(root=root, upstream="http://127.0.0.1:5000", public_url="https://share.example", transport=httpx.MockTransport(upstream), download_service=downloads, share_store=shares)
    alice = Client(app)
    bob = Client(app)
    try:
        alice_csrf = login(alice, "alice")
        bob_csrf = login(bob, "bob")
        assert alice.request("POST", "/_chatshare/downloads", json={"url": "https://files.example/a?signed-secret", "target": "docs/a.bin"}).status_code == 403
        created = alice.request("POST", "/_chatshare/downloads", headers={"Origin": "https://share.example", "X-CSRF-Token": alice_csrf}, json={"url": "https://files.example/a?signed-secret", "target": "docs/a.bin"})
        assert created.status_code == 202
        assert "signed-secret" not in created.text
        assert alice.request("GET", "/_chatshare/downloads").json()["jobs"][0]["source_host"] == "files.example"
        assert bob.request("GET", "/_chatshare/downloads/job1").status_code == 404

        shared = alice.request("POST", "/_chatshare/shares", headers={"Origin": "https://share.example", "X-CSRF-Token": alice_csrf}, json={"directory": "/docs/"})
        assert shared.status_code == 201
        item = shared.json()
        assert bob.request("DELETE", f"/_chatshare/shares/{item['id']}", headers={"Origin": "https://share.example", "X-CSRF-Token": bob_csrf}).status_code == 404
        page = alice.request("GET", item["url"])
        assert page.status_code == 200
        assert 'href="/docs/manual.pdf"' in page.text
        assert f'href="{item["url"]}sub/"' in page.text
        assert "上传" not in page.text and "搜索" not in page.text and "zip" not in page.text
        assert alice.request("GET", item["url"] + "sub/").status_code == 200
        assert alice.request("GET", item["url"] + "../").status_code in {400, 404}
        assert alice.request("GET", item["url"] + "?q=secret").status_code == 404
        assert alice.request("POST", item["url"]).status_code == 404
        assert alice.request("DELETE", f"/_chatshare/shares/{item['id']}", headers={"Origin": "https://share.example", "X-CSRF-Token": alice_csrf}).status_code == 204
        assert alice.request("GET", item["url"]).status_code == 404

        directory = alice.request("GET", "/")
        assert directory.status_code == 200
        assert "从链接下载" in directory.text
        assert "分享当前目录" in directory.text
        assert "downloads-shares-v1" in directory.text
        assert alice.request("GET", "/_chatshare/assets/manage.js").status_code == 200
    finally:
        alice.close()
        bob.close()


def test_share_creation_fails_closed_for_missing_or_wrong_owner_directory(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    def upstream(request):
        if request.method == "CHECKAUTH": return httpx.Response(200, content=b"alice")
        return httpx.Response(200, json={"user": "mallory", "allow_upload": True, "dir_exists": True})
    shares = ShareStore(tmp_path / "shares"); asyncio.run(shares.start())
    app = create_app(root=root, upstream="http://127.0.0.1:5000", public_url="https://share.example", transport=httpx.MockTransport(upstream), share_store=shares)
    client = Client(app)
    try:
        token = login(client, "alice")
        response = client.request("POST", "/_chatshare/shares", headers={"Origin": "https://share.example", "X-CSRF-Token": token}, json={"directory": "/docs/"})
        assert response.status_code == 403
        assert shares.list("alice") == []
    finally:
        client.close()
