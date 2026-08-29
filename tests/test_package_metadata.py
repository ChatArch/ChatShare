from importlib import resources
from pathlib import Path


def test_chatarch_internal_dependencies_are_bounded_for_release():
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"click>=8.0,<9.0"' in text
    assert '"chatstyle>=0.2.0,<0.3.0"' in text
    assert '"chatenv>=0.2.10,<0.3.0"' in text
    assert '[project.entry-points."chatenv.configs"]' in text
    assert 'chatshare = "chatshare.config"' in text
    assert '"chatshare.assets.dufs"' in text
    assert "chatstyle>=0.1.0,<0.2.0" not in text
    assert "chatenv>=0.2.0,<0.3.0" not in text


def test_packaged_dufs_assets_include_chatshare_login_dialog():
    asset_root = resources.files("chatshare.assets.dufs")
    index_html = asset_root.joinpath("index.html").read_text(encoding="utf-8")
    index_js = asset_root.joinpath("index.js").read_text(encoding="utf-8")

    assert asset_root.joinpath("favicon.ico").is_file()
    assert "login-dialog" in index_html
    assert "upload-panel" in index_html
    assert "auth-menu" in index_html
    assert "登录后上传" in index_html
    assert "登录上传" in index_html
    assert "退出登录" in index_html
    assert "拖拽文件到这里上传" in index_html
    assert "CHATSHARE_AUTH_STORAGE" in index_js
    assert "ensureAuthenticated" in index_js
    assert "setAuthenticatedUser" in index_js
    assert "basicAuthHeader" in index_js
    assert "LOGOUT" not in index_js
    assert "openWithCredentials" in index_js


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
