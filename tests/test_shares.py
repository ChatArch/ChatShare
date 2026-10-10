import asyncio
import json
import re

import pytest

from chatshare.shares import ShareError, ShareStore, normalize_directory


def run(value):
    return asyncio.run(value)


def test_directory_normalization_rejects_traversal_ambiguity_and_files():
    assert normalize_directory("/") == "/"
    assert normalize_directory("/docs/sub/") == "/docs/sub/"
    for value in ("", "docs", "/docs", "/docs//sub/", "/../x/", "/a/%2e%2e/", "/a\\b/", "/a\x00b/"):
        with pytest.raises(ShareError):
            normalize_directory(value)


def test_share_store_is_owner_scoped_persistent_bounded_and_uses_256_bit_tokens(tmp_path):
    store = ShareStore(tmp_path / "shares", max_shares=2)

    async def scenario():
        await store.start()
        first = await store.create("alice", "/docs/")
        second = await store.create("bob", "/other/")
        with pytest.raises(ShareError, match="capacity"):
            await store.create("alice", "/third/")
        with pytest.raises(ShareError, match="owner"):
            await store.revoke("bob", first["id"])
        return first, second

    first, second = run(scenario())
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", first["token"])
    assert len(__import__("base64").urlsafe_b64decode(first["token"] + "=")) == 32
    assert store.resolve(first["token"], "sub/")["directory"] == "/docs/sub/"
    with pytest.raises(ShareError):
        store.resolve(first["token"], "../private/")
    assert [item["id"] for item in store.list("bob")] == [second["id"]]
    payload = json.loads((tmp_path / "shares/shares.json").read_text())
    assert payload["schema"] == 1
    assert oct((tmp_path / "shares").stat().st_mode & 0o777) == "0o700"
    assert oct((tmp_path / "shares/shares.json").stat().st_mode & 0o777) == "0o600"

    loaded = ShareStore(tmp_path / "shares", max_shares=2)
    run(loaded.start())
    assert loaded.resolve(first["token"], "")["directory"] == "/docs/"
    run(loaded.revoke("alice", first["id"]))
    with pytest.raises(ShareError):
        loaded.resolve(first["token"], "")


def test_share_store_rejects_symlink_root_and_malformed_metadata(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "shares"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ShareError, match="symlink"):
        run(ShareStore(link).start())
    with pytest.raises(ShareError, match="symlink"):
        run(ShareStore(link / "nested").start())

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "shares.json").write_text('{"schema":1,"shares":[{"token":"short"}]}')
    with pytest.raises(ShareError, match="invalid"):
        run(ShareStore(bad).start())
