import shutil
import subprocess

import pytest


def test_gateway_and_native_ui_javascript_contracts():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not available for the optional JS contract test")
    result = subprocess.run(
        [node, "tests/code-tests/gateway-ui.cjs"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
