from pathlib import Path


def test_chatarch_internal_dependencies_are_bounded_for_release():
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"click>=8.0,<9.0"' in text
    assert '"chatstyle>=0.2.0,<0.3.0"' in text
    assert '"chatenv>=0.2.10,<0.3.0"' in text
    assert '[project.entry-points."chatenv.configs"]' in text
    assert 'chatshare = "chatshare.config"' in text
    assert "chatstyle>=0.1.0,<0.2.0" not in text
    assert "chatenv>=0.2.0,<0.3.0" not in text


def test_development_guide_documents_shared_tree_runtime():
    text = Path("DEVELOP.md").read_text(encoding="utf-8")

    assert "chatstyle>=0.2.0,<0.3.0" in text
    assert "chatenv>=0.2.10,<0.3.0" in text
    assert "add_tree_option()" in text
    assert "--tree-brief" in text


def test_ci_runs_installed_cli_and_distribution_gates():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for command in (
        "chatshare --version",
        "chatshare --tree",
        "chatshare --tree-brief",
        "python -m build",
        "python -m twine check dist/*",
        "mkdocs build --strict",
    ):
        assert command in text
