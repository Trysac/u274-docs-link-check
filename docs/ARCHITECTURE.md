# Architecture

## Purpose

`trysac-docs-link-check` is a small, dependency-free Python library: Check links in Markdown documentation: relative files with exact case, heading anchors with GitHub slugs, root escapes, and external URLs through an injected HTTP checker with caching

## Shape

```text
caller code --> docs_link_check (public API in __init__.py)
                    |
                    +-- pure functions, no I/O, no global state
```

- **Public API**: the names listed in `__all__` of `src/docs_link_check/__init__.py`. Anything else is
  internal and may change without a major version.
- **Errors**: invalid input raises built-in exceptions (`ValueError`, `TypeError`) with a clear
  message, and `LinkCheckError` (with a `code`) when the whole check cannot run; the library never
  prints or exits.
- **Side effects**: the pure helpers have none. `check_docs` reads the filesystem, and network access
  only happens through a caller-supplied `HttpChecker`.
- **CLI**: `src/docs_link_check/__main__.py` is the only place that prints or chooses an exit code.

## Quality contract

The gates are plain tool invocations: `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy` and `uv run pytest --cov=docs_link_check`. `fabrica.json` tells the factory how the
environment is installed. See [TESTING.md](TESTING.md).

## Decisions

Architecture decisions are recorded in [decisions/](decisions/) as numbered ADRs.
