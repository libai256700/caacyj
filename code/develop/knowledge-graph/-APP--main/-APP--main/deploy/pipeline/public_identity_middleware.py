#!/usr/bin/env python3
"""Hash-bound HS256 gateway authentication for the public WSGI surface."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import re
import stat
import sys
import time
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from deploy.cloud_v2.identity_policy import (  # noqa: E402
    PUBLIC_AUDIENCE,
    VERIFIED_IDENTITY_ENVIRON_KEY,
    VerifiedIdentity,
)


CONFIG_ENVIRONMENT_VARIABLE = "KG_PUBLIC_IDENTITY_CONFIG"
CONFIG_SHA256_ENVIRONMENT_VARIABLE = "KG_PUBLIC_IDENTITY_CONFIG_SHA256"
CONFIG_SCHEMA_VERSION = "kg-public-identity-gateway-config-v1"
VERIFIER_KIND = "hs256-jwt-gateway-v1"
JWT_ALGORITHM = "HS256"
JWT_TYPE = "JWT"
PUBLIC_SERVICE_ACCOUNT = PUBLIC_AUDIENCE
PUBLIC_TOKEN_KIND = "public-app-access"
PUBLIC_NETWORK_ZONE = "public-app"
PUBLIC_REQUIRED_ROLE = "app-user"
MAX_CONFIG_BYTES = 64 * 1024
MAX_TOKEN_BYTES = 16 * 1024
MIN_SECRET_BYTES = 32
MAX_SECRET_BYTES = 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_REF = re.compile(r"^secretref:(KG_[A-Z0-9_]{1,96})$")
_CLAIM_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_AUTHN_METHOD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


class PublicIdentityError(RuntimeError):
    """Sanitized public identity failure with a stable error code."""

    def __init__(self, code: str) -> None:
        super().__init__("public identity verification failed")
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "kg-public-identity-bootstrap-error-v1",
            "error": self.code,
            "public_identity_ready": False,
        }


class PublicIdentityConfigError(PublicIdentityError):
    pass


class PublicIdentitySecretError(PublicIdentityError):
    pass


class PublicIdentityTokenError(PublicIdentityError):
    pass


@dataclass(frozen=True)
class PublicIdentityConfig:
    issuer: str
    audience: str
    secret_environment_variable: str
    leeway_seconds: int
    max_lifetime_seconds: int
    subject_claim: str
    roles_claim: str
    authn_methods_claim: str
    config_path: Path
    config_sha256: str

    def contract(self) -> dict[str, Any]:
        return {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "verifier_kind": VERIFIER_KIND,
            "algorithm": JWT_ALGORITHM,
            "config_sha256": self.config_sha256,
            "issuer": self.issuer,
            "audience": self.audience,
            "token_source": "HTTP_AUTHORIZATION:Bearer",
            "identity_contract": {
                "service_account": PUBLIC_SERVICE_ACCOUNT,
                "token_kind": PUBLIC_TOKEN_KIND,
                "network_zone": PUBLIC_NETWORK_ZONE,
                "required_roles": [PUBLIC_REQUIRED_ROLE],
            },
        }


@dataclass(frozen=True)
class PublicIdentityVerifier:
    config: PublicIdentityConfig
    _secret: bytes = field(repr=False)
    _clock: Callable[[], float] = field(repr=False, compare=False)

    def verify_environ(self, environ: Mapping[str, Any]) -> VerifiedIdentity:
        if not isinstance(environ, Mapping):
            raise PublicIdentityTokenError("public_identity_access_denied")
        authorization = environ.get("HTTP_AUTHORIZATION")
        if (
            not isinstance(authorization, str)
            or not authorization.startswith("Bearer ")
            or authorization != authorization.strip()
        ):
            raise PublicIdentityTokenError("public_identity_access_denied")
        token = authorization.removeprefix("Bearer ")
        if (
            not token
            or len(token.encode("utf-8")) > MAX_TOKEN_BYTES
            or any(character.isspace() for character in token)
        ):
            raise PublicIdentityTokenError("public_identity_access_denied")
        payload = self._verified_payload(token)
        subject = _subject(payload.get(self.config.subject_claim))
        roles = _roles(payload.get(self.config.roles_claim))
        authn_methods = _authn_methods(
            payload.get(self.config.authn_methods_claim)
        )
        return VerifiedIdentity(
            subject=subject,
            audience=PUBLIC_AUDIENCE,
            service_account=PUBLIC_SERVICE_ACCOUNT,
            token_kind=PUBLIC_TOKEN_KIND,
            network_zone=PUBLIC_NETWORK_ZONE,
            authn_methods=authn_methods,
            roles=roles,
        )

    def _verified_payload(self, token: str) -> dict[str, Any]:
        segments = token.split(".")
        if len(segments) != 3 or any(not segment for segment in segments):
            raise PublicIdentityTokenError("public_identity_access_denied")
        header_segment, payload_segment, signature_segment = segments
        header = _jwt_json_segment(header_segment)
        if set(header) != {"alg", "typ"}:
            raise PublicIdentityTokenError("public_identity_access_denied")
        if header["alg"] != JWT_ALGORITHM or header["typ"] != JWT_TYPE:
            raise PublicIdentityTokenError("public_identity_access_denied")
        payload = _jwt_json_segment(payload_segment)
        signature = _decode_base64url(signature_segment)
        expected = hmac.new(
            self._secret,
            f"{header_segment}.{payload_segment}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        if len(signature) != len(expected) or not hmac.compare_digest(
            signature, expected
        ):
            raise PublicIdentityTokenError("public_identity_access_denied")
        self._validate_registered_claims(payload)
        return payload

    def _validate_registered_claims(self, payload: Mapping[str, Any]) -> None:
        issuer = payload.get("iss")
        if not isinstance(issuer, str) or not _constant_time_text_equal(
            issuer, self.config.issuer
        ):
            raise PublicIdentityTokenError("public_identity_access_denied")
        audience = payload.get("aud")
        if isinstance(audience, str):
            audiences = (audience,)
        elif (
            isinstance(audience, list)
            and len(audience) == 1
            and isinstance(audience[0], str)
        ):
            audiences = (audience[0],)
        else:
            raise PublicIdentityTokenError("public_identity_access_denied")
        if not hmac.compare_digest(audiences[0], self.config.audience):
            raise PublicIdentityTokenError("public_identity_access_denied")

        issued_at = _integer_timestamp(payload.get("iat"))
        not_before = _integer_timestamp(payload.get("nbf"))
        expires_at = _integer_timestamp(payload.get("exp"))
        if expires_at <= issued_at or not_before > expires_at:
            raise PublicIdentityTokenError("public_identity_access_denied")
        if expires_at - issued_at > self.config.max_lifetime_seconds:
            raise PublicIdentityTokenError("public_identity_access_denied")
        try:
            raw_now = self._clock()
        except Exception:
            raise PublicIdentityTokenError("public_identity_access_denied") from None
        if (
            isinstance(raw_now, bool)
            or not isinstance(raw_now, (int, float))
            or not math.isfinite(raw_now)
        ):
            raise PublicIdentityTokenError("public_identity_access_denied")
        now = int(raw_now)
        leeway = self.config.leeway_seconds
        if issued_at > now + leeway or not_before > now + leeway:
            raise PublicIdentityTokenError("public_identity_access_denied")
        if now >= expires_at + leeway:
            raise PublicIdentityTokenError("public_identity_access_denied")


class PublicIdentityMiddleware:
    """Verify the signed gateway JWT before installing a typed identity."""

    def __init__(self, application: Callable[..., Any], verifier: PublicIdentityVerifier):
        if not callable(application):
            raise PublicIdentityConfigError("public_wsgi_application_invalid")
        if not isinstance(verifier, PublicIdentityVerifier):
            raise PublicIdentityConfigError("public_identity_verifier_invalid")
        self._application = application
        self._verifier = verifier

    def __call__(
        self,
        environ: MutableMapping[str, Any],
        start_response: Callable[..., Any],
    ) -> Any:
        if not isinstance(environ, MutableMapping):
            return _access_denied(start_response)
        environ.pop(VERIFIED_IDENTITY_ENVIRON_KEY, None)
        try:
            identity = self._verifier.verify_environ(environ)
            environ[VERIFIED_IDENTITY_ENVIRON_KEY] = identity
        except Exception:
            environ.pop(VERIFIED_IDENTITY_ENVIRON_KEY, None)
            return _access_denied(start_response)
        return self._application(environ, start_response)


def load_public_identity_verifier_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    clock: Callable[[], float] = time.time,
) -> PublicIdentityVerifier:
    values = os.environ if environment is None else environment
    if not isinstance(values, Mapping):
        raise PublicIdentityConfigError("public_identity_environment_invalid")
    raw_path = values.get(CONFIG_ENVIRONMENT_VARIABLE)
    if not isinstance(raw_path, str) or not raw_path:
        raise PublicIdentityConfigError("public_identity_config_missing")
    expected_sha256 = values.get(CONFIG_SHA256_ENVIRONMENT_VARIABLE)
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(
        expected_sha256
    ):
        raise PublicIdentityConfigError("public_identity_config_hash_missing")
    config_path, payload = _stable_config_bytes(raw_path)
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise PublicIdentityConfigError("public_identity_config_hash_mismatch")
    document = _strict_json_object(
        payload, error_type=PublicIdentityConfigError, code="public_identity_config_invalid"
    )
    parsed = _parse_config(document, config_path, actual_sha256)
    raw_secret = values.get(parsed.secret_environment_variable)
    if not isinstance(raw_secret, str) or not raw_secret:
        raise PublicIdentitySecretError("public_identity_secret_missing")
    secret = _decode_secret(raw_secret)
    return PublicIdentityVerifier(parsed, secret, clock)


def create_authenticated_wsgi_app(
    application_factory: Callable[[], Any],
    *,
    environment: Mapping[str, str] | None = None,
    clock: Callable[[], float] = time.time,
) -> Any:
    """Preflight identity first, then create and wrap the production Flask app."""

    if not callable(application_factory):
        raise PublicIdentityConfigError("public_wsgi_factory_invalid")
    verifier = load_public_identity_verifier_from_environment(
        environment, clock=clock
    )
    application = application_factory()
    raw_wsgi = getattr(application, "wsgi_app", None)
    extensions = getattr(application, "extensions", None)
    if not callable(raw_wsgi) or not isinstance(extensions, dict):
        raise PublicIdentityConfigError("public_wsgi_application_invalid")
    application.wsgi_app = PublicIdentityMiddleware(raw_wsgi, verifier)
    extensions["public_identity_contract"] = verifier.config.contract()
    return application


def startup_error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, PublicIdentityError):
        return error.to_dict()
    return {
        "schema_version": "kg-public-identity-bootstrap-error-v1",
        "error": "public_identity_preflight_failed",
        "public_identity_ready": False,
    }


def _stable_config_bytes(path: str) -> tuple[Path, bytes]:
    raw = Path(path)
    if not raw.is_absolute():
        raise PublicIdentityConfigError("public_identity_config_path_invalid")
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError:
        raise PublicIdentityConfigError("public_identity_config_unavailable") from None
    if resolved != lexical:
        raise PublicIdentityConfigError("public_identity_config_path_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError:
        raise PublicIdentityConfigError("public_identity_config_unavailable") from None
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > MAX_CONFIG_BYTES
            or mode & 0o022
            or before.st_uid not in {0, os.geteuid()}
        ):
            raise PublicIdentityConfigError("public_identity_config_permissions_invalid")
        blocks: list[bytes] = []
        remaining = MAX_CONFIG_BYTES + 1
        while remaining > 0:
            block = os.read(descriptor, min(64 * 1024, remaining))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        payload = b"".join(blocks)
        after = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or len(payload) != before.st_size
            or len(payload) > MAX_CONFIG_BYTES
        ):
            raise PublicIdentityConfigError("public_identity_config_changed")
        return resolved, payload
    finally:
        os.close(descriptor)


def _parse_config(
    value: Mapping[str, Any], config_path: Path, config_sha256: str
) -> PublicIdentityConfig:
    root = _exact_object(
        value,
        {"schema_version", "verifier"},
        code="public_identity_config_invalid",
    )
    if root["schema_version"] != CONFIG_SCHEMA_VERSION:
        raise PublicIdentityConfigError("public_identity_config_schema_mismatch")
    verifier = _exact_object(
        root["verifier"],
        {
            "kind",
            "algorithm",
            "issuer",
            "audience",
            "secret_ref",
            "token_source",
            "time_policy",
            "claim_mapping",
            "identity_contract",
        },
        code="public_identity_config_invalid",
    )
    if verifier["kind"] != VERIFIER_KIND or verifier["algorithm"] != JWT_ALGORITHM:
        raise PublicIdentityConfigError("public_identity_verifier_not_allowed")
    issuer = _strict_text(verifier["issuer"], maximum=512)
    if verifier["audience"] != PUBLIC_AUDIENCE:
        raise PublicIdentityConfigError("public_identity_audience_invalid")
    secret_ref = _exact_object(
        verifier["secret_ref"],
        {"value", "encoding"},
        code="public_identity_config_invalid",
    )
    match = _SECRET_REF.fullmatch(str(secret_ref["value"] or ""))
    if match is None or secret_ref["encoding"] != "base64url":
        raise PublicIdentityConfigError("public_identity_secret_ref_invalid")
    token_source = _exact_object(
        verifier["token_source"],
        {"wsgi_environ_key", "scheme"},
        code="public_identity_config_invalid",
    )
    if token_source != {
        "wsgi_environ_key": "HTTP_AUTHORIZATION",
        "scheme": "Bearer",
    }:
        raise PublicIdentityConfigError("public_identity_token_source_invalid")
    time_policy = _exact_object(
        verifier["time_policy"],
        {"leeway_seconds", "max_lifetime_seconds"},
        code="public_identity_config_invalid",
    )
    leeway = _bounded_integer(time_policy["leeway_seconds"], minimum=0, maximum=60)
    maximum_lifetime = _bounded_integer(
        time_policy["max_lifetime_seconds"], minimum=1, maximum=3600
    )
    claim_mapping = _exact_object(
        verifier["claim_mapping"],
        {"subject", "roles", "authn_methods"},
        code="public_identity_config_invalid",
    )
    subject_claim = _claim_name(claim_mapping["subject"])
    roles_claim = _claim_name(claim_mapping["roles"])
    authn_methods_claim = _claim_name(claim_mapping["authn_methods"])
    if len({subject_claim, roles_claim, authn_methods_claim}) != 3:
        raise PublicIdentityConfigError("public_identity_claim_mapping_invalid")
    if {subject_claim, roles_claim, authn_methods_claim} & {
        "iss",
        "aud",
        "iat",
        "nbf",
        "exp",
    }:
        raise PublicIdentityConfigError("public_identity_claim_mapping_invalid")
    identity = _exact_object(
        verifier["identity_contract"],
        {"service_account", "token_kind", "network_zone", "required_roles"},
        code="public_identity_config_invalid",
    )
    if identity != {
        "service_account": PUBLIC_SERVICE_ACCOUNT,
        "token_kind": PUBLIC_TOKEN_KIND,
        "network_zone": PUBLIC_NETWORK_ZONE,
        "required_roles": [PUBLIC_REQUIRED_ROLE],
    }:
        raise PublicIdentityConfigError("public_identity_contract_invalid")
    return PublicIdentityConfig(
        issuer=issuer,
        audience=PUBLIC_AUDIENCE,
        secret_environment_variable=match.group(1),
        leeway_seconds=leeway,
        max_lifetime_seconds=maximum_lifetime,
        subject_claim=subject_claim,
        roles_claim=roles_claim,
        authn_methods_claim=authn_methods_claim,
        config_path=config_path,
        config_sha256=config_sha256,
    )


def _strict_json_object(
    payload: bytes,
    *,
    error_type: type[PublicIdentityError],
    code: str,
) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = item
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise error_type(code) from None
    if not isinstance(value, dict):
        raise error_type(code)
    return value


def _jwt_json_segment(segment: str) -> dict[str, Any]:
    payload = _decode_base64url(segment)
    return _strict_json_object(
        payload,
        error_type=PublicIdentityTokenError,
        code="public_identity_access_denied",
    )


def _decode_base64url(value: str) -> bytes:
    if not isinstance(value, str) or not _BASE64URL.fullmatch(value):
        raise PublicIdentityTokenError("public_identity_access_denied")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        raise PublicIdentityTokenError("public_identity_access_denied") from None
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(canonical, value):
        raise PublicIdentityTokenError("public_identity_access_denied")
    return decoded


def _decode_secret(value: str) -> bytes:
    if (
        not isinstance(value, str)
        or not _BASE64URL.fullmatch(value)
        or len(value) > 2048
    ):
        raise PublicIdentitySecretError("public_identity_secret_invalid")
    try:
        secret = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        raise PublicIdentitySecretError("public_identity_secret_invalid") from None
    canonical = base64.urlsafe_b64encode(secret).rstrip(b"=").decode("ascii")
    if (
        not hmac.compare_digest(canonical, value)
        or not MIN_SECRET_BYTES <= len(secret) <= MAX_SECRET_BYTES
    ):
        raise PublicIdentitySecretError("public_identity_secret_invalid")
    return secret


def _exact_object(value: Any, fields: set[str], *, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise PublicIdentityConfigError(code)
    return dict(value)


def _strict_text(value: Any, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise PublicIdentityConfigError("public_identity_config_invalid")
    return value


def _bounded_integer(value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PublicIdentityConfigError("public_identity_config_invalid")
    return value


def _claim_name(value: Any) -> str:
    if not isinstance(value, str) or _CLAIM_NAME.fullmatch(value) is None:
        raise PublicIdentityConfigError("public_identity_claim_mapping_invalid")
    return value


def _integer_timestamp(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PublicIdentityTokenError("public_identity_access_denied")
    return value


def _subject(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 256
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise PublicIdentityTokenError("public_identity_access_denied")
    return value


def _roles(value: Any) -> tuple[str, ...]:
    if value != [PUBLIC_REQUIRED_ROLE]:
        raise PublicIdentityTokenError("public_identity_access_denied")
    return (PUBLIC_REQUIRED_ROLE,)


def _authn_methods(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 8
        or any(not isinstance(item, str) or _AUTHN_METHOD.fullmatch(item) is None for item in value)
        or len(set(value)) != len(value)
    ):
        raise PublicIdentityTokenError("public_identity_access_denied")
    return tuple(value)


def _constant_time_text_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _access_denied(start_response: Callable[..., Any]) -> list[bytes]:
    body = b'{"error":"access_denied","request_rejected":true}\n'
    start_response(
        "403 Forbidden",
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]
