from click.testing import CliRunner

from chatshare.cli import main


def test_hello_command_accepts_explicit_name():
    result = CliRunner().invoke(main, ["hello", "ChatArch"])

    assert result.exit_code == 0
    assert "Hello, ChatArch!" in result.output
