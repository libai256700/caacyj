#!/usr/bin/env python3
"""Fixed-query, immutable SQLite readers for the cloud runtime.

The public API deliberately exposes no connection object and accepts no SQL.
Every statement is fixed in this module and every database is opened with both
``mode=ro`` and SQLite's ``query_only`` guard.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


AUTHORITY_SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE document_sources (
    document_source_id TEXT PRIMARY KEY,
    doc_name TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL UNIQUE,
    source_sha256 TEXT NOT NULL,
    source_page_count INTEGER,
    authority TEXT NOT NULL,
    published_at TEXT,
    ocr_engine TEXT,
    ocr_version TEXT,
    ocr_backend TEXT,
    ocr_language TEXT,
    extractor_version TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_document_sources_sha ON document_sources(source_sha256);
CREATE INDEX idx_document_sources_run ON document_sources(import_run_id);
CREATE TABLE documents (
    doc_name TEXT PRIMARY KEY,
    doc_path TEXT NOT NULL UNIQUE,
    chunk_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    doc_name TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(doc_name) REFERENCES documents(doc_name),
    UNIQUE(doc_name, chunk_index)
);
CREATE INDEX idx_chunks_doc ON chunks(doc_name);
CREATE INDEX idx_chunks_doc_idx ON chunks(doc_name, chunk_index);
CREATE TABLE chunk_provenance (
    chunk_id TEXT PRIMARY KEY,
    document_source_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    pdf_page_start INTEGER NOT NULL,
    pdf_page_end INTEGER NOT NULL,
    printed_page_start INTEGER,
    printed_page_end INTEGER,
    chapter_id TEXT,
    chapter_title TEXT,
    section_id TEXT,
    section_title TEXT,
    content_type TEXT NOT NULL,
    confidence REAL,
    review_status TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY(document_source_id) REFERENCES document_sources(document_source_id)
);
CREATE INDEX idx_chunk_provenance_scope ON chunk_provenance(source_sha256, import_run_id);
CREATE INDEX idx_chunk_provenance_section ON chunk_provenance(section_id, content_type);
"""
BM25_SCHEMA_SQL = (
    "CREATE VIRTUAL TABLE chunks_fts USING fts5("
    "text, chunk_id UNINDEXED, doc_name UNINDEXED, tokenize='trigram')"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


class ReadOnlySQLiteError(RuntimeError):
    """A sealed SQLite input or fixed read operation failed closed."""


class SQLiteSemanticValidationError(ReadOnlySQLiteError):
    """A production authority/BM25 pair failed a deterministic semantic gate."""

    def __init__(self, code: str) -> None:
        super().__init__("production SQLite data semantics are invalid")
        self.code = code


@dataclass(frozen=True)
class AuthorityBm25SemanticSnapshot:
    authority_database_sha256: str
    bm25_database_sha256: str
    source: Mapping[str, Any]
    indexed_chunk_count: int
    chunk_documents: Mapping[str, str]
    document_chunk_counts: Mapping[str, int]
    source_records: tuple[Mapping[str, Any], ...]
    provenance_chunk_ids: frozenset[str]


def _database_path(raw: str | Path, label: str) -> Path:
    path = Path(raw)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReadOnlySQLiteError(f"{label} is unavailable") from exc
    if resolved != path:
        raise ReadOnlySQLiteError(f"{label} must be a canonical regular file")
    return resolved


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mode,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _descriptor_sha256(descriptor: int, label: str) -> str:
    digest = hashlib.sha256()
    offset = 0
    try:
        while True:
            block = os.pread(descriptor, 1024 * 1024, offset)
            if not block:
                return digest.hexdigest()
            digest.update(block)
            offset += len(block)
    except OSError as exc:
        raise ReadOnlySQLiteError(f"{label} descriptor is unreadable") from exc


def read_stable_regular_file(
    raw: str | Path,
    label: str,
) -> tuple[Path, bytes, str]:
    """Read one canonical regular file while holding and rechecking its descriptor."""

    path = _database_path(raw, label)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReadOnlySQLiteError(f"{label} could not be opened read-only") from exc
    try:
        opened_stat = os.fstat(descriptor)
        named_stat = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or not stat.S_ISREG(named_stat.st_mode)
            or not _same_file(opened_stat, named_stat)
        ):
            raise ReadOnlySQLiteError(f"{label} changed while it was opened")
        chunks: list[bytes] = []
        offset = 0
        while True:
            block = os.pread(descriptor, 1024 * 1024, offset)
            if not block:
                break
            chunks.append(block)
            offset += len(block)
        payload = b"".join(chunks)
        final_descriptor_stat = os.fstat(descriptor)
        final_named_stat = os.stat(path, follow_symlinks=False)
        if (
            not _same_file(opened_stat, final_descriptor_stat)
            or not _same_file(final_descriptor_stat, final_named_stat)
            or opened_stat.st_size != final_descriptor_stat.st_size
            or opened_stat.st_mtime_ns != final_descriptor_stat.st_mtime_ns
            or opened_stat.st_ctime_ns != final_descriptor_stat.st_ctime_ns
        ):
            raise ReadOnlySQLiteError(f"{label} path binding changed during read")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != _descriptor_sha256(descriptor, label):
            raise ReadOnlySQLiteError(f"{label} bytes changed during read")
        return path, payload, digest
    except OSError as exc:
        raise ReadOnlySQLiteError(f"{label} is unreadable") from exc
    finally:
        os.close(descriptor)


def _descriptor_alias(
    descriptor: int,
    opened_stat: os.stat_result,
    label: str,
) -> str:
    for candidate in (f"/proc/self/fd/{descriptor}", f"/dev/fd/{descriptor}"):
        probe: int | None = None
        try:
            probe = os.open(candidate, os.O_RDONLY)
            candidate_stat = os.fstat(probe)
        except OSError:
            continue
        finally:
            if probe is not None:
                os.close(probe)
        if _same_file(opened_stat, candidate_stat):
            return candidate
    raise ReadOnlySQLiteError(f"{label} stable descriptor path is unavailable")


def _open_database_descriptor(
    raw: str | Path,
    label: str,
) -> tuple[Path, int, str, os.stat_result, str]:
    path = _database_path(raw, label)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReadOnlySQLiteError(f"{label} could not be opened read-only") from exc
    try:
        opened_stat = os.fstat(descriptor)
        named_stat = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or not stat.S_ISREG(named_stat.st_mode)
            or not _same_file(opened_stat, named_stat)
        ):
            raise ReadOnlySQLiteError(
                f"{label} changed while its descriptor was opened"
            )
        alias = _descriptor_alias(descriptor, opened_stat, label)
        digest = _descriptor_sha256(descriptor, label)
    except Exception:
        os.close(descriptor)
        raise
    return path, descriptor, alias, opened_stat, digest


def _positive_limit(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError(f"{label} must be between 1 and 100")
    return value


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _schema_records(connection: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        )
    )


def _expected_schema_records(schema_sql: str) -> tuple[tuple[Any, ...], ...]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(schema_sql)
        return _schema_records(connection)
    finally:
        connection.close()


EXPECTED_AUTHORITY_SCHEMA_RECORDS = _expected_schema_records(AUTHORITY_SCHEMA_SQL)
EXPECTED_BM25_SCHEMA_RECORDS = _expected_schema_records(BM25_SCHEMA_SQL)


class _ReadOnlyDatabase:
    def __init__(self, database_path: str | Path, label: str) -> None:
        (
            self.database_path,
            self._database_descriptor,
            self._database_descriptor_path,
            self._database_opened_stat,
            self._database_sha256,
        ) = _open_database_descriptor(database_path, label)
        self._label = label
        self._connection_handle: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def database_sha256(self) -> str:
        return self._database_sha256

    def _require_path_binding(self) -> None:
        try:
            named_stat = os.stat(self.database_path, follow_symlinks=False)
            opened_stat = os.fstat(self._database_descriptor)
        except OSError as exc:
            raise ReadOnlySQLiteError(
                f"{self._label} path binding is unavailable"
            ) from exc
        if (
            not stat.S_ISREG(named_stat.st_mode)
            or not stat.S_ISREG(opened_stat.st_mode)
            or _stat_identity(opened_stat)
            != _stat_identity(self._database_opened_stat)
            or _stat_identity(named_stat)
            != _stat_identity(self._database_opened_stat)
        ):
            raise ReadOnlySQLiteError(
                f"{self._label} path binding changed after open"
            )

    def verify_unchanged(self) -> None:
        """Revalidate the configured pathname and bytes held by this reader."""

        with self._lock:
            if self._closed:
                raise ReadOnlySQLiteError("immutable SQLite reader is closed")
            self._require_path_binding()
            if (
                _descriptor_sha256(self._database_descriptor, self._label)
                != self._database_sha256
            ):
                raise ReadOnlySQLiteError(
                    f"{self._label} bytes changed after open"
                )

    def _connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._closed:
                raise ReadOnlySQLiteError("immutable SQLite reader is closed")
            if self._connection_handle is None:
                self._require_path_binding()
                uri = Path(self._database_descriptor_path).as_uri() + (
                    "?mode=ro&immutable=1"
                )
                connection: sqlite3.Connection | None = None
                try:
                    connection = sqlite3.connect(
                        uri,
                        uri=True,
                        check_same_thread=False,
                    )
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA query_only=ON")
                    connection.execute("PRAGMA foreign_keys=ON")
                    self._require_path_binding()
                except ReadOnlySQLiteError:
                    if connection is not None:
                        try:
                            connection.close()
                        except sqlite3.Error:
                            pass
                    raise
                except sqlite3.Error as exc:
                    if connection is not None:
                        try:
                            connection.close()
                        except sqlite3.Error:
                            pass
                    raise ReadOnlySQLiteError(
                        "immutable SQLite input could not be opened"
                    ) from exc
                self._connection_handle = connection
            return self._connection_handle

    def _fetchone(
        self,
        statement: str,
        parameters: Sequence[Any] = (),
    ) -> sqlite3.Row | None:
        with self._lock:
            if self._closed:
                raise ReadOnlySQLiteError("immutable SQLite reader is closed")
            try:
                self._require_path_binding()
                row = self._connection().execute(statement, parameters).fetchone()
                self._require_path_binding()
                return row
            except sqlite3.Error as exc:
                raise ReadOnlySQLiteError("immutable SQLite fixed read failed") from exc

    def _fetchall(
        self,
        statement: str,
        parameters: Sequence[Any] = (),
    ) -> list[sqlite3.Row]:
        with self._lock:
            if self._closed:
                raise ReadOnlySQLiteError("immutable SQLite reader is closed")
            try:
                self._require_path_binding()
                rows = self._connection().execute(statement, parameters).fetchall()
                self._require_path_binding()
                return rows
            except sqlite3.Error as exc:
                raise ReadOnlySQLiteError("immutable SQLite fixed read failed") from exc

    def integrity_check(self) -> str:
        row = self._fetchone("PRAGMA integrity_check")
        return str(row[0]) if row is not None else "missing"

    def user_version(self) -> int:
        row = self._fetchone("PRAGMA user_version")
        if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
            raise ReadOnlySQLiteError("SQLite user version is invalid")
        return row[0]

    def foreign_key_violation_count(self) -> int:
        return len(self._fetchall("PRAGMA foreign_key_check"))

    def table_names(self) -> frozenset[str]:
        rows = self._fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return frozenset(str(row[0]) for row in rows)

    def schema_records(self) -> tuple[tuple[Any, ...], ...]:
        rows = self._fetchall(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        )
        return tuple(tuple(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            close_error: sqlite3.Error | None = None
            if self._connection_handle is not None:
                try:
                    self._connection_handle.close()
                except sqlite3.Error as exc:
                    close_error = exc
                self._connection_handle = None
            try:
                os.close(self._database_descriptor)
            except OSError as exc:
                raise ReadOnlySQLiteError("immutable SQLite close failed") from exc
            if close_error is not None:
                raise ReadOnlySQLiteError("immutable SQLite close failed") from close_error

    def __enter__(self) -> "_ReadOnlyDatabase":
        try:
            self._connection()
        except Exception:
            try:
                self.close()
            except ReadOnlySQLiteError:
                pass
            raise
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()


class ReadOnlyAuthorityReader(_ReadOnlyDatabase):
    """Authority-specific fixed reads with ordered SQLite backfill."""

    def __init__(self, database_path: str | Path) -> None:
        super().__init__(database_path, "authority database")

    def integrity_check(self) -> str:
        row = self._fetchone("PRAGMA integrity_check")
        return str(row[0]) if row is not None else "missing"

    def user_version(self) -> int:
        row = self._fetchone("PRAGMA user_version")
        if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
            raise ReadOnlySQLiteError("authority database user version is invalid")
        return row[0]

    def foreign_key_violation_count(self) -> int:
        rows = self._fetchall("PRAGMA foreign_key_check")
        return len(rows)

    def table_names(self) -> frozenset[str]:
        rows = self._fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return frozenset(str(row[0]) for row in rows)

    def all_chunks(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT chunk_id, doc_name, chunk_index, text "
            "FROM chunks ORDER BY chunk_id"
        )
        return [dict(row) for row in rows]

    def chunk_evidence_rows(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT chunk_id, doc_name, text FROM chunks ORDER BY chunk_id"
        )
        return [dict(row) for row in rows]

    def chunk_document_map(self) -> dict[str, str]:
        rows = self._fetchall(
            "SELECT chunk_id, doc_name FROM chunks ORDER BY chunk_id"
        )
        return {str(row[0]): str(row[1]) for row in rows}

    def embedding_chunk_rows(self) -> list[dict[str, Any]]:
        """Return the complete, provenance-bound embedding source set."""

        rows = self._fetchall(
            "SELECT c.chunk_id, c.text, c.doc_name, c.chunk_index, "
            "p.content_type FROM chunks AS c "
            "JOIN chunk_provenance AS p ON p.chunk_id = c.chunk_id "
            "ORDER BY c.chunk_id"
        )
        return [dict(row) for row in rows]

    def provenance_chunk_ids(self) -> frozenset[str]:
        rows = self._fetchall(
            "SELECT chunk_id FROM chunk_provenance ORDER BY chunk_id"
        )
        return frozenset(str(row[0]) for row in rows)

    def source_records(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT doc_name, source_path, source_sha256, source_page_count, "
            "authority, extractor_version, import_run_id, metadata_json "
            "FROM document_sources ORDER BY doc_name"
        )
        return [dict(row) for row in rows]

    def validate_provenance_bindings(
        self,
        expected_source_text_sha256: Mapping[str, str] | None = None,
    ) -> None:
        """Require each chunk provenance row to bind to its own approved source."""

        rows = self._fetchall(
            "SELECT c.chunk_id, c.doc_name, c.chunk_index, "
            "p.source_sha256, p.import_run_id, p.review_status, p.evidence_json, "
            "s.doc_name AS source_doc_name, "
            "s.source_sha256 AS document_source_sha256, "
            "s.import_run_id AS document_source_import_run_id, "
            "s.extractor_version AS source_extractor_version "
            "FROM chunks AS c "
            "JOIN chunk_provenance AS p ON p.chunk_id = c.chunk_id "
            "JOIN document_sources AS s "
            "ON s.document_source_id = p.document_source_id "
            "ORDER BY c.chunk_id"
        )
        for row in rows:
            try:
                evidence = json.loads(
                    row["evidence_json"],
                    object_pairs_hook=_unique_json_object,
                    parse_constant=_reject_json_constant,
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                raise SQLiteSemanticValidationError(
                    "authority_provenance_mismatch"
                ) from None
            if (
                str(row["doc_name"]) != str(row["source_doc_name"])
                or str(row["source_sha256"])
                != str(row["document_source_sha256"])
                or str(row["import_run_id"])
                != str(row["document_source_import_run_id"])
                or row["review_status"] != "approved-source-extracted"
                or type(evidence) is not dict
                or set(evidence)
                != {"extractor", "source_text_sha256", "unit_ordinal"}
                or evidence.get("extractor") != row["source_extractor_version"]
                or not isinstance(evidence.get("source_text_sha256"), str)
                or not _SHA256.fullmatch(evidence["source_text_sha256"])
                or (
                    expected_source_text_sha256 is not None
                    and evidence["source_text_sha256"]
                    != expected_source_text_sha256.get(str(row["doc_name"]))
                )
                or isinstance(evidence.get("unit_ordinal"), bool)
                or not isinstance(evidence.get("unit_ordinal"), int)
                or evidence.get("unit_ordinal") != row["chunk_index"]
            ):
                raise SQLiteSemanticValidationError(
                    "authority_provenance_mismatch"
                )

    def document_chunk_counts(self) -> dict[str, int]:
        rows = self._fetchall(
            "SELECT doc_name, chunk_count FROM documents ORDER BY doc_name"
        )
        return {str(row[0]): int(row[1]) for row in rows}

    def get_chunks_batch(self, chunk_ids: Sequence[str]) -> list[dict[str, Any]]:
        ordered = list(dict.fromkeys(str(item) for item in chunk_ids if str(item)))
        if not ordered:
            return []
        placeholders = ",".join("?" for _ in ordered)
        rows = self._fetchall(
            "SELECT chunk_id, text, doc_name, chunk_index FROM chunks "
            f"WHERE chunk_id IN ({placeholders})",
            ordered,
        )
        by_id = {str(row["chunk_id"]): dict(row) for row in rows}
        return [by_id[item] for item in ordered if item in by_id]

    def require_chunks(self, chunk_ids: Sequence[str]) -> list[dict[str, Any]]:
        ordered = list(dict.fromkeys(str(item) for item in chunk_ids if str(item)))
        rows = self.get_chunks_batch(ordered)
        if [str(row["chunk_id"]) for row in rows] != ordered:
            raise ReadOnlySQLiteError(
                "derived retrieval contains an id outside SQLite authority"
            )
        return rows

    def search_chunks(
        self, terms: Sequence[str], limit: int = 20
    ) -> list[dict[str, Any]]:
        bounded_limit = _positive_limit(limit, "authority search limit")
        normalized = [str(term).strip() for term in terms if len(str(term).strip()) >= 2]
        if not normalized:
            return []
        scored: dict[str, dict[str, Any]] = {}
        for term in normalized[:8]:
            escaped = _escape_like(term)
            rows = self._fetchall(
                "SELECT chunk_id, text, doc_name, chunk_index FROM chunks "
                "WHERE text LIKE ? ESCAPE '\\' OR doc_name LIKE ? ESCAPE '\\' "
                "ORDER BY doc_name, chunk_index, chunk_id LIMIT ?",
                (f"%{escaped}%", f"%{escaped}%", bounded_limit),
            )
            for row in rows:
                item = dict(row)
                entry = scored.setdefault(
                    str(item["chunk_id"]), {**item, "_score": 0}
                )
                entry["_score"] += str(item.get("text") or "").count(term) + 1
        ranked = sorted(
            scored.values(),
            key=lambda item: (
                -int(item["_score"]),
                str(item["doc_name"]),
                int(item["chunk_index"]),
                str(item["chunk_id"]),
            ),
        )
        for item in ranked:
            item.pop("_score", None)
        return ranked[:bounded_limit]


class ReadOnlyFtsReader(_ReadOnlyDatabase):
    """Fixed FTS5 reads whose ids and text are backfilled from authority."""

    def __init__(
        self,
        database_path: str | Path,
        authority: ReadOnlyAuthorityReader,
    ) -> None:
        super().__init__(database_path, "BM25 database")
        self.authority = authority

    @staticmethod
    def _match_expression(query: str) -> str:
        cjk_runs = re.findall(r"[\u3400-\u9fff]+", query)
        latin_terms = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.-]{2,}", query)
        terms: list[str] = []
        combined_cjk = "".join(cjk_runs)
        for run in [*cjk_runs, combined_cjk]:
            if len(run) >= 3:
                terms.extend(run[index : index + 3] for index in range(len(run) - 2))
        terms.extend(latin_terms)
        unique = list(dict.fromkeys(term for term in terms if term))[:96]
        return " OR ".join('"' + term.replace('"', '""') + '"' for term in unique)

    def all_rows(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT chunk_id, text, doc_name FROM chunks_fts ORDER BY chunk_id"
        )
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        bounded_limit = _positive_limit(limit, "BM25 limit")
        expression = self._match_expression(str(query or ""))
        if not expression:
            return self._short_query_fallback(str(query or ""), bounded_limit)
        rows = self._fetchall(
            "SELECT chunk_id, bm25(chunks_fts) AS rank FROM chunks_fts "
            "WHERE chunks_fts MATCH ? ORDER BY rank, chunk_id LIMIT ?",
            (expression, bounded_limit),
        )
        if not rows:
            return self._short_query_fallback(str(query or ""), bounded_limit)
        ids = [str(row["chunk_id"]) for row in rows]
        authority_rows = self.authority.require_chunks(ids)
        rank_by_id = {str(row["chunk_id"]): float(row["rank"]) for row in rows}
        return [
            {
                **row,
                "score": max(0.0, -rank_by_id[str(row["chunk_id"])]) * 10_000_000,
                "source": "bm25",
            }
            for row in authority_rows
        ]

    def _short_query_fallback(self, query: str, limit: int) -> list[dict[str, Any]]:
        terms = list(
            dict.fromkeys(
                [
                    *re.findall(r"[\u3400-\u9fff]{2,}", query),
                    *re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.-]+", query),
                ]
            )
        )[:8]
        rows = self.authority.search_chunks(terms, limit=limit)
        return [
            {
                **row,
                "score": 50.0 / position,
                "source": "sqlite_lexical_short_query",
            }
            for position, row in enumerate(rows, start=1)
        ]


def _authority_content_fingerprint(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    digest = hashlib.sha256()
    byte_count = 0
    codepoint_count = 0
    documents: set[str] = set()
    for row in sorted(rows, key=lambda item: str(item.get("chunk_id") or "")):
        chunk_id = row.get("chunk_id")
        doc_name = row.get("doc_name")
        chunk_index = row.get("chunk_index")
        text = row.get("text")
        if (
            not isinstance(chunk_id, str)
            or not chunk_id
            or not isinstance(doc_name, str)
            or not doc_name
            or isinstance(chunk_index, bool)
            or not isinstance(chunk_index, int)
            or chunk_index < 0
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise SQLiteSemanticValidationError("authority_schema_mismatch")
        documents.add(doc_name)
        byte_count += len(text.encode("utf-8"))
        codepoint_count += len(text)
        digest.update(
            json.dumps(
                [chunk_id, doc_name, chunk_index, text],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    if not rows:
        raise SQLiteSemanticValidationError("authority_coverage_mismatch")
    return {
        "chunk_count": len(rows),
        "document_count": len(documents),
        "text_byte_count": byte_count,
        "text_codepoint_count": codepoint_count,
        "schema_version": "chunks-v1",
        "fingerprint_algorithm": "sha256-jsonl-chunk-content-v1",
        "fingerprint": digest.hexdigest(),
    }


def inspect_authority_bm25_semantics(
    authority_database_path: str | Path,
    bm25_database_path: str | Path,
    *,
    expected_source_text_sha256: Mapping[str, str] | None = None,
) -> AuthorityBm25SemanticSnapshot:
    """Inspect one immutable authority/BM25 pair without accepting caller SQL."""

    try:
        with ReadOnlyAuthorityReader(authority_database_path) as authority_reader:
            if (
                authority_reader.integrity_check() != "ok"
                or authority_reader.user_version() != 1
                or authority_reader.foreign_key_violation_count() != 0
                or authority_reader.schema_records()
                != EXPECTED_AUTHORITY_SCHEMA_RECORDS
            ):
                raise SQLiteSemanticValidationError("authority_schema_mismatch")
            authority_rows = authority_reader.all_chunks()
            source = _authority_content_fingerprint(authority_rows)
            chunk_documents = authority_reader.chunk_document_map()
            provenance_chunk_ids = authority_reader.provenance_chunk_ids()
            document_chunk_counts = authority_reader.document_chunk_counts()
            source_records = authority_reader.source_records()
            authority_reader.validate_provenance_bindings(
                expected_source_text_sha256
            )
            actual_document_chunk_counts: dict[str, int] = {}
            per_document_indexes: dict[str, list[int]] = {}
            for row in authority_rows:
                doc_name = str(row["doc_name"])
                actual_document_chunk_counts[doc_name] = (
                    actual_document_chunk_counts.get(doc_name, 0) + 1
                )
                per_document_indexes.setdefault(doc_name, []).append(
                    int(row["chunk_index"])
                )
            chunk_ids = frozenset(str(row["chunk_id"]) for row in authority_rows)
            if (
                len(chunk_documents) != len(authority_rows)
                or frozenset(chunk_documents) != chunk_ids
                or provenance_chunk_ids != chunk_ids
                or document_chunk_counts != actual_document_chunk_counts
                or {str(row.get("doc_name") or "") for row in source_records}
                != set(document_chunk_counts)
                or any(
                    sorted(indexes) != list(range(len(indexes)))
                    for indexes in per_document_indexes.values()
                )
            ):
                raise SQLiteSemanticValidationError("authority_coverage_mismatch")

            with ReadOnlyFtsReader(
                bm25_database_path,
                authority_reader,
            ) as bm25_reader:
                if (
                    bm25_reader.integrity_check() != "ok"
                    or bm25_reader.user_version() != 0
                    or bm25_reader.foreign_key_violation_count() != 0
                    or bm25_reader.schema_records() != EXPECTED_BM25_SCHEMA_RECORDS
                ):
                    raise SQLiteSemanticValidationError("bm25_schema_mismatch")
                indexed_rows = bm25_reader.all_rows()
                expected_rows = {
                    (str(row["chunk_id"]), str(row["doc_name"]), str(row["text"]))
                    for row in authority_rows
                }
                actual_rows = {
                    (str(row["chunk_id"]), str(row["doc_name"]), str(row["text"]))
                    for row in indexed_rows
                }
                if (
                    len(indexed_rows) != len(expected_rows)
                    or actual_rows != expected_rows
                ):
                    raise SQLiteSemanticValidationError("bm25_authority_mismatch")
                bm25_reader.verify_unchanged()
                authority_reader.verify_unchanged()
                return AuthorityBm25SemanticSnapshot(
                    authority_database_sha256=authority_reader.database_sha256,
                    bm25_database_sha256=bm25_reader.database_sha256,
                    source=MappingProxyType(source),
                    indexed_chunk_count=len(indexed_rows),
                    chunk_documents=MappingProxyType(dict(chunk_documents)),
                    document_chunk_counts=MappingProxyType(
                        dict(document_chunk_counts)
                    ),
                    source_records=tuple(
                        MappingProxyType(dict(row)) for row in source_records
                    ),
                    provenance_chunk_ids=provenance_chunk_ids,
                )
    except SQLiteSemanticValidationError:
        raise
    except ReadOnlySQLiteError:
        raise SQLiteSemanticValidationError(
            "production_data_validation_failed"
        ) from None


__all__ = [
    "AUTHORITY_SCHEMA_SQL",
    "AuthorityBm25SemanticSnapshot",
    "BM25_SCHEMA_SQL",
    "EXPECTED_AUTHORITY_SCHEMA_RECORDS",
    "EXPECTED_BM25_SCHEMA_RECORDS",
    "ReadOnlyAuthorityReader",
    "ReadOnlyFtsReader",
    "ReadOnlySQLiteError",
    "SQLiteSemanticValidationError",
    "inspect_authority_bm25_semantics",
    "read_stable_regular_file",
]
