#!/usr/bin/env python3
"""Offline tests for the hash-bound public HS256 WSGI identity chain."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from deploy.cloud_v2.identity_policy import (
    VERIFIED_IDENTITY_ENVIRON_KEY,
    VerifiedIdentity,
)
from deploy.pipeline.public_identity_middleware import (
    CONFIG_ENVIRONMENT_VARIABLE,
    CONFIG_SCHEMA_VERSION,
    CONFIG_SHA256_ENVIRONMENT_VARIABLE,
    PublicIdentityConfigError,
    PublicIdentityMiddleware,
    PublicIdentitySecretError,
    create_authenticated_wsgi_app,
    load_public_identity_verifier_from_environment,
    startup_error_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "deploy/pipeline/public_identity_config.schema.json"
WSGI_PATH = REPO_ROOT / "deploy/pipeline/wsgi.py"
NOW = 2_000_000_000
SECRET = b"public-gateway-hs256-secret-key-32"
WRONG_SECRET = b"wrong--gateway-hs256-secret-key-32"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _segment(value: object) -> str:
    return _base64url(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def signed_token(
    payload: dict[str, object],
    *,
    secret: bytes = SECRET,
    header: dict[str, object] | None = None,
) -> str:
    encoded_header = _segment(header or {"alg": "HS256", "typ": "JWT"})
    encoded_payload = _segment(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = _base64url(hmac.new(secret, signing_input, hashlib.sha256).digest())
    return f"{encoded_header}.{encoded_payload}.{signature}"


def config_document() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "verifier": {
            "kind": "hs256-jwt-gateway-v1",
            "algorithm": "HS256",
            "issuer": "urn:example:trusted-public-gateway",
            "audience": "public-app-agent",
            "secret_ref": {
                "value": "secretref:KG_PUBLIC_IDENTITY_HS256_SECRET",
                "encoding": "base64url",
            },
            "token_source": {
                "wsgi_environ_key": "HTTP_AUTHORIZATION",
                "scheme": "Bearer",
            },
            "time_policy": {
                "leeway_seconds": 5,
                "max_lifetime_seconds": 300,
            },
            "claim_mapping": {
                "subject": "sub",
                "roles": "roles",
                "authn_methods": "amr",
            },
            "identity_contract": {
                "service_account": "public-app-agent",
                "token_kind": "public-app-access",
                "network_zone": "public-app",
                "required_roles": ["app-user"],
            },
        },
    }


def token_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "iss": "urn:example:trusted-public-gateway",
        "aud": "public-app-agent",
        "sub": "app-user:synthetic-1",
        "roles": ["app-user"],
        "amr": ["gateway-hs256"],
        "iat": NOW - 10,
        "nbf": NOW - 10,
        "exp": NOW + 60,
    }
    payload.update(changes)
    return payload


class PublicIdentityMiddlewareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="kg-public-identity-test-"
        )
        self.root = Path(self.temporary.name).resolve()
        self.config_path = self.root / "public-identity.json"
        self.environment: dict[str, str] = {}
        self.write_config(config_document())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_config(self, document: dict[str, object]) -> None:
        payload = json.dumps(
            document,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.config_path.write_bytes(payload)
        os.chmod(self.config_path, 0o600)
        self.environment = {
            CONFIG_ENVIRONMENT_VARIABLE: str(self.config_path),
            CONFIG_SHA256_ENVIRONMENT_VARIABLE: hashlib.sha256(payload).hexdigest(),
            "KG_PUBLIC_IDENTITY_HS256_SECRET": _base64url(SECRET),
        }

    def verifier(self):
        return load_public_identity_verifier_from_environment(
            self.environment, clock=lambda: NOW
        )

    def invoke(
        self,
        *,
        token: str | None = None,
        extra_environ: dict[str, object] | None = None,
    ) -> tuple[str, bytes, list[VerifiedIdentity]]:
        identities: list[VerifiedIdentity] = []

        def application(environ, start_response):
            identities.append(environ[VERIFIED_IDENTITY_ENVIRON_KEY])
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"downstream-ok"]

        middleware = PublicIdentityMiddleware(application, self.verifier())
        environ: dict[str, object] = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/ask",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "5001",
            "wsgi.url_scheme": "http",
        }
        if token is not None:
            environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        environ.update(extra_environ or {})
        captured: dict[str, object] = {}

        def start_response(status, headers, _exc_info=None):
            captured["status"] = status
            captured["headers"] = headers

        body = b"".join(middleware(environ, start_response))
        return str(captured["status"]), body, identities

    def assert_denied(self, token: str | None, **kwargs) -> None:
        status, body, identities = self.invoke(token=token, **kwargs)
        self.assertEqual("403 Forbidden", status)
        self.assertEqual(
            {"error": "access_denied", "request_rejected": True},
            json.loads(body),
        )
        self.assertEqual([], identities)

    def test_valid_signature_installs_only_fixed_public_identity(self) -> None:
        status, body, identities = self.invoke(
            token=signed_token(token_payload()),
            extra_environ={
                "HTTP_X_KG_VERIFIED_AUDIENCE": "ops-admin-agent",
                "HTTP_X_KG_VERIFIED_ROLE": "ops-maintainer",
                VERIFIED_IDENTITY_ENVIRON_KEY: "forged-preinstalled-value",
            },
        )

        self.assertEqual("200 OK", status)
        self.assertEqual(b"downstream-ok", body)
        self.assertEqual(1, len(identities))
        identity = identities[0]
        self.assertIsInstance(identity, VerifiedIdentity)
        self.assertEqual("app-user:synthetic-1", identity.subject)
        self.assertEqual("public-app-agent", identity.audience)
        self.assertEqual("public-app-agent", identity.service_account)
        self.assertEqual("public-app-access", identity.token_kind)
        self.assertEqual("public-app", identity.network_zone)
        self.assertEqual(("gateway-hs256",), identity.authn_methods)
        self.assertEqual(("app-user",), identity.roles)

    def test_plain_forwarded_identity_headers_and_preinstalled_value_are_denied(self) -> None:
        self.assert_denied(
            None,
            extra_environ={
                "HTTP_X_KG_VERIFIED_AUDIENCE": "public-app-agent",
                "HTTP_X_KG_VERIFIED_ROLE": "app-user",
                "HTTP_KG_VERIFIED_IDENTITY": "forged",
                VERIFIED_IDENTITY_ENVIRON_KEY: "forged-preinstalled-value",
            },
        )

    def test_alg_none_and_wrong_key_are_denied(self) -> None:
        self.assert_denied(
            signed_token(
                token_payload(),
                header={"alg": "none", "typ": "JWT"},
            )
        )
        self.assert_denied(signed_token(token_payload(), secret=WRONG_SECRET))

    def test_wrong_issuer_or_audience_is_denied(self) -> None:
        invalid = (
            token_payload(iss="urn:example:untrusted-gateway"),
            token_payload(aud="ops-admin-agent"),
            token_payload(aud=["public-app-agent", "other-audience"]),
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assert_denied(signed_token(payload))

    def test_expired_or_future_token_is_denied(self) -> None:
        invalid = (
            token_payload(iat=NOW - 100, nbf=NOW - 100, exp=NOW - 6),
            token_payload(iat=NOW + 6, nbf=NOW + 6, exp=NOW + 100),
            token_payload(iat=NOW - 400, nbf=NOW - 400, exp=NOW + 1),
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assert_denied(signed_token(payload))

    def test_missing_or_extra_role_is_denied(self) -> None:
        invalid = (
            token_payload(roles=[]),
            token_payload(roles=["ops-observer"]),
            token_payload(roles=["app-user", "ops-maintainer"]),
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assert_denied(signed_token(payload))

    def test_missing_config_hash_or_secret_fails_preflight(self) -> None:
        cases = (
            (
                {
                    key: value
                    for key, value in self.environment.items()
                    if key != CONFIG_ENVIRONMENT_VARIABLE
                },
                PublicIdentityConfigError,
                "public_identity_config_missing",
            ),
            (
                {
                    key: value
                    for key, value in self.environment.items()
                    if key != CONFIG_SHA256_ENVIRONMENT_VARIABLE
                },
                PublicIdentityConfigError,
                "public_identity_config_hash_missing",
            ),
            (
                {
                    key: value
                    for key, value in self.environment.items()
                    if key != "KG_PUBLIC_IDENTITY_HS256_SECRET"
                },
                PublicIdentitySecretError,
                "public_identity_secret_missing",
            ),
        )
        for environment, error_type, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(error_type) as caught:
                    load_public_identity_verifier_from_environment(environment)
                self.assertEqual(code, caught.exception.code)

    def test_config_hash_drift_and_unsafe_permissions_fail_preflight(self) -> None:
        self.config_path.write_bytes(self.config_path.read_bytes() + b"\n")
        with self.assertRaises(PublicIdentityConfigError) as drifted:
            load_public_identity_verifier_from_environment(self.environment)
        self.assertEqual("public_identity_config_hash_mismatch", drifted.exception.code)

        self.write_config(config_document())
        os.chmod(self.config_path, 0o666)
        try:
            with self.assertRaises(PublicIdentityConfigError) as unsafe:
                load_public_identity_verifier_from_environment(self.environment)
            self.assertEqual(
                "public_identity_config_permissions_invalid", unsafe.exception.code
            )
        finally:
            os.chmod(self.config_path, 0o600)

    def test_symlink_config_path_is_rejected(self) -> None:
        link = self.root / "public-identity-link.json"
        link.symlink_to(self.config_path)
        environment = dict(self.environment)
        environment[CONFIG_ENVIRONMENT_VARIABLE] = str(link)
        with self.assertRaises(PublicIdentityConfigError) as caught:
            load_public_identity_verifier_from_environment(environment)
        self.assertEqual("public_identity_config_path_invalid", caught.exception.code)

    def test_unknown_verifier_or_drifted_fixed_contract_is_rejected(self) -> None:
        invalid = config_document()
        invalid["verifier"]["algorithm"] = "none"
        self.write_config(invalid)
        with self.assertRaises(PublicIdentityConfigError) as algorithm:
            load_public_identity_verifier_from_environment(self.environment)
        self.assertEqual("public_identity_verifier_not_allowed", algorithm.exception.code)

        invalid = config_document()
        invalid["verifier"]["identity_contract"]["required_roles"] = [
            "ops-maintainer"
        ]
        self.write_config(invalid)
        with self.assertRaises(PublicIdentityConfigError) as contract:
            load_public_identity_verifier_from_environment(self.environment)
        self.assertEqual("public_identity_contract_invalid", contract.exception.code)

    def test_identity_preflight_precedes_runtime_factory_and_wraps_app(self) -> None:
        calls: list[str] = []

        class Application:
            def __init__(self) -> None:
                self.wsgi_app = lambda _environ, _start_response: []
                self.extensions: dict[str, object] = {}

        def factory():
            calls.append("factory")
            return Application()

        missing = dict(self.environment)
        del missing[CONFIG_ENVIRONMENT_VARIABLE]
        with self.assertRaises(PublicIdentityConfigError):
            create_authenticated_wsgi_app(factory, environment=missing)
        self.assertEqual([], calls)

        application = create_authenticated_wsgi_app(
            factory,
            environment=self.environment,
            clock=lambda: NOW,
        )
        self.assertEqual(["factory"], calls)
        self.assertIsInstance(application.wsgi_app, PublicIdentityMiddleware)
        contract = application.extensions["public_identity_contract"]
        self.assertEqual("HS256", contract["algorithm"])
        self.assertEqual(
            self.environment[CONFIG_SHA256_ENVIRONMENT_VARIABLE],
            contract["config_sha256"],
        )

    def test_schema_and_startup_error_are_machine_readable_and_sanitized(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(CONFIG_SCHEMA_VERSION, schema["properties"]["schema_version"]["const"])
        self.assertEqual(
            "HS256",
            schema["properties"]["verifier"]["properties"]["algorithm"]["const"],
        )
        payload = startup_error_payload(
            PublicIdentityConfigError("public_identity_config_hash_mismatch")
        )
        self.assertEqual("public_identity_config_hash_mismatch", payload["error"])
        self.assertFalse(payload["public_identity_ready"])
        self.assertNotIn(str(self.config_path), json.dumps(payload))

    def test_pipeline_wsgi_exports_eager_wrapped_app(self) -> None:
        calls: list[str] = []

        class Application:
            def __init__(self) -> None:
                self.wsgi_app = lambda _environ, _start_response: []
                self.extensions: dict[str, object] = {}

        server = types.ModuleType("pipeline.server")
        server.EX_CONFIG = 78

        def factory():
            calls.append("factory")
            return Application()

        server.create_wsgi_app = factory
        spec = importlib.util.spec_from_file_location(
            "pipeline_wsgi_valid_identity_test", WSGI_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        with (
            mock.patch.object(
                sys, "path", [str(REPO_ROOT / "deploy"), *sys.path]
            ),
            mock.patch.dict(sys.modules, {"pipeline.server": server}),
            mock.patch.dict(os.environ, self.environment, clear=True),
        ):
            spec.loader.exec_module(module)

        self.assertEqual(["factory"], calls)
        self.assertEqual(
            "PublicIdentityMiddleware", type(module.app.wsgi_app).__name__
        )
        self.assertTrue(callable(module.app.wsgi_app))

    def test_pipeline_wsgi_missing_identity_config_exits_before_runtime_factory(self) -> None:
        calls: list[str] = []
        server = types.ModuleType("pipeline.server")
        server.EX_CONFIG = 78

        def factory():
            calls.append("factory")
            raise AssertionError("runtime factory must not run")

        server.create_wsgi_app = factory
        spec = importlib.util.spec_from_file_location(
            "pipeline_wsgi_missing_identity_test", WSGI_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        stderr = io.StringIO()
        with (
            mock.patch.object(
                sys, "path", [str(REPO_ROOT / "deploy"), *sys.path]
            ),
            mock.patch.dict(sys.modules, {"pipeline.server": server}),
            mock.patch.dict(os.environ, {}, clear=True),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as caught,
        ):
            spec.loader.exec_module(module)

        self.assertEqual(78, caught.exception.code)
        self.assertEqual([], calls)
        payload = json.loads(stderr.getvalue())
        self.assertEqual("public_identity_config_missing", payload["error"])
        self.assertFalse(payload["public_identity_ready"])


if __name__ == "__main__":
    unittest.main()
