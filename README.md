# docs-link-check

[![PyPI version](https://img.shields.io/pypi/v/trysac-docs-link-check)](https://pypi.org/project/trysac-docs-link-check/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-docs-link-check)](LICENSE)

Check links in Markdown documentation: relative files with exact case, heading anchors with GitHub slugs, root escapes, and external URLs through an injected HTTP checker with caching

## Problem

Documentation rots quietly: files move, headings are renamed and anchors stop working, external pages
disappear, and a link that works on a case-insensitive laptop breaks on Linux. Existing checkers either
hit the network in every test or ignore anchors. This library extracts links from Markdown, validates
files and anchors offline with exact case and checks external URLs through a port that tests replace.

## Install

```sh
pip install trysac-docs-link-check
# or
uv add trysac-docs-link-check
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
from pathlib import Path

from docs_link_check import check_docs, extract_links, heading_anchors

print(extract_links("See [docs](guide.md#setup) and ![logo](img/logo.png).\n"))
# [Link(target='guide.md#setup', line=1, column=5, kind='link'),
#  Link(target='img/logo.png', line=1, column=32, kind='image')]

print(heading_anchors("# Install & Run\n## API (v2)\n"))
# {'install--run', 'api-v2'}

report = check_docs(Path("docs"))
for problem in report.problems:
    print(problem.file, problem.line, problem.column, problem.code, problem.target)
print(f"checked {report.files} files and {report.links} links")

# External URLs are only requested through a checker you pass in (any object with
# status(url) -> int); without one they are skipped and counted in
# report.skipped_external.
```

### Command line

```sh
docs-link-check docs                            # offline: files and anchors
docs-link-check docs --external                 # also check http(s) URLs (10 s timeout)
docs-link-check docs --external --strict        # also fail on unreachable URLs
```

Each problem is printed as `file:line:column: code target`. Exit codes: `0` when the docs are clean,
`1` when any problem is found (`--strict` also counts `unreachable`), and `2` for a usage error or an
invalid root directory.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
