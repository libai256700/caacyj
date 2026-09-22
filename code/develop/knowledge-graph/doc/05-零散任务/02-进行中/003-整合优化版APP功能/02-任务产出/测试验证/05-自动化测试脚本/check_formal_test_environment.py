#!/usr/bin/env python3
"""Validate formal Test entry metadata without connecting to any service."""

from __future__ import annotations

import os
from urllib.parse import urlparse


REQUIRED = (
    "KG_TEST_BASE_URL",
    "KG_TEST_PAGE_URL",
    "KG_TEST_NEO4J_URI",
    "KG_TEST_SQLITE_ENTRY",
    "KG_TEST_START_OR_DEPLOY_ENTRY",
)


def main() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        print("BLOCKED: missing formal Test entries: " + ", ".join(missing))
        return 2

    for name in ("KG_TEST_BASE_URL", "KG_TEST_PAGE_URL"):
        value = os.environ[name].strip()
        host = (urlparse(value).hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            print(f"BLOCKED: {name} must reference formal Test, not local host")
            return 2

    print("FORMAL_TEST_ENVIRONMENT_METADATA_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

