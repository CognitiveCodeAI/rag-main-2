"""Verify all service connections.

Tests connectivity to:
- PostgreSQL
- Milvus
- MinIO
- Redis
- OpenAI API (optional)
"""

import os
import sys
from pathlib import Path

# Add backend to path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

# Load environment
load_dotenv(backend_dir / ".env")


def check_postgres() -> bool:
    """Check PostgreSQL connection."""
    from urllib.parse import quote_plus
    from sqlalchemy import create_engine, text
    
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "appdb")
    db_user = os.getenv("DB_USER", "appuser")
    db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
    
    url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    print(f"PostgreSQL ({db_host}:{db_port}/{db_name}):")
    
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            # Check version
            result = conn.execute(text("SELECT version()"))
            version = result.scalar().split(",")[0]
            print(f"  [OK] Version: {version}")
            
            # Check tables
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            table_count = result.scalar()
            print(f"  [OK] Tables: {table_count}")
            
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def check_milvus() -> bool:
    """Check Milvus connection."""
    from pymilvus import connections, utility
    
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    
    print(f"\nMilvus ({host}:{port}):")
    
    try:
        connections.connect(alias="default", host=host, port=port)
        
        # Check version
        version = utility.get_server_version()
        print(f"  [OK] Version: {version}")
        
        # Check collections
        collections = utility.list_collections()
        print(f"  [OK] Collections: {len(collections)}")
        
        # Check v2 collections specifically
        v2_collections = ["graph_chunks_v2", "graph_figures_v2", "graph_tables_v2"]
        v2_found = [c for c in v2_collections if c in collections]
        print(f"  [OK] V2 collections: {len(v2_found)}/3")
        
        connections.disconnect("default")
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def check_minio() -> bool:
    """Check MinIO connection."""
    from minio import Minio
    
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "admin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    
    print(f"\nMinIO ({endpoint}):")
    
    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        
        # Check buckets
        buckets = client.list_buckets()
        print(f"  [OK] Buckets: {len(buckets)}")
        
        # Check required buckets
        bucket_names = [b.name for b in buckets]
        required = ["npr-corpus", "npr-traces"]
        found = [b for b in required if b in bucket_names]
        print(f"  [OK] Required buckets: {len(found)}/2")
        
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def check_redis() -> bool:
    """Check Redis connection."""
    import redis
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Parse host from URL
    host = redis_url.split("://")[1].split(":")[0] if "://" in redis_url else "localhost"
    
    print(f"\nRedis ({host}):")
    
    try:
        client = redis.from_url(redis_url)
        
        # Check ping
        client.ping()
        print(f"  [OK] Connected")
        
        # Check info
        info = client.info()
        version = info.get("redis_version", "unknown")
        print(f"  [OK] Version: {version}")
        
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def check_openai() -> bool:
    """Check OpenAI API connection (optional)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    
    print(f"\nOpenAI API:")
    
    if not api_key or api_key == "sk-your-api-key-here":
        print(f"  [SKIP] No API key configured")
        return True  # Optional, not a failure
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # Test with a simple embedding
        response = client.embeddings.create(
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
            input="test",
        )
        
        dim = len(response.data[0].embedding)
        print(f"  [OK] Connected")
        print(f"  [OK] Embedding dimension: {dim}")
        
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("Connection Verification")
    print("=" * 60)
    print()
    
    results = {}
    
    # Check all services
    results["PostgreSQL"] = check_postgres()
    results["Milvus"] = check_milvus()
    results["MinIO"] = check_minio()
    results["Redis"] = check_redis()
    results["OpenAI"] = check_openai()
    
    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_ok = True
    for service, ok in results.items():
        status = "[OK]" if ok else "[FAILED]"
        print(f"  {status} {service}")
        if not ok:
            all_ok = False
    
    print()
    
    if all_ok:
        print("[SUCCESS] All services connected")
        return 0
    else:
        print("[WARNING] Some services failed to connect")
        return 1


if __name__ == "__main__":
    sys.exit(main())
