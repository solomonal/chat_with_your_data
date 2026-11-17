from __future__ import annotations

from pathlib import Path


SKILLS = {
    "calculator",
    "mathematics",
    "datetime",
    "general_assistant",
    "data_analysis",
    "python_developer",
    "file_assistant",
}


def test_each_initial_skill_has_a_skill_document() -> None:
    root = Path(__file__).resolve().parents[1] / "skills"
    for skill in SKILLS:
        document = root / skill / "SKILL.md"
        assert document.is_file()
        content = document.read_text(encoding="utf-8")
        assert content.startswith("---\nname:")
        assert "## Purpose" in content
        assert "## When to use" in content
        assert "## Instructions" in content
        assert "## Available tools" in content
        assert "## Required input" in content
        assert "## Expected output" in content
        assert "## Error handling" in content
        assert "## Example" in content
