from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_streamlit_entrypoint_imports_from_isolated_path(tmp_path: Path) -> None:
    app_path = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
    code = (
        "from streamlit.testing.v1 import AppTest\n"
        f"app = AppTest.from_file({str(app_path)!r}, default_timeout=15).run()\n"
        "assert not app.exception, [item.message for item in app.exception]\n"
        "assert app.title[0].value == 'AI Agent Assistant'\n"
    )
    env = os.environ.copy()
    env["API_BASE_URL"] = "http://127.0.0.1:1"
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
