#!/usr/bin/env python3
"""Deterministically extract approved DOCX and PDF source text."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import resource
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator
from xml.etree import ElementTree


EXTRACTOR_VERSION = "cloud-v2-source-extractor-v1"
DEFAULT_CHUNK_CHARS = 1200
MAX_XML_MEMBER_BYTES = 64 * 1024 * 1024
OCR_RENDER_DPI = 170
OCR_PSM = 6
TOOL_SEARCH_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
SANDBOX_EXEC_PATH = Path("/usr/bin/sandbox-exec")
NATIVE_ENV_EXEC_PATH = Path("/usr/bin/env")
POPPLER_DATA_ROOT = Path("/opt/homebrew/Cellar/poppler/26.08.0/share/poppler")
POPPLER_FALLBACK_FONT_PATH = Path(
    "/System/Library/Fonts/Supplemental/Songti.ttc"
)
POPPLER_FALLBACK_FONT_NAME = "Songti.ttc"
POPPLER_FONTCONFIG_NAME = "fonts.conf"
POPPLER_FONTCONFIG_BYTES = (
    b'<?xml version="1.0"?>\n'
    b"<fontconfig>\n"
    b'  <dir prefix="relative">.</dir>\n'
    b"</fontconfig>\n"
)
FD_SAFETY_RESERVE = 16
SUBPROCESS_FD_BUDGET = 14
EXPECTED_POPPLER_EXECUTABLE_SHA256 = {
    "pdftotext": "52cb759b328134d667e0e9ba9142e952811473fba6caa3a053ff1e2605512fd9",
    "pdftoppm": "504dd5b6efe73d7d23bc04c90d2cfd75962b8893df95de6db7f45ab54bf47fc1",
}
EXPECTED_TESSERACT_SHA256 = (
    "6855d30ee1e9e97de11a58624973d2c7eb115a050df64fc3ba88b4077e153997"
)
EXPECTED_NATIVE_CLOSURE_IDENTITY = {
    "pdftotext": {
        "root_executable_sha256": EXPECTED_POPPLER_EXECUTABLE_SHA256["pdftotext"],
        "image_set_sha256": "d29d9548a809ab66d0ffa1edfc88c7223a0087adc9e0d48fee0100eb64aec341",
        "identity_sha256": "c8325741673c0e3456bf6deceb0a66ed88b35a8dfdd0fb19b895aa9e023ffe0b",
    },
    "pdftoppm": {
        "root_executable_sha256": EXPECTED_POPPLER_EXECUTABLE_SHA256["pdftoppm"],
        "image_set_sha256": "2ed03d67537427c539724dfa515c93fb2a09cf2bbf64a90ca60acff0e1a0b6ef",
        "identity_sha256": "bf67e573a9592177508d1d1c46205fcbd72d96f1a6344d8810b4572ef2c42c6a",
    },
    "tesseract": {
        "root_executable_sha256": EXPECTED_TESSERACT_SHA256,
        "image_set_sha256": "5765670b2044cb25961921616ce322c3cd5586a118c40fffdb59b6149bb915ba",
        "identity_sha256": "a18a4ba5ff542e12a1cc4de3110a44626f1938b2180fd3df0bd64a3234a1feee",
    },
}
EXPECTED_POPPLER_DATA_IDENTITY = {
    "schema_version": "cloud-v2-bound-runtime-tree-v1",
    "root_path_sha256": "0c46b1ec369465f6a91ab4f2286602ed173eb52eefa0f6adaa6023469b77f096",
    "node_count": 274,
    "node_set_sha256": "a1677e9e4a9c908cade23c1b8625e90f6a6f5bff4402f135f4cc89b92fbde790",
    "identity_sha256": "4bfcf01d0e5302dd62f57187318b27ec1d5e6fc9627b5ec487b617b09b876f13",
}
EXPECTED_POPPLER_FALLBACK_FONT_SHA256 = (
    "6873ac2ccab5c2e74d87d6b690f3773098dd6a6238805363a3b3567f2caf6f47"
)
EXPECTED_TESSDATA_SHA256 = {
    "chi_sim.traineddata": "a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730",
    "eng.traineddata": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
}
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DOCX_TEXT_MEMBERS = re.compile(
    r"^word/(?:document|footnotes|endnotes|comments|header\d+|footer\d+)\.xml$"
)


class SourceExtractionError(RuntimeError):
    """An approved source cannot be deterministically extracted."""


@dataclass(frozen=True)
class _NodeState:
    device: int
    inode: int
    mode: int
    link_count: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass
class _HeldDirectoryPath:
    path: Path
    field: str
    descriptors: tuple[int, ...]
    states: tuple[_NodeState, ...]
    stable_prefix_count: int
    sealed_read_only: bool = False
    closed: bool = False

    def revalidate(self) -> None:
        self._revalidate(stable_leaf=False)

    def revalidate_mutable_leaf(self) -> None:
        self._revalidate(stable_leaf=True)

    def _revalidate(self, *, stable_leaf: bool) -> None:
        if self.closed:
            raise SourceExtractionError(f"{self.field} binding is closed")
        try:
            current_state = _node_state(os.fstat(self.descriptors[-1]))
        except OSError as exc:
            raise SourceExtractionError(
                f"{self.field} ancestor identity changed"
            ) from exc
        if not _directory_state_matches(
            current_state,
            self.states[-1],
            stable_only=(
                stable_leaf or self.stable_prefix_count == len(self.states)
            ),
        ):
            raise SourceExtractionError(f"{self.field} ancestor identity changed")
        reopened = _open_directory_path(self.path, self.field)
        try:
            if not _directory_states_match(
                reopened.states,
                self.states,
                stable_prefix_count=self.stable_prefix_count,
                stable_leaf=stable_leaf,
            ):
                raise SourceExtractionError(f"{self.field} path identity changed")
        finally:
            reopened.close()

    def seal_read_only(self) -> None:
        if self.closed:
            raise SourceExtractionError(f"{self.field} binding is closed")
        self.revalidate()
        try:
            os.fchmod(self.descriptors[-1], 0o500)
            self.sealed_read_only = True
            reopened = _open_directory_path(self.path, self.field)
        except OSError as exc:
            raise SourceExtractionError(f"{self.field} could not be sealed") from exc
        try:
            current = _node_state(os.fstat(self.descriptors[-1]))
            if (
                current != reopened.states[-1]
                or stat.S_IMODE(current.mode) != 0o500
            ):
                raise SourceExtractionError(f"{self.field} could not be sealed")
            self.states = reopened.states
            self.stable_prefix_count = reopened.stable_prefix_count
        finally:
            reopened.close()
        self.revalidate()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.sealed_read_only:
            try:
                os.fchmod(self.descriptors[-1], 0o700)
            except OSError:
                pass
        for descriptor in reversed(self.descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


@dataclass
class _HeldFile:
    path: Path
    field: str
    parent: _HeldDirectoryPath
    descriptor: int
    state: _NodeState
    sha256: str
    owns_parent: bool
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise SourceExtractionError(f"{self.field} binding is closed")
        self.parent.revalidate()
        try:
            descriptor_state = _node_state(os.fstat(self.descriptor))
            path_state = _node_state(
                os.stat(
                    self.path.name,
                    dir_fd=self.parent.descriptors[-1],
                    follow_symlinks=False,
                )
            )
        except OSError as exc:
            raise SourceExtractionError(f"{self.field} identity changed") from exc
        if descriptor_state != self.state or path_state != self.state:
            raise SourceExtractionError(f"{self.field} identity changed")
        if _sha256_descriptor(self.descriptor, self.state, self.field) != self.sha256:
            raise SourceExtractionError(f"{self.field} bytes changed")
        self.parent.revalidate()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            os.close(self.descriptor)
        except OSError:
            pass
        if self.owns_parent:
            self.parent.close()


@dataclass
class _TessdataBinding:
    root: _HeldDirectoryPath
    language_files: dict[str, _HeldFile]
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise SourceExtractionError("OCR tessdata binding is closed")
        self.root.revalidate()
        for name in sorted(self.language_files):
            self.language_files[name].revalidate()
        self.root.revalidate()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for name in sorted(self.language_files, reverse=True):
            self.language_files[name].close()
        self.root.close()


@dataclass
class _PrivateFileSet:
    root: _HeldDirectoryPath
    files: dict[str, _HeldFile]
    field: str
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise SourceExtractionError(f"{self.field} binding is closed")
        self.root.revalidate()
        for name in sorted(self.files):
            self.files[name].revalidate()
        self.root.revalidate()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for name in sorted(self.files, reverse=True):
            self.files[name].close()
        self.root.close()


@dataclass
class _NativeRuntimeBinding:
    name: str
    snapshot_root: Path
    launcher_path: Path
    executable: _HeldFile
    source_libraries: dict[Path, _HeldFile]
    closure: object
    execution_bin: _PrivateFileSet
    execution_objects: _PrivateFileSet
    library_root: _HeldDirectoryPath
    library_aliases: dict[str, str]
    library_alias_states: dict[str, _NodeState]
    runtime_data_identity: dict[str, object] | None
    source_font: _HeldFile | None
    execution_fontconfig: _PrivateFileSet | None
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise SourceExtractionError(f"{self.name} native runtime binding is closed")
        self.executable.revalidate()
        for path in sorted(self.source_libraries, key=str):
            self.source_libraries[path].revalidate()
        current = _resolve_native_closure(self.launcher_path, self.name)
        if current != self.closure:
            raise SourceExtractionError(f"{self.name} native closure changed")
        _verify_approved_native_closure(self.name, current, self.executable.sha256)
        if self.runtime_data_identity is not None:
            current_data = _resolve_poppler_runtime_data_identity()
            if current_data != self.runtime_data_identity:
                raise SourceExtractionError("Poppler runtime data identity changed")
        if self.name == "pdftoppm":
            if self.source_font is None or self.execution_fontconfig is None:
                raise SourceExtractionError("pdftoppm font runtime is incomplete")
            self.source_font.revalidate()
            self.execution_fontconfig.revalidate()
        elif self.source_font is not None or self.execution_fontconfig is not None:
            raise SourceExtractionError(
                f"{self.name} native runtime has an unexpected font binding"
            )
        self.execution_bin.revalidate()
        self.execution_objects.revalidate()
        self.library_root.revalidate()
        listing_root = _open_directory_path(
            self.library_root.path,
            f"{self.name} private library aliases",
        )
        try:
            if not _directory_states_match(
                listing_root.states,
                self.library_root.states,
                stable_prefix_count=self.library_root.stable_prefix_count,
            ):
                raise SourceExtractionError(
                    f"{self.name} private library alias closure changed"
                )
            names = os.listdir(listing_root.descriptors[-1])
        except OSError as exc:
            raise SourceExtractionError(
                f"{self.name} private library aliases cannot be read"
            ) from exc
        finally:
            listing_root.close()
        if set(names) != set(self.library_aliases) or len(names) != len(
            self.library_aliases
        ):
            raise SourceExtractionError(
                f"{self.name} private library alias closure changed"
            )
        for alias, digest in sorted(self.library_aliases.items()):
            expected_target = f"../objects/{digest}.dylib"
            try:
                state = _node_state(
                    os.stat(
                        alias,
                        dir_fd=self.library_root.descriptors[-1],
                        follow_symlinks=False,
                    )
                )
                target = os.readlink(
                    alias,
                    dir_fd=self.library_root.descriptors[-1],
                )
            except OSError as exc:
                raise SourceExtractionError(
                    f"{self.name} private library alias changed: {alias}"
                ) from exc
            if (
                state != self.library_alias_states.get(alias)
                or not stat.S_ISLNK(state.mode)
                or target != expected_target
            ):
                raise SourceExtractionError(
                    f"{self.name} private library alias changed: {alias}"
                )
            try:
                resolved = (self.library_root.path / alias).resolve(strict=True)
            except OSError as exc:
                raise SourceExtractionError(
                    f"{self.name} private library alias target changed: {alias}"
                ) from exc
            if resolved != self.execution_objects.files[f"{digest}.dylib"].path:
                raise SourceExtractionError(
                    f"{self.name} private library alias target changed: {alias}"
                )
        self.library_root.revalidate()
        self.execution_objects.revalidate()
        self.execution_bin.revalidate()
        if self.execution_fontconfig is not None:
            self.execution_fontconfig.revalidate()
        if self.source_font is not None:
            self.source_font.revalidate()
        for path in sorted(self.source_libraries, key=str):
            self.source_libraries[path].revalidate()
        self.executable.revalidate()

    @property
    def command_path(self) -> Path:
        return self.execution_bin.files[self.name].path

    def environment(self) -> dict[str, str]:
        environment = {
            "PATH": TOOL_SEARCH_PATH,
            "DYLD_LIBRARY_PATH": str(self.library_root.path),
        }
        if self.execution_fontconfig is not None:
            environment["FONTCONFIG_FILE"] = str(
                self.execution_fontconfig.files[POPPLER_FONTCONFIG_NAME].path
            )
        return environment

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.execution_fontconfig is not None:
            self.execution_fontconfig.close()
        self.library_root.close()
        self.execution_objects.close()
        self.execution_bin.close()
        for path in sorted(self.source_libraries, key=str, reverse=True):
            self.source_libraries[path].close()
        if self.source_font is not None:
            self.source_font.close()
        self.executable.close()


@dataclass
class _OCRRuntimeBinding:
    native_runtime: _NativeRuntimeBinding
    snapshot_root: Path
    tessdata: _TessdataBinding
    execution_tessdata: _PrivateFileSet
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise SourceExtractionError("OCR runtime binding is closed")
        self.native_runtime.revalidate()
        self.tessdata.revalidate()
        self.execution_tessdata.revalidate()
        self.native_runtime.revalidate()
        self.tessdata.revalidate()

    @property
    def execution_tesseract(self) -> _HeldFile:
        return self.native_runtime.execution_bin.files["tesseract"]

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.execution_tessdata.close()
        self.tessdata.close()
        self.native_runtime.close()


@dataclass(frozen=True)
class ExtractedUnit:
    ordinal: int
    text: str
    page_start: int
    page_end: int
    section_title: str | None
    content_type: str


@dataclass(frozen=True)
class ExtractedDocument:
    relative_path: str
    units: tuple[ExtractedUnit, ...]
    page_count: int
    extractor: str
    text_sha256: str


def _clean_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = []
    for line in value.splitlines():
        line = re.sub(r"[\t ]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _validate_zip_member(name: str) -> str:
    if "\\" in name or name.startswith("/") or "//" in name:
        raise SourceExtractionError("DOCX contains a noncanonical ZIP member")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise SourceExtractionError("DOCX contains ZIP path traversal")
    return path.as_posix()


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == _WORD_NS + "t" and node.text:
            parts.append(node.text)
        elif node.tag == _WORD_NS + "tab":
            parts.append("\t")
        elif node.tag in {_WORD_NS + "br", _WORD_NS + "cr"}:
            parts.append("\n")
    return _clean_text("".join(parts))


def extract_docx(payload: bytes, relative_path: str) -> ExtractedDocument:
    paragraphs: list[tuple[str, str]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = []
            for info in archive.infolist():
                name = _validate_zip_member(info.filename)
                if info.flag_bits & 0x1:
                    raise SourceExtractionError("encrypted DOCX members are forbidden")
                if _DOCX_TEXT_MEMBERS.fullmatch(name):
                    if info.file_size > MAX_XML_MEMBER_BYTES:
                        raise SourceExtractionError("DOCX text XML member exceeds the extraction cap")
                    members.append((0 if name == "word/document.xml" else 1, name, info))
            if not any(name == "word/document.xml" for _, name, _ in members):
                raise SourceExtractionError("DOCX is missing word/document.xml")
            for _, name, info in sorted(members):
                try:
                    root = ElementTree.fromstring(archive.read(info))
                except ElementTree.ParseError as exc:
                    raise SourceExtractionError(f"invalid DOCX XML member: {name}") from exc
                for paragraph in root.iter(_WORD_NS + "p"):
                    text = _paragraph_text(paragraph)
                    if text:
                        paragraphs.append((name, text))
    except (OSError, zipfile.BadZipFile) as exc:
        raise SourceExtractionError("invalid DOCX container") from exc

    if not paragraphs:
        raise SourceExtractionError("DOCX extraction produced no text")
    units = _pack_paragraphs(paragraphs, page=1, content_type="docx_text")
    return _document(relative_path, units, page_count=1, extractor=EXTRACTOR_VERSION + ":docx-xml")


_SYSTEM_PATH_ALIAS_TARGETS = {
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}


def _node_state(value: os.stat_result) -> _NodeState:
    return _NodeState(
        device=value.st_dev,
        inode=value.st_ino,
        mode=value.st_mode,
        link_count=value.st_nlink,
        size=value.st_size,
        mtime_ns=value.st_mtime_ns,
        ctime_ns=value.st_ctime_ns,
    )


def _directory_states_match(
    current: tuple[_NodeState, ...],
    expected: tuple[_NodeState, ...],
    *,
    stable_prefix_count: int,
    stable_leaf: bool = False,
) -> bool:
    if len(current) != len(expected) or not 0 <= stable_prefix_count <= len(expected):
        return False
    return all(
        _directory_state_matches(
            current_state,
            expected_state,
            stable_only=(
                index < stable_prefix_count
                or stable_leaf
                and index == len(expected) - 1
            ),
        )
        for index, (current_state, expected_state) in enumerate(
            zip(current, expected, strict=True)
        )
    )


def _directory_state_matches(
    current: _NodeState,
    expected: _NodeState,
    *,
    stable_only: bool,
) -> bool:
    if not stable_only:
        return current == expected
    return (
        current.device,
        current.inode,
        current.mode,
    ) == (
        expected.device,
        expected.inode,
        expected.mode,
    )


def _absolute_path(raw: str | Path, field: str) -> Path:
    try:
        value = os.fspath(raw)
    except TypeError as exc:
        raise SourceExtractionError(f"{field} path is invalid") from exc
    if isinstance(value, bytes) or not value or "\x00" in value:
        raise SourceExtractionError(f"{field} path is invalid")
    path = Path(value)
    if not path.is_absolute():
        path = Path(os.path.abspath(path))
    if sys.platform == "darwin":
        for alias, target in _SYSTEM_PATH_ALIAS_TARGETS.items():
            try:
                relative = path.relative_to(alias)
            except ValueError:
                continue
            return target / relative
    return path


def _stable_directory_prefix_count(path: Path) -> int:
    try:
        temporary_root = _absolute_path(
            tempfile.gettempdir(),
            "canonical temporary root",
        ).resolve(strict=True)
        path.relative_to(temporary_root)
    except (OSError, SourceExtractionError, ValueError):
        return 0
    return len(temporary_root.parts)


def _current_open_fd_count() -> int:
    try:
        return len(os.listdir("/dev/fd"))
    except OSError as exc:
        raise SourceExtractionError("open file descriptor count is unavailable") from exc


def _require_fd_capacity(additional: int, field: str) -> None:
    if not isinstance(additional, int) or additional < 0:
        raise SourceExtractionError(f"{field} file descriptor budget is invalid")
    try:
        soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError) as exc:
        raise SourceExtractionError(
            f"{field} file descriptor soft limit is unavailable"
        ) from exc
    if soft_limit == resource.RLIM_INFINITY:
        return
    required = _current_open_fd_count() + additional + FD_SAFETY_RESERVE
    if required > soft_limit:
        raise SourceExtractionError(
            f"{field} requires {required} file descriptors but the soft limit is "
            f"{soft_limit}"
        )


def _open_directory_path(raw: str | Path, field: str) -> _HeldDirectoryPath:
    path = _absolute_path(raw, field)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    stable_prefix_count = _stable_directory_prefix_count(path)
    states: list[_NodeState] = []
    current: int | None = None
    try:
        current = os.open("/", flags)
        states.append(_node_state(os.fstat(current)))
        for component in path.parts[1:]:
            inspected = os.stat(
                component,
                dir_fd=current,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(inspected.st_mode):
                raise SourceExtractionError(
                    f"{field} must be a real directory; path contains a symlink"
                )
            if not stat.S_ISDIR(inspected.st_mode):
                raise SourceExtractionError(f"{field} path contains a non-directory")
            child: int | None = None
            try:
                child = os.open(component, flags, dir_fd=current)
                opened = _node_state(os.fstat(child))
                if not _directory_state_matches(
                    opened,
                    _node_state(inspected),
                    stable_only=len(states) < stable_prefix_count,
                ):
                    raise SourceExtractionError(
                        f"{field} identity changed while opening"
                    )
            except BaseException:
                if child is not None:
                    try:
                        os.close(child)
                    except OSError:
                        pass
                raise
            states.append(opened)
            try:
                os.close(current)
            except OSError:
                pass
            current = child
        if current is None:
            raise SourceExtractionError(f"{field} cannot be opened safely")
        return _HeldDirectoryPath(
            path=path,
            field=field,
            descriptors=(current,),
            states=tuple(states),
            stable_prefix_count=stable_prefix_count,
        )
    except SourceExtractionError:
        if current is not None:
            try:
                os.close(current)
            except OSError:
                pass
        raise
    except OSError as exc:
        if current is not None:
            try:
                os.close(current)
            except OSError:
                pass
        raise SourceExtractionError(f"{field} cannot be opened safely") from exc
    except BaseException:
        if current is not None:
            try:
                os.close(current)
            except OSError:
                pass
        raise


def _sha256_descriptor(
    descriptor: int,
    expected_state: _NodeState,
    field: str,
) -> str:
    try:
        if _node_state(os.fstat(descriptor)) != expected_state:
            raise SourceExtractionError(f"{field} identity changed while reading")
        digest = hashlib.sha256()
        offset = 0
        while offset < expected_state.size:
            block = os.pread(
                descriptor,
                min(1024 * 1024, expected_state.size - offset),
                offset,
            )
            if not block:
                raise SourceExtractionError(f"{field} became shorter while reading")
            digest.update(block)
            offset += len(block)
        if _node_state(os.fstat(descriptor)) != expected_state:
            raise SourceExtractionError(f"{field} identity changed while reading")
        return digest.hexdigest()
    except SourceExtractionError:
        raise
    except OSError as exc:
        raise SourceExtractionError(f"{field} cannot be read safely") from exc


def _open_file_under_directory(
    parent: _HeldDirectoryPath,
    name: str,
    field: str,
    *,
    owns_parent: bool,
) -> _HeldFile:
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise SourceExtractionError(f"{field} filename is invalid")
    descriptor: int | None = None
    try:
        parent.revalidate()
        inspected = os.stat(
            name,
            dir_fd=parent.descriptors[-1],
            follow_symlinks=False,
        )
        if stat.S_ISLNK(inspected.st_mode) or not stat.S_ISREG(inspected.st_mode):
            raise SourceExtractionError(
                f"{field} must be a regular unsymlinked file"
            )
        if inspected.st_nlink != 1:
            raise SourceExtractionError(f"{field} must not be a hardlink")
        state = _node_state(inspected)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(name, flags, dir_fd=parent.descriptors[-1])
        if _node_state(os.fstat(descriptor)) != state:
            raise SourceExtractionError(f"{field} identity changed while opening")
        digest = _sha256_descriptor(descriptor, state, field)
        if (
            _node_state(
                os.stat(
                    name,
                    dir_fd=parent.descriptors[-1],
                    follow_symlinks=False,
                )
            )
            != state
        ):
            raise SourceExtractionError(f"{field} identity changed while reading")
        parent.revalidate()
        return _HeldFile(
            path=parent.path / name,
            field=field,
            parent=parent,
            descriptor=descriptor,
            state=state,
            sha256=digest,
            owns_parent=owns_parent,
        )
    except SourceExtractionError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise SourceExtractionError(f"{field} cannot be opened safely") from exc
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _open_held_file(path: Path, field: str) -> _HeldFile:
    parent = _open_directory_path(path.parent, f"{field} parent")
    try:
        return _open_file_under_directory(
            parent,
            path.name,
            field,
            owns_parent=True,
        )
    except BaseException:
        parent.close()
        raise


def _read_held_file_bytes(held: _HeldFile) -> bytes:
    held.revalidate()
    try:
        chunks: list[bytes] = []
        offset = 0
        while offset < held.state.size:
            block = os.pread(
                held.descriptor,
                min(1024 * 1024, held.state.size - offset),
                offset,
            )
            if not block:
                raise SourceExtractionError(
                    f"{held.field} became shorter while snapshotting"
                )
            chunks.append(block)
            offset += len(block)
        payload = b"".join(chunks)
        if _node_state(os.fstat(held.descriptor)) != held.state:
            raise SourceExtractionError(
                f"{held.field} identity changed while snapshotting"
            )
        if hashlib.sha256(payload).hexdigest() != held.sha256:
            raise SourceExtractionError(f"{held.field} bytes changed while snapshotting")
        held.revalidate()
        return payload
    except SourceExtractionError:
        raise
    except OSError as exc:
        raise SourceExtractionError(
            f"{held.field} cannot be snapshotted safely"
        ) from exc


def _open_private_directory(
    raw: str | Path,
    field: str,
    *,
    expected_names: set[str],
) -> _HeldDirectoryPath:
    root = _open_directory_path(raw, field)
    try:
        leaf = os.fstat(root.descriptors[-1])
        if stat.S_IMODE(leaf.st_mode) != 0o700:
            raise SourceExtractionError(f"{field} must have mode 0700")
        if hasattr(os, "geteuid") and leaf.st_uid != os.geteuid():
            raise SourceExtractionError(f"{field} must be owned by the current user")
        names = os.listdir(root.descriptors[-1])
        if set(names) != expected_names or len(names) != len(expected_names):
            raise SourceExtractionError(f"{field} contents are not closed")
        folded = {name.casefold() for name in names}
        if len(folded) != len(names):
            raise SourceExtractionError(f"{field} contains case aliases")
        root.revalidate()
        return root
    except BaseException:
        root.close()
        raise


def _write_all(descriptor: int, payload: bytes, field: str) -> None:
    view = memoryview(payload)
    offset = 0
    try:
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise SourceExtractionError(f"{field} could not be written completely")
            offset += written
    except SourceExtractionError:
        raise
    except OSError as exc:
        raise SourceExtractionError(f"{field} could not be written safely") from exc


def _prepare_private_subdirectories(
    root_path: Path,
    names: tuple[str, ...],
    field: str,
) -> dict[str, Path]:
    if not names or len(set(names)) != len(names):
        raise SourceExtractionError(f"{field} directory plan is invalid")
    root = _open_private_directory(
        root_path,
        field,
        expected_names=set(),
    )
    try:
        for name in names:
            if not name or "/" in name or "\\" in name or name in {".", ".."}:
                raise SourceExtractionError(f"{field} directory name is invalid")
            os.mkdir(name, mode=0o700, dir_fd=root.descriptors[-1])
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root.descriptors[-1],
            )
            try:
                os.fchmod(descriptor, 0o700)
            finally:
                os.close(descriptor)
    except OSError as exc:
        raise SourceExtractionError(f"{field} could not be prepared safely") from exc
    finally:
        root.close()
    verified = _open_private_directory(
        root_path,
        field,
        expected_names=set(names),
    )
    try:
        for name in names:
            inspected = os.stat(
                name,
                dir_fd=verified.descriptors[-1],
                follow_symlinks=False,
            )
            if (
                stat.S_ISLNK(inspected.st_mode)
                or not stat.S_ISDIR(inspected.st_mode)
                or stat.S_IMODE(inspected.st_mode) != 0o700
                or (hasattr(os, "geteuid") and inspected.st_uid != os.geteuid())
            ):
                raise SourceExtractionError(f"{field} child is not private: {name}")
        verified.revalidate()
    finally:
        verified.close()
    return {name: root_path / name for name in names}


def _materialize_private_file_set(
    root_path: Path,
    files: dict[str, tuple[bytes, int]],
    field: str,
) -> _PrivateFileSet:
    root = _open_private_directory(root_path, field, expected_names=set())
    created: list[str] = []
    try:
        for name in sorted(files):
            payload, mode = files[name]
            if (
                not name
                or "/" in name
                or "\\" in name
                or name in {".", ".."}
                or not payload
                or mode not in {0o400, 0o500}
            ):
                raise SourceExtractionError(f"{field} file plan is invalid")
            descriptor = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=root.descriptors[-1],
            )
            created.append(name)
            try:
                _write_all(descriptor, payload, f"{field} {name}")
                os.fsync(descriptor)
                os.fchmod(descriptor, mode)
                state = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(state.st_mode)
                    or state.st_nlink != 1
                    or state.st_size != len(payload)
                    or stat.S_IMODE(state.st_mode) != mode
                ):
                    raise SourceExtractionError(f"{field} file identity mismatch: {name}")
            finally:
                os.close(descriptor)
    except BaseException:
        for name in reversed(created):
            try:
                os.unlink(name, dir_fd=root.descriptors[-1])
            except OSError:
                pass
        root.close()
        raise
    root.close()

    bound_root = _open_private_directory(
        root_path,
        field,
        expected_names=set(files),
    )
    held_files: dict[str, _HeldFile] = {}
    try:
        for name in sorted(files):
            payload, mode = files[name]
            held = _open_file_under_directory(
                bound_root,
                name,
                f"{field} {name}",
                owns_parent=False,
            )
            held_files[name] = held
            if (
                held.sha256 != hashlib.sha256(payload).hexdigest()
                or stat.S_IMODE(held.state.mode) != mode
            ):
                raise SourceExtractionError(f"{field} file bytes mismatch: {name}")
        result = _PrivateFileSet(root=bound_root, files=held_files, field=field)
        result.revalidate()
        bound_root.seal_read_only()
        result.revalidate()
        return result
    except BaseException:
        for held in held_files.values():
            held.close()
        bound_root.close()
        raise


def _bind_executable(
    name: str,
    *,
    expected_sha256: str | None = None,
    launcher_path: Path | None = None,
) -> _HeldFile:
    if launcher_path is None:
        discovered = shutil.which(name, path=TOOL_SEARCH_PATH)
        if not discovered:
            raise SourceExtractionError(f"{name} executable is unavailable")
        launcher_path = Path(discovered)
    if not launcher_path.is_absolute() or launcher_path.name != name:
        raise SourceExtractionError(f"{name} executable launcher is not approved")
    try:
        canonical = launcher_path.resolve(strict=True)
    except OSError as exc:
        raise SourceExtractionError(f"{name} executable is unavailable") from exc
    held = _open_held_file(canonical, f"{name} executable")
    if stat.S_IMODE(held.state.mode) & 0o111 == 0:
        held.close()
        raise SourceExtractionError(f"{name} executable is not executable")
    if expected_sha256 is not None and held.sha256 != expected_sha256:
        held.close()
        raise SourceExtractionError(f"{name} executable identity is not approved")
    return held


def _resolve_native_closure(path: Path, name: str) -> object:
    try:
        from .offline_evidence import (
            OfflineEvidenceError,
            _external_tool_macho_closure,
        )
    except (ImportError, AttributeError) as exc:
        raise SourceExtractionError(
            f"{name} native closure resolver is unavailable"
        ) from exc
    try:
        return _external_tool_macho_closure(path, tool_name=name)
    except OfflineEvidenceError as exc:
        raise SourceExtractionError(f"{name} native closure cannot be resolved") from exc


def _verify_approved_native_closure(
    name: str,
    closure: object,
    executable_sha256: str,
) -> None:
    expected = EXPECTED_NATIVE_CLOSURE_IDENTITY.get(name)
    try:
        identity = closure.identity
        actual = {
            field: identity[field]
            for field in (
                "root_executable_sha256",
                "image_set_sha256",
                "identity_sha256",
            )
        }
    except (AttributeError, KeyError, TypeError) as exc:
        raise SourceExtractionError(f"{name} native closure is malformed") from exc
    if (
        expected is None
        or actual != expected
        or actual["root_executable_sha256"] != executable_sha256
    ):
        raise SourceExtractionError(f"{name} native closure identity is not approved")


def _resolve_poppler_runtime_data_identity() -> dict[str, object]:
    try:
        from .offline_evidence import (
            OfflineEvidenceError,
            _bound_runtime_tree_identity,
        )
    except (ImportError, AttributeError) as exc:
        raise SourceExtractionError("Poppler runtime data resolver is unavailable") from exc
    try:
        identity, _read_literals = _bound_runtime_tree_identity(
            POPPLER_DATA_ROOT,
            "Poppler runtime data tree",
            reject_symlinks=True,
        )
    except OfflineEvidenceError as exc:
        raise SourceExtractionError("Poppler runtime data cannot be resolved") from exc
    if identity != EXPECTED_POPPLER_DATA_IDENTITY:
        raise SourceExtractionError("Poppler runtime data identity is not approved")
    return identity


def _bind_native_runtime(
    name: str,
    snapshot_root: Path,
    *,
    expected_sha256: str | None = None,
) -> _NativeRuntimeBinding:
    executable: _HeldFile | None = None
    source_libraries: dict[Path, _HeldFile] = {}
    execution_bin: _PrivateFileSet | None = None
    execution_objects: _PrivateFileSet | None = None
    source_font: _HeldFile | None = None
    execution_fontconfig: _PrivateFileSet | None = None
    library_root: _HeldDirectoryPath | None = None
    try:
        bind_poppler_font = name == "pdftoppm"
        directories = _prepare_private_subdirectories(
            snapshot_root,
            (
                "bin",
                "objects",
                "lib",
                *(("fontconfig",) if bind_poppler_font else ()),
            ),
            f"private {name} native runtime root",
        )
        discovered = shutil.which(name, path=TOOL_SEARCH_PATH)
        if not discovered:
            raise SourceExtractionError(f"{name} executable is unavailable")
        launcher_path = Path(discovered)
        executable = _bind_executable(
            name,
            expected_sha256=expected_sha256,
            launcher_path=launcher_path,
        )
        closure = _resolve_native_closure(launcher_path, name)
        _verify_approved_native_closure(name, closure, executable.sha256)
        try:
            resolved_images = tuple(
                Path(path).resolve(strict=True) for path in closure.resolved_images
            )
            read_literals = tuple(Path(path) for path in closure.read_literals)
        except (AttributeError, TypeError) as exc:
            raise SourceExtractionError(f"{name} native closure is malformed") from exc
        if (
            executable.path not in resolved_images
            or len(set(resolved_images)) != len(resolved_images)
            or any(not path.is_absolute() for path in resolved_images)
        ):
            raise SourceExtractionError(f"{name} native closure is malformed")
        dependency_count = len(set(resolved_images) - {executable.path})
        _require_fd_capacity(
            3 * dependency_count + 5 + (5 if bind_poppler_font else 0),
            f"{name} native runtime",
        )
        runtime_data_identity = (
            _resolve_poppler_runtime_data_identity()
            if name in EXPECTED_POPPLER_EXECUTABLE_SHA256
            else None
        )
        if bind_poppler_font:
            source_font = _open_held_file(
                POPPLER_FALLBACK_FONT_PATH,
                "Poppler fallback font",
            )
            if source_font.sha256 != EXPECTED_POPPLER_FALLBACK_FONT_SHA256:
                raise SourceExtractionError(
                    "Poppler fallback font identity is not approved"
                )
        for path in sorted(set(resolved_images) - {executable.path}, key=str):
            source_libraries[path] = _open_held_file(
                path,
                f"{name} native library",
            )
        if _resolve_native_closure(launcher_path, name) != closure:
            raise SourceExtractionError(f"{name} native closure changed while binding")
        executable.revalidate()
        for path in sorted(source_libraries, key=str):
            source_libraries[path].revalidate()

        execution_bin = _materialize_private_file_set(
            directories["bin"],
            {name: (_read_held_file_bytes(executable), 0o500)},
            f"private {name} executable snapshot",
        )
        digest_to_payload: dict[str, bytes] = {}
        resolved_digests: dict[Path, str] = {}
        for path, held in sorted(source_libraries.items(), key=lambda item: str(item[0])):
            payload = _read_held_file_bytes(held)
            digest = hashlib.sha256(payload).hexdigest()
            digest_to_payload.setdefault(digest, payload)
            resolved_digests[path] = digest
        execution_objects = _materialize_private_file_set(
            directories["objects"],
            {
                f"{digest}.dylib": (payload, 0o400)
                for digest, payload in sorted(digest_to_payload.items())
            },
            f"private {name} native object snapshot",
        )
        if source_font is not None:
            execution_fontconfig = _materialize_private_file_set(
                directories["fontconfig"],
                {
                    POPPLER_FALLBACK_FONT_NAME: (
                        _read_held_file_bytes(source_font),
                        0o400,
                    ),
                    POPPLER_FONTCONFIG_NAME: (POPPLER_FONTCONFIG_BYTES, 0o400),
                },
                "private pdftoppm fontconfig snapshot",
            )
            source_font.revalidate()

        aliases: dict[str, str] = {}
        alias_keys: dict[str, str] = {}
        alias_candidates = set(source_libraries)
        alias_candidates.update(
            path for path in read_literals if path.name.endswith(".dylib")
        )
        for candidate in sorted(alias_candidates, key=str):
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise SourceExtractionError(
                    f"{name} native library alias is unavailable"
                ) from exc
            digest = resolved_digests.get(resolved)
            if digest is None:
                continue
            alias = candidate.name
            if not re.fullmatch(r"[A-Za-z0-9._+\-]+\.dylib", alias):
                raise SourceExtractionError(
                    f"{name} native library alias is not canonical"
                )
            folded = alias.casefold()
            previous_alias = alias_keys.get(folded)
            previous_digest = aliases.get(previous_alias or "")
            if previous_alias is not None and (
                previous_alias != alias or previous_digest != digest
            ):
                raise SourceExtractionError(
                    f"{name} native library alias conflicts"
                )
            existing_digest = aliases.get(alias)
            if existing_digest is not None and existing_digest != digest:
                raise SourceExtractionError(
                    f"{name} native library alias maps to multiple images"
                )
            alias_keys[folded] = alias
            aliases[alias] = digest
        if set(aliases.values()) != set(digest_to_payload):
            raise SourceExtractionError(
                f"{name} private native library alias closure is incomplete"
            )

        alias_parent = _open_private_directory(
            directories["lib"],
            f"private {name} native library aliases",
            expected_names=set(),
        )
        try:
            for alias, digest in sorted(aliases.items()):
                os.symlink(
                    f"../objects/{digest}.dylib",
                    alias,
                    dir_fd=alias_parent.descriptors[-1],
                )
        except OSError as exc:
            raise SourceExtractionError(
                f"{name} private native library aliases could not be created"
            ) from exc
        finally:
            alias_parent.close()
        library_root = _open_private_directory(
            directories["lib"],
            f"private {name} native library aliases",
            expected_names=set(aliases),
        )
        alias_states = {
            alias: _node_state(
                os.stat(
                    alias,
                    dir_fd=library_root.descriptors[-1],
                    follow_symlinks=False,
                )
            )
            for alias in sorted(aliases)
        }
        library_root.seal_read_only()
        result = _NativeRuntimeBinding(
            name=name,
            snapshot_root=snapshot_root,
            launcher_path=launcher_path,
            executable=executable,
            source_libraries=source_libraries,
            closure=closure,
            execution_bin=execution_bin,
            execution_objects=execution_objects,
            library_root=library_root,
            library_aliases=aliases,
            library_alias_states=alias_states,
            runtime_data_identity=runtime_data_identity,
            source_font=source_font,
            execution_fontconfig=execution_fontconfig,
        )
        result.revalidate()
        return result
    except BaseException:
        if library_root is not None:
            library_root.close()
        if execution_fontconfig is not None:
            execution_fontconfig.close()
        if execution_objects is not None:
            execution_objects.close()
        if execution_bin is not None:
            execution_bin.close()
        for path in sorted(source_libraries, key=str, reverse=True):
            source_libraries[path].close()
        if source_font is not None:
            source_font.close()
        if executable is not None:
            executable.close()
        raise


@contextlib.contextmanager
def _bound_executable(
    name: str,
    *,
    expected_sha256: str | None = None,
) -> Iterator[_HeldFile]:
    held = _bind_executable(name, expected_sha256=expected_sha256)
    try:
        yield held
    finally:
        held.close()


def _bind_tessdata(tessdata_dir: str | Path) -> _TessdataBinding:
    root = _open_directory_path(tessdata_dir, "OCR tessdata")
    language_files: dict[str, _HeldFile] = {}
    try:
        for name, expected in EXPECTED_TESSDATA_SHA256.items():
            held = _open_file_under_directory(
                root,
                name,
                f"OCR language data {name}",
                owns_parent=False,
            )
            language_files[name] = held
            if held.sha256 != expected:
                raise SourceExtractionError(
                    f"OCR language data identity mismatch: {name}"
                )
        binding = _TessdataBinding(root=root, language_files=language_files)
        binding.revalidate()
        return binding
    except BaseException:
        for held in language_files.values():
            held.close()
        root.close()
        raise


@contextlib.contextmanager
def _bound_ocr_runtime(
    tessdata_dir: str | Path,
    *,
    _snapshot_root: Path | None = None,
) -> Iterator[_OCRRuntimeBinding]:
    temporary: tempfile.TemporaryDirectory[str] | None = None
    native_runtime: _NativeRuntimeBinding | None = None
    tessdata: _TessdataBinding | None = None
    execution_tessdata: _PrivateFileSet | None = None
    runtime: _OCRRuntimeBinding | None = None
    try:
        if _snapshot_root is None:
            temporary = tempfile.TemporaryDirectory(
                prefix="kg-cloud-v2-ocr-runtime-"
            )
            snapshot_root = Path(temporary.name)
            os.chmod(snapshot_root, 0o700)
        else:
            snapshot_root = _snapshot_root
        directories = _prepare_private_subdirectories(
            snapshot_root,
            ("native", "tessdata"),
            "private OCR runtime root",
        )
        native_runtime = _bind_native_runtime(
            "tesseract",
            directories["native"],
            expected_sha256=EXPECTED_TESSERACT_SHA256,
        )
        tessdata = _bind_tessdata(tessdata_dir)
        execution_tessdata = _materialize_private_file_set(
            directories["tessdata"],
            {
                name: (_read_held_file_bytes(held), 0o400)
                for name, held in sorted(tessdata.language_files.items())
            },
            "private OCR tessdata snapshot",
        )
        runtime = _OCRRuntimeBinding(
            native_runtime=native_runtime,
            snapshot_root=snapshot_root,
            tessdata=tessdata,
            execution_tessdata=execution_tessdata,
        )
        runtime.revalidate()
        yield runtime
    finally:
        try:
            if runtime is not None:
                try:
                    runtime.revalidate()
                finally:
                    runtime.close()
            else:
                if execution_tessdata is not None:
                    execution_tessdata.close()
                if tessdata is not None:
                    tessdata.close()
                if native_runtime is not None:
                    native_runtime.close()
        finally:
            if temporary is not None:
                temporary.cleanup()


def _ocr_runtime_identity() -> dict[str, object]:
    return {
        "engine": "tesseract",
        "engine_sha256": EXPECTED_TESSERACT_SHA256,
        "languages": "chi_sim+eng",
        "language_data_sha256": {
            name.removesuffix(".traineddata"): expected
            for name, expected in EXPECTED_TESSDATA_SHA256.items()
        },
        "render_dpi": OCR_RENDER_DPI,
        "page_segmentation_mode": OCR_PSM,
    }


def _bind_root_owned_system_executable(path: Path, field: str) -> _HeldFile:
    try:
        canonical = path.resolve(strict=True)
    except OSError as exc:
        raise SourceExtractionError(f"{field} is unavailable") from exc
    if canonical != path or path.is_symlink():
        raise SourceExtractionError(f"{field} path is not approved")
    held = _open_held_file(canonical, field)
    try:
        state = os.fstat(held.descriptor)
        if (
            stat.S_IMODE(state.st_mode) & 0o111 == 0
            or (hasattr(os, "geteuid") and state.st_uid != 0)
        ):
            raise SourceExtractionError(f"{field} identity is not approved")
        return held
    except BaseException:
        held.close()
        raise


def _bind_sandbox_exec() -> _HeldFile:
    return _bind_root_owned_system_executable(
        SANDBOX_EXEC_PATH,
        "sandbox-exec executable",
    )


def _bind_native_env_exec() -> _HeldFile:
    return _bind_root_owned_system_executable(
        NATIVE_ENV_EXEC_PATH,
        "native environment launcher",
    )


def _sandbox_path_literal(path: Path, field: str) -> str:
    value = str(path)
    if (
        not path.is_absolute()
        or value != os.path.normpath(value)
        or any(character in value for character in ("\x00", "\r", "\n"))
    ):
        raise SourceExtractionError(f"{field} is not a canonical absolute path")
    return json.dumps(value, ensure_ascii=False)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _native_tool_sandbox_profile(
    command_path: Path,
    *,
    writable_roots: tuple[Path, ...],
    read_only_roots: tuple[Path, ...] = (),
    read_only_files: tuple[Path, ...] = (),
    launcher_paths: tuple[Path, ...] = (),
) -> str:
    if not writable_roots or len(set(writable_roots)) != len(writable_roots):
        raise SourceExtractionError("native sandbox writable roots are invalid")
    process_paths = {command_path, *launcher_paths}
    if len(process_paths) != len(launcher_paths) + 1:
        raise SourceExtractionError("native sandbox executable paths are invalid")
    read_roots = set(read_only_roots) | set(writable_roots)
    if Path("/") in read_roots:
        raise SourceExtractionError("native sandbox read roots are invalid")
    read_files = set(read_only_files) | process_paths | {Path("/dev/null")}
    read_ancestors = {
        ancestor
        for path in read_roots | read_files
        for ancestor in path.parents
    } - read_roots - read_files
    read_ancestor_rules = "".join(
        f"(allow file-read* (literal {literal}))"
        for literal in (
            _sandbox_path_literal(path, "native sandbox read ancestor")
            for path in sorted(read_ancestors, key=str)
        )
    )
    read_root_rules = "".join(
        (
            f"(allow file-read* (literal {literal}))"
            f"(allow file-read* (subpath {literal}))"
        )
        for literal in (
            _sandbox_path_literal(path, "native sandbox read root")
            for path in sorted(read_roots, key=str)
        )
    )
    read_file_rules = "".join(
        f"(allow file-read* (literal {literal}))"
        for literal in (
            _sandbox_path_literal(path, "native sandbox read file")
            for path in sorted(read_files, key=str)
        )
    )
    read_only_rules = "".join(
        (
            f"(deny file-write* (literal {literal}))"
            f"(deny file-write* (subpath {literal}))"
        )
        for literal in (
            _sandbox_path_literal(path, "native sandbox read-only root")
            for path in sorted(set(read_only_roots), key=str)
        )
    )
    read_only_file_rules = "".join(
        f"(deny file-write* (literal {literal}))"
        for literal in (
            _sandbox_path_literal(path, "native sandbox read-only file")
            for path in sorted(set(read_only_files) | process_paths, key=str)
        )
    )
    writable_rules = "".join(
        (
            f"(allow file-write* (literal {literal}))"
            f"(allow file-write* (subpath {literal}))"
        )
        for literal in (
            _sandbox_path_literal(path, "native sandbox writable root")
            for path in sorted(writable_roots, key=str)
        )
    )
    process_exec_rules = "".join(
        f"(allow process-exec (literal {literal}))"
        for literal in (
            _sandbox_path_literal(path, "native sandbox executable")
            for path in sorted(process_paths, key=str)
        )
    )
    return (
        "(version 1)(allow default)(deny network*)"
        "(deny file-read*)"
        "(deny file-write*)"
        + read_ancestor_rules
        + read_root_rules
        + read_file_rules
        + read_only_rules
        + read_only_file_rules
        + "(allow file-write* (literal \"/dev/null\"))"
        + writable_rules
        + "(deny process-fork)(deny process-exec*)"
        + process_exec_rules
    )


def _run_sandboxed_native_tool(
    runtime: _NativeRuntimeBinding,
    arguments: list[str],
    *,
    containment_root_path: Path,
    scratch_root_path: Path,
    writable_root_paths: tuple[Path, ...] = (),
    read_only_root_paths: tuple[Path, ...] = (),
    read_only_file_paths: tuple[Path, ...] = (),
    input_bytes: bytes | None,
    timeout_seconds: int,
    environment_updates: dict[str, str] | None = None,
) -> object:
    _require_fd_capacity(
        SUBPROCESS_FD_BUDGET,
        f"{runtime.name} sandboxed subprocess",
    )
    containment_root = _open_directory_path(
        containment_root_path,
        f"private {runtime.name} containment root",
    )
    writable_roots: list[_HeldDirectoryPath] = []
    sandbox_exec: _HeldFile | None = None
    env_exec: _HeldFile | None = None
    try:
        containment_state = os.fstat(containment_root.descriptors[-1])
        if (
            stat.S_IMODE(containment_state.st_mode) != 0o700
            or (
                hasattr(os, "geteuid")
                and containment_state.st_uid != os.geteuid()
            )
        ):
            raise SourceExtractionError(
                f"private {runtime.name} containment root is not private"
            )
        runtime_snapshot_root = _absolute_path(
            runtime.snapshot_root,
            f"private {runtime.name} runtime snapshot root",
        )
        if (
            not _path_is_within(runtime.command_path, containment_root.path)
            or not _path_is_within(
                runtime_snapshot_root,
                containment_root.path,
            )
        ):
            raise SourceExtractionError(
                f"private {runtime.name} runtime escapes its containment root"
            )

        planned_writable_paths = (scratch_root_path, *writable_root_paths)
        if len(set(planned_writable_paths)) != len(planned_writable_paths):
            raise SourceExtractionError("native sandbox writable roots overlap")
        for raw_path in planned_writable_paths:
            held = _open_directory_path(
                raw_path,
                f"private {runtime.name} writable root",
            )
            writable_roots.append(held)
            state = os.fstat(held.descriptors[-1])
            if (
                stat.S_IMODE(state.st_mode) != 0o700
                or (hasattr(os, "geteuid") and state.st_uid != os.geteuid())
                or held.path == containment_root.path
                or not _path_is_within(held.path, containment_root.path)
            ):
                raise SourceExtractionError(
                    f"private {runtime.name} writable root is not isolated"
                )
        for index, left in enumerate(writable_roots):
            for right in writable_roots[index + 1 :]:
                if _path_is_within(left.path, right.path) or _path_is_within(
                    right.path,
                    left.path,
                ):
                    raise SourceExtractionError(
                        "native sandbox writable roots overlap"
                    )

        normalized_read_only_roots = tuple(
            _absolute_path(path, "native sandbox read-only root")
            for path in read_only_root_paths
        )
        normalized_read_only_files = tuple(
            _absolute_path(path, "native sandbox read-only file")
            for path in read_only_file_paths
        )
        for writable in writable_roots:
            if _path_is_within(runtime.command_path, writable.path):
                raise SourceExtractionError(
                    "private native executable overlaps a writable root"
                )
            if any(
                _path_is_within(writable.path, root)
                or _path_is_within(root, writable.path)
                for root in normalized_read_only_roots
            ) or any(
                _path_is_within(path, writable.path)
                for path in normalized_read_only_files
            ):
                raise SourceExtractionError(
                    "native sandbox read-only and writable roots overlap"
                )

        sandbox_exec = _bind_sandbox_exec()
        env_exec = _bind_native_env_exec()
        profile = _native_tool_sandbox_profile(
            runtime.command_path,
            writable_roots=tuple(root.path for root in writable_roots),
            read_only_roots=normalized_read_only_roots,
            read_only_files=normalized_read_only_files,
            launcher_paths=(env_exec.path,),
        )
        allowed_environment_updates = {"TESSDATA_PREFIX", "OMP_THREAD_LIMIT"}
        if environment_updates and not set(environment_updates).issubset(
            allowed_environment_updates
        ):
            raise SourceExtractionError(
                "native sandbox environment update is not allowlisted"
            )
        environment = runtime.environment()
        if environment_updates:
            environment.update(environment_updates)
        scratch_value = str(writable_roots[0].path)
        environment.update(
            {
                "TMPDIR": scratch_value,
                "TMP": scratch_value,
                "TEMP": scratch_value,
                "HOME": scratch_value,
            }
        )
        command = [
            str(sandbox_exec.path),
            "-p",
            profile,
            str(env_exec.path),
            "-i",
            *(f"{name}={value}" for name, value in sorted(environment.items())),
            str(runtime.command_path),
            *arguments,
        ]
        runtime.revalidate()
        containment_root.revalidate()
        for writable in writable_roots:
            writable.revalidate_mutable_leaf()
        sandbox_exec.revalidate()
        env_exec.revalidate()
        try:
            kwargs: dict[str, object] = {
                "check": False,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "timeout": timeout_seconds,
                "env": environment,
                "cwd": scratch_value,
            }
            if input_bytes is None:
                kwargs["stdin"] = subprocess.DEVNULL
            else:
                kwargs["input"] = input_bytes
            return subprocess.run(command, **kwargs)
        finally:
            env_exec.revalidate()
            sandbox_exec.revalidate()
            for writable in reversed(writable_roots):
                writable.revalidate_mutable_leaf()
            containment_root.revalidate()
            runtime.revalidate()
    finally:
        if env_exec is not None:
            env_exec.close()
        if sandbox_exec is not None:
            sandbox_exec.close()
        for writable in reversed(writable_roots):
            writable.close()
        containment_root.close()


def _run_poppler(
    command: list[str],
    *,
    input_bytes: bytes,
    timeout_seconds: int = 300,
    _snapshot_root: Path | None = None,
    _containment_root: Path | None = None,
    _scratch_root: Path | None = None,
    _output_root: Path | None = None,
) -> bytes:
    if not command or command[0] not in {"pdftotext", "pdftoppm"}:
        raise SourceExtractionError("Poppler command is not allowlisted")
    temporary: tempfile.TemporaryDirectory[str] | None = None
    native_runtime: _NativeRuntimeBinding | None = None
    try:
        if _snapshot_root is None:
            if any(
                value is not None
                for value in (_containment_root, _scratch_root, _output_root)
            ):
                raise SourceExtractionError(
                    "Poppler private directory plan is incomplete"
                )
            temporary = tempfile.TemporaryDirectory(
                prefix=f"kg-cloud-v2-{command[0]}-runtime-"
            )
            private_root = Path(temporary.name)
            os.chmod(private_root, 0o700)
            directories = _prepare_private_subdirectories(
                private_root,
                ("native-runtime", "scratch"),
                f"private {command[0]} operation root",
            )
            snapshot_root = directories["native-runtime"]
            containment_root = private_root
            scratch_root = directories["scratch"]
            output_root = None
        else:
            if _containment_root is None or _scratch_root is None:
                raise SourceExtractionError(
                    "Poppler private directory plan is incomplete"
                )
            snapshot_root = _snapshot_root
            containment_root = _containment_root
            scratch_root = _scratch_root
            output_root = _output_root

        writable_output_roots: tuple[Path, ...] = ()
        sandbox_arguments = list(command[1:])
        if output_root is not None:
            if command[0] != "pdftoppm" or len(command) < 2:
                raise SourceExtractionError("Poppler output root is not approved")
            canonical_output = _absolute_path(
                output_root,
                "Poppler output root",
            )
            output_prefix = _absolute_path(
                command[-1],
                "Poppler output prefix",
            )
            if (
                output_prefix.parent != canonical_output
                or output_prefix.name != "page"
            ):
                raise SourceExtractionError("Poppler output prefix is not approved")
            writable_output_roots = (canonical_output,)
            sandbox_arguments[-1] = str(output_prefix)

        native_runtime = _bind_native_runtime(
            command[0],
            snapshot_root,
            expected_sha256=EXPECTED_POPPLER_EXECUTABLE_SHA256[command[0]],
        )
        native_runtime.revalidate()
        result = _run_sandboxed_native_tool(
            native_runtime,
            sandbox_arguments,
            containment_root_path=containment_root,
            scratch_root_path=scratch_root,
            writable_root_paths=writable_output_roots,
            read_only_root_paths=(snapshot_root, POPPLER_DATA_ROOT),
            input_bytes=input_bytes,
            timeout_seconds=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceExtractionError("Poppler extraction failed") from exc
    finally:
        try:
            if native_runtime is not None:
                native_runtime.revalidate()
        finally:
            if native_runtime is not None:
                native_runtime.close()
            if temporary is not None:
                temporary.cleanup()
    if result.returncode != 0:
        raise SourceExtractionError("Poppler rejected the PDF")
    return result.stdout


def validate_ocr_runtime(tessdata_dir: str | Path) -> dict[str, object]:
    with _bound_ocr_runtime(tessdata_dir) as runtime:
        runtime.revalidate()
        return _ocr_runtime_identity()


def _ocr_image(
    page: _HeldFile,
    runtime: _OCRRuntimeBinding,
    containment_root: Path,
    scratch_root: Path,
) -> str:
    try:
        runtime.revalidate()
        page.revalidate()
        try:
            result = _run_sandboxed_native_tool(
                runtime.native_runtime,
                [
                    str(page.path),
                    "stdout",
                    "-l",
                    "chi_sim+eng",
                    "--psm",
                    str(OCR_PSM),
                ],
                containment_root_path=containment_root,
                scratch_root_path=scratch_root,
                read_only_root_paths=(
                    runtime.snapshot_root,
                ),
                read_only_file_paths=(page.path,),
                input_bytes=None,
                timeout_seconds=120,
                environment_updates={
                    "TESSDATA_PREFIX": str(runtime.execution_tessdata.root.path),
                    "OMP_THREAD_LIMIT": "1",
                },
            )
        finally:
            page.revalidate()
            runtime.revalidate()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceExtractionError("Tesseract OCR failed") from exc
    if result.returncode != 0:
        raise SourceExtractionError("Tesseract rejected a rendered page")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceExtractionError("Tesseract returned invalid UTF-8") from exc


_RENDERED_PAGE_PATTERN = re.compile(r"^page-([0-9]+)\.jpg$")


def _bind_rendered_pages(root_path: Path) -> tuple[_PrivateFileSet, tuple[str, ...]]:
    root = _open_directory_path(root_path, "rendered OCR page root")
    files: dict[str, _HeldFile] = {}
    try:
        leaf = os.fstat(root.descriptors[-1])
        if (
            stat.S_IMODE(leaf.st_mode) != 0o700
            or (hasattr(os, "geteuid") and leaf.st_uid != os.geteuid())
        ):
            raise SourceExtractionError("rendered OCR page root is not private")
        names = os.listdir(root.descriptors[-1])
        if len({name.casefold() for name in names}) != len(names):
            raise SourceExtractionError("PDF rendering produced case-aliased pages")
        if not names:
            raise SourceExtractionError("PDF rendering produced no OCR pages")
        # pdftoppm pads every suffix to the decimal width of the final page.
        expected_width = len(str(len(names)))
        numbered: list[tuple[int, str, str]] = []
        seen_numbers: set[int] = set()
        for name in names:
            match = _RENDERED_PAGE_PATTERN.fullmatch(name)
            if match is None:
                raise SourceExtractionError(
                    "PDF rendering produced a noncanonical OCR page entry"
                )
            token = match.group(1)
            significant = token.lstrip("0")
            if not significant:
                raise SourceExtractionError(
                    "PDF rendering produced a noncanonical OCR page entry"
                )
            if len(significant) > expected_width:
                raise SourceExtractionError(
                    "PDF rendering produced noncanonical page padding"
                )
            number = int(significant)
            if number in seen_numbers:
                raise SourceExtractionError(
                    "PDF rendering produced a duplicate page number"
                )
            seen_numbers.add(number)
            numbered.append((number, token, name))
        numbered.sort(key=lambda item: item[0])
        if [number for number, _token, _name in numbered] != list(
            range(1, len(numbered) + 1)
        ):
            raise SourceExtractionError("PDF rendering produced a noncontiguous page set")
        if any(
            token != str(number).zfill(expected_width)
            for number, token, _name in numbered
        ):
            raise SourceExtractionError(
                "PDF rendering produced noncanonical page padding"
            )
        for _number, _token, name in numbered:
            held = _open_file_under_directory(
                root,
                name,
                f"rendered OCR page {name}",
                owns_parent=False,
            )
            files[name] = held
            if held.state.size == 0:
                raise SourceExtractionError("PDF rendering produced an empty OCR page")
        result = _PrivateFileSet(
            root=root,
            files=files,
            field="rendered OCR page set",
        )
        result.revalidate()
        return result, tuple(name for _number, _token, name in numbered)
    except BaseException:
        for held in files.values():
            held.close()
        root.close()
        raise


@contextlib.contextmanager
def _bound_approved_page_snapshots(
    rendered_root: Path,
    approved_root: Path,
    workers: int,
) -> Iterator[tuple[_HeldFile, ...]]:
    rendered, names = _bind_rendered_pages(rendered_root)
    approved: _PrivateFileSet | None = None
    try:
        payloads = {
            name: (_read_held_file_bytes(rendered.files[name]), 0o400)
            for name in names
        }
        rendered.revalidate()
    finally:
        rendered.close()
    try:
        _require_fd_capacity(
            len(names) + 1 + workers * SUBPROCESS_FD_BUDGET,
            "approved OCR page snapshots",
        )
        approved = _materialize_private_file_set(
            approved_root,
            payloads,
            "approved OCR page snapshot",
        )
        approved.revalidate()
        yield tuple(approved.files[name] for name in names)
    finally:
        if approved is not None:
            try:
                approved.revalidate()
            finally:
                approved.close()


def _ocr_pdf(
    payload: bytes,
    tessdata_dir: str | Path,
    workers: int,
) -> list[str]:
    if workers < 1 or workers > 4:
        raise SourceExtractionError("OCR worker count must be between 1 and 4")
    with tempfile.TemporaryDirectory(prefix="kg-cloud-v2-ocr-") as temporary:
        private_root = Path(temporary)
        os.chmod(private_root, 0o700)
        directories = _prepare_private_subdirectories(
            private_root,
            (
                "ocr-runtime",
                "poppler-runtime",
                "poppler-scratch",
                "rendered-pages",
                "approved-pages",
                "tesseract-scratch",
            ),
            "private OCR operation root",
        )
        with _bound_ocr_runtime(
            tessdata_dir,
            _snapshot_root=directories["ocr-runtime"],
        ) as runtime:
            runtime.revalidate()
            try:
                prefix = directories["rendered-pages"] / "page"
                _run_poppler(
                    [
                        "pdftoppm",
                        "-r",
                        str(OCR_RENDER_DPI),
                        "-jpeg",
                        "-jpegopt",
                        "quality=92",
                        "-",
                        str(prefix),
                    ],
                    input_bytes=payload,
                    timeout_seconds=900,
                    _snapshot_root=directories["poppler-runtime"],
                    _containment_root=private_root,
                    _scratch_root=directories["poppler-scratch"],
                    _output_root=directories["rendered-pages"],
                )
                with _bound_approved_page_snapshots(
                    directories["rendered-pages"],
                    directories["approved-pages"],
                    workers,
                ) as pages:
                    scratch_names = tuple(
                        f"page-{index}"
                        for index in range(1, len(pages) + 1)
                    )
                    page_scratch = _prepare_private_subdirectories(
                        directories["tesseract-scratch"],
                        scratch_names,
                        "private Tesseract scratch root",
                    )
                    jobs = tuple(
                        (page, page_scratch[name])
                        for page, name in zip(pages, scratch_names, strict=True)
                    )
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        page_texts = list(
                            executor.map(
                                lambda job: _ocr_image(
                                    job[0],
                                    runtime,
                                    private_root,
                                    job[1],
                                ),
                                jobs,
                            )
                        )
            finally:
                runtime.revalidate()
        return page_texts


def _text_layer_is_sufficient(page_texts: list[str]) -> bool:
    if not page_texts:
        return False
    cleaned = [_clean_text(page) for page in page_texts]
    nonempty_pages = sum(bool(page) for page in cleaned)
    character_count = sum(len(page) for page in cleaned)
    minimum_pages = max(1, (len(page_texts) + 3) // 4)
    minimum_characters = max(200, len(page_texts) * 50)
    return nonempty_pages >= minimum_pages and character_count >= minimum_characters


def extract_pdf(
    payload: bytes,
    relative_path: str,
    *,
    ocr_tessdata_dir: str | Path | None = None,
    ocr_workers: int = 4,
) -> ExtractedDocument:
    raw = _run_poppler(
        ["pdftotext", "-enc", "UTF-8", "-layout", "-", "-"],
        input_bytes=payload,
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceExtractionError("pdftotext returned invalid UTF-8") from exc
    page_texts = text.split("\f")
    if page_texts and not page_texts[-1].strip():
        page_texts.pop()
    units: list[ExtractedUnit] = []
    text_layer_sufficient = _text_layer_is_sufficient(page_texts)
    if text_layer_sufficient:
        for page_number, page_text in enumerate(page_texts, 1):
            paragraphs = [
                ("pdf", part)
                for part in re.split(r"\n\s*\n", page_text)
                if _clean_text(part)
            ]
            units.extend(
                _pack_paragraphs(
                    paragraphs,
                    page=page_number,
                    content_type="pdf_text",
                    ordinal_base=len(units),
                )
            )
    extractor = EXTRACTOR_VERSION + ":poppler-layout"
    if not text_layer_sufficient:
        if ocr_tessdata_dir is None:
            raise SourceExtractionError("PDF has no text layer and requires the approved OCR runtime")
        page_texts = _ocr_pdf(
            payload,
            ocr_tessdata_dir,
            ocr_workers,
        )
        for page_number, page_text in enumerate(page_texts, 1):
            paragraphs = [
                ("pdf_ocr", part)
                for part in re.split(r"\n\s*\n", page_text)
                if _clean_text(part)
            ]
            units.extend(
                _pack_paragraphs(
                    paragraphs,
                    page=page_number,
                    content_type="pdf_ocr_text",
                    ordinal_base=len(units),
                )
            )
        if not units:
            raise SourceExtractionError("approved OCR extraction produced no text")
        extractor = (
            EXTRACTOR_VERSION
            + ":tesseract-5.5.2-chi_sim+eng-poppler-26.08.0-r170-psm6"
        )
    return _document(
        relative_path,
        tuple(units),
        page_count=max(len(page_texts), 1),
        extractor=extractor,
    )


def _split_long_paragraph(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    remaining = text
    sentence_pattern = re.compile(r"(?<=[。！？；.!?;])")
    sentences = [part for part in sentence_pattern.split(remaining) if part]
    current = ""
    for sentence in sentences:
        if len(sentence) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(sentence[index : index + limit] for index in range(0, len(sentence), limit))
        elif current and len(current) + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        pieces.append(current)
    return pieces


def _pack_paragraphs(
    paragraphs: list[tuple[str, str]],
    *,
    page: int,
    content_type: str,
    ordinal_base: int = 0,
    limit: int = DEFAULT_CHUNK_CHARS,
) -> tuple[ExtractedUnit, ...]:
    packed: list[ExtractedUnit] = []
    current: list[str] = []
    current_member: str | None = None

    def flush() -> None:
        nonlocal current, current_member
        if not current:
            return
        packed.append(
            ExtractedUnit(
                ordinal=ordinal_base + len(packed),
                text="\n".join(current),
                page_start=page,
                page_end=page,
                section_title=current_member,
                content_type=content_type,
            )
        )
        current = []
        current_member = None

    for member, raw_text in paragraphs:
        for text in _split_long_paragraph(_clean_text(raw_text), limit):
            projected = len(text) + sum(len(value) for value in current) + len(current)
            if current and projected > limit:
                flush()
            current.append(text)
            current_member = member
    flush()
    return tuple(packed)


def _document(
    relative_path: str,
    units: tuple[ExtractedUnit, ...],
    *,
    page_count: int,
    extractor: str,
) -> ExtractedDocument:
    digest = hashlib.sha256()
    for unit in units:
        digest.update(unit.text.encode("utf-8"))
        digest.update(b"\x00")
    return ExtractedDocument(
        relative_path=relative_path,
        units=units,
        page_count=page_count,
        extractor=extractor,
        text_sha256=digest.hexdigest(),
    )


def extract_source(
    payload: bytes,
    relative_path: str,
    *,
    ocr_tessdata_dir: str | Path | None = None,
    ocr_workers: int = 4,
) -> ExtractedDocument:
    suffix = PurePosixPath(relative_path).suffix.lower()
    if suffix == ".docx":
        return extract_docx(payload, relative_path)
    if suffix == ".pdf":
        return extract_pdf(
            payload,
            relative_path,
            ocr_tessdata_dir=ocr_tessdata_dir,
            ocr_workers=ocr_workers,
        )
    raise SourceExtractionError("unsupported approved source type")
