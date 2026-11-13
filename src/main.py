from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.exceptions import register_exception_handlers
from src.core.pagination import APIResponse
from src.modules.iam.router import router as iam_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    # Startup: could log or verify DB connection
    yield
    # Shutdown: clean up connection pools
    from src.core.database import engine

    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Modular Python Backend for LaRose Floral Studio",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers
    register_exception_handlers(app)

    # API Routers
    app.include_router(iam_router, prefix=settings.API_V1_PREFIX)

    # Health Check Endpoint
    @app.get("/healthz", tags=["Health"], response_model=APIResponse[dict])
    async def health_check():
        return APIResponse(
            success=True,
            data={
                "status": "healthy",
                "environment": settings.ENVIRONMENT,
                "version": settings.APP_VERSION,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            message="LaRose Floral Studio Backend is operational.",
        )

    # Root Endpoint
    @app.get("/", tags=["Root"], response_model=APIResponse[dict])
    async def root():
        return APIResponse(
            success=True,
            data={
                "name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "docsUrl": "/docs",
                "redocUrl": "/redoc",
            },
            message="Welcome to LaRose Floral Studio API Gateway.",
        )

    return app


app = create_app()
