"""ChatEnv configuration schema and loaders for ChatShare."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from chatenv import BaseEnvConfig, EnvField, EnvStore, get_paths


class ChatshareConfig(BaseEnvConfig):
    """ChatShare ChatEnv configuration."""

    _title = "ChatShare Configuration"
    _aliases: ClassVar[list[str]] = ["chatshare"]
    _storage_dir = "Chatshare"

    @classmethod
    def test(cls) -> None:
        """Validate schema registration without external side effects."""

        print(f"Testing {cls._title}...")
        print("Schema loaded; no network test is required.")

    CHATSHARE_DUFS_USERNAME = EnvField(
        "CHATSHARE_DUFS_USERNAME",
        default="chatshare",
        desc="Dufs account name used for authenticated writes",
    )
    CHATSHARE_DUFS_PASSWORD = EnvField(
        "CHATSHARE_DUFS_PASSWORD",
        desc="Dufs password used for authenticated writes",
        is_sensitive=True,
    )
    CHATSHARE_DUFS_BASE_URL = EnvField(
        "CHATSHARE_DUFS_BASE_URL",
        desc="Public base URL for generated ChatShare links",
    )


def load_active_chatshare_env(home: Path | str | None = None) -> dict[str, str]:
    """Load the active ChatShare ChatEnv profile without process-env fallback."""

    paths = get_paths(home)
    return EnvStore(paths.envs_dir).load_active(ChatshareConfig)


def merged_chatshare_environ(
    home: Path | str | None = None,
    process_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge ChatEnv defaults with process env, letting process env win."""

    merged = load_active_chatshare_env(home)
    merged.update(dict(os.environ if process_environ is None else process_environ))
    return merged


__all__ = [
    "ChatshareConfig",
    "load_active_chatshare_env",
    "merged_chatshare_environ",
]
