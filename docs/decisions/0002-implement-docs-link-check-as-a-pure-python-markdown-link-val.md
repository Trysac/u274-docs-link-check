# Implement docs-link-check as a pure-Python Markdown link validator

Status: accepted (generated, pending human review)

## Context

Documentation links rot when files move, headings rename, or external pages disappear. Existing checkers either require network access in tests or ignore anchors and case sensitivity.

## Decision

Build a pure-Python library (`docs_link_check`) following the requested public API. Extraction handles inline links/images, reference definitions, and autolinks while skipping fenced code blocks and inline code spans. Heading anchors follow the github-slugger 2.0.0 algorithm for ATX headings. `check_docs` validates relative paths with exact case, root escapes, percent-decoding, and anchors; external URLs are checked through an injected `HttpChecker` protocol with caching and limits. A CLI (`__main__.py`) provides `--external` and `--strict`.

## Consequences

The library has no runtime dependencies and is fully testable with a fake checker. Limits (`max_files`, `max_urls`, file-size cap) prevent resource exhaustion. The implementation is line-oriented for Markdown, which covers the specified scope and accepts the out-of-scope items (raw HTML, setext headings).
