#!/usr/bin/env python3
"""Hash-bound gateway authentication for the private ops WSGI surface."""

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
import time
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .identity_policy import (
    MAINTENANCE_CONFIRMATION_ISSUER,
    MAINTENANCE_CONFIRMATION_SCHEMA_VERSION,
    OPS_AUDIENCE,
    OPS_REQUIRED_AUTHN_METHODS,
    VERIFIED_IDENTITY_ENVIRON_KEY,
    VERIFIED_MAINTENANCE_CONFIRMATION_ENVIRON_KEY,
    VerifiedIdentity,
    VerifiedMaintenanceConfirmation,
)


CONFIG_ENVIRONMENT_VARIABLE = "KG_OPS_IDENTITY_CONFIG"
CONFIG_SHA256_ENVIRONMENT_VARIABLE = "KG_OPS_IDENTITY_CONFIG_SHA256"
CONFIG_SCHEMA_VERSION = "kg-ops-identity-gateway-config-v1"
VERIFIER_KIND = "hs256-jwt-gateway-v1"
JWT_ALGORITHM = "HS256"
JWT_TYPE = "JWT"
IDENTITY_SECRET_ENVIRONMENT_VARIABLE = "KG_OPS_IDENTITY_HS256_SECRET"
CONFIRMATION_SECRET_ENVIRONMENT_VARIABLE = "KG_OPS_CONFIRMATION_HS256_SECRET"
IDENTITY_TOKEN_ENVIRON_KEY = "HTTP_AUTHORIZATION"
CONFIRMATION_TOKEN_ENVIRON_KEY = "HTTP_X_KG_MAINTENANCE_CONFIRMATION"
MAINTENANCE_ROUTE = "/ops/maintenance/jobs"
OPS_SERVICE_ACCOUNT = OPS_AUDIENCE
OPS_TOKEN_KIND = "ops-admin-access"
OPS_NETWORK_ZONE = "private-admin"
OPS_ALLOWED_ROLES = ("ops-observer", "ops-maintainer")
CONFIRMATION_AUDIENCE = "maintenance-controller-cloud"
CONFIRMATION_DECISION = "approved"
CONFIRMATION_REQUIRED_AUTHN_METHODS = ("mfa",)
MAX_CONFIG_BYTES = 64 * 1024
MAX_TOKEN_BYTES = 16 * 1024
MIN_SECRET_BYTES = 32
MAX_SECRET_BYTES = 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_CLAIM_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_AUTHN_METHOD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class OpsIdentityError(RuntimeError):
    """Sanitized ops identity failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        super().__init__("ops identity verification failed")
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "kg-ops-identity-bootstrap-error-v1",
            "error": self.code,
            "ops_identity_ready": False,
        }


class OpsIdentityConfigError(OpsIdentityError):
    pass


class OpsIdentitySecretError(OpsIdentityError):
    pass


class OpsIdentityTokenError(OpsIdentityError):
    pass


@dataclass(frozen=True)
class _JwtVerifierConfig:
    issuer: str
    audience: str
    secret_environment_variable: str
    token_environ_key: str
    leeway_seconds: int
    max_lifetime_seconds: int


@dataclass(frozen=True)
class _IdentityVerifierConfig:
    jwt: _JwtVerifierConfig
    subject_claim: str
    roles_claim: str
    authn_methods_claim: str
    required_authn_methods: tuple[str, ...]
    allowed_roles: tuple[str, ...]


@dataclass(frozen=True)
class _ConfirmationVerifierConfig:
    jwt: _JwtVerifierConfig
    plan_id_claim: str
    confirmation_id_claim: str
    confirmed_by_claim: str
    authn_methods_claim: str
    decision_claim: str
    required_authn_methods: tuple[str, ...]
    decision: str


@dataclass(frozen=True)
class OpsIdentityConfig:
    identity: _IdentityVerifierConfig
    confirmation: _ConfirmationVerifierConfig
    config_path: Path
    config_sha256: str

    def contract(self) -> dict[str, Any]:
        return {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "config_sha256": self.config_sha256,
            "verifier_kind": VERIFIER_KIND,
            "algorithm": JWT_ALGORITHM,
            "identity": {
                "issuer": self.identity.jwt.issuer,
                "audience": self.identity.jwt.audience,
                "token_source": "HTTP_AUTHORIZATION:Bearer",
                "service_account": OPS_SERVICE_ACCOUNT,
                "token_kind": OPS_TOKEN_KIND,
                "network_zone": OPS_NETWORK_ZONE,
                "required_authn_methods": list(
                    self.identity.required_authn_methods
                ),
                "allowed_roles": list(self.identity.allowed_roles),
            },
            "confirmation": {
                "issuer": self.confirmation.jwt.issuer,
                "audience": self.confirmation.jwt.audience,
                "token_source": (
                    "HTTP_X_KG_MAINTENANCE_CONFIRMATION:Bearer"
                ),
                "schema_version": MAINTENANCE_CONFIRMATION_SCHEMA_VERSION,
                "required_authn_methods": list(
                    self.confirmation.required_authn_methods
                ),
                "decision": self.confirmation.decision,
            },
            "independent_secrets": True,
        }


@dataclass(frozen=True)
class OpsIdentityVerifier:
    config: OpsIdentityConfig
    _identity_secret: bytes = field(repr=False)
    _confirmation_secret: bytes = field(repr=False)
    _clock: Callable[[], float] = field(repr=False, compare=False)

    def verify_identity(self, environ: Mapping[str, Any]) -> VerifiedIdentity:
        token = _bearer_token(environ, self.config.identity.jwt.token_environ_key)
        payload = self._verified_payload(
            token,
            self.config.identity.jwt,
            self._identity_secret,
        )
        subject = _subject(payload.get(self.config.identity.subject_claim))
        roles = _roles(
            payload.get(self.config.identity.roles_claim),
            allowed=self.config.identity.allowed_roles,
        )
        authn_methods = _authn_methods(
            payload.get(self.config.identity.authn_methods_claim)
        )
        if not set(self.config.identity.required_authn_methods).issubset(
            authn_methods
        ):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        return VerifiedIdentity(
            subject=subject,
            audience=OPS_AUDIENCE,
            service_account=OPS_SERVICE_ACCOUNT,
            token_kind=OPS_TOKEN_KIND,
            network_zone=OPS_NETWORK_ZONE,
            authn_methods=authn_methods,
            roles=roles,
        )

    def verify_confirmation(
        self,
        environ: Mapping[str, Any],
        *,
        identity: VerifiedIdentity,
    ) -> VerifiedMaintenanceConfirmation:
        if not isinstance(identity, VerifiedIdentity):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        token = _bearer_token(
            environ, self.config.confirmation.jwt.token_environ_key
        )
        payload = self._verified_payload(
            token,
            self.config.confirmation.jwt,
            self._confirmation_secret,
        )
        plan_id = _sha256_claim(
            payload.get(self.config.confirmation.plan_id_claim)
        )
        confirmation_id = _identifier_claim(
            payload.get(self.config.confirmation.confirmation_id_claim)
        )
        confirmed_by = _subject(
            payload.get(self.config.confirmation.confirmed_by_claim)
        )
        if not hmac.compare_digest(
            confirmed_by.encode("utf-8"), identity.subject.encode("utf-8")
        ):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        authn_methods = _authn_methods(
            payload.get(self.config.confirmation.authn_methods_claim)
        )
        if not set(self.config.confirmation.required_authn_methods).issubset(
            authn_methods
        ):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        decision = payload.get(self.config.confirmation.decision_claim)
        if not isinstance(decision, str) or not hmac.compare_digest(
            decision, self.config.confirmation.decision
        ):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        issued_at = _integer_timestamp(payload.get("iat"))
        expires_at = _integer_timestamp(payload.get("exp"))
        return VerifiedMaintenanceConfirmation(
            issuer=self.config.confirmation.jwt.issuer,
            audience=self.config.confirmation.jwt.audience,
            plan_id=plan_id,
            confirmation_id=confirmation_id,
            confirmed_by=confirmed_by,
            authn_methods=authn_methods,
            decision=decision,
            issued_at_epoch_seconds=issued_at,
            expires_at_epoch_seconds=expires_at,
        )

    def _verified_payload(
        self,
        token: str,
        config: _JwtVerifierConfig,
        secret: bytes,
    ) -> dict[str, Any]:
        segments = token.split(".")
        if len(segments) != 3 or any(not segment for segment in segments):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        header_segment, payload_segment, signature_segment = segments
        header = _jwt_json_segment(header_segment)
        if set(header) != {"alg", "typ"}:
            raise OpsIdentityTokenError("ops_identity_access_denied")
        if header["alg"] != JWT_ALGORITHM or header["typ"] != JWT_TYPE:
            raise OpsIdentityTokenError("ops_identity_access_denied")
        payload = _jwt_json_segment(payload_segment)
        signature = _decode_base64url(signature_segment)
        expected = hmac.new(
            secret,
            f"{header_segment}.{payload_segment}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        if len(signature) != len(expected) or not hmac.compare_digest(
            signature, expected
        ):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        self._validate_registered_claims(payload, config)
        return payload

    def _validate_registered_claims(
        self,
        payload: Mapping[str, Any],
        config: _JwtVerifierConfig,
    ) -> None:
        issuer = payload.get("iss")
        if not isinstance(issuer, str) or not _constant_time_text_equal(
            issuer, config.issuer
        ):
            raise OpsIdentityTokenError("ops_identity_access_denied")
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
            raise OpsIdentityTokenError("ops_identity_access_denied")
        if not hmac.compare_digest(audiences[0], config.audience):
            raise OpsIdentityTokenError("ops_identity_access_denied")

        issued_at = _integer_timestamp(payload.get("iat"))
        not_before = _integer_timestamp(payload.get("nbf"))
        expires_at = _integer_timestamp(payload.get("exp"))
        if expires_at <= issued_at or not_before > expires_at:
            raise OpsIdentityTokenError("ops_identity_access_denied")
        if expires_at - issued_at > config.max_lifetime_seconds:
            raise OpsIdentityTokenError("ops_identity_access_denied")
        try:
            raw_now = self._clock()
        except Exception:
            raise OpsIdentityTokenError("ops_identity_access_denied") from None
        if (
            isinstance(raw_now, bool)
            or not isinstance(raw_now, (int, float))
            or not math.isfinite(raw_now)
        ):
            raise OpsIdentityTokenError("ops_identity_access_denied")
        now = int(raw_now)
        leeway = config.leeway_seconds
        if issued_at > now + leeway or not_before > now + leeway:
            raise OpsIdentityTokenError("ops_identity_access_denied")
        if now >= expires_at + leeway:
            raise OpsIdentityTokenError("ops_identity_access_denied")


class OpsIdentityMiddleware:
    """Install typed ops claims only after both gateway proofs verify."""

    def __init__(self, application: Callable[..., Any], verifier: OpsIdentityVerifier):
        if not callable(application):
            raise OpsIdentityConfigError("ops_wsgi_application_invalid")
        if not isinstance(verifier, OpsIdentityVerifier):
            raise OpsIdentityConfigError("ops_identity_verifier_invalid")
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
        environ.pop(VERIFIED_MAINTENANCE_CONFIRMATION_ENVIRON_KEY, None)
        try:
            identity = self._verifier.verify_identity(environ)
            confirmation = (
                self._verifier.verify_confirmation(environ, identity=identity)
                if environ.get("PATH_INFO") == MAINTENANCE_ROUTE
                else None
            )
        except Exception:
            environ.pop(VERIFIED_IDENTITY_ENVIRON_KEY, None)
            environ.pop(VERIFIED_MAINTENANCE_CONFIRMATION_ENVIRON_KEY, None)
            return _access_denied(start_response)
        environ[VERIFIED_IDENTITY_ENVIRON_KEY] = identity
        if confirmation is not None:
            environ[VERIFIED_MAINTENANCE_CONFIRMATION_ENVIRON_KEY] = confirmation
        return self._application(environ, start_response)


def load_ops_identity_verifier_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    clock: Callable[[], float] = time.time,
) -> OpsIdentityVerifier:
    values = os.environ if environment is None else environment
    if not isinstance(values, Mapping):
        raise OpsIdentityConfigError("ops_identity_environment_invalid")
    raw_path = values.get(CONFIG_ENVIRONMENT_VARIABLE)
    if not isinstance(raw_path, str) or not raw_path:
        raise OpsIdentityConfigError("ops_identity_config_missing")
    expected_sha256 = values.get(CONFIG_SHA256_ENVIRONMENT_VARIABLE)
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(
        expected_sha256
    ):
        raise OpsIdentityConfigError("ops_identity_config_hash_missing")
    config_path, payload = _stable_config_bytes(raw_path)
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise OpsIdentityConfigError("ops_identity_config_hash_mismatch")
    document = _strict_json_object(
        payload,
        error_type=OpsIdentityConfigError,
        code="ops_identity_config_invalid",
    )
    parsed = _parse_config(document, config_path, actual_sha256)
    identity_secret = _load_secret(
        values,
        parsed.identity.jwt.secret_environment_variable,
        missing_code="ops_identity_secret_missing",
        invalid_code="ops_identity_secret_invalid",
    )
    confirmation_secret = _load_secret(
        values,
        parsed.confirmation.jwt.secret_environment_variable,
        missing_code="ops_confirmation_secret_missing",
        invalid_code="ops_confirmation_secret_invalid",
    )
    if hmac.compare_digest(identity_secret, confirmation_secret):
        raise OpsIdentityConfigError("ops_identity_secrets_not_independent")
    return OpsIdentityVerifier(
        parsed,
        identity_secret,
        confirmation_secret,
        clock,
    )


def create_authenticated_ops_wsgi_app(
    application_factory: Callable[[], Any],
    *,
    environment: Mapping[str, str] | None = None,
    clock: Callable[[], float] = time.time,
) -> Any:
    """Preflight authentication before constructing any production runtime."""

    if not callable(application_factory):
        raise OpsIdentityConfigError("ops_wsgi_factory_invalid")
    verifier = load_ops_identity_verifier_from_environment(
        environment,
        clock=clock,
    )
    application = application_factory()
    raw_wsgi = getattr(application, "wsgi_app", None)
    extensions = getattr(application, "extensions", None)
    if callable(raw_wsgi) and isinstance(extensions, dict):
        application.wsgi_app = OpsIdentityMiddleware(raw_wsgi, verifier)
        extensions["ops_identity_contract"] = verifier.config.contract()
        return application
    if callable(application):
        return OpsIdentityMiddleware(application, verifier)
    raise OpsIdentityConfigError("ops_wsgi_application_invalid")


def startup_error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, OpsIdentityError):
        return error.to_dict()
    return {
        "schema_version": "kg-ops-identity-bootstrap-error-v1",
        "error": "ops_identity_preflight_failed",
        "ops_identity_ready": False,
    }


def _stable_config_bytes(path: str) -> tuple[Path, bytes]:
    raw = Path(path)
    if not raw.is_absolute():
        raise OpsIdentityConfigError("ops_identity_config_path_invalid")
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError:
        raise OpsIdentityConfigError("ops_identity_config_unavailable") from None
    if resolved != lexical:
        raise OpsIdentityConfigError("ops_identity_config_path_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError:
        raise OpsIdentityConfigError("ops_identity_config_unavailable") from None
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
            raise OpsIdentityConfigError(
                "ops_identity_config_permissions_invalid"
            )
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
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if (
            before_identity != after_identity
            or len(payload) != before.st_size
            or len(payload) > MAX_CONFIG_BYTES
        ):
            raise OpsIdentityConfigError("ops_identity_config_changed")
        return resolved, payload
    finally:
        os.close(descriptor)


def _parse_config(
    value: Mapping[str, Any],
    config_path: Path,
    config_sha256: str,
) -> OpsIdentityConfig:
    root = _exact_object(
        value,
        {"schema_version", "identity_verifier", "confirmation_verifier"},
    )
    if root["schema_version"] != CONFIG_SCHEMA_VERSION:
        raise OpsIdentityConfigError("ops_identity_config_schema_mismatch")
    identity = _parse_identity_verifier(root["identity_verifier"])
    confirmation = _parse_confirmation_verifier(
        root["confirmation_verifier"]
    )
    if (
        identity.jwt.secret_environment_variable
        == confirmation.jwt.secret_environment_variable
    ):
        raise OpsIdentityConfigError("ops_identity_secret_refs_not_independent")
    return OpsIdentityConfig(
        identity=identity,
        confirmation=confirmation,
        config_path=config_path,
        config_sha256=config_sha256,
    )


def _parse_identity_verifier(value: Any) -> _IdentityVerifierConfig:
    verifier = _exact_object(
        value,
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
    )
    _require_verifier_kind(verifier)
    issuer = _strict_text(verifier["issuer"], maximum=512)
    if verifier["audience"] != OPS_AUDIENCE:
        raise OpsIdentityConfigError("ops_identity_audience_invalid")
    secret = _parse_secret_ref(
        verifier["secret_ref"],
        expected=IDENTITY_SECRET_ENVIRONMENT_VARIABLE,
    )
    _require_token_source(
        verifier["token_source"], expected=IDENTITY_TOKEN_ENVIRON_KEY
    )
    leeway, lifetime = _parse_time_policy(verifier["time_policy"])
    mapping = _exact_object(
        verifier["claim_mapping"],
        {"subject", "roles", "authn_methods"},
    )
    mapped = tuple(_claim_name(mapping[name]) for name in sorted(mapping))
    _require_distinct_custom_claims(mapped)
    identity_contract = _exact_object(
        verifier["identity_contract"],
        {
            "service_account",
            "token_kind",
            "network_zone",
            "required_authn_methods",
            "allowed_roles",
        },
    )
    if (
        identity_contract["service_account"] != OPS_SERVICE_ACCOUNT
        or identity_contract["token_kind"] != OPS_TOKEN_KIND
        or identity_contract["network_zone"] != OPS_NETWORK_ZONE
        or identity_contract["required_authn_methods"]
        != sorted(OPS_REQUIRED_AUTHN_METHODS)
        or identity_contract["allowed_roles"] != list(OPS_ALLOWED_ROLES)
    ):
        raise OpsIdentityConfigError("ops_identity_contract_invalid")
    return _IdentityVerifierConfig(
        jwt=_JwtVerifierConfig(
            issuer=issuer,
            audience=OPS_AUDIENCE,
            secret_environment_variable=secret,
            token_environ_key=IDENTITY_TOKEN_ENVIRON_KEY,
            leeway_seconds=leeway,
            max_lifetime_seconds=lifetime,
        ),
        subject_claim=_claim_name(mapping["subject"]),
        roles_claim=_claim_name(mapping["roles"]),
        authn_methods_claim=_claim_name(mapping["authn_methods"]),
        required_authn_methods=tuple(sorted(OPS_REQUIRED_AUTHN_METHODS)),
        allowed_roles=OPS_ALLOWED_ROLES,
    )


def _parse_confirmation_verifier(value: Any) -> _ConfirmationVerifierConfig:
    verifier = _exact_object(
        value,
        {
            "kind",
            "algorithm",
            "issuer",
            "audience",
            "secret_ref",
            "token_source",
            "time_policy",
            "claim_mapping",
            "confirmation_contract",
        },
    )
    _require_verifier_kind(verifier)
    if verifier["issuer"] != MAINTENANCE_CONFIRMATION_ISSUER:
        raise OpsIdentityConfigError("ops_confirmation_issuer_invalid")
    if verifier["audience"] != CONFIRMATION_AUDIENCE:
        raise OpsIdentityConfigError("ops_confirmation_audience_invalid")
    secret = _parse_secret_ref(
        verifier["secret_ref"],
        expected=CONFIRMATION_SECRET_ENVIRONMENT_VARIABLE,
    )
    _require_token_source(
        verifier["token_source"], expected=CONFIRMATION_TOKEN_ENVIRON_KEY
    )
    leeway, lifetime = _parse_time_policy(verifier["time_policy"])
    mapping = _exact_object(
        verifier["claim_mapping"],
        {
            "plan_id",
            "confirmation_id",
            "confirmed_by",
            "authn_methods",
            "decision",
        },
    )
    mapped = tuple(_claim_name(mapping[name]) for name in sorted(mapping))
    _require_distinct_custom_claims(mapped)
    contract = _exact_object(
        verifier["confirmation_contract"],
        {"schema_version", "required_authn_methods", "decision"},
    )
    if contract != {
        "schema_version": MAINTENANCE_CONFIRMATION_SCHEMA_VERSION,
        "required_authn_methods": list(CONFIRMATION_REQUIRED_AUTHN_METHODS),
        "decision": CONFIRMATION_DECISION,
    }:
        raise OpsIdentityConfigError("ops_confirmation_contract_invalid")
    return _ConfirmationVerifierConfig(
        jwt=_JwtVerifierConfig(
            issuer=MAINTENANCE_CONFIRMATION_ISSUER,
            audience=CONFIRMATION_AUDIENCE,
            secret_environment_variable=secret,
            token_environ_key=CONFIRMATION_TOKEN_ENVIRON_KEY,
            leeway_seconds=leeway,
            max_lifetime_seconds=lifetime,
        ),
        plan_id_claim=_claim_name(mapping["plan_id"]),
        confirmation_id_claim=_claim_name(mapping["confirmation_id"]),
        confirmed_by_claim=_claim_name(mapping["confirmed_by"]),
        authn_methods_claim=_claim_name(mapping["authn_methods"]),
        decision_claim=_claim_name(mapping["decision"]),
        required_authn_methods=CONFIRMATION_REQUIRED_AUTHN_METHODS,
        decision=CONFIRMATION_DECISION,
    )


def _require_verifier_kind(value: Mapping[str, Any]) -> None:
    if value["kind"] != VERIFIER_KIND or value["algorithm"] != JWT_ALGORITHM:
        raise OpsIdentityConfigError("ops_identity_verifier_not_allowed")


def _parse_secret_ref(value: Any, *, expected: str) -> str:
    secret_ref = _exact_object(value, {"value", "encoding"})
    if secret_ref != {
        "value": f"secretref:{expected}",
        "encoding": "base64url",
    }:
        raise OpsIdentityConfigError("ops_identity_secret_ref_invalid")
    return expected


def _require_token_source(value: Any, *, expected: str) -> None:
    source = _exact_object(value, {"wsgi_environ_key", "scheme"})
    if source != {"wsgi_environ_key": expected, "scheme": "Bearer"}:
        raise OpsIdentityConfigError("ops_identity_token_source_invalid")


def _parse_time_policy(value: Any) -> tuple[int, int]:
    policy = _exact_object(
        value, {"leeway_seconds", "max_lifetime_seconds"}
    )
    return (
        _bounded_integer(policy["leeway_seconds"], minimum=0, maximum=60),
        _bounded_integer(
            policy["max_lifetime_seconds"], minimum=1, maximum=3600
        ),
    )


def _require_distinct_custom_claims(values: Sequence[str]) -> None:
    if len(set(values)) != len(values) or set(values) & {
        "iss",
        "aud",
        "iat",
        "nbf",
        "exp",
    }:
        raise OpsIdentityConfigError("ops_identity_claim_mapping_invalid")


def _strict_json_object(
    payload: bytes,
    *,
    error_type: type[OpsIdentityError],
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


def _exact_object(value: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OpsIdentityConfigError("ops_identity_config_invalid")
    return dict(value)


def _strict_text(value: Any, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise OpsIdentityConfigError("ops_identity_config_invalid")
    return value


def _bounded_integer(value: Any, *, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise OpsIdentityConfigError("ops_identity_config_invalid")
    return value


def _claim_name(value: Any) -> str:
    if not isinstance(value, str) or _CLAIM_NAME.fullmatch(value) is None:
        raise OpsIdentityConfigError("ops_identity_claim_mapping_invalid")
    return value


def _load_secret(
    environment: Mapping[str, str],
    name: str,
    *,
    missing_code: str,
    invalid_code: str,
) -> bytes:
    raw = environment.get(name)
    if not isinstance(raw, str) or not raw:
        raise OpsIdentitySecretError(missing_code)
    return _decode_secret(raw, invalid_code=invalid_code)


def _bearer_token(environ: Mapping[str, Any], key: str) -> str:
    if not isinstance(environ, Mapping):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    authorization = environ.get(key)
    if (
        not isinstance(authorization, str)
        or not authorization.startswith("Bearer ")
        or authorization != authorization.strip()
    ):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    token = authorization.removeprefix("Bearer ")
    if (
        not token
        or len(token.encode("utf-8")) > MAX_TOKEN_BYTES
        or any(character.isspace() for character in token)
    ):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return token


def _jwt_json_segment(segment: str) -> dict[str, Any]:
    return _strict_json_object(
        _decode_base64url(segment),
        error_type=OpsIdentityTokenError,
        code="ops_identity_access_denied",
    )


def _decode_base64url(value: str) -> bytes:
    if not isinstance(value, str) or not _BASE64URL.fullmatch(value):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        raise OpsIdentityTokenError("ops_identity_access_denied") from None
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(canonical, value):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return decoded


def _decode_secret(value: str, *, invalid_code: str) -> bytes:
    if (
        not isinstance(value, str)
        or not _BASE64URL.fullmatch(value)
        or len(value) > 2048
    ):
        raise OpsIdentitySecretError(invalid_code)
    try:
        secret = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        raise OpsIdentitySecretError(invalid_code) from None
    canonical = base64.urlsafe_b64encode(secret).rstrip(b"=").decode("ascii")
    if (
        not hmac.compare_digest(canonical, value)
        or not MIN_SECRET_BYTES <= len(secret) <= MAX_SECRET_BYTES
    ):
        raise OpsIdentitySecretError(invalid_code)
    return secret


def _integer_timestamp(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return value


def _subject(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 256
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return value


def _roles(value: Any, *, allowed: tuple[str, ...]) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= len(allowed)
        or len(set(value)) != len(value)
        or any(not isinstance(item, str) or item not in allowed for item in value)
    ):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return tuple(value)


def _authn_methods(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 8
        or any(
            not isinstance(item, str) or _AUTHN_METHOD.fullmatch(item) is None
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return tuple(value)


def _sha256_claim(value: Any) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return value


def _identifier_claim(value: Any) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise OpsIdentityTokenError("ops_identity_access_denied")
    return value


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
