"""ChatArch-owned paths for ChatShare."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from chatenv import get_paths


@dataclass(frozen=True)
class ChatSharePaths:
    """Resolved filesystem layout for the single managed ChatShare instance."""

    chatarch_home: Path

    @classmethod
    def from_home(cls, home: Path | str | None = None) -> ChatSharePaths:
        value = get_paths().home_dir if home is None else home
        return cls(Path(value).expanduser().resolve())

    @property
    def base(self) -> Path:
        return self.chatarch_home / "chatshare"

    @property
    def dufs_runtimes(self) -> Path:
        return self.base / "runtimes" / "dufs"

    def dufs_runtime(self, version: str) -> Path:
        return self.dufs_runtimes / version

    def dufs_binary(self, version: str) -> Path:
        return self.dufs_runtime(version) / "dufs"

    def dufs_manifest(self, version: str) -> Path:
        return self.dufs_runtime(version) / "install.json"

    @property
    def dufs_current(self) -> Path:
        return self.dufs_runtimes / "current"

    @property
    def dufs_current_binary(self) -> Path:
        return self.dufs_current / "dufs"

    @property
    def instance_dir(self) -> Path:
        return self.base / "instances" / "default"

    @property
    def config_file(self) -> Path:
        return self.instance_dir / "config.yaml"

    @property
    def state_file(self) -> Path:
        return self.instance_dir / "instance.json"

    @property
    def data_dir(self) -> Path:
        return self.instance_dir / "data"

    @property
    def dufs_assets_dir(self) -> Path:
        return self.instance_dir / "assets" / "dufs"

    @property
    def logs_dir(self) -> Path:
        return self.instance_dir / "logs"

    @property
    def access_log(self) -> Path:
        return self.logs_dir / "access.log"

    @property
    def canonical_unit(self) -> Path:
        return self.base / "services" / "chatshare-dufs.service"
