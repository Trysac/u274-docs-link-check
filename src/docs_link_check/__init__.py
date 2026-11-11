"""Check links in Markdown documentation.

Public API:
- :class:`Link` and :class:`Problem` frozen dataclasses
- :func:`extract_links`
- :func:`heading_anchors`
- :class:`HttpChecker` protocol
- :func:`check_docs`
- :class:`LinkCheckError`
"""

from __future__ import annotations

import logging
import posixpath
import re
import unicodedata
import urllib.parse
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

__all__ = [
    "CheckReport",
    "HttpChecker",
    "Link",
    "LinkCheckError",
    "Problem",
    "check_docs",
    "extract_links",
    "heading_anchors",
]

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_MAX_FILE_SIZE = 5_242_880  # 5 MiB


@dataclass(frozen=True, slots=True)
class Link:
    """A link extracted from Markdown.

    ``line`` and ``column`` are 1-based and point to the ``[``, ``!`` or
    ``<`` character that starts the link.
    """

    target: str
    line: int
    column: int
    kind: Literal["link", "image", "reference", "autolink"]


@dataclass(frozen=True, slots=True)
class Problem:
    """A single problem found while checking documentation."""

    file: str
    line: int
    column: int
    code: Literal[
        "missing_file",
        "missing_anchor",
        "outside_root",
        "broken_external",
        "unreachable",
        "file_too_large",
    ]
    target: str


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Result of :func:`check_docs`."""

    problems: list[Problem]
    files: int
    links: int
    skipped_external: int


class LinkCheckError(Exception):
    """Raised when the overall check cannot proceed."""

    def __init__(
        self,
        code: Literal["too_many_files", "too_many_urls", "invalid_root"],
        message: str = "",
    ) -> None:
        self.code = code
        super().__init__(message or code)


class HttpChecker(Protocol):
    """Protocol for checking external URLs.

    ``status`` must return an HTTP-like status code (200..599) or raise an
    exception on network failure.
    """

    def status(self, url: str) -> int: ...


# ---------------------------------------------------------------------------
# Markdown extraction
# ---------------------------------------------------------------------------


def _fence_open(line: str) -> tuple[str, int] | None:
    """Return ``(fence_char, fence_len)`` if ``line`` opens a fenced code block."""
    stripped = line.lstrip(" ")
    indent = len(line) - len(stripped)
    if indent > 3:
        return None
    if len(stripped) < 3:
        return None
    ch = stripped[0]
    if ch not in ("`", "~"):
        return None
    run = 0
    while run < len(stripped) and stripped[run] == ch:
        run += 1
    if run < 3:
        return None
    return ch, run


def _fence_close(line: str, char: str, min_len: int) -> bool:
    """True if ``line`` closes a fence opened with ``char`` repeated ``min_len`` times."""
    stripped = line.lstrip(" ")
    indent = len(line) - len(stripped)
    if indent > 3:
        return False
    run = 0
    while run < len(stripped) and stripped[run] == char:
        run += 1
    if run < min_len:
        return False
    return not stripped[run:].strip()


def _looks_like_autolink(line: str, i: int) -> bool:
    """True if line[i] starts an autolink ``<scheme://...>``."""
    if line[i] != "<":
        return False
    j = i + 1
    # scheme
    if j >= len(line) or not line[j].isalpha():
        return False
    j += 1
    while j < len(line) and (line[j].isalnum() or line[j] in "+.-"):
        j += 1
    return j + 2 < len(line) and line[j : j + 3] == "://"


def _skip_title(line: str, j: int) -> int | None:
    """Skip an optional title after a link target; return index after title."""
    if j >= len(line) or line[j] not in ('"', "'", "("):
        return None
    if line[j] == "(":
        depth = 1
        j += 1
        while j < len(line):
            if line[j] == "\\":
                j += 2
                continue
            if line[j] == "(":
                depth += 1
            elif line[j] == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
    else:
        quote = line[j]
        j += 1
        while j < len(line):
            if line[j] == "\\":
                j += 2
                continue
            if line[j] == quote:
                j += 1
                break
            j += 1
    return j


def _parse_target(line: str, open_paren: int) -> tuple[str, int] | None:
    """Parse a link target starting at ``open_paren`` (index of '(').

    Returns ``(target, end_index)`` where end_index is just past the closing
    ``)``, or ``None`` on failure.
    """
    if line[open_paren] != "(":
        return None
    i = open_paren + 1
    if i < len(line) and line[i] == "<":
        # Angle-bracket target: <target>
        i += 1
        target_start = i
        while i < len(line) and line[i] != ">":
            if line[i] == "\\":
                i += 2
                continue
            i += 1
        if i >= len(line):
            return None
        target = line[target_start:i]
        i += 1  # skip '>'
        # Optional whitespace, title, whitespace, then ')'
        j = i
        while j < len(line) and line[j].isspace():
            j += 1
        if j < len(line) and line[j] in ('"', "'", "("):
            after_title = _skip_title(line, j)
            if after_title is None:
                return None
            j = after_title
            while j < len(line) and line[j].isspace():
                j += 1
        if j < len(line) and line[j] == ")":
            return target, j + 1
        return None

    # Normal target: balanced parentheses, optional title before final ')'
    target_start = i
    depth = 1
    while i < len(line):
        if depth == 1 and line[i].isspace():
            # Look ahead for a title
            j = i
            while j < len(line) and line[j].isspace():
                j += 1
            if j < len(line) and line[j] in ('"', "'", "("):
                target = line[target_start:i]
                skip_i = _skip_title(line, j)
                if skip_i is None:
                    return None
                j = skip_i
                while j < len(line) and line[j].isspace():
                    j += 1
                if j < len(line) and line[j] == ")":
                    return target, j + 1
                return None
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "(":
            depth += 1
        elif line[i] == ")":
            depth -= 1
            if depth == 0:
                target = line[target_start:i]
                return target, i + 1
        i += 1
    return None


def _find_label_end(line: str, start: int) -> int | None:
    """Return index just past the closing ']' of a link label starting at ``start``."""
    depth = 1
    i = start + 1
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "[":
            depth += 1
        elif line[i] == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _parse_image_at(line: str, i: int, line_no: int, result: list[Link]) -> int | None:
    """Parse an image starting at ``i`` (index of '!').

    Returns index just past the image or ``None``.
    """
    if line[i] != "!" or i + 1 >= len(line) or line[i + 1] != "[":
        return None
    label_end = _find_label_end(line, i + 1)
    if label_end is None or label_end >= len(line) or line[label_end] != "(":
        return None
    parsed = _parse_target(line, label_end)
    if parsed is None:
        return None
    target, end = parsed
    result.append(Link(target=target, line=line_no, column=i + 1, kind="image"))
    return end


def _parse_link_at(line: str, i: int, line_no: int, result: list[Link]) -> int | None:
    """Parse a normal link starting at ``i`` (index of '[').

    Images nested inside the label are extracted as well. Returns index just
    past the link or ``None``.
    """
    if line[i] != "[":
        return None
    label_end = _find_label_end(line, i)
    if label_end is None or label_end >= len(line) or line[label_end] != "(":
        return None

    # While scanning the label, extract nested images.
    j = i + 1
    while j < label_end:
        if line[j] == "!" and j + 1 < label_end and line[j + 1] == "[":
            _parse_image_at(line, j, line_no, result)
        j += 1

    parsed = _parse_target(line, label_end)
    if parsed is None:
        return None
    target, end = parsed
    result.append(Link(target=target, line=line_no, column=i + 1, kind="link"))
    return end


def _parse_autolink_at(line: str, i: int, line_no: int, result: list[Link]) -> int | None:
    """Parse an autolink ``<scheme://...>``."""
    if not _looks_like_autolink(line, i):
        return None
    end = line.find(">", i + 1)
    if end == -1:
        return None
    target = line[i + 1 : end]
    result.append(Link(target=target, line=line_no, column=i + 1, kind="autolink"))
    return end + 1


def _try_reference_definition(line: str, line_no: int) -> Link | None:
    """Try to parse ``[label]: target`` at line start (up to 3 leading spaces)."""
    if not re.match(r"^ {0,3}\[", line):
        return None
    stripped = line.lstrip(" ")
    col = len(line) - len(stripped) + 1  # 1-based column of '['
    try:
        closing = stripped.index("]:")
    except ValueError:
        return None
    rest = stripped[closing + 2 :]
    # Skip optional spaces after colon
    i = 0
    while i < len(rest) and rest[i].isspace():
        i += 1
    if i >= len(rest):
        return None
    if rest[i] == "<":
        end_angle = rest.find(">", i + 1)
        if end_angle == -1:
            return None
        target = rest[i + 1 : end_angle]
        i = end_angle + 1
    else:
        # Target is the first whitespace-delimited token; may contain nested parens
        j = i
        depth = 0
        while j < len(rest):
            if rest[j] == "\\":
                j += 2
                continue
            if rest[j] == "(":
                depth += 1
            elif rest[j] == ")":
                depth -= 1
            elif rest[j].isspace() and depth == 0:
                break
            j += 1
        target = rest[i:j]
        i = j
    if not target:
        return None
    # After target, allow optional whitespace + title, then only whitespace
    while i < len(rest) and rest[i].isspace():
        i += 1
    if i < len(rest):
        return None  # unexpected trailing content
    return Link(target=target, line=line_no, column=col, kind="reference")


def _process_inline_line(line: str, line_no: int, result: list[Link]) -> None:
    """Extract inline links, images and autolinks from a single line."""
    i = 0
    in_code_span = False
    code_delim_len = 0
    while i < len(line):
        if in_code_span:
            if line[i] == "`":
                run = 0
                while i + run < len(line) and line[i + run] == "`":
                    run += 1
                if run == code_delim_len:
                    i += run
                    in_code_span = False
                    continue
            i += 1
            continue

        if line[i] == "`":
            run = 0
            while i + run < len(line) and line[i + run] == "`":
                run += 1
            in_code_span = True
            code_delim_len = run
            i += run
            continue

        if line[i] == "!" and i + 1 < len(line) and line[i + 1] == "[":
            end = _parse_image_at(line, i, line_no, result)
            if end is not None:
                i = end
                continue
        if line[i] == "[":
            end = _parse_link_at(line, i, line_no, result)
            if end is not None:
                i = end
                continue
        if line[i] == "<":
            end = _parse_autolink_at(line, i, line_no, result)
            if end is not None:
                i = end
                continue
        i += 1


def extract_links(markdown: str) -> list[Link]:
    """Extract inline links, images, reference definitions and autolinks.

    Fenced code blocks and inline code spans are skipped.
    """
    result: list[Link] = []
    lines = markdown.splitlines()
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line_no, line in enumerate(lines, start=1):
        if in_fence:
            if _fence_close(line, fence_char, fence_len):
                in_fence = False
            continue
        opened = _fence_open(line)
        if opened is not None:
            in_fence = True
            fence_char, fence_len = opened
            continue
        ref = _try_reference_definition(line, line_no)
        if ref is not None:
            result.append(ref)
            continue
        _process_inline_line(line, line_no, result)
    return result


# ---------------------------------------------------------------------------
# Heading anchors
# ---------------------------------------------------------------------------


def _clean_inline_markup(text: str) -> str:
    """Remove inline Markdown markup per the spec."""
    # Remove backticks (code spans) and asterisks (emphasis)
    text = text.replace("`", "").replace("*", "")
    # Replace link/image syntax [alt](target) or ![alt](target) with alt
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove remaining bracket characters
    text = text.replace("[", "").replace("]", "")
    return text


def _slugify(heading: str) -> str:
    cleaned = _clean_inline_markup(heading).lower()
    out_chars: list[str] = []
    for ch in cleaned:
        if ch in ("-", "_", " "):
            out_chars.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("M") or cat in ("Nd", "Nl"):
            out_chars.append(ch)
    slug = "".join(out_chars).replace(" ", "-")
    return slug


def heading_anchors(markdown: str) -> set[str]:
    """Return GitHub-style heading anchors for ATX headings in ``markdown``.

    Duplicate slugs are suffixed with ``-1``, ``-2``, ... per base slug in
    document order.
    """
    anchors: set[str] = set()
    base_counts: dict[str, int] = {}
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in markdown.splitlines():
        if in_fence:
            if _fence_close(line, fence_char, fence_len):
                in_fence = False
            continue
        opened = _fence_open(line)
        if opened is not None:
            in_fence = True
            fence_char, fence_len = opened
            continue
        m = re.match(r"^ {0,3}(#{1,6})(?:[ \t]+(.*)|$)", line)
        if not m:
            continue
        heading = (m.group(2) or "").strip()
        if not heading:
            continue
        base_slug = _slugify(heading)
        next_num = base_counts.get(base_slug, 1)
        final_slug = base_slug
        if final_slug in anchors:
            while True:
                final_slug = f"{base_slug}-{next_num}"
                next_num += 1
                if final_slug not in anchors:
                    break
            base_counts[base_slug] = next_num
        else:
            base_counts[base_slug] = 1
        anchors.add(final_slug)
        if final_slug not in base_counts:
            base_counts[final_slug] = 1
    return anchors


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def _path_exists_exact(root: Path, rel_posix: str) -> bool:
    """Check that every path segment exists with exact case."""
    current = root
    parts = PurePosixPath(rel_posix).parts
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            return False
        try:
            entries = list(current.iterdir())
        except OSError:
            return False
        found = False
        for entry in entries:
            if entry.name == part:
                current = entry
                found = True
                break
        if not found:
            return False
    return True


def _decode_path_once(path: str) -> str:
    return urllib.parse.unquote(path)


# ---------------------------------------------------------------------------
# check_docs
# ---------------------------------------------------------------------------


def _relative_target_posix(file_rel_posix: str, decoded_path: str) -> str | None:
    """Return target path relative to root, or None if outside."""
    file_parts = PurePosixPath(file_rel_posix).parts
    parent = PurePosixPath(*file_parts[:-1]) if len(file_parts) > 1 else PurePosixPath(".")
    combined = parent.joinpath(decoded_path)
    norm = posixpath.normpath(str(combined))
    if norm.startswith("../") or norm == "..":
        return None
    return norm


def check_docs(
    root: Path,
    *,
    checker: HttpChecker | None = None,
    include: Sequence[str] = ("**/*.md",),
    max_files: int = 10_000,
    max_urls: int = 1000,
    workers: int = 4,
) -> CheckReport:
    """Check all Markdown files under ``root``.

    Raises:
        LinkCheckError: if ``root`` is not a directory, if more than
            ``max_files`` files are matched, or if more than ``max_urls``
            distinct external URLs are found.
    """
    if not root.is_dir():
        raise LinkCheckError("invalid_root", f"{root} is not a directory")

    # 1. Collect files
    file_paths: set[Path] = set()
    for pattern in include:
        for p in root.glob(pattern):
            if p.is_file():
                file_paths.add(p)
    files = sorted(file_paths, key=lambda p: p.relative_to(root).as_posix())
    if len(files) > max_files:
        raise LinkCheckError("too_many_files", f"{len(files)} files exceed max_files={max_files}")

    problems: list[Problem] = []
    total_links = 0
    external_occurrences: list[tuple[str, int, int, str]] = []
    anchors_cache: dict[str, set[str]] = {}

    def get_anchors(rel_file: str, text: str) -> set[str]:
        if rel_file not in anchors_cache:
            anchors_cache[rel_file] = heading_anchors(text)
        return anchors_cache[rel_file]

    for file_path in files:
        rel = file_path.relative_to(root).as_posix()
        try:
            size = file_path.stat().st_size
        except OSError:
            continue
        if size > _MAX_FILE_SIZE:
            problems.append(Problem(file=rel, line=1, column=1, code="file_too_large", target=""))
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        links = extract_links(content)
        total_links += len(links)
        for link in links:
            target = link.target
            if target.startswith(("http://", "https://")):
                external_occurrences.append((rel, link.line, link.column, target))
                continue
            if target.startswith("#"):
                fragment = target[1:]
                if not fragment:
                    continue
                anchors = get_anchors(rel, content)
                if fragment not in anchors:
                    problems.append(
                        Problem(
                            file=rel,
                            line=link.line,
                            column=link.column,
                            code="missing_anchor",
                            target=target,
                        )
                    )
                continue
            if ":" in target:
                scheme = target.split(":", 1)[0]
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9+.\-]*", scheme):
                    # Non-http(s) schemes such as mailto:, tel: and ftp: are ignored.
                    continue
            path_part, _sep, fragment = target.partition("#")
            decoded_path = _decode_path_once(path_part)
            if not decoded_path:
                continue
            rel_target = _relative_target_posix(rel, decoded_path)
            if rel_target is None:
                problems.append(
                    Problem(
                        file=rel,
                        line=link.line,
                        column=link.column,
                        code="outside_root",
                        target=target,
                    )
                )
                continue
            if not _path_exists_exact(root, rel_target):
                problems.append(
                    Problem(
                        file=rel,
                        line=link.line,
                        column=link.column,
                        code="missing_file",
                        target=target,
                    )
                )
                continue
            if fragment:
                target_path = root / rel_target
                if target_path.suffix.lower() == ".md":
                    try:
                        target_content = target_path.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue
                    target_anchors = get_anchors(rel_target, target_content)
                    if fragment not in target_anchors:
                        problems.append(
                            Problem(
                                file=rel,
                                line=link.line,
                                column=link.column,
                                code="missing_anchor",
                                target=target,
                            )
                        )

    # 2. External URL checking
    distinct_urls = {url for _, _, _, url in external_occurrences}
    if len(distinct_urls) > max_urls:
        raise LinkCheckError(
            "too_many_urls", f"{len(distinct_urls)} distinct URLs exceed max_urls={max_urls}"
        )

    if checker is not None and distinct_urls:
        results: dict[str, str | None] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(checker.status, url): url for url in distinct_urls}
            for future in as_completed(future_map):
                url = future_map[future]
                code: str | None
                try:
                    status = future.result()
                except Exception:
                    code = "unreachable"
                else:
                    if 200 <= status < 400:
                        code = None
                    elif status in (404, 410):
                        code = "broken_external"
                    else:
                        code = "unreachable"
                results[url] = code
        for rel, line, column, url in external_occurrences:
            code = results.get(url)
            if code is not None:
                problems.append(
                    Problem(file=rel, line=line, column=column, code=code, target=url)  # type: ignore[arg-type]
                )
        skipped_external = 0
    else:
        skipped_external = len(external_occurrences)

    problems.sort(key=lambda p: (p.file, p.line, p.column, p.target))
    return CheckReport(
        problems=problems,
        files=len(files),
        links=total_links,
        skipped_external=skipped_external,
    )
