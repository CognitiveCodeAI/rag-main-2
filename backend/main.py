"""NPR - Near-Perfect RAG Backend Service.

FastAPI service for query orchestration, tool routing, policy checks, and streaming responses.
Phase 1: Document ingestion pipeline now active.
"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.graph.backend_selector import get_supported_types
from app.models import HealthResponse, ServiceStatus
from app.routes import ingest, embed, retrieve, qa, documents, prompts, acl
from app.routes import settings as settings_routes
from app.services.worker_health import inspect_celery_workers

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(
        "%s v%s | %s | %s",
        settings.app_name,
        settings.app_version,
        settings.vendor_name,
        settings.vendor_website.replace("https://", ""),
    )
    logger.info("CORS origins: %s", settings.cors_origins)
    
    # Log configuration summary
    settings.log_configuration_summary()
    
    # Check for missing required settings
    missing = settings.validate_required_for_embeddings()
    if missing:
        logger.warning("Missing required settings: %s", ", ".join(missing))
        logger.warning("Embedding operations will fail until these are configured.")
    
    yield
    # Shutdown
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=f"{settings.app_name} — {settings.vendor_name}",
    description="Evidence-first RAG with grounded citations. Never guesses.",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ingest.router)
app.include_router(embed.router)
app.include_router(retrieve.router)
app.include_router(qa.router)
app.include_router(documents.router)
app.include_router(prompts.router)
app.include_router(acl.router)
app.include_router(settings_routes.router)


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "metadata": "/metadata",
    }


@app.get("/metadata", tags=["root"])
async def metadata():
    """Application metadata endpoint (non-sensitive)."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "vendor": settings.vendor_name,
        "website": settings.vendor_website,
        "developer": settings.vendor_developer,
    }


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health(check_services: bool = Query(default=False, description="Check connectivity to backend services")):
    """Health check endpoint.
    
    Returns basic health status by default. Pass check_services=true to also
    verify connectivity to PostgreSQL, Milvus, MinIO, and Redis.
    """
    warnings = []
    services = None
    overall_status = "healthy"
    
    # Check for missing required configuration
    missing = settings.validate_required_for_embeddings()
    if missing:
        warnings.append(f"Missing required settings: {', '.join(missing)}")
    
    # Optionally check service connectivity
    if check_services:
        services = {}

        def _service_failure(service_name: str, exc: Exception) -> ServiceStatus:
            error_id = str(uuid.uuid4())
            logger.warning(
                "[Health] %s check failed (error_id=%s): %s",
                service_name,
                error_id,
                exc,
                exc_info=True,
            )
            return ServiceStatus(
                status="unhealthy",
                message=f"Service check failed (error_id={error_id})",
            )
        
        # Check PostgreSQL
        try:
            from sqlalchemy import text
            from app.db.session import engine
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            services["postgresql"] = ServiceStatus(status="healthy")
        except Exception as e:
            services["postgresql"] = _service_failure("postgresql", e)
            overall_status = "degraded"
        
        # Check Milvus
        try:
            from pymilvus import connections, utility
            alias = "health_check"
            connections.connect(alias, host=settings.milvus_host, port=settings.milvus_port, timeout=5)
            utility.list_collections(using=alias)
            connections.disconnect(alias)
            services["milvus"] = ServiceStatus(status="healthy")
        except Exception as e:
            services["milvus"] = _service_failure("milvus", e)
            overall_status = "degraded"
        
        # Check MinIO
        try:
            from minio import Minio
            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=False,
            )
            client.list_buckets()
            services["minio"] = ServiceStatus(status="healthy")
        except Exception as e:
            services["minio"] = _service_failure("minio", e)
            overall_status = "degraded"
        
        # Check Redis
        try:
            import redis
            r = redis.from_url(settings.redis_url, socket_timeout=5)
            r.ping()
            services["redis"] = ServiceStatus(status="healthy")
        except Exception as e:
            services["redis"] = _service_failure("redis", e)
            overall_status = "degraded"

        # Check Celery workers
        worker_status = inspect_celery_workers(timeout=1.0)
        services["celery_worker"] = ServiceStatus(
            status="healthy" if worker_status.healthy else "unhealthy",
            message=worker_status.message,
        )
        if not worker_status.healthy:
            overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        timestamp=datetime.utcnow(),
        config_warnings=warnings,
        services=services,
        features={
            "acl_enabled": settings.acl_enabled,
            "supported_file_types": sorted(get_supported_types()),
            "cross_format_highlighting_enabled": settings.enable_cross_format_highlighting,
        },
    )


@app.get("/health/live", tags=["health"])
async def health_live():
    """Liveness endpoint: process is running and can serve requests."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "timestamp": datetime.utcnow(),
    }


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def health_ready():
    """Readiness endpoint: dependencies reachable and worker checks applied."""
    return await health(check_services=True)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected errors with stable client detail."""
    error_id = str(uuid.uuid4())
    logger.error(
        f"[Unhandled] error_id={error_id} path={request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error (error_id={error_id})"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
