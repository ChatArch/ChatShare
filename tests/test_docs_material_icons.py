from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIAL_ICON_PATTERN = re.compile(r":material-[A-Za-z0-9_-]+:")


def test_material_icons_enable_mkdocs_material_emoji_renderer() -> None:
    docs_sources = [*REPO_ROOT.glob("README*.md"), *REPO_ROOT.glob("docs/**/*.md")]
    source_icons = [
        (path.relative_to(REPO_ROOT).as_posix(), match.group(0))
        for path in docs_sources
        for match in MATERIAL_ICON_PATTERN.finditer(path.read_text(encoding="utf-8"))
    ]

    assert source_icons, "This regression test is active only when docs use Material icons."

    mkdocs_config = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "pymdownx.emoji" in mkdocs_config
    assert "material.extensions.emoji.twemoji" in mkdocs_config
    assert "material.extensions.emoji.to_svg" in mkdocs_config
