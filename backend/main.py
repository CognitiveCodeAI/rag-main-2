"""NPR - Near-Perfect RAG Backend Service.

FastAPI service for query orchestration, tool routing, policy checks, and streaming responses.
Phase 1: Document ingestion pipeline now active.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Query
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
    print(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    print(f"📡 CORS origins: {settings.cors_origins}")
    
    # Log configuration summary
    settings.log_configuration_summary()
    
    # Check for missing required settings
    missing = settings.validate_required_for_embeddings()
    if missing:
        print(f"⚠️  Warning: Missing required settings: {', '.join(missing)}")
        print("   Embedding operations will fail until these are configured.")
    
    yield
    # Shutdown
    print("👋 Shutting down NPR backend")


app = FastAPI(
    title=settings.app_name,
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
        
        # Check PostgreSQL
        try:
            from sqlalchemy import text
            from app.db.session import engine
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            services["postgresql"] = ServiceStatus(status="healthy")
        except Exception as e:
            services["postgresql"] = ServiceStatus(status="unhealthy", message=str(e))
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
            services["milvus"] = ServiceStatus(status="unhealthy", message=str(e))
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
            services["minio"] = ServiceStatus(status="unhealthy", message=str(e))
            overall_status = "degraded"
        
        # Check Redis
        try:
            import redis
            r = redis.from_url(settings.redis_url, socket_timeout=5)
            r.ping()
            services["redis"] = ServiceStatus(status="healthy")
        except Exception as e:
            services["redis"] = ServiceStatus(status="unhealthy", message=str(e))
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
