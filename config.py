from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def _project_path(value: str, default: str) -> Path:
    path = Path(os.getenv(value, default)).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    workspace_dir: Path = _project_path("COPILOT_WORKSPACE_DIR", ".")
    database_path: Path = _project_path("DATABASE_PATH", "data/conversations.sqlite3")
    log_dir: Path = PROJECT_ROOT / "logs"
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    backend_host: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8765"))
    api_base_url: str | None = os.getenv("API_BASE_URL")


settings = Settings()
