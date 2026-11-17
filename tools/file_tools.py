from __future__ import annotations

import os
from pathlib import Path

from config import settings


_MAX_FILE_BYTES = 250_000
_BLOCKED_PARTS = {
    ".git",
    ".venv",
    ".ssh",
    ".aws",
    ".azure",
    ".kube",
    "__pycache__",
    "node_modules",
}
_BLOCKED_NAMES = {
    ".env",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}


def _workspace_path(relative_path: str) -> Path:
    root = settings.workspace_dir.resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path must stay within the configured workspace.")
    if any(part.lower() in _BLOCKED_PARTS for part in target.relative_to(root).parts):
        raise ValueError("Access to this workspace path is not allowed.")
    target_name = target.name.lower()
    if (
        target_name in _BLOCKED_NAMES
        or target_name.startswith(".env.")
        or target.suffix.lower() in {".env", ".key", ".p8", ".p12", ".pem", ".pfx"}
    ):
        raise ValueError("Access to credential and private key files is not allowed.")
    return target


def search_files(query: str, limit: int = 20) -> dict[str, object]:
    root = settings.workspace_dir.resolve()
    if not root.is_dir():
        raise ValueError("The configured workspace directory does not exist.")
    needle = query.casefold()
    matches: list[str] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            item
            for item in directories
            if item.lower() not in _BLOCKED_PARTS
            and not (current_path / item).is_symlink()
        ]
        for filename in filenames:
            candidate = current_path / filename
            if candidate.is_symlink():
                continue
            relative = candidate.relative_to(root)
            try:
                _workspace_path(str(relative))
            except ValueError:
                continue
            if needle in filename.casefold() or needle in str(relative).casefold():
                matches.append(str(relative))
                if len(matches) >= limit:
                    return {"query": query, "matches": matches, "truncated": True}
    return {"query": query, "matches": matches, "truncated": False}


def read_file(relative_path: str) -> dict[str, object]:
    target = _workspace_path(relative_path)
    if not target.is_file():
        raise ValueError("The requested workspace file does not exist.")
    if target.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError(f"Files larger than {_MAX_FILE_BYTES} bytes cannot be read.")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text files can be read.") from exc
    return {"path": str(target.relative_to(settings.workspace_dir.resolve())), "content": content}
