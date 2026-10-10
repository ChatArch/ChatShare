"""Private persistence for owner-managed directory bearer capabilities."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
SHORT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{22}$")


def short_code(token: str) -> str:
    """Stable 128-bit alias; retain the stored token and legacy addresses."""
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise ShareError("Share not found")
    digest = hashlib.sha256(token.encode("ascii")).digest()[:16]
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class ShareError(Exception):
    """A safe directory-share error."""


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.absolute().parts[1:]:
        current /= component
        if current.is_symlink():
            raise ShareError("Share runtime root contains a symlink")


def normalize_directory(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or not value.endswith("/"):
        raise ShareError("Directory must be an absolute URI ending in a slash")
    if "\\" in value or "%" in value or "//" in value:
        raise ShareError("Directory URI is ambiguous")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ShareError("Directory URI contains control characters")
    parts = value[1:-1].split("/") if value != "/" else []
    if any(part in {"", ".", ".."} or len(part.encode()) > 255 for part in parts):
        raise ShareError("Directory URI contains an unsafe component")
    if len(value.encode()) > 4096:
        raise ShareError("Directory URI is too long")
    return "/" + "/".join(parts) + ("/" if parts else "")


class ShareStore:
    def __init__(self, base: Path, *, max_shares: int = 200, clock=time.time):
        if isinstance(max_shares, bool) or not isinstance(max_shares, int) or max_shares <= 0:
            raise ValueError("max_shares must be a positive integer")
        self.base = Path(base)
        self.metadata = self.base / "shares.json"
        self.max_shares = max_shares
        self.clock = clock
        self.shares: dict[str, dict] = {}

    async def start(self) -> None:
        _reject_symlink_components(self.base)
        if self.base.is_symlink():
            raise ShareError("Share runtime root must not be a symlink")
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.base.is_symlink() or not self.base.is_dir():
            raise ShareError("Share runtime root is unsafe")
        self.base.chmod(0o700)
        if self.metadata.exists():
            if self.metadata.is_symlink() or not self.metadata.is_file():
                raise ShareError("Share metadata is unsafe")
            try:
                payload = json.loads(self.metadata.read_text(encoding="utf-8"))
                if set(payload) != {"schema", "shares"} or payload["schema"] != 1:
                    raise ValueError("schema")
                values = payload["shares"]
                if not isinstance(values, list) or len(values) > self.max_shares:
                    raise ValueError("shares")
                for item in values:
                    required = {"id", "token", "owner", "directory", "created_at"}
                    if set(item) != required or not all(isinstance(item[key], str) for key in required - {"created_at"}):
                        raise ValueError("record")
                    if not isinstance(item["created_at"], (int, float)) or not TOKEN_RE.fullmatch(item["token"]):
                        raise ValueError("record")
                    normalize_directory(item["directory"])
                    if item["id"] in self.shares or any(value["token"] == item["token"] for value in self.shares.values()):
                        raise ValueError("duplicate")
                    self.shares[item["id"]] = item
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ShareError("Share metadata is invalid") from exc
        await self._persist()

    async def _persist(self) -> None:
        temporary = self.base / f".shares.{secrets.token_hex(8)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            content = json.dumps(
                {"schema": 1, "shares": list(self.shares.values())},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            if len(content) > 1024 * 1024:
                raise ShareError("Share metadata exceeds its storage bound")
            view = memoryview(content)
            while view:
                view = view[os.write(descriptor, view) :]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self.metadata)
        self.metadata.chmod(0o600)

    async def create(self, owner: str, directory: str) -> dict:
        directory = normalize_directory(directory)
        if len(self.shares) >= self.max_shares:
            raise ShareError("Directory share capacity is full")
        if any(item["owner"] == owner and item["directory"] == directory for item in self.shares.values()):
            raise ShareError("Directory is already shared by this owner")
        item = {
            "id": secrets.token_urlsafe(12),
            "token": secrets.token_urlsafe(32),
            "owner": owner,
            "directory": directory,
            "created_at": self.clock(),
        }
        self.shares[item["id"]] = item
        await self._persist()
        return dict(item)

    def list(self, owner: str) -> list[dict]:
        return [dict(item) for item in sorted(self.shares.values(), key=lambda value: value["created_at"], reverse=True) if item["owner"] == owner]

    async def revoke(self, owner: str, identifier: str) -> dict:
        item = self.shares.get(identifier)
        if not item or item["owner"] != owner:
            raise ShareError("Share not found for owner")
        removed = self.shares.pop(identifier)
        await self._persist()
        return dict(removed)

    def resolve(self, token: str, descendant: str) -> dict:
        if not isinstance(token, str):
            raise ShareError("Share not found")
        if TOKEN_RE.fullmatch(token):
            item = next((value for value in self.shares.values() if secrets.compare_digest(value["token"], token)), None)
        elif SHORT_TOKEN_RE.fullmatch(token):
            item = next((value for value in self.shares.values() if secrets.compare_digest(short_code(value["token"]), token)), None)
        else:
            raise ShareError("Share not found")
        if item is None:
            raise ShareError("Share not found")
        if descendant:
            if descendant.startswith("/") or not descendant.endswith("/"):
                raise ShareError("Shared path must name a directory")
            directory = normalize_directory(item["directory"] + descendant)
            if not directory.startswith(item["directory"]):
                raise ShareError("Shared path escapes its root")
        else:
            directory = item["directory"]
        return {**item, "directory": directory}


__all__ = ["ShareError", "ShareStore", "normalize_directory"]
