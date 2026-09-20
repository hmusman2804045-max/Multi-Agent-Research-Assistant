"""FastAPI application factory for the Phase 7 web layer."""

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from src.config import BASE_DIR, settings
from src.api.errors import register_exception_handlers
from src.api.routes import auth_routes, history_routes, quota_routes, research_routes
from src.logger import get_logger

logger = get_logger(__name__)

API_TITLE = "Multi-Agent Research Assistant API"
API_VERSION = "7.0.0"


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React frontend from the same origin, when a build is present.

    In production (e.g. a Hugging Face Space) the API and the SPA are served together, so
    no cross-origin configuration is required at all. In local development the frontend
    runs on its own Vite server and reaches the API through CORS instead.
    """
    dist_dir = Path(settings.frontend_dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = BASE_DIR / dist_dir

    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        logger.info(f"No frontend build found at '{dist_dir}'; serving API only.")
        return

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    api_prefixes = ("api/", "docs", "redoc", "openapi.json")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Serve static files, falling back to index.html so client-side routes resolve.

        API paths are excluded so that an unknown endpoint returns a real 404 instead of
        silently handing the caller an HTML page.
        """
        if full_path.startswith(api_prefixes):
            raise HTTPException(status_code=404, detail=f"Not found: /{full_path}")

        candidate = (dist_dir / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist_dir.resolve()):
            return FileResponse(candidate)
        return FileResponse(index_file)

    logger.info(f"Serving frontend build from '{dist_dir}'.")


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=(
            "HTTP surface for the 5-agent research pipeline, user authentication, "
            "per-user research history, and rate limit telemetry."
        ),
    )

    origins = settings.cors_origin_list
    if origins:
        allow_all = origins == ["*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            # The web client authenticates with a bearer token, not cookies, so credentialed
            # cross-origin requests are never needed - and must not be enabled alongside '*'.
            allow_credentials=not allow_all,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
        logger.info(f"CORS enabled for origins: {', '.join(origins)}")

    api = APIRouter(prefix="/api")
    api.include_router(auth_routes.router)
    api.include_router(research_routes.router)
    api.include_router(history_routes.router)
    api.include_router(quota_routes.router)

    @api.get("/health", tags=["meta"])
    def health():
        """Liveness probe reporting the caps the UI needs to render quota copy."""
        return {
            "status": "ok",
            "version": API_VERSION,
            "daily_query_limit": settings.daily_query_limit,
            "global_daily_query_limit": settings.global_daily_query_limit,
            "requests_per_minute_limit": settings.requests_per_minute_limit,
            "max_query_length": settings.max_query_length,
        }

    # The API lives under a single /api prefix. It must not also be mounted unprefixed:
    # paths like /history are simultaneously client-side routes of the SPA served from
    # this same origin, and an unprefixed API route shadows them, so a direct page load
    # or a refresh of /history would return JSON instead of the app.
    app.include_router(api)

    register_exception_handlers(app)

    _mount_frontend(app)
    return app


app = create_app()
