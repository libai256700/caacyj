#!/usr/bin/env python3
"""Start the knowledge graph API in the local Anaconda know-v2 environment."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVICE_URL = "http://127.0.0.1:5001"
DEFAULT_KNOW_V2_PYTHON = Path(r"D:\ProgramData\anaconda3\envs\know-v2\python.exe")
COMPOSE_FILE = PROJECT_ROOT / "neo4j-docker" / "docker-compose.yml"
SERVER_LOG = PROJECT_ROOT / "logs" / "know_v2_service.log"


def run(command: list[str], *, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")
    return result


def find_python() -> Path:
    env_path = os.getenv("KNOW_V2_PYTHON")
    candidates = [
        Path(env_path) if env_path else None,
        DEFAULT_KNOW_V2_PYTHON,
        Path(r"C:\ProgramData\anaconda3\envs\know-v2\python.exe"),
        Path(r"C:\Users\renquan\anaconda3\envs\know-v2\python.exe"),
        Path(r"C:\Users\renquan\miniconda3\envs\know-v2\python.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Cannot find know-v2 python. Set KNOW_V2_PYTHON to the full python.exe path."
    )


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(host: str, port: int, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if port_open(host, port):
            return True
        time.sleep(2)
    return False


def request_text(url: str, timeout: int = 10) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def wait_for_health(service_url: str, seconds: int) -> tuple[bool, str]:
    deadline = time.time() + seconds
    last = ""
    health_url = service_url.rstrip("/") + "/api/health"
    while time.time() < deadline:
        status, body = request_text(health_url)
        last = f"HTTP {status}: {body}"
        if status == 200:
            return True, last
        time.sleep(3)
    return False, last


def start_service(python_exe: Path, service_url: str) -> None:
    if port_open("127.0.0.1", 5001):
        print("Port 5001 is already open; assuming the API is already running.")
        return

    log_dir = SERVER_LOG.parent
    log_dir.mkdir(exist_ok=True)
    log_file = SERVER_LOG.open("ab")
    command = [str(python_exe), "-X", "utf8", "pipeline/server.py"]
    print(f"> start {' '.join(command)}")
    print(f"Logging to: {SERVER_LOG}")
    subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not wait_for_port("127.0.0.1", 5001, 60):
        raise TimeoutError(f"API did not open port 5001. Check log: {SERVER_LOG}")
    print(f"API port is reachable: {service_url}")


def start_neo4j(skip: bool) -> None:
    if skip:
        print("Skipping Neo4j startup.")
        return
    if not COMPOSE_FILE.is_file():
        raise FileNotFoundError(f"Missing compose file: {COMPOSE_FILE}")
    run(["docker", "info"], timeout=30, check=True)
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"], timeout=300, check=True)
    if wait_for_port("127.0.0.1", 7687, 180):
        print("Neo4j Bolt port is reachable: 127.0.0.1:7687")
    else:
        raise TimeoutError("Neo4j Bolt port did not become reachable on 127.0.0.1:7687")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the knowledge graph API in know-v2.")
    parser.add_argument("--skip-neo4j", action="store_true", help="Do not start Neo4j.")
    parser.add_argument("--service-url", default=DEFAULT_SERVICE_URL)
    args = parser.parse_args()

    python_exe = find_python()
    print(f"Project root: {PROJECT_ROOT}")
    print(f"know-v2 python: {python_exe}")

    start_neo4j(args.skip_neo4j)
    start_service(python_exe, args.service_url)
    ok, health = wait_for_health(args.service_url, 180)
    print(f"Health check: {health}")
    if not ok:
        return 2

    print(f"Knowledge graph API is ready: {args.service_url}")
    print(f"Query example: {args.service_url}/api/ask?q=测试")
    print(f"File import endpoint: POST {args.service_url}/api/files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
