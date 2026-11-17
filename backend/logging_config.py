from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config import settings


def configure_logging() -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    level = getattr(logging, settings.log_level, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    root.setLevel(level)
    if not any(getattr(handler, "_chat_app_file_handler", False) for handler in root.handlers):
        file_handler = RotatingFileHandler(
            settings.log_dir / "app.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler._chat_app_file_handler = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)
    if not any(getattr(handler, "_chat_app_console_handler", False) for handler in root.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler._chat_app_console_handler = True  # type: ignore[attr-defined]
        root.addHandler(stream_handler)
