import shutil
import subprocess

import pytest


@pytest.mark.parametrize("script", ["gateway-ui.cjs", "upload-progress.cjs"])
def test_gateway_and_native_ui_javascript_contracts(script):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not available for the optional JS contract test")
    result = subprocess.run(
        [node, f"tests/code-tests/{script}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
