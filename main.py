from __future__ import annotations

import uvicorn

from config import settings


if __name__ == "__main__":
    uvicorn.run(
        "backend.api:app",
        host=settings.backend_host,
        port=settings.backend_port,
        log_level=settings.log_level.lower(),
    )
