from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.config import get_settings
from api.routers import health, pipeline, articles


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title="News Data Extraction API",
        description="Automated news article extraction, embedding, and grouping pipeline.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow all for dev; tighten for production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers under the versioned prefix
    prefix = settings.API_PREFIX
    app.include_router(health.router,   prefix=prefix)
    app.include_router(pipeline.router, prefix=prefix)
    app.include_router(articles.router, prefix=prefix)

    return app
