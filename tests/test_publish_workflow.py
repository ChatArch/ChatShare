from __future__ import annotations

from pathlib import Path

PUBLISH_WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish.yml"
)


def test_publish_workflow_is_tag_only() -> None:
    text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch" not in text
    assert "push:" in text
    assert "tags:" in text
    assert '- "v*"' in text


def test_publish_workflow_matches_pypi_trusted_publisher_claims() -> None:
    text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "id-token: write" in text
    assert "environment: pypi" in text
    assert "pypa/gh-action-pypi-publish@release/v1" in text
    assert 'PACKAGE_NAME: "ChatShare"' in text


def test_publish_workflow_rejects_tag_version_mismatch() -> None:
    text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "Check tag matches package version" in text
    assert "GITHUB_REF_NAME" in text
    assert "RELEASE_TAG" in text
    assert "does not match package version" in text


def test_publish_workflow_requires_default_branch_ancestry() -> None:
    text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "fetch-depth: 0" in text
    assert 'git merge-base --is-ancestor "${GITHUB_SHA}" refs/remotes/origin/main' in text
