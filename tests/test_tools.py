from __future__ import annotations

import pytest

from types import SimpleNamespace

import tools.file_tools as file_tools
from tools.datetime_tools import calculate_date_difference
from tools.python_tools import analyze_python_code


def test_date_difference() -> None:
    assert calculate_date_difference("2026-01-01", "2026-01-10")["days"] == 9
    assert calculate_date_difference("2026-01-10", "2026-01-01")["days"] == -9


def test_date_difference_validates_iso_dates() -> None:
    with pytest.raises(ValueError, match="ISO format"):
        calculate_date_difference("01/01/2026", "2026-01-10")


def test_python_analysis_does_not_execute_source() -> None:
    result = analyze_python_code("raise RuntimeError('must not run')", "analyze")
    assert result["valid"] is True
    assert result["executed"] is False


def test_python_analysis_reports_syntax_error() -> None:
    result = analyze_python_code("def broken(:", "analyze")
    assert result["valid"] is False
    assert result["syntax_error"]["line"] == 1


def test_file_tools_are_scoped_to_workspace_and_exclude_credentials(
    tmp_path, monkeypatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "notes.txt").write_text("workspace data", encoding="utf-8")
    (root / ".env").write_text("SECRET=value", encoding="utf-8")
    monkeypatch.setattr(file_tools, "settings", SimpleNamespace(workspace_dir=root))

    assert file_tools.read_file("notes.txt")["content"] == "workspace data"
    with pytest.raises(ValueError, match="credential"):
        file_tools.read_file(".env")
    with pytest.raises(ValueError, match="within"):
        file_tools.read_file("../outside.txt")
