#!/usr/bin/env python3
"""Production assembly for loopback legacy GET over authenticated cloud-v2."""

from __future__ import annotations

import json
import sys

from pipeline.legacy_compat_wsgi import LegacyCompatWSGI
from pipeline.mixed_provider_bootstrap import (
    load_mixed_provider_bound_runtime_from_environment,
)
from pipeline.public_identity_middleware import (
    PublicIdentityMiddleware,
    load_public_identity_verifier_from_environment,
    startup_error_payload,
)
from pipeline.server import EX_CONFIG, create_app


def create_legacy_production_app() -> LegacyCompatWSGI:
    verifier = load_public_identity_verifier_from_environment()
    runtime = load_mixed_provider_bound_runtime_from_environment()
    try:
        inner = create_app(lambda: runtime, preflight=True)
        inner.wsgi_app = PublicIdentityMiddleware(inner.wsgi_app, verifier)
        return LegacyCompatWSGI(inner.wsgi_app, verifier)
    except Exception:
        runtime.close()
        raise


try:
    app = create_legacy_production_app()
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


__all__ = ["app", "create_legacy_production_app"]
