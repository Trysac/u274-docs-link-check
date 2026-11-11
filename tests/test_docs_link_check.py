"""Tests for docs_link_check public API and CLI."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest

from docs_link_check import (
    Link,
    LinkCheckError,
    Problem,
    check_docs,
    extract_links,
    heading_anchors,
)
from docs_link_check.__main__ import _NoNonHttpRedirectHandler, _UrllibChecker, main


class FakeChecker:
    def __init__(self, responses: dict[str, int] | None = None, error_urls: set[str] | None = None):
        self.responses = responses or {}
        self.error_urls = error_urls or set()
        self.calls: list[str] = []

    def status(self, url: str) -> int:
        self.calls.append(url)
        if url in self.error_urls:
            raise TimeoutError(url)
        return self.responses.get(url, 200)


# ---------------------------------------------------------------------------
# extract_links
# ---------------------------------------------------------------------------


def test_extract_links_acceptance():
    md = "See [docs](guide.md#setup) and ![logo](img/logo.png).\n"
    links = extract_links(md)
    assert links == [
        Link(target="guide.md#setup", line=1, column=5, kind="link"),
        Link(target="img/logo.png", line=1, column=32, kind="image"),
    ]


def test_extract_links_skips_fenced_code_and_code_spans():
    md = """```
[ignored](target.md)
```
`[also](ignored.md)`

~~~
![img](img.png)
~~~
"""
    assert extract_links(md) == []


def test_extract_links_reference_definition_and_autolink():
    md = """[guide]: docs/a.md
See <https://example.com/> and [page](https://example.com).
"""
    links = extract_links(md)
    assert len(links) == 3
    assert any(
        link.kind == "reference" and link.target == "docs/a.md" and link.line == 1 for link in links
    )
    assert any(
        link.kind == "autolink" and link.target == "https://example.com/" and link.line == 2
        for link in links
    )
    assert any(
        link.kind == "link" and link.target == "https://example.com" and link.line == 2
        for link in links
    )


def test_extract_links_link_with_title_and_angle_target():
    md = '[a](<docs/guide with spaces.md> "Title")'
    links = extract_links(md)
    assert links == [Link(target="docs/guide with spaces.md", line=1, column=1, kind="link")]


def test_extract_links_image_inside_link():
    md = "[![alt](img.png)](target.md)"
    links = extract_links(md)
    assert len(links) == 2
    image = next(link for link in links if link.kind == "image")
    link = next(link for link in links if link.kind == "link")
    assert image.target == "img.png"
    assert link.target == "target.md"


def test_extract_links_balanced_parentheses_in_target():
    md = "[a](docs/foo(bar).md)"
    assert extract_links(md)[0].target == "docs/foo(bar).md"


# ---------------------------------------------------------------------------
# heading_anchors
# ---------------------------------------------------------------------------


def test_heading_anchors_acceptance():
    md = "# Install & Run\n## API (v2)\n## API (v2)\n"
    assert heading_anchors(md) == {"install--run", "api-v2", "api-v2-1"}


def test_heading_anchors_duplicate_and_suffixed():
    md = "# a\n# a\n# a-1\n"
    assert heading_anchors(md) == {"a", "a-1", "a-1-1"}


def test_heading_anchors_inline_code_markup():
    md = "# `code` **bold** [text](url.md)\n"
    assert heading_anchors(md) == {"code-bold-text"}


def test_heading_anchors_skips_fenced_code_blocks():
    md = "# T\n```\n# not a heading\n```\n~~~\n# also not\n~~~\n"
    assert heading_anchors(md) == {"t"}


def test_heading_anchors_up_to_three_spaces_indented():
    assert heading_anchors("   # Indented\n") == {"indented"}
    assert heading_anchors("    # Not a heading\n") == set()


# ---------------------------------------------------------------------------
# check_docs
# ---------------------------------------------------------------------------


def test_check_docs_acceptance(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text(
        "Read [the guide](docs/a.md#usage), [gone](#missing) and [up](../outside.md).\n",
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("## Usage\n", encoding="utf-8")
    report = check_docs(root)
    assert report.problems == [
        Problem(
            file="README.md",
            line=1,
            column=36,
            code="missing_anchor",
            target="#missing",
        ),
        Problem(
            file="README.md",
            line=1,
            column=57,
            code="outside_root",
            target="../outside.md",
        ),
    ]
    assert report.files == 2
    assert report.links == 3
    assert report.skipped_external == 0


def test_check_docs_missing_file_case_sensitive(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text("[x](Docs/A.md)\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("content\n", encoding="utf-8")
    report = check_docs(root)
    assert len(report.problems) == 1
    assert report.problems[0].code == "missing_file"
    assert report.problems[0].target == "Docs/A.md"


def test_check_docs_reference_definition_and_autolink(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text(
        "[guide]: docs/a.md\nSee <https://example.com/>\n", encoding="utf-8"
    )
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("content\n", encoding="utf-8")
    report = check_docs(root)
    # no checker -> external skipped, no problems
    assert report.problems == []
    assert report.skipped_external == 1


def test_check_docs_external_with_fake_checker(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text(
        "[ok](https://example.com/ok) and [ok2](https://example.com/ok) "
        "[gone](https://example.com/gone) [slow](https://example.com/slow)\n",
        encoding="utf-8",
    )
    checker = FakeChecker(
        responses={
            "https://example.com/ok": 200,
            "https://example.com/gone": 404,
        },
        error_urls={"https://example.com/slow"},
    )
    report = check_docs(root, checker=checker, workers=1)
    # each URL requested once
    assert checker.calls.count("https://example.com/ok") == 1
    assert checker.calls.count("https://example.com/gone") == 1
    assert checker.calls.count("https://example.com/slow") == 1
    # problems: gone broken, slow unreachable; ok links no problems (two occurrences?)
    codes = {p.code for p in report.problems}
    assert codes == {"broken_external", "unreachable"}
    broken = [p for p in report.problems if p.code == "broken_external"]
    assert len(broken) == 1
    assert broken[0].target == "https://example.com/gone"
    unreachable = [p for p in report.problems if p.code == "unreachable"]
    assert len(unreachable) == 1
    assert unreachable[0].target == "https://example.com/slow"
    assert report.skipped_external == 0


def test_check_docs_skipped_external_count_no_checker(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text(
        "[a](https://example.com/a) [b](https://example.com/a) [c](mailto:x@y.com) [d](tel:123)\n",
        encoding="utf-8",
    )
    report = check_docs(root)
    assert report.skipped_external == 2  # two http/https links
    assert report.problems == []


def test_check_docs_file_too_large(tmp_path: Path):
    root = tmp_path
    p = root / "big.md"
    p.write_bytes(b"a" * (5_242_881))
    (root / "small.md").write_text("x\n", encoding="utf-8")
    report = check_docs(root)
    assert any(prob.code == "file_too_large" and prob.file == "big.md" for prob in report.problems)
    assert report.files == 2


def test_check_docs_too_many_files(tmp_path: Path):
    root = tmp_path
    (root / "a.md").write_text("a\n", encoding="utf-8")
    (root / "b.md").write_text("b\n", encoding="utf-8")
    with pytest.raises(LinkCheckError) as exc_info:
        check_docs(root, max_files=1)
    assert exc_info.value.code == "too_many_files"


def test_check_docs_too_many_urls(tmp_path: Path):
    root = tmp_path
    (root / "a.md").write_text(
        "[one](https://example.com/1) [two](https://example.com/2)\n", encoding="utf-8"
    )
    with pytest.raises(LinkCheckError) as exc_info:
        check_docs(root, max_urls=1)
    assert exc_info.value.code == "too_many_urls"


def test_check_docs_invalid_root(tmp_path: Path):
    with pytest.raises(LinkCheckError) as exc_info:
        check_docs(tmp_path / "missing")
    assert exc_info.value.code == "invalid_root"


def test_check_docs_percent_encoding(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text("[x](docs/a%20b.md)\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "a b.md").write_text("content\n", encoding="utf-8")
    report = check_docs(root)
    assert report.problems == []


def test_check_docs_anchor_to_heading_with_inline_code(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text("[go](#code)\n\n# `code`\n", encoding="utf-8")
    report = check_docs(root)
    assert report.problems == []


def test_check_docs_duplicate_headings_across_files(tmp_path: Path):
    root = tmp_path
    (root / "README.md").write_text("[a](docs/a.md#x) [b](docs/b.md#x)\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("# x\n", encoding="utf-8")
    (root / "docs" / "b.md").write_text("# x\n# x\n", encoding="utf-8")
    report = check_docs(root)
    assert report.problems == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_missing_directory(tmp_path: Path, capsys):
    rc = main([str(tmp_path / "nonexistent")])
    assert rc == 2
    captured = capsys.readouterr()
    assert "is not a directory" in captured.err


def test_cli_problems_return_1(tmp_path: Path, capsys):
    root = tmp_path
    (root / "README.md").write_text("[x](#missing)\n", encoding="utf-8")
    rc = main([str(root)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "README.md:1:1: missing_anchor #missing" in out


def test_cli_problems_line_output_acceptance(tmp_path: Path, capsys):
    root = tmp_path
    (root / "README.md").write_text(
        "Read [the guide](docs/a.md#usage), [gone](#missing) and [up](../outside.md).\n",
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("## Usage\n", encoding="utf-8")
    rc = main([str(root)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "README.md:1:36: missing_anchor #missing" in out


def test_cli_unreachable_non_strict_returns_0(tmp_path: Path, capsys):
    root = tmp_path
    (root / "README.md").write_text("[x](https://example.com/slow)\n", encoding="utf-8")
    # Without --external, external links are skipped and no unreachable problem exists.
    rc = main([str(root), "--strict"])
    assert rc == 0


def test_cli_external_strict_fails_on_broken(monkeypatch, tmp_path: Path, capsys):
    root = tmp_path
    (root / "README.md").write_text("[x](https://example.com/gone)\n", encoding="utf-8")

    class Checker:
        def status(self, url: str) -> int:
            return 404

    monkeypatch.setattr("docs_link_check.__main__._UrllibChecker", Checker)
    rc = main([str(root), "--external", "--strict"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "broken_external https://example.com/gone" in out


def test_cli_external_non_strict_skips_unreachable(monkeypatch, tmp_path: Path, capsys):
    root = tmp_path
    (root / "README.md").write_text("[x](https://example.com/slow)\n", encoding="utf-8")

    class Checker:
        def status(self, url: str) -> int:
            raise TimeoutError(url)

    monkeypatch.setattr("docs_link_check.__main__._UrllibChecker", Checker)
    rc = main([str(root), "--external"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_urllib_checker_head_then_get():
    calls: list[tuple[str, float]] = []

    class Response:
        def __init__(self, status: int) -> None:
            self.status = status

    class Opener:
        def __init__(self, statuses: list[int]) -> None:
            self.statuses = list(statuses)

        def open(self, req, timeout):
            calls.append((req.method, timeout))
            return Response(self.statuses.pop(0))

    checker = _UrllibChecker(timeout=3.0)
    checker.opener = Opener([200])  # type: ignore[assignment]
    assert checker.status("https://example.com") == 200
    checker.opener = Opener([405, 204])  # type: ignore[assignment]
    assert checker.status("https://example.com") == 204
    assert calls == [("HEAD", 3.0), ("HEAD", 3.0), ("GET", 3.0)]


def test_no_non_http_redirect_handler():
    handler = _NoNonHttpRedirectHandler()
    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(None, None, 302, "Found", {}, "file:///etc/passwd")


def test_no_non_http_redirect_handler_allows_http():
    handler = _NoNonHttpRedirectHandler()
    request = urllib.request.Request("https://example.com/")
    redirected = handler.redirect_request(
        request, None, 302, "Found", {}, "https://example.com/new"
    )
    assert redirected is not None
    assert redirected.full_url == "https://example.com/new"


# ---------------------------------------------------------------------------
# Additional extraction edge cases
# ---------------------------------------------------------------------------


def test_extract_links_titles_parenthesized_and_escaped():
    md = '[a](docs/x.md (title)) [b](docs/y.md "ti\\"tle")\n'
    links = extract_links(md)
    assert [link.target for link in links] == ["docs/x.md", "docs/y.md"]


def test_extract_links_angle_target_without_title():
    md = "[a](<docs/x.md>) [bad](<x> y)\n"
    assert extract_links(md) == [Link(target="docs/x.md", line=1, column=1, kind="link")]


def test_extract_links_unterminated_angle_target():
    assert extract_links("[a](<nope)\n") == []


def test_extract_links_malformed_shapes_are_ignored():
    assert extract_links("![alt]\n") == []
    assert extract_links("[unclosed\n") == []
    assert extract_links("![unclosed\n") == []
    assert extract_links("[label](unterminated\n") == []
    assert extract_links("![alt](unterminated\n") == []
    assert extract_links("a < b <https://unterminated\n") == []
    assert extract_links('[a](x "t" y)\n') == []


def test_extract_links_escaped_bracket_in_label():
    links = extract_links("[a\\]b](x.md)\n")
    assert links == [Link(target="x.md", line=1, column=1, kind="link")]


def test_extract_links_reference_definition_variants():
    md = "[a]: <docs/a.md>\n[b]: docs/foo(bar).md\n[c]:\n[d]: docs/a.md junk\n[e]: <>\n"
    links = extract_links(md)
    assert [link.target for link in links] == ["docs/a.md", "docs/foo(bar).md"]
    assert all(link.kind == "reference" for link in links)


def test_extract_links_code_span_with_different_backtick_run():
    md = "``code ` [no](no.md)`` and [yes](yes.md)\n"
    assert [link.target for link in extract_links(md)] == ["yes.md"]


def test_extract_links_indented_fence_is_not_a_fence():
    md = "    ```\n[yes](yes.md)\n    ```\n"
    assert [link.target for link in extract_links(md)] == ["yes.md"]


def test_extract_links_fence_info_string_does_not_close_block():
    md = "```\n```python\n    ```\n[x](a.md)\n```\n"
    assert extract_links(md) == []


def test_extract_links_longer_fence_needs_matching_close():
    md = "````\n```\n[x](a.md)\n````\n[y](b.md)\n"
    assert [link.target for link in extract_links(md)] == ["b.md"]


def test_heading_anchors_empty_headings_and_collision_chain():
    md = "#\n## \n# a\n# a\n# a-1\n# a-2\n# a\n"
    assert heading_anchors(md) == {"a", "a-1", "a-1-1", "a-2", "a-3"}


# ---------------------------------------------------------------------------
# Additional check_docs edge cases
# ---------------------------------------------------------------------------


def test_check_docs_empty_fragment_is_ignored(tmp_path: Path):
    (tmp_path / "README.md").write_text("[x](#)\n", encoding="utf-8")
    assert check_docs(tmp_path).problems == []


def test_check_docs_anchor_cache_is_reused(tmp_path: Path):
    (tmp_path / "README.md").write_text("[a](#x) [b](#y)\n\n# x\n# y\n", encoding="utf-8")
    assert check_docs(tmp_path).problems == []


def test_check_docs_fragment_on_non_markdown_target(tmp_path: Path):
    (tmp_path / "README.md").write_text("[x](data.txt#frag)\n", encoding="utf-8")
    (tmp_path / "data.txt").write_text("data\n", encoding="utf-8")
    assert check_docs(tmp_path).problems == []


def test_check_docs_missing_anchor_in_other_markdown_file(tmp_path: Path):
    (tmp_path / "README.md").write_text("[x](docs/a.md#nope)\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# Other\n", encoding="utf-8")
    report = check_docs(tmp_path)
    assert [problem.code for problem in report.problems] == ["missing_anchor"]


def test_check_docs_undecodable_source_file_is_skipped(tmp_path: Path):
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe")
    report = check_docs(tmp_path)
    assert report.problems == []
    assert report.files == 1


def test_check_docs_undecodable_target_file_is_skipped(tmp_path: Path):
    (tmp_path / "README.md").write_text("[x](docs/bad.md#x)\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bad.md").write_bytes(b"\xff\xfe")
    report = check_docs(tmp_path)
    assert report.problems == []


def test_check_docs_colon_in_target_is_not_a_scheme(tmp_path: Path):
    (tmp_path / "README.md").write_text("[x](1:2.md)\n", encoding="utf-8")
    report = check_docs(tmp_path)
    assert [problem.code for problem in report.problems] == ["missing_file"]


def test_check_docs_include_pattern_matching_directories(tmp_path: Path):
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    report = check_docs(tmp_path, include=("README.md", "**"))
    assert report.files == 1


# ---------------------------------------------------------------------------
# Additional CLI and urllib edge cases
# ---------------------------------------------------------------------------


def test_urllib_checker_returns_http_error_code():
    class Opener:
        def open(self, req, timeout):
            raise urllib.error.HTTPError("https://example.com", 404, "Not Found", {}, None)

    checker = _UrllibChecker(timeout=1.0)
    checker.opener = Opener()  # type: ignore[assignment]
    assert checker.status("https://example.com") == 404


def test_urllib_checker_propagates_network_errors():
    class Opener:
        def open(self, req, timeout):
            raise TimeoutError("timed out")

    checker = _UrllibChecker(timeout=1.0)
    checker.opener = Opener()  # type: ignore[assignment]
    with pytest.raises(TimeoutError):
        checker.status("https://example.com")


def test_cli_check_docs_error_returns_2(monkeypatch, tmp_path: Path, capsys):
    def boom(*args, **kwargs):
        raise LinkCheckError("too_many_files")

    monkeypatch.setattr("docs_link_check.__main__.check_docs", boom)
    rc = main([str(tmp_path)])
    assert rc == 2
    assert "too_many_files" in capsys.readouterr().err
