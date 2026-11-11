"""Command line interface for docs-link-check."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import HttpChecker, check_docs


class _UrllibChecker(HttpChecker):
    """HEAD-then-GET checker using urllib with a 10s timeout."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self.opener = urllib.request.build_opener(_NoNonHttpRedirectHandler())

    def _request(self, url: str, method: str) -> int:
        req = urllib.request.Request(url, method=method)  # noqa: S310
        try:
            resp = self.opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            raise
        return resp.status  # type: ignore[no-any-return]

    def status(self, url: str) -> int:
        head_status = self._request(url, "HEAD")
        if 200 <= head_status < 400:
            return head_status
        # Fall back to GET for any non-2xx HEAD result (including 404/410)
        return self._request(url, "GET")


class _NoNonHttpRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects to non-http(s) schemes."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        scheme = urlparse(newurl).scheme
        if scheme not in ("http", "https"):
            raise urllib.error.URLError(f"redirect to disallowed scheme {scheme!r}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs-link-check",
        description="Check links in Markdown documentation.",
    )
    parser.add_argument("root", help="Root directory containing Markdown files")
    parser.add_argument(
        "--external",
        action="store_true",
        help="Check external http/https URLs (requires network)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat 'unreachable' external links as failures",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"docs-link-check: {args.root} is not a directory", file=sys.stderr)
        return 2

    checker: HttpChecker | None = _UrllibChecker() if args.external else None
    try:
        report = check_docs(root, checker=checker)
    except Exception as exc:
        print(f"docs-link-check: {exc}", file=sys.stderr)
        return 2

    for problem in report.problems:
        if not args.strict and problem.code == "unreachable":
            continue
        message = f"{problem.file}:{problem.line}:{problem.column}: {problem.code} {problem.target}"
        print(message.rstrip())

    fatal = any(p.code != "unreachable" if not args.strict else True for p in report.problems)
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
