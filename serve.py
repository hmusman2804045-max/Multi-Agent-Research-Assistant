"""Entrypoint for the Multi-Agent Research Assistant web API + frontend.

    python serve.py

Host/port come from API_HOST / API_PORT (see .env.example). The default port is 7860,
which is what Hugging Face Spaces expects.
"""

import uvicorn

from src.config import settings


def main() -> None:
    uvicorn.run(
        "src.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
