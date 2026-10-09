from pathlib import Path

import httpx

from click.testing import CliRunner

from chatshare.cli import main


def test_remote_put_and_tree_work_without_local_dufs_instance(monkeypatch, tmp_path):
    from chatshare.remote import RemoteClient

    source = tmp_path / "clip.mov"
    source.write_bytes(b"video-bytes")
    calls = []

    def fake_publish(self, source_path, destination, *, overwrite, progress=None):
        calls.append(("put", source_path, destination, overwrite))
        return {"path": destination, "size": 11, "source": str(source_path), "url": "https://share.example.test/videos/clip.mov"}

    def fake_list(self, prefix):
        calls.append(("tree", prefix))
        return {"entries": 1, "lines": ["videos/", "`-- clip.mov"], "path": prefix, "url": "https://share.example.test/videos"}

    monkeypatch.setattr(RemoteClient, "publish_file", fake_publish)
    monkeypatch.setattr(RemoteClient, "list_directory", fake_list)
    runner = CliRunner()
    env = {
        "CHATSHARE_DUFS_BASE_URL": "https://share.example.test",
        "CHATSHARE_DUFS_USERNAME": "writer",
        "CHATSHARE_DUFS_PASSWORD": "not-a-real-secret",
    }

    put = runner.invoke(main, ["--home", str(tmp_path / "fresh-home"), "put", str(source), "videos/clip.mov"], env=env)
    tree = runner.invoke(main, ["--home", str(tmp_path / "fresh-home"), "tree", "videos"], env=env)

    assert put.exit_code == 0, put.output
    assert tree.exit_code == 0, tree.output
    assert "instance.json" not in put.output + tree.output
    assert calls == [
        ("put", source, "videos/clip.mov", False),
        ("tree", "videos"),
    ]


def test_remote_commands_explain_missing_client_configuration(tmp_path):
    runner = CliRunner()

    result = runner.invoke(main, ["--home", str(tmp_path / "fresh-home"), "tree"])

    assert result.exit_code != 0
    assert "CHATSHARE_DUFS_BASE_URL" in result.output
    assert "chatenv init -t chatshare -I" in result.output
    assert "instance.json" not in result.output
