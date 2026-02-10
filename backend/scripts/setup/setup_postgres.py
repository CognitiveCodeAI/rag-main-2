"""Setup PostgreSQL database and run migrations.

This script:
1. Tests the database connection
2. Runs all Alembic migrations to create the schema

Prerequisites:
- PostgreSQL server running
- Database created (e.g., CREATE DATABASE appdb;)
- User with permissions (e.g., GRANT ALL ON DATABASE appdb TO appuser;)
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


def test_connection() -> bool:
    """Test PostgreSQL connection."""
    from urllib.parse import quote_plus
    from sqlalchemy import create_engine, text
    
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "appdb")
    db_user = os.getenv("DB_USER", "appuser")
    db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
    
    url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    print(f"Connecting to PostgreSQL at {db_host}:{db_port}/{db_name}...")
    
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"  [OK] Connected to PostgreSQL")
            print(f"  [OK] Server version: {version.split(',')[0]}")
        return True
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        return False


def run_migrations() -> bool:
    """Run Alembic migrations."""
    import subprocess
    
    alembic_dir = backend_dir / "alembic"
    
    if not alembic_dir.exists():
        print(f"  [ERROR] Alembic directory not found: {alembic_dir}")
        return False
    
    print("Running Alembic migrations...")
    
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("  [OK] Migrations completed successfully")
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        print(f"       {line}")
            return True
        else:
            print(f"  [ERROR] Migration failed:")
            print(f"       {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("  [ERROR] Alembic not found. Install with: pip install alembic")
        return False
    except Exception as e:
        print(f"  [ERROR] Migration failed: {e}")
        return False


def get_migration_status() -> None:
    """Show current migration status."""
    import subprocess
    
    print("\nMigration status:")
    
    try:
        result = subprocess.run(
            ["alembic", "current"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                print(f"  Current: {output}")
            else:
                print("  No migrations applied yet")
        
        result = subprocess.run(
            ["alembic", "history", "--verbose"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout:
            print("\n  Available migrations:")
            for line in result.stdout.strip().split("\n")[:10]:
                if line.strip():
                    print(f"    {line}")
                    
    except Exception as e:
        print(f"  [ERROR] Could not get status: {e}")


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("PostgreSQL Setup")
    print("=" * 60)
    print()
    
    # Test connection
    if not test_connection():
        print("\n[FAILED] Cannot proceed without database connection")
        print("\nTroubleshooting:")
        print("  1. Verify PostgreSQL is running")
        print("  2. Check .env file has correct DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        print("  3. Ensure database exists: CREATE DATABASE <db_name>;")
        print("  4. Ensure user has permissions: GRANT ALL ON DATABASE <db_name> TO <user>;")
        return 1
    
    print()
    
    # Run migrations
    if not run_migrations():
        print("\n[FAILED] Migration failed")
        return 1
    
    # Show status
    get_migration_status()
    
    print()
    print("=" * 60)
    print("[SUCCESS] PostgreSQL setup complete")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
