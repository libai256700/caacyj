from __future__ import annotations

import os

DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")


def resolve_neo4j_password() -> str:
    env_password = os.environ.get("NEO4J_PASSWORD") or os.environ.get("NEO4J_PASS")
    if env_password:
        return env_password.strip()
    raise FileNotFoundError("Neo4j password not found in NEO4J_PASSWORD or NEO4J_PASS")


def ensure_runtime_secret_files() -> None:
    """线上部署不写任何凭据文件；密码只经 NEO4J_PASSWORD 环境变量注入。
    保留空实现以兼容既有调用点。"""
    return None

