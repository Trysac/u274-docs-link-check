# docs-link-check

[![PyPI version](https://img.shields.io/pypi/v/trysac-docs-link-check)](https://pypi.org/project/trysac-docs-link-check/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-docs-link-check)](LICENSE)
[![CI](https://github.com/Trysac/u274-docs-link-check/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u274-docs-link-check/actions/workflows/ci.yml)

Check links in Markdown documentation: relative files with exact case, heading anchors with GitHub slugs, root escapes, and external URLs through an injected HTTP checker with caching

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-docs-link-check
# or
uv add trysac-docs-link-check
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import docs_link_check

# normalize() trims surrounding whitespace and lower-cases the text.
print(docs_link_check.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    docs_link_check.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
