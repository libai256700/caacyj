#!/usr/bin/env python3
"""Fail-closed WSGI entrypoint for the public knowledge service."""

from __future__ import annotations

import json
import sys

from pipeline.public_identity_middleware import (
    create_authenticated_wsgi_app,
    startup_error_payload,
)
from pipeline.server import EX_CONFIG, create_wsgi_app


try:
    app = create_authenticated_wsgi_app(create_wsgi_app)
except Exception as error:
    print(
        json.dumps(
            startup_error_payload(error),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
        flush=True,
    )
    raise SystemExit(EX_CONFIG) from None
