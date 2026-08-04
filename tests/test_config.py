from __future__ import annotations

from chatshare.config import ChatshareConfig


def test_chatshare_chatenv_schema_marks_put_password_sensitive():
    assert ChatshareConfig._aliases == ["chatshare"]
    assert ChatshareConfig.get_storage_name() == "Chatshare"
    fields = ChatshareConfig.get_fields()

    assert fields["CHATSHARE_DUFS_USERNAME"].env_key == "CHATSHARE_DUFS_USERNAME"
    assert fields["CHATSHARE_DUFS_PASSWORD"].env_key == "CHATSHARE_DUFS_PASSWORD"
    assert fields["CHATSHARE_DUFS_PASSWORD"].is_sensitive is True
    assert fields["CHATSHARE_DUFS_BASE_URL"].is_sensitive is False
