"""FastAPI web layer (Phase 7).

A deliberately thin HTTP wrapper around the already-built, already-hardened core
modules (`src.auth`, `src.storage`, `src.rate_limiter`, `src.pipeline`). No security,
quota, isolation or pipeline logic lives here - routes only translate HTTP requests
into calls on those modules and translate their exceptions into status codes.
"""

from src.api.app import app, create_app

__all__ = ["app", "create_app"]
