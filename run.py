#!/usr/bin/env python3
"""NPR RAG application launcher with supervised child processes."""

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
LOG_DIR = ROOT_DIR / "logs"

if sys.platform == "win32":
    VENV_PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
    VENV_CELERY = BACKEND_DIR / "venv" / "Scripts" / "celery.exe"
else:
    VENV_PYTHON = BACKEND_DIR / "venv" / "bin" / "python"
    VENV_CELERY = BACKEND_DIR / "venv" / "bin" / "celery"

SHUTTING_DOWN = False
SERVICES = []


@dataclass
class ManagedService:
    name: str
    cmd: list[str]
    cwd: Path
    env: dict
    log_path: Path
    restart_limit: int = 3
    proc: subprocess.Popen | None = None
    restart_count: int = 0
    log_handle: object | None = None


@dataclass(frozen=True)
class InfraTarget:
    name: str
    host: str
    port: int


def load_backend_env() -> dict:
    env_file = BACKEND_DIR / ".env"
    env = os.environ.copy()
    if env_file.exists():
        def parse_env_line(raw_line: str) -> tuple[str | None, str | None]:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                return None, None

            if line.startswith("export "):
                line = line[len("export "):].strip()

            if "=" not in line:
                return None, None

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                return None, None

            if not value:
                return key, ""

            # Quoted values keep everything inside quotes (including '#').
            if value[0] in ("'", '"'):
                quote = value[0]
                end_idx = value.find(quote, 1)
                if end_idx != -1:
                    return key, value[1:end_idx]
                return key, value[1:]

            # Unquoted values: strip inline comments like `KEY=value  # comment`.
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
            return key, value

        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                key, value = parse_env_line(line)
                if key is None or value is None:
                    continue
                # Do not clobber existing non-empty secrets with blank .env entries.
                if value == "" and env.get(key):
                    continue
                env[key] = value
    return env


def parse_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def parse_host_port(endpoint: str, default_port: int) -> tuple[str, int]:
    value = endpoint.strip()
    if "://" in value:
        parsed = urllib.parse.urlparse(value)
        host = parsed.hostname or "localhost"
        port = parsed.port or default_port
        return host, port

    bare = value.split("/", 1)[0]
    if ":" in bare:
        host, port_str = bare.rsplit(":", 1)
        return host, parse_int(port_str, default_port)
    return bare, default_port


def parse_redis_host_port(redis_url: str) -> tuple[str, int]:
    normalized = redis_url if "://" in redis_url else f"redis://{redis_url}"
    parsed = urllib.parse.urlparse(normalized)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    return host, port


def get_infra_targets(env: dict) -> list[InfraTarget]:
    db_host = env.get("DB_HOST", "localhost")
    db_port = parse_int(env.get("DB_PORT"), 5432)
    milvus_host = env.get("MILVUS_HOST", "localhost")
    milvus_port = parse_int(env.get("MILVUS_PORT"), 19530)
    minio_host, minio_port = parse_host_port(env.get("MINIO_ENDPOINT", "localhost:9000"), 9000)
    redis_host, redis_port = parse_redis_host_port(env.get("REDIS_URL", "redis://localhost:6379/0"))

    return [
        InfraTarget(name="postgresql", host=db_host, port=db_port),
        InfraTarget(name="milvus", host=milvus_host, port=milvus_port),
        InfraTarget(name="minio", host=minio_host, port=minio_port),
        InfraTarget(name="redis", host=redis_host, port=redis_port),
    ]


def check_tcp_endpoint(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def missing_infra_targets(targets: list[InfraTarget]) -> list[InfraTarget]:
    return [target for target in targets if not check_tcp_endpoint(target.host, target.port)]


def run_docker_infra_up() -> bool:
    commands = (
        ["docker", "compose", "up", "-d"],
        ["docker-compose", "up", "-d"],
    )
    errors: list[str] = []
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            errors.append(f"{cmd[0]} not found")
            continue

        if result.returncode == 0:
            print(f"Infrastructure startup command succeeded: {' '.join(cmd)}")
            return True
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        errors.append(f"{' '.join(cmd)} failed: {stderr or stdout or 'unknown error'}")

    print("Could not start Docker infrastructure automatically.")
    for err in errors:
        print(f"  - {err}")
    return False


def ensure_infrastructure_ready(backend_env: dict, auto_start: bool, timeout: int = 90) -> bool:
    targets = get_infra_targets(backend_env)
    missing = missing_infra_targets(targets)
    if not missing:
        print("Infrastructure preflight passed.")
        return True

    print("Infrastructure dependencies are not reachable:")
    for target in missing:
        print(f"  - {target.name}: {target.host}:{target.port}")

    if not auto_start:
        print("Start infrastructure manually (e.g. `docker compose up -d`) and retry.")
        return False

    print("Attempting to start Docker infrastructure...")
    if not run_docker_infra_up():
        return False

    print("Waiting for infrastructure endpoints...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        missing = missing_infra_targets(targets)
        if not missing:
            print(" ready")
            print("Infrastructure preflight passed.")
            return True
        print(".", end="", flush=True)
        time.sleep(2)

    print(" timeout")
    print("Infrastructure is still unavailable after startup attempt:")
    for target in missing:
        print(f"  - {target.name}: {target.host}:{target.port}")
    return False


def list_listening_pids(port: int) -> list[str]:
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                shell=True,
            )
            pids = []
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit():
                        pids.append(pid)
            return sorted(set(pids))

        result = subprocess.run(
            ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return sorted(set(pid.strip() for pid in result.stdout.splitlines() if pid.strip().isdigit()))
    except Exception:
        return []


def kill_process_on_port(port: int) -> None:
    for pid in list_listening_pids(port):
        print(f"  Killing process {pid} on port {port}...")
        if sys.platform == "win32":
            subprocess.run(f"taskkill /F /T /PID {pid}", capture_output=True, shell=True)
        else:
            subprocess.run(["kill", "-TERM", pid], capture_output=True, text=True)


def check_port_conflicts(force_cleanup: bool) -> bool:
    conflicts = {port: list_listening_pids(port) for port in (8000, 3000)}
    in_use = {port: pids for port, pids in conflicts.items() if pids}
    if not in_use:
        return True

    if force_cleanup:
        print("Cleaning up previous instances...")
        for port in in_use:
            kill_process_on_port(port)
        time.sleep(1)
        return not any(list_listening_pids(port) for port in (8000, 3000))

    print("Port conflicts detected:")
    for port, pids in in_use.items():
        print(f"  - port {port} is already in use by PID(s): {', '.join(pids)}")
    print("Use --force-cleanup to terminate listeners on 3000/8000.")
    return False


def check_prerequisites() -> bool:
    errors = []
    if not VENV_PYTHON.exists():
        errors.append(f"Backend venv not found: {VENV_PYTHON}")
    if not (FRONTEND_DIR / "node_modules").exists():
        errors.append("Frontend node_modules not found (run: cd frontend && npm install)")
    if not (BACKEND_DIR / ".env").exists():
        errors.append("Backend .env not found (run: cd backend && cp .env.example .env)")

    if errors:
        print("PREREQUISITE ERRORS:")
        for idx, err in enumerate(errors, 1):
            print(f"  {idx}. {err}")
        return False
    return True


def start_service(service: ManagedService) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    service.log_handle = open(service.log_path, "a", buffering=1, encoding="utf-8")

    kwargs = {
        "cwd": service.cwd,
        "env": service.env,
        "stdin": subprocess.DEVNULL,
        "stdout": service.log_handle,
        "stderr": subprocess.STDOUT,
        "text": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    service.proc = subprocess.Popen(service.cmd, **kwargs)
    print(f"[{service.name}] started (pid={service.proc.pid})")


def stop_service(service: ManagedService, timeout: int = 8) -> None:
    proc = service.proc
    if not proc or proc.poll() is not None:
        return

    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=timeout)
    except Exception:
        try:
            if sys.platform == "win32":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


def wait_for_backend(timeout: int = 45) -> bool:
    url = "http://localhost:8000/health/live"
    print("Waiting for backend to be ready...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(url, timeout=3)
            if resp.status == 200:
                print(" ready")
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" timeout")
    return False


def check_services() -> None:
    url = "http://localhost:8000/health/ready"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read().decode())
        services = data.get("services", {})
        if services:
            print("Infrastructure status:")
            for name, info in services.items():
                status = info.get("status", "unknown")
                print(f"  - {name}: {status}")
    except Exception:
        print("Could not check infrastructure services.")


def shutdown(signum=None, frame=None) -> None:
    del signum, frame
    global SHUTTING_DOWN
    if SHUTTING_DOWN:
        return
    SHUTTING_DOWN = True

    print("\nShutting down services...")
    for svc in SERVICES:
        stop_service(svc)
        if svc.log_handle:
            svc.log_handle.close()
    print("All services stopped.")
    raise SystemExit(0)


def detach_on_sigterm(signum=None, frame=None) -> None:
    del signum, frame
    print("\nReceived SIGTERM: detaching launcher and leaving services running.")
    for svc in SERVICES:
        if svc.log_handle:
            svc.log_handle.close()
            svc.log_handle = None
    raise SystemExit(0)


def monitor_services() -> None:
    global SHUTTING_DOWN
    while not SHUTTING_DOWN:
        time.sleep(1)
        for svc in SERVICES:
            if not svc.proc:
                continue
            rc = svc.proc.poll()
            if rc is None:
                continue

            print(f"[{svc.name}] exited with code {rc}")
            if svc.restart_count >= svc.restart_limit:
                print(f"[{svc.name}] restart limit reached ({svc.restart_limit}); shutting down.")
                shutdown()
                return

            svc.restart_count += 1
            print(f"[{svc.name}] restarting ({svc.restart_count}/{svc.restart_limit})...")
            if svc.log_handle:
                svc.log_handle.close()
            start_service(svc)


def build_celery_command() -> list[str]:
    """Build a platform-appropriate Celery worker command.

    Defaults:
    - Windows: solo pool (process forking is unavailable)
    - macOS: solo pool (prefork forks the process; native extensions used by the
      ingestion pipeline — PyMuPDF, gRPC — are not fork-safe on Darwin and the
      worker aborts with SIGABRT/SIGSEGV, leaving jobs stuck in "pending")
    - Linux: prefork pool (keeps control-plane ping responsive while tasks run)
    Override with CELERY_POOL=prefork if you know your stack is fork-safe.
    """
    base = (
        [str(VENV_CELERY), "-A", "app.worker", "worker", "--loglevel=info"]
        if VENV_CELERY.exists()
        else [str(VENV_PYTHON), "-m", "celery", "-A", "app.worker", "worker", "--loglevel=info"]
    )

    default_pool = "solo" if sys.platform in ("win32", "darwin") else "prefork"
    pool = os.getenv("CELERY_POOL", default_pool)
    cmd = [*base, "--pool", pool]

    if pool != "solo":
        # Keep default concurrency conservative for local laptops unless explicitly set.
        default_concurrency = str(max(2, min(4, os.cpu_count() or 2)))
        concurrency = os.getenv("CELERY_CONCURRENCY", default_concurrency)
        cmd.extend(["--concurrency", concurrency])

    return cmd


def build_services(skip_celery: bool, backend_env: dict) -> list[ManagedService]:
    services = [
        ManagedService(
            name="backend",
            cmd=[
                str(VENV_PYTHON),
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ],
            cwd=BACKEND_DIR,
            env=backend_env,
            log_path=LOG_DIR / "backend.log",
            restart_limit=5,
        ),
        ManagedService(
            name="frontend",
            cmd=["npm", "run", "dev"],
            cwd=FRONTEND_DIR,
            env=os.environ.copy(),
            log_path=LOG_DIR / "frontend.log",
            restart_limit=5,
        ),
    ]

    if not skip_celery:
        celery_cmd = build_celery_command()
        services.append(
            ManagedService(
                name="celery",
                cmd=celery_cmd,
                cwd=BACKEND_DIR,
                env=backend_env,
                log_path=LOG_DIR / "celery.log",
                restart_limit=5,
            )
        )
    return services


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NPR RAG app services")
    parser.add_argument("--no-celery", action="store_true", help="Skip celery worker")
    parser.add_argument(
        "--skip-infra-check",
        action="store_true",
        help="Skip infrastructure preflight checks (PostgreSQL, Milvus, MinIO, Redis)",
    )
    parser.add_argument(
        "--no-auto-infra",
        action="store_true",
        help="Do not auto-run `docker compose up -d` when local infrastructure is down",
    )
    parser.add_argument(
        "--force-cleanup",
        action="store_true",
        help="Kill listeners on ports 3000 and 8000 before starting",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("=" * 55)
    print("  Near Perfect RAG | Cognitive Code | cognitiveCode.ai")
    print("=" * 55)

    signal.signal(signal.SIGINT, shutdown)
    # Keep child services alive if the parent launcher receives SIGTERM
    # from terminal/session teardown.
    signal.signal(signal.SIGTERM, detach_on_sigterm)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, shutdown)

    if not check_prerequisites():
        raise SystemExit(1)
    if not check_port_conflicts(args.force_cleanup):
        raise SystemExit(1)

    backend_env = load_backend_env()
    if not args.skip_infra_check:
        if not ensure_infrastructure_ready(
            backend_env,
            auto_start=not args.no_auto_infra,
        ):
            raise SystemExit(1)

    lock_file = FRONTEND_DIR / ".next" / "dev" / "lock"
    if lock_file.exists():
        try:
            lock_file.unlink()
        except Exception:
            pass

    SERVICES.extend(build_services(skip_celery=args.no_celery, backend_env=backend_env))
    for svc in SERVICES:
        start_service(svc)

    wait_for_backend()
    check_services()

    print("\nAll services running:")
    print("  Frontend:    http://localhost:3000")
    print("  Backend API: http://localhost:8000")
    print("  API docs:    http://localhost:8000/docs")
    print("  Logs:")
    for svc in SERVICES:
        print(f"    - {svc.name}: {svc.log_path}")
    print("\nPress Ctrl+C to stop.")

    monitor_services()


if __name__ == "__main__":
    main()
