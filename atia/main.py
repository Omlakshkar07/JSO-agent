"""
main.py
─────────────────────────────────────────────
PURPOSE:
  Entry point for the ATIA agent API server.
  Does ONLY three things: configure, mount, and run.

RESPONSIBILITIES:
  - Create FastAPI application
  - Mount the API router
  - Configure logging on startup

NOT RESPONSIBLE FOR:
  - Any business logic whatsoever
─────────────────────────────────────────────
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config.settings import get_settings
from utils.logger import setup_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = get_logger("main")
    logger.info(
        "ATIA agent starting",
        extra={"extra_data": {
            "environment": settings.environment,
            "llm_model": settings.llm_model,
        }},
    )
    yield
    logger.info("ATIA agent shutting down")


app = FastAPI(
    title="ATIA — Agency Trust & Transparency Agent",
    description=(
        "Evaluates recruitment agency trustworthiness using "
        "multi-signal analysis and manipulation detection."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ──────────────────────────────────────────────────
# Allow the Next.js frontend (dev server on port 3000) to
# call this API. Without this, browsers block every request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "atia-agent"}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )
