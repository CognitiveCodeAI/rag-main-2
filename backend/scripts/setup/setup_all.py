"""Run all setup steps for NPR RAG application.

This script runs all setup steps in order:
1. PostgreSQL - Create tables via Alembic migrations
2. Milvus - Create vector collections
3. MinIO - Create storage buckets
4. Verify - Test all connections

Usage:
    python -m scripts.setup.setup_all
"""

import sys
from pathlib import Path

# Add backend to path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

# Load environment
load_dotenv(backend_dir / ".env")


def run_step(name: str, module_name: str) -> bool:
    """Run a setup step by importing and calling its main function."""
    print()
    print("#" * 60)
    print(f"# {name}")
    print("#" * 60)
    print()
    
    try:
        # Import the module
        module = __import__(
            f"scripts.setup.{module_name}",
            fromlist=[module_name]
        )
        
        # Call main
        result = module.main()
        return result == 0
        
    except Exception as e:
        print(f"[ERROR] {name} failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("NPR RAG Application Setup")
    print("=" * 60)
    print()
    print("This script will set up all required databases and storage")
    print("for the NPR RAG application.")
    print()
    print("Prerequisites:")
    print("  - PostgreSQL server running with database created")
    print("  - Milvus server running")
    print("  - MinIO server running")
    print("  - Redis server running")
    print("  - .env file configured with connection details")
    print()
    
    # Check for .env file
    env_file = backend_dir / ".env"
    if not env_file.exists():
        print("[ERROR] .env file not found!")
        print()
        print("Create .env from template:")
        print("  copy .env.example .env")
        print()
        print("Then edit .env with your connection details.")
        return 1
    
    print(f"Using config: {env_file}")
    print()
    
    # Run setup steps
    steps = [
        ("PostgreSQL Setup", "setup_postgres"),
        ("Milvus Setup", "setup_milvus"),
        ("MinIO Setup", "setup_minio"),
    ]
    
    results = {}
    
    for name, module in steps:
        results[name] = run_step(name, module)
    
    # Run verification
    print()
    print("#" * 60)
    print("# Verification")
    print("#" * 60)
    print()
    
    results["Verification"] = run_step("Connection Verification", "verify_connections")
    
    # Summary
    print()
    print("=" * 60)
    print("Setup Summary")
    print("=" * 60)
    print()
    
    all_ok = True
    for step, ok in results.items():
        status = "[OK]" if ok else "[FAILED]"
        print(f"  {status} {step}")
        if not ok:
            all_ok = False
    
    print()
    
    if all_ok:
        print("=" * 60)
        print("[SUCCESS] All setup steps completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Start the backend: uvicorn app.main:app --reload")
        print("  2. Start the frontend: npm run dev")
        print("  3. Upload documents via the UI or API")
        print()
        return 0
    else:
        print("=" * 60)
        print("[WARNING] Some setup steps failed!")
        print("=" * 60)
        print()
        print("Review the errors above and fix any issues.")
        print("You can re-run individual setup scripts:")
        print("  python -m scripts.setup.setup_postgres")
        print("  python -m scripts.setup.setup_milvus")
        print("  python -m scripts.setup.setup_minio")
        print("  python -m scripts.setup.verify_connections")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
